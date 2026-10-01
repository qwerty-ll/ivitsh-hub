# 📘 Руководство по развертыванию

**Проект:** ИВИТШ Хаб — единая площадка студентов Высшей ИТ-школы КГУ
**Архитектура:** React (Vite SPA) + FastAPI + PostgreSQL + Nginx (HTTPS)
**Домен:** `ivitsh-portal.kosgos.ru`
**Способ развертывания:** Docker Compose (`db`, `backend`, `client`)

---

## 0. ⚠️ Перед первым запуском после обновления: смена секретов

В истории git этого публичного репозитория остались старые секреты: ключ GigaChat, несколько
значений `SECRET_KEY`, пароль администратора, пароль PostgreSQL и файл базы `backend/portal.db`
с хэшами паролей. Считайте их скомпрометированными:

1. Перевыпустите ключ авторизации GigaChat в личном кабинете Сбера (developers.sber.ru) и отзовите старый.
2. Сгенерируйте новые `SECRET_KEY`, `ADMIN_PASSWORD`, `POSTGRES_PASSWORD` (команды — в `.env.example`).
   Смена `SECRET_KEY` разлогинит всех пользователей — это ожидаемо.
3. Сообщите владельцу учётной записи из `backend/portal.db` (коммит `eb5a634`), что пароль ЭИОС нужно сменить.
4. После смены секретов вычистите историю (`git filter-repo --path backend/portal.db --invert-paths`
   и замена строк секретов через `--replace-text`), затем force-push всех веток. Это переписывает историю
   у всех участников — согласуйте заранее. Уже сделанные клоны и форки всё равно сохранят старые данные,
   поэтому шаги 1–3 обязательны независимо от чистки.

---

## 1. Требования к серверу

Только Docker: `docker` 20.10+ и `docker compose` v2. Python, Node.js, Nginx и PostgreSQL на хост ставить не нужно.

Nginx отдаёт SPA и проксирует `/api/` на backend. Swagger (`/docs`) доступен только при `DOCS_ENABLED=true`.

---

## 2. Установка

### Шаг 1. Клонирование
```bash
git clone https://github.com/qwerty-ll/ivitsh-hub.git
cd ivitsh-hub
```

### Шаг 2. Файл окружения
```bash
cp .env.example .env
```
Заполните обязательные значения: `SECRET_KEY` (≥ 32 символов), `POSTGRES_PASSWORD`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `GIGACHAT_AUTH_KEY`. Backend не запустится с пустым или коротким `SECRET_KEY`.
`ADMIN_USERNAME` не должен совпадать ни с одним логином ЭИОС.

### Шаг 3. TLS-сертификат
Nginx слушает 443 и перенаправляет весь HTTP на HTTPS. Положите сертификат в `infrastructure/certs/`:
`fullchain.pem` и `privkey.pem`.

**Let's Encrypt (домен должен указывать на сервер, порт 80 свободен):**
```bash
sudo certbot certonly --standalone -d ivitsh-portal.kosgos.ru
sudo cp /etc/letsencrypt/live/ivitsh-portal.kosgos.ru/fullchain.pem infrastructure/certs/
sudo cp /etc/letsencrypt/live/ivitsh-portal.kosgos.ru/privkey.pem infrastructure/certs/
```
Продление без остановки портала (nginx отдаёт `/.well-known/acme-challenge/` из `infrastructure/certbot-www`):
```bash
sudo certbot renew --webroot -w "$(pwd)/infrastructure/certbot-www" \
  --deploy-hook "cp /etc/letsencrypt/live/ivitsh-portal.kosgos.ru/*.pem $(pwd)/infrastructure/certs/ && docker exec ivitsh_portal_client nginx -s reload"
```
Если университет выдаёт свой сертификат — просто положите его файлы под теми же именами.

**Для локальной проверки** подойдёт самоподписанный:
```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=localhost" \
  -keyout infrastructure/certs/privkey.pem -out infrastructure/certs/fullchain.pem
```

### Шаг 4. Сертификат для GigaChat
Серверы GigaChat подписаны сертификатами НУЦ Минцифры, которых нет в стандартных хранилищах. Проверку TLS
мы не отключаем: корневой «Russian Trusted Root CA» и выпускающие «Russian Trusted Sub CA» (2022 и 2024)
лежат в `server/app/assets/certs/russian_trusted_ca.pem` и используются только для запросов к GigaChat.
Ничего скачивать не нужно. Отпечатки SHA-256 записаны в самом файле и проверяются тестом.

Если Минцифры выпустит новый сертификат раньше, чем обновится портал, положите PEM-файл рядом с `.env`
и укажите путь к нему в `GIGACHAT_CA_BUNDLE` — он добавится к встроенным.

Проверить ключ, сертификат и модель реальными запросами (ключ и токен не печатаются):
```bash
docker compose -f infrastructure/docker-compose.yml exec backend python -m app.services.gigachat_check
```

Без ключа чат-бот продолжит работать, но будет отвечать текстом из базы портала
без перефразирования GigaChat.

У физлиц (`GIGACHAT_SCOPE=GIGACHAT_API_PERS`) GigaChat обрабатывает один запрос за раз, лишние получают
HTTP 429. Портал выстраивает вопросы в очередь (`GIGACHAT_MAX_STREAMS=1`); кто ждал бы дольше 5 секунд,
сразу получает ответ из базы. Backend должен работать в одном процессе uvicorn, иначе очередей станет несколько.

### Шаг 4а. СДО КГУ (курсы в календаре)
При входе через ЭИОС портал тем же логином и паролем запрашивает у `SDO_BASE_URL` (по умолчанию
`https://sdo.kosgos.ru`) список курсов студента через мобильный сервис Moodle (`SDO_SERVICE=moodle_mobile_app`,
он должен быть включён в СДО). Запрос идёт после ответа на вход и ни на что не влияет при ошибке — смотрите
предупреждения `ivitsh_portal.sdo` в логах. Пустой `SDO_BASE_URL` отключает запрос.

### Шаг 5. Запуск
```bash
docker compose -f infrastructure/docker-compose.yml up -d --build
```
При старте backend сам применяет миграции базы (Alembic) и при первом запуске заполняет
справочники преподавателей и предметов. Дальше они редактируются только из админ-панели.

---

## 3. Образы

- **`infrastructure/docker/Dockerfile.client`** — сборка SPA на Node 20 и `nginx:1.27-alpine`.
  Конфигурация: `infrastructure/nginx/default.conf`, заголовки безопасности и CSP — `infrastructure/nginx/snippets/`.
- **`infrastructure/docker/Dockerfile.server`** — Python 3.11-slim, запуск от непривилегированного пользователя,
  `WEB_CONCURRENCY` процессов uvicorn (в продакшн-compose — 2). Общее для них — лимиты частоты, снимок турнира
  трайбов, число занятых потоков GigaChat — лежит в Redis (сервис `redis`, `REDIS_URL`); миграции и начальные данные
  при старте выполняет один процесс (блокировка PostgreSQL). Больше одного процесса — только с Redis и PostgreSQL,
  иначе backend не запустится с понятной ошибкой. Кэш расписания у каждого процесса свой — это только скорость.
  Сколько ставить: по числу ядер сервера, но не больше 4 (пул соединений к БД делится между процессами,
  вместе они укладываются в 100 соединений PostgreSQL). Standalone-сборка (`docker-compose.yml` в корне,
  SQLite) всегда работает одним процессом.

---

## 4. Администратор

Вход: **Личный кабинет → Администратор** с `ADMIN_USERNAME` / `ADMIN_PASSWORD` из `.env`.
Главного администратора нельзя удалить, заблокировать или понизить из админ-панели.

Студенты входят через ЭИОС КГУ. Чтобы закрыть студенту доступ, используйте **блокировку**:
удалённый аккаунт создаётся заново при следующем входе через ЭИОС.

**Удаление** обезличивает учётную запись: ФИО, логин, группа, контакты, фото, личные задачи и ручные записи ПГАС
стираются, членство в объединениях и будущие записи снимаются, неполученные заказы отменяются, а история (выданные
заказы, брони, посещаемость, вопросы на форуме) остаётся под именем «Удалённый пользователь». Полностью стереть такую
запись вместе с историей можно отдельной кнопкой «Стереть полностью» (фильтр «Удалённые» на вкладке «Пользователи»).
Смена ролей, блокировки, удаления, назначение руководителей и ручные начисления бит пишутся в «Журнал действий».

---

## 5. База данных

- PostgreSQL 16 в томе `postgres_data`.
- Миграции: `server/migrations/`. Вручную: `docker exec ivitsh_portal_backend python -m app.db.migrate`.
  Новая миграция при разработке: `cd server && alembic revision --autogenerate -m "описание"`.
- **Резервные копии по расписанию** делает сервис `backup` (`infrastructure/docker/backup.sh`): при старте и
  затем каждую ночь в `BACKUP_HOUR` (UTC, по умолчанию `00` = 03:00 МСК) — `pg_dump` базы (`db_*.dump`) и архив
  загруженных файлов (`uploads_*.tgz`) в `infrastructure/backups/`; копии старше `BACKUP_KEEP_DAYS` (14) удаляются.
  Каталог `infrastructure/backups/` стоит регулярно копировать на другой сервер или диск.
  Восстановление базы: `docker exec -i ivitsh_portal_db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < infrastructure/backups/db_<дата>.dump`.
- Разовая копия вручную:
  ```bash
  docker exec ivitsh_portal_db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup_$(date +%Y%m%d).sql
  ```
- Файлы к задачам и объявлениям объединений лежат в томе `backend_data` (`/app/data/uploads` в контейнере,
  переменная `UPLOAD_DIR`). Это персональные данные (распоряжения с ФИО): копируйте том вместе с базой.
  ```bash
  docker run --rm -v infrastructure_backend_data:/data -v "$PWD":/backup alpine tar czf /backup/uploads_$(date +%Y%m%d).tgz -C /data uploads
  ```
  Размер файла ограничен `MAX_UPLOAD_MB` (10 МБ); nginx пропускает до 11 МБ только на адреса загрузки.

---

## 6. Управление

- Логи: `docker compose -f infrastructure/docker-compose.yml logs -f`
- Остановка: `docker compose -f infrastructure/docker-compose.yml down`
- Обновление: `git pull && docker compose -f infrastructure/docker-compose.yml up -d --build`
