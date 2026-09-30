"""ВИТШик's agent with a scripted GigaChat: function calls, the portal's data, the checks and every fallback."""
import asyncio
import json

import pytest

from app.services import agent, assistant, rag_service
from test_assistant import ask, fake_timetable, student  # noqa: F401


def call(function, **arguments):
    return {"message": {"role": "assistant", "content": "", "function_call": {"name": function, "arguments": arguments},
                        "functions_state_id": f"state-{function}"}, "finish_reason": "function_call"}


def text(content):
    return {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}


def script(monkeypatch, *steps, delay=0.0):
    """GigaChat that returns the given completions in turn; every request is recorded."""
    sent = []
    queue = list(steps)

    async def chat(messages, functions=None, function_call="auto", max_tokens=350):
        sent.append({"messages": [dict(m) for m in messages], "functions": functions, "function_call": function_call})
        if delay:
            await asyncio.sleep(delay)
        step = queue.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    monkeypatch.setattr(rag_service, "chat", chat)
    monkeypatch.setattr(rag_service.settings, "GIGACHAT_AUTH_KEY", "configured")
    return sent


def function_results(request):
    return [json.loads(m["content"]) for m in request["messages"] if m["role"] == "function"]


def test_the_model_asks_the_timetable_and_words_the_answer(student, monkeypatch):
    sent = script(
        monkeypatch,
        # The model gets the date wrong; the day named in the question wins
        call("schedule", date_from="2026-09-30", date_to="2026-09-30"),
        text("Завтра одна пара: в 13:40 лабораторная по базам данных в Б-407, это замена."),
    )
    reply, actions = ask(student, "мне к какому часу приходить завтра")
    assert reply == "Завтра одна пара: в 13:40 лабораторная по базам данных в Б-407, это замена."
    assert actions == [("Б-407 на карте", "/map?room=Б-407"), ("Расписание", "/schedule")]

    first, second = sent
    assert [f["name"] for f in first["functions"]] == ["schedule", "find_room", "find_teacher", "search_portal"]
    assert first["function_call"] == "auto"
    assert first["messages"][-1] == {"role": "user", "content": "мне к какому часу приходить завтра"}
    called, result = second["messages"][-2:]
    assert called == {"role": "assistant", "content": "", "function_call": {"name": "schedule", "arguments": {
        "date_from": "2026-09-30", "date_to": "2026-09-30"}}, "functions_state_id": "state-schedule"}
    assert result["role"] == "function" and result["name"] == "schedule"
    data = json.loads(result["content"])
    assert data["group"] == "группа студента" and data["period"] == {"from": "2026-09-25", "to": "2026-09-25"}
    # Neither the student's name nor group goes to GigaChat
    everything_sent = json.dumps([first, second], ensure_ascii=False)
    for private in ("Иванов Иван", "24-ИСбо-1"):
        at = everything_sent.find(private)
        assert at == -1, everything_sent[max(0, at - 120):at + 60]
    assert data["lessons"] == [{
        "date": "2026-09-25", "weekday": "пятница", "start": "13:40", "end": "15:10", "discipline": "Базы данных",
        "kind": "лабораторная", "room": "Б-407", "teacher": "Иванов И.И.", "subgroup": "вся группа", "replaced": True,
    }]


def test_made_up_details_send_the_data_itself(student, monkeypatch):
    script(monkeypatch, call("schedule"), text("Завтра в 14:00 пара в Б-999."))
    reply, _ = ask(student, "мне к какому часу приходить завтра")
    assert reply.startswith("Пары группы 24-ИСбо-1 (25.09):\n• 25.09, 13:40–15:10 — Базы данных, лабораторная, Б-407")


def test_teacher_and_room_functions(student, monkeypatch):
    sent = script(
        monkeypatch,
        call("find_teacher", name="Киприна"),
        call("find_room", room="Б-305"),
        text("Людмила Юрьевна сейчас ведёт информатику в Б-305 до 11:40, это 3 этаж корпуса Б."),
    )
    reply, actions = ask(student, "с кем можно поговорить про курсовую по ИСиТ")
    assert reply.startswith("Людмила Юрьевна сейчас ведёт информатику в Б-305 до 11:40") and reply.endswith("[IMG:floor3.png]")
    assert ("Карточка преподавателя", "/teachers?q=Киприна") in actions
    teacher, room = function_results(sent[2])
    assert "Сейчас ведёт пару «Информатика» в Б-305, до 11:40." in teacher["answer"]
    assert "на 3 этаже корпуса Б" in room["answer"]


def test_search_portal_with_the_model_s_own_words(student, monkeypatch):
    sent = script(
        monkeypatch,
        call("search_portal", query="стипендия за отличную сессию"),
        text("За сессию на отлично платят 4500 рублей."),
    )
    assert ask(student, "скок платят если одни пятерки")[0] == "За сессию на отлично платят 4500 рублей."
    [found] = function_results(sent[1])
    assert found["count"] >= 1 and "4500 руб" in found["results"][0]


def test_nothing_in_the_base(student, monkeypatch):
    script(monkeypatch, call("search_portal", query="общежитие"), text(assistant.NO_ANSWER_MARK))
    assert ask(student, "где общага") == (assistant.NOT_FOUND_REPLY, [("Спросить на форуме", "/forum")])


def test_two_calls_at_most(student, monkeypatch):
    sent = script(monkeypatch, call("search_portal", query="a"), call("search_portal", query="b"), call("search_portal", query="c"))
    assert ask(student, "где общага")[0] == assistant.NOT_FOUND_REPLY
    assert [r["function_call"] for r in sent] == ["auto", "auto", "none"]


def test_bad_calls_do_not_break_the_chat(student, monkeypatch):
    sent = script(monkeypatch, call("delete_everything"), call("find_room", room="Б-999"), text(assistant.NO_ANSWER_MARK))
    assert ask(student, "где общага")[0] == assistant.NOT_FOUND_REPLY
    assert function_results(sent[2]) == [
        {"error": "Функции delete_everything нет."},
        {"error": "Такой аудитории в корпусе Б нет. Номера аудиторий: 101–420."},
    ]


def test_without_functions_the_model_only_retells(student, monkeypatch):
    sent = script(monkeypatch, rag_service.FunctionsRejected("HTTP 422"), text("За отличную сессию — 4500 рублей."))
    question = "Какая стипендия за отличную сессию?"
    assert ask(student, question)[0] == "За отличную сессию — 4500 рублей."
    assert sent[0]["functions"] and sent[1]["functions"] is None
    # Paused for a while: the next question goes straight to retelling
    script(monkeypatch, text("Отличникам — 4500 рублей."))
    assert ask(student, question)[0] == "Отличникам — 4500 рублей."
    assert not agent.available()


def test_a_slow_model_is_not_waited_for(student, monkeypatch):
    monkeypatch.setattr(agent, "ANSWER_DEADLINE", 0.05)
    script(monkeypatch, text("поздно"), delay=0.5)
    assert ask(student, "Какая стипендия за отличную сессию?")[0].startswith("Академическая стипендия: 3000 руб")


def test_guests_and_exact_answers_never_reach_the_model(client, student, fake_timetable, monkeypatch):
    sent = script(monkeypatch)
    ask(client, "где общага")
    ask(student, "Где у меня следующая пара?")
    ask(student, "как найти Б-407")
    assert sent == []


def test_a_follow_up_keeps_its_chat(student, monkeypatch):
    sent = script(monkeypatch, call("search_portal", query="стипендия четверки"), text("С четвёрками — 3000 рублей."))
    history = [{"role": "user", "content": "какая стипендия у отличников"}, {"role": "assistant", "content": "4500 рублей."}]
    r = student.post("/api/v1/chat", json={"message": "а если есть четверки", "history": history},
                     headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.json()["reply"] == "С четвёрками — 3000 рублей."
    assert [m["role"] for m in sent[0]["messages"]] == ["system", "user", "assistant", "user"]
    assert sent[0]["messages"][1:3] == history


def test_a_follow_up_about_pairs_is_answered_from_the_timetable(student, monkeypatch):
    sent = script(monkeypatch)
    history = [{"role": "user", "content": "что у меня в четверг"}, {"role": "assistant", "content": "В четверг 2 пары."}]
    r = student.post("/api/v1/chat", json={"message": "а в пятницу", "history": history},
                     headers={"X-Requested-With": "XMLHttpRequest"})
    assert r.json()["reply"].startswith("Завтра у группы 24-ИСбо-1 — 1 пара:\n• 13:40–15:10 — Базы данных")
    assert sent == []


def test_without_any_data_the_model_may_only_talk_about_itself(student, monkeypatch):
    script(monkeypatch, text("Библиотека находится в главном корпусе на первом этаже."),
           text("Я ВИТШик! Могу подсказать пары, аудитории и преподавателей."))
    assert ask(student, "где библиотека")[0] == assistant.NOT_FOUND_REPLY
    assert ask(student, "ты вообще кто такой")[0] == "Я ВИТШик! Могу подсказать пары, аудитории и преподавателей."


def test_rooms_facts_reach_the_model(student, monkeypatch):
    sent = script(
        monkeypatch,
        call("find_room", room="Б-301"),
        call("search_portal", query="Linux"),
        text("В Б-301 13 ПК и 12 ноутбуков на Linux."),
    )
    # The floor plan of the room found comes along
    assert ask(student, "подскажи, куда пойти покодить вечером")[0] == "В Б-301 13 ПК и 12 ноутбуков на Linux.\n\n[IMG:301.png]"
    room, found = function_results(sent[2])
    assert room["room"] == "Б-301 — учебная: 25 мест, 13 ПК и 12 ноутбуков на Linux, 3 этаж.\nЕсть: переносная доска, телевизор, кликер."
    assert found["results"][0].startswith("Компьютеры на Linux — в 6 аудиториях:")
