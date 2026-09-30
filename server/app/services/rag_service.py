"""GigaChat client and the built-in knowledge base of ВИТШик.

GigaChat for individuals (scope GIGACHAT_API_PERS) serves one request at a time: a second parallel
request is refused with HTTP 429. Requests therefore take turns for GIGACHAT_MAX_STREAMS slots, and a
student who would wait too long gets the portal's own text instead of a rephrased one.

Every call sends only the messages of the chat it answers. No X-Session-ID is sent, so GigaChat keeps
no context between calls and one student's chat can never leak into another's.
"""
import asyncio
import json
import logging
import os
import re
import ssl
import time
import uuid
from typing import List, Optional

import certifi
import httpx

from app.core.config import settings

logger = logging.getLogger("ivitsh_portal.rag")

# НУЦ Минцифры: Russian Trusted Root CA and its Sub CAs (2022, 2024), checked by SHA-256 fingerprint
RUSSIAN_CA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "certs", "russian_trusted_ca.pem")

OAUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
CHAT_URL = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
MODELS_URL = "https://gigachat.devices.sberbank.ru/api/v1/models"

# How long a question may wait for a free stream before the student gets the portal's text right away
QUEUE_WAIT = 5.0
# One completion: token, request and one retry together. A whole answer (agent.ANSWER_DEADLINE) stays
# under the chat client's 24 s and nginx's 25 s.
CALL_DEADLINE = 12.0
REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
# After a 429 or a server error GigaChat is left alone for a while instead of being asked again at once
COOLDOWN = 30.0
HISTORY_TURNS = 4
HISTORY_CHARS = 600


class GigaChatUnavailable(RuntimeError):
    """No answer from GigaChat (busy, refused, blocked by its filter, down); the caller answers without it."""


def _build_ssl_context() -> ssl.SSLContext:
    """GigaChat certificates are issued by the Russian Trusted Root CA, which is not in certifi.

    Instead of disabling verification, this context (used for GigaChat only) trusts certifi, the
    bundled Russian CAs and the optional GIGACHAT_CA_BUNDLE. A missing or broken extra file must not
    stop the portal.
    """
    context = ssl.create_default_context(cafile=certifi.where())
    for path in (RUSSIAN_CA_FILE, settings.GIGACHAT_CA_BUNDLE):
        if not path:
            continue
        try:
            context.load_verify_locations(cafile=path)
        except (OSError, ssl.SSLError) as e:
            logger.error("CA file %s could not be loaded (%s); GigaChat calls may fail TLS checks", path, e)
    return context


_ssl_context = _build_ssl_context()
_token_cache = {
    "access_token": "",
    "expires_at": 0.0,
}
_state = {"cooldown_until": 0.0}
# asyncio primitives belong to one event loop; tests start a new loop per client
_primitives: dict = {}


def _loop_bound(name: str, factory):
    loop = asyncio.get_running_loop()
    held = _primitives.get(name)
    if held is None or held[0] is not loop:
        held = _primitives[name] = (loop, factory())
    return held[1]


def _streams() -> asyncio.Semaphore:
    return _loop_bound("streams", lambda: asyncio.Semaphore(settings.GIGACHAT_MAX_STREAMS))


def _token_lock() -> asyncio.Lock:
    return _loop_bound("token", asyncio.Lock)


def is_llm_configured() -> bool:
    return bool(settings.GIGACHAT_AUTH_KEY)


def _token_is_fresh(now: float) -> bool:
    return bool(_token_cache["access_token"]) and now < _token_cache["expires_at"] - 60


def _explain(error: Exception) -> str:
    text = str(error) or type(error).__name__
    if "CERTIFICATE_VERIFY_FAILED" in text:
        text += " (the server certificate is not signed by the bundled Russian CAs; put the current one in GIGACHAT_CA_BUNDLE)"
    return text


async def get_access_token(force_refresh: bool = False) -> str:
    # With force_refresh the current token was rejected by the API and must not be returned again.
    rejected_token = _token_cache["access_token"] if force_refresh else None
    if not force_refresh and _token_is_fresh(time.time()):
        return _token_cache["access_token"]

    async with _token_lock():
        # Another coroutine may have refreshed the token while we waited for the lock.
        if _token_is_fresh(time.time()) and _token_cache["access_token"] != rejected_token:
            return _token_cache["access_token"]

        headers = {
            "Authorization": f"Basic {settings.GIGACHAT_AUTH_KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        try:
            async with httpx.AsyncClient(verify=_ssl_context, timeout=REQUEST_TIMEOUT) as client:
                resp = await client.post(OAUTH_URL, headers=headers, data={"scope": settings.GIGACHAT_SCOPE})
                resp.raise_for_status()
                data = resp.json()
                token = str(data["access_token"])
        except Exception as e:
            _token_cache["access_token"] = ""
            _token_cache["expires_at"] = 0.0
            logger.error("GigaChat authentication failed: %s", _explain(e))
            raise GigaChatUnavailable("GigaChat auth failed") from e

        now = time.time()
        expires_at = data.get("expires_at")
        if isinstance(expires_at, (int, float)) and expires_at > 0:
            # GigaChat gives milliseconds since the epoch; the token lives 30 minutes
            _token_cache["expires_at"] = expires_at / 1000 if expires_at > 1e11 else float(expires_at)
        else:
            _token_cache["expires_at"] = now + 1800
        _token_cache["access_token"] = token
        logger.info("Obtained GigaChat OAuth token")
        return token


KNOWLEDGE_CHUNKS = [
    {
        "keywords": [
            "портал", "раздел", "сайт", "пользоваться", "личный кабинет",
            "что есть на", "на телефон", "установить",
            "на форуме", "на форум", "карта кампуса", "картой", "войти", "вход",
        ],
        "content": (
            "Что есть в ИВИТШ Хабе: на главной — расписание вашей группы и объявления; "
            "«Форум» — вопросы старшекурсникам и кураторам; "
            "«Карта кампуса» — поиск аудитории по номеру; «Преподаватели» — кабинеты, почта и где преподаватель сейчас; "
            "«Вопросы и ответы» — частые вопросы; «Личный кабинет» — вход через ЭИОС, активность и установка портала "
            "на главный экран телефона. А я, ВИТШик, подсказываю пары, аудитории, преподавателей и пишу объяснительные."
        )
    },
    {
        "keywords": ["директор", "руководител", "руководит ивитш", "руководит витш", "руководит высш", "глава", "борисов", "декан"],
        "content": "Директор Высшей ИТ-школы (ИВИТШ) КГУ — Борисов Александр Сергеевич. Дирекция находится в Корпусе Б на 2 этаже, кабинет Б-209 (ул. Ивановская, 24а) [IMG:209.png]."
    },
    {
        "keywords": ["дирекц", "деканат", "209", "корпус б", "ивановск", "кабинет", "администр", "часы работ"],
        "content": "Дирекция Высшей ИТ-школы (ИВИТШ) КГУ находится в Корпусе Б на 2 этаже, кабинет Б-209. Работает с Пн по Пт с 9:00 до 17:00 (перерыв 12:00-13:00). Адрес Корпуса Б: ул. Ивановская, 24а [IMG:209.png]."
    },
    {
        "keywords": ["стипенд", "деньги", "пгас", "академическ", "социальн", "выплат", "повышенн", "сколько платят"],
        "content": "Академическая стипендия: 3000 руб за сессию на «4» и «5», 4500 руб за отличную сессию («5»). Повышенная стипендия (ПГАС) — от 5000 до 10000 руб за успехи в науке, спорте и творчестве. Социальная стипендия — 2980 руб."
    },
    {
        "keywords": ["клуб", "объединен", "медиа", "идея", "мафи", "программирован", "nexthub", "играй", "кружок", "досуг"],
        "content": "ВИТШ-медиа (рук. Макар Смирнов), ИДЕЯ (рук. Ирина Горева @KrisBeet), Спортивное программирование (рук. Глеб Лебедев @xeGalaxy), NextHub (рук. Денислав Чеботарев), Играй (рук. Василиса Никитина), Кибербезопасность (@SNEWYEWRS), Спортивная мафия (рук. Владислав Смирнов)."
    },
    {
        "keywords": ["аудитор", "кабинет", "301", "101", "102", "104", "107", "108", "201", "202", "203", "204", "206", "207", "208", "209", "302", "303", "304", "306", "307", "308", "309", "310", "312", "313", "401", "403", "406", "407", "408", "409", "коворкинг", "этаж", "преподавательск"],
        "content": "Аудитория 301 и все 300-е аудитории (301-313) находятся на 3 этаже Корпуса Б (ул. Ивановская, 24а). 100-е аудитории — 1 этаж. 200-е — 2 этаж (включая Б-209) [IMG:209.png]. 400-е — 4 этаж. Коворкинг ВИТШ находится на 4 этаже Корпуса Б [IMG:coworking.png]."
    },
    {
        "keywords": ["кушать", "поесть", "еда", "столовая", "обед", "кофе", "магазин", "шаурма", "голоден", "перекус"],
        "content": "Рядом с Корпусом Б можно покушать: столовая «Жуй да Ешь» (от 100р, ул. Советская 42/1), Шаурмастер44 (шаурма от 140р, ул. Советская 61/39), «Еда-кафе» (от 150р, ул. Лермонтова 3/1), Coffee Like (Советская 26/1), магазины Пятерочка (Советская 47) и Высшая лига."
    },
    {
        "keywords": ["староста", "куратор", "тьютор", "профорг", "культорг", "лекция", "лабораторн", "семинар", "дифзачет", "сдо", "еиос", "зачетка", "расписан"],
        "content": "Староста: студент-лидер группы. Куратор: преподаватель-наставник. Тьютор: старшекурсник-помощник. Профорг: защита прав, матпомощь. ЭИОС КГУ: цифровая платформа обучения, расписания и портфолио (eios.kosgos.ru)."
    },
    {
        "keywords": [
            "преподавател", "препод", "учител", "киприна", "барило", "лустгартен", "красавина",
            "прядкина", "смирнова", "демчинова", "дорохова", "орлов", "мозохин", "логинова",
            "силенок", "иваницкий", "попова", "денисов", "дружинина", "кириллова", "чувиляева", "заведующ"
        ],
        "content": (
            "**Преподавательский состав Высшей ИТ-Школы (ИВИТШ) КГУ:**\n\n"
            "• **Киприна Людмила Юрьевна** — Заведующая кафедрой ИСиТ, к.т.н., доцент. Каб. Б-214, e-mail: L_kiprina@Kosgos.ru, тел: 63-49-00 (доб. 8120).\n"
            "• **Барило Илья Иванович** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Лустгартен Юрий Леонидович** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Красавина Мария Сергеевна** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Прядкина Нина Олеговна** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Смирнова Светлана Геннадьевна** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Демчинова Елена Александровна** — Старший преподаватель кафедры ИСиТ (Корпус Б).\n"
            "• **Дорохова Жанна Викторовна** — Старший преподаватель кафедры ИСиТ (Корпус Б).\n"
            "• **Орлов Александр Валерьевич** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Мозохин Александр Евгеньевич** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Логинова Анна Александровна** — Ассистент кафедры ИСиТ (Корпус Б).\n"
            "• **Силенок Юрий Викторович** — Преподаватель (Корпус Б).\n"
            "• **Иваницкий Виталий Викторович** — Доцент кафедры ИСиТ, к.т.н., доцент (Корпус Б).\n"
            "• **Попова Светлана Валентиновна** — Преподаватель кафедры экономики и управления.\n"
            "• **Денисов Артем Руфимович** — Доцент кафедры ИиВТ, д.т.н., доцент.\n"
            "• **Дружинина Анна Григорьевна** — Доцент кафедры ИСиТ, к.т.н., доцент.\n"
            "• **Кириллова Екатерина Сергеевна** — Доцент кафедры ИСиТ, к.т.н., доцент.\n"
            "• **Чувиляева Александра Сергеевна** — Доцент кафедры ИСиТ, к.т.н., доцент."
        )
    }
]


_FOOD_CHUNK = next(chunk for chunk in KNOWLEDGE_CHUNKS if "столовая" in chunk["keywords"])
PORTAL_GUIDE = next(chunk for chunk in KNOWLEDGE_CHUNKS if "портал" in chunk["keywords"])


def evaluate_query(query: str):
    q_lower = query.lower().strip()
    q_words = re.findall(r"\w{2,}", q_lower)

    room_match = re.search(r"\b(101|102|104|107|108|201|202|203|204|206|207|208|209|301|302|303|304|306|307|308|309|310|312|313|401|403|406|407|408|409)\b", q_lower)
    if room_match:
        room_num = room_match.group(1)
        floor_map = {'1': '1 этаже', '2': '2 этаже', '3': '3 этаже', '4': '4 этаже'}
        floor = floor_map.get(room_num[0], 'соответствующем этаже')
        extra = ' (Дирекция ИВИТШ КГУ)' if room_num == '209' else ''
        return 100, {
            "keywords": [room_num],
            "content": f"Аудитория {room_num}{extra} находится на **{floor} Корпуса Б** (ул. Ивановская, 24а).\n\n[IMG:{room_num}.png]"
        }

    if any(k in q_lower for k in ("поесть", "голоден", "столов", "еда", "шаурм", "обед")):
        return 100, _FOOD_CHUNK

    best_match = None
    max_score = 0
    # Words any question can have; two of them must not be enough to pick a text
    stop_words = {
        "где", "как", "что", "кто", "это", "есть", "для", "про", "при", "или", "все", "мне", "меня", "нас",
        "находиться", "находится", "какой", "какая", "какие", "пожалуйста", "можно", "нужно", "надо",
    }

    for chunk in KNOWLEDGE_CHUNKS:
        score = 0
        for kw in chunk["keywords"]:
            if re.match(r"^\d{3}$", kw):
                # A room number, not part of "2026" or "4500"
                if re.search(rf"(?<!\d){kw}(?!\d)", q_lower):
                    score += 35
            elif kw in q_lower:
                score += 8
        for w in q_words:
            if w not in stop_words and len(w) >= 3 and w in chunk["content"].lower():
                score += 2
        if score > max_score:
            max_score = score
            best_match = chunk

    return max_score, best_match


def clean_reply(reply: str) -> str:
    """Drop the tag noise GigaChat sometimes invents, and emoji outside the basic plane."""
    reply = re.sub(r'\[(SMILEY|EMOJI|TAG)_.*?\]', '', reply, flags=re.IGNORECASE)
    return re.sub(r'[\U00010000-\U0010ffff]', '', reply).strip()


def build_messages(system_prompt: str, history: list, user_message: str) -> List[dict]:
    """The system prompt, the last turns of this one chat, and the question; a fresh list for every call."""
    turns = [t for t in (history or []) if isinstance(t, dict) and t.get("role") in ("user", "assistant")]
    # Older clients included the current question in history; don't send it twice.
    if turns and turns[-1].get("role") == "user" and str(turns[-1].get("content", "")).strip() == user_message.strip():
        turns = turns[:-1]
    messages = [{"role": "system", "content": system_prompt}]
    for turn in turns[-HISTORY_TURNS:]:
        content = str(turn.get("content", ""))[:HISTORY_CHARS].strip()
        if content:
            messages.append({"role": turn["role"], "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


_SENTENCE_END = re.compile(r"[.!?…](?=\s+[А-ЯЁA-Z«\"(]|\s*$)")


def _whole_sentences(text: str) -> str:
    """A reply cut by max_tokens ends mid-word; keep it up to the last full sentence."""
    ends = [m.end() for m in _SENTENCE_END.finditer(text.strip())]
    return text.strip()[:ends[-1]] if ends else text.strip() + "…"


def _cool_down(reason: str) -> None:
    _state["cooldown_until"] = time.monotonic() + COOLDOWN
    logger.warning("GigaChat %s; answering without it for %.0f s", reason, COOLDOWN)


class FunctionsRejected(GigaChatUnavailable):
    """GigaChat refused a request with functions (the model or the account does not support them)."""


async def _post(payload: dict) -> dict:
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=_ssl_context, timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(CHAT_URL, headers=headers, json=payload)
            if resp.status_code == 401:
                token = await get_access_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                resp = await client.post(CHAT_URL, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise GigaChatUnavailable(_explain(e)) from e

    if resp.status_code == 429 or resp.status_code >= 500:
        _cool_down(f"answered HTTP {resp.status_code}")
    if resp.status_code in (400, 404, 422) and payload.get("functions"):
        raise FunctionsRejected(f"HTTP {resp.status_code} for a request with functions")
    if resp.status_code != 200:
        raise GigaChatUnavailable(f"HTTP {resp.status_code}")
    try:
        body = resp.json()
        choice = body["choices"][0]
        message = choice["message"]
        if not isinstance(message, dict):
            raise TypeError("message")
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise GigaChatUnavailable("unexpected answer format") from e

    reason = choice.get("finish_reason")
    usage = body.get("usage") or {}
    logger.info("GigaChat answered in %.1f s (%s, %s tokens)", time.monotonic() - started, reason, usage.get("total_tokens", "?"))
    # "blacklist": GigaChat's own filter swapped the answer for a canned phrase unrelated to the question
    if reason in ("blacklist", "error"):
        raise GigaChatUnavailable(f"finish_reason={reason}")
    return {"message": message, "finish_reason": reason}


async def chat(messages: List[dict], functions: Optional[List[dict]] = None, function_call: str = "auto",
               max_tokens: int = 350) -> dict:
    """One completion: {"message": {...}, "finish_reason": ...}. Waits for a free stream, never longer than
    QUEUE_WAIT, and raises GigaChatUnavailable on anything that is not an answer."""
    if time.monotonic() < _state["cooldown_until"]:
        raise GigaChatUnavailable("cooling down after a refusal")
    payload = {"model": settings.GIGACHAT_MODEL, "messages": messages, "temperature": 0.1, "max_tokens": max_tokens}
    if functions:
        payload["functions"] = functions
        payload["function_call"] = function_call
    streams = _streams()
    try:
        await asyncio.wait_for(streams.acquire(), QUEUE_WAIT)
    except asyncio.TimeoutError:
        raise GigaChatUnavailable("all streams are busy") from None
    try:
        return await asyncio.wait_for(_post(payload), CALL_DEADLINE)
    except asyncio.TimeoutError:
        raise GigaChatUnavailable(f"no answer in {CALL_DEADLINE:.0f} s") from None
    finally:
        streams.release()


def text_of(choice: dict) -> str:
    """The reply text of a completion, cleaned; cut at a whole sentence when max_tokens stopped it."""
    reply = clean_reply(str(choice["message"].get("content") or ""))
    if choice.get("finish_reason") == "length":
        reply = _whole_sentences(reply)
    return reply


async def ask_gigachat(system_prompt: str, history: list, user_message: str, max_tokens: int = 350) -> str:
    """One GigaChat completion; raises GigaChatUnavailable so the caller can answer from its own data."""
    reply = text_of(await chat(build_messages(system_prompt, history, user_message), max_tokens=max_tokens))
    if not reply:
        raise GigaChatUnavailable("empty answer")
    return reply


async def self_check(say=print, question: str = "Ответь одним словом: работает?") -> None:
    """Each step of a real GigaChat call, for `python -m app.services.gigachat_check`; raises on the failing step."""
    if not is_llm_configured():
        say("GIGACHAT_AUTH_KEY не задан: ВИТШик отвечает только данными портала.")
        return
    say(f"Ключ задан, scope {settings.GIGACHAT_SCOPE}, модель {settings.GIGACHAT_MODEL}, "
        f"одновременных запросов {settings.GIGACHAT_MAX_STREAMS}.")
    extra = f" + {settings.GIGACHAT_CA_BUNDLE}" if settings.GIGACHAT_CA_BUNDLE else ""
    say(f"Сертификаты Минцифры: встроенные{extra}.")
    token = await get_access_token(force_refresh=True)
    say(f"OAuth: токен получен, действует ещё {(_token_cache['expires_at'] - time.time()) / 60:.0f} мин.")
    async with httpx.AsyncClient(verify=_ssl_context, timeout=REQUEST_TIMEOUT) as client:
        resp = await client.get(MODELS_URL, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    resp.raise_for_status()
    names = [str(m.get("id")) for m in resp.json().get("data", []) if isinstance(m, dict)]
    say("Доступные модели: " + ", ".join(names))
    if settings.GIGACHAT_MODEL not in names:
        say(f"ВНИМАНИЕ: модели {settings.GIGACHAT_MODEL} нет в списке, укажите GIGACHAT_MODEL из него.")
    say(f"Ответ на «{question}»: {await ask_gigachat('Отвечай кратко.', [], question, max_tokens=20)}")
    probe = [{"name": "server_time", "description": "Текущее время на сервере портала.",
              "parameters": {"type": "object", "properties": {}}}]
    try:
        choice = await chat([{"role": "user", "content": "Который час на сервере? Узнай через функцию."}], functions=probe, max_tokens=50)
    except FunctionsRejected:
        say(f"Функции: модель {settings.GIGACHAT_MODEL} их не принимает — ВИТШик будет только пересказывать найденное "
            "в базе. Попробуйте GIGACHAT_MODEL=GigaChat-2-Pro.")
        return
    call = choice["message"].get("function_call")
    if call:
        # The whole round: the call, its result back, the answer. The agent sends messages in exactly this shape.
        called = {"role": "assistant", "content": choice["message"].get("content") or "",
                  "function_call": {"name": call.get("name"), "arguments": call.get("arguments") or {}}}
        if choice["message"].get("functions_state_id"):
            called["functions_state_id"] = choice["message"]["functions_state_id"]
        messages = [{"role": "user", "content": "Который час на сервере? Узнай через функцию."}, called,
                    {"role": "function", "name": call.get("name"), "content": json.dumps({"time": "12:34"})}]
        try:
            final = text_of(await chat(messages, functions=probe, function_call="none", max_tokens=50))
        except FunctionsRejected as e:
            say(f"Функции: модель вызвала функцию, но не приняла её результат ({e}). ВИТШик будет пересказывать "
                "найденное без функций; сообщите разработчику.")
            return
        say(f"Функции: работают — вызов, результат и ответ «{final}». ВИТШик понимает вопросы своими словами.")
    else:
        say("Функции: модель ответила без вызова функции; ВИТШик всё равно проверяет её ответы по данным портала.")
