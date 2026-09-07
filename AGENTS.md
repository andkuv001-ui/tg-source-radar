# TG Source Radar — Project Context

## О проекте

**Telegram Chat Discovery Platform** — поисковик Telegram-чатов по теме с веб-интерфейсом и LLM-оценкой релевантности.

Это НЕ парсер сообщений. Это поиск каналов/групп Telegram по тематике с автоматической оценкой релевантности через RouterAI.

## Стек

- **Backend**: FastAPI (Python 3.11)
- **Telegram API**: Telethon (StringSession, авторизация через session string)
- **БД**: Supabase (PostgreSQL) — self-hosted на `supabase.pro-n01.ru`
- **LLM**: RouterAI (`routerai.ru/api/v1/chat/completions`, модель `xiaomi/mimo-v2.5`)
- **Шаблоны**: Jinja2 (серверный рендеринг, тёмная тема)
- **Деплой**: Docker → Coolify (сервер `p699718` / `178.208.66.153`)
- **Git**: `https://github.com/andkuv001-ui/tg-source-radar.git` (ветка `main`)

## Структура файлов

```
TG Source Radar/
├── sql/
│   └── 001_schema.sql          # SQL-схема + миграции (запускать в Supabase SQL Editor)
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + lifespan (connect/disconnect Telethon)
│   ├── config.py               # Pydantic Settings из .env (+MIN_PARTICIPANTS, MAX_INACTIVE_DAYS)
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic модели (+channel_type, is_community)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db.py               # Supabase client wrapper (ClientOptions с schema)
│   │   ├── telegram_search.py  # Telethon: поиск чатов + get_last_message_date()
│   │   ├── llm_evaluator.py    # RouterAI: оценка релевантности (channel_type/is_community)
│   │   └── search_pipeline.py  # Оркестрация: pre-filter → LLM → сохранение
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── search.py           # API: POST /api/search, GET /api/results/{id}, GET /api/status/{id}
│   │   └── pages.py            # HTML: /, /results/{id}, /history
│   └── templates/
│       ├── base.html           # Layout (тёмная тема, навигация, CSS-бейджи)
│       ├── index.html          # Форма поиска + JS-поллинг статуса
│       ├── results.html        # Таблица с бейджами типа канала, фильтр ≥0.3
│       └── history.html        # Список прошлых поисков
├── Dockerfile                  # python:3.11-slim + curl
├── docker-compose.yml          # Порт 8010:8000
├── requirements.txt
├── .env.example
├── .env                        # Реальные credentials (НЕ коммитить)
├── .dockerignore
├── .gitignore
└── start.sh                    # Скрипт запуска
```

## Переменные окружения (.env)

```env
# Telegram (Telethon)
TELEGRAM_API_ID=             # с my.telegram.org
TELEGRAM_API_HASH=           # с my.telegram.org
TELEGRAM_SESSION_STRING=     # StringSession из Telethon (для non-interactive auth)

# Supabase (self-hosted)
SUPABASE_URL=https://supabase.pro-n01.ru
SUPABASE_KEY=                # service_role key
SUPABASE_SCHEMA=public       # КРИТИЧНО: public (не lead_intel — не экспонирована)

# RouterAI
ROUTER_AI_BASE_URL=https://routerai.ru/api/v1
ROUTER_AI_KEY=               # ключ API
ROUTER_AI_MODEL=xiaomi/mimo-v2.5

# Filters
MIN_PARTICIPANTS=50          # Мин. кол-во участников для pre-filter
MAX_INACTIVE_DAYS=90         # Макс. дней без активности для pre-filter

# App
APP_ENV=production
APP_PORT=8000
```

## Supabase — важные замечания

1. **Схема**: Supabase self-hosted экспонирует только `public, storage, graphql_public, tg_lead_parser`. Используем `public`.
2. **service_role key** — обходит RLS, работает с `public` схемой.
3. **Таблицы** в `public`: `search_queries`, `found_chats`, `chat_evaluations`.
4. **VIEW** `search_results` — удобный JOIN всех трёх таблиц (+ channel_type, is_community).
5. **RLS** выключен (service_role обходит).

## SQL-миграция (для существующих БД)

```sql
ALTER TABLE public.chat_evaluations ADD COLUMN IF NOT EXISTS channel_type TEXT;
ALTER TABLE public.chat_evaluations ADD COLUMN IF NOT EXISTS is_community BOOLEAN DEFAULT false;
```

VIEW `search_results` уже включает новые колонки (пересоздаётся через `CREATE OR REPLACE VIEW`).

## API

- `POST /api/search` — тело `{topic, keywords[]}` → запускает pipeline в фоне, возвращает query
- `GET /api/status/{query_id}` → `{status, total_found, total_scored}`
- `GET /api/results/{query_id}` → `{query, results[]}`
- `GET /health` → `{status: "ok"}`

## Pipeline (search_pipeline.py)

```
POST /api/search
  → INSERT search_queries (status=searching)
  → Telethon: search_chats(topic) + search_chats(keyword_1) + ...
  → Дедупликация по telegram_chat_id
  → status=evaluating, total_found=N
  → PRE-FILTER (до LLM):
      → Фильтр по участникам (min_participants=50, in-memory)
      → Фильтр по активности (get_last_message_date, Semaphore=5, параллельно)
  → Параллельная LLM-оценка (Semaphore=5):
      → UPSERT found_chats
      → RouterAI: evaluate_chat_relevance (channel_type, is_community)
      → INSERT chat_evaluations
      → UPDATE total_scored (прогресс)
  → status=completed, completed_at=datetime.now(UTC)
```

### Pre-filter (уровень фильтрации 1)

- **Участники**: каналы с `< MIN_PARTICIPANTS` участников отсеиваются (бесплатно, in-memory)
- **Активность**: `get_last_message_date()` через `client.get_messages(channel, limit=1)` — параллельно (Semaphore=5). Каналы без сообщений или с `последнее сообщение > MAX_INACTIVE_DAYS` отсеиваются
- Логирует количество отсеянных по каждому критерию

### LLM-оценка (уровень фильтрации 2)

- Промпт явно различает discussion/broadcast/commercial/mixed каналы
- Коммерческие каналы получают `relevance_score ≤ 0.2`
- Обсуждения темы получают `relevance_score ≥ 0.5`
- Ответ LLM: `{relevance_score, topic_match, category, language, channel_type, is_community}`

### UI-фильтрация (уровень фильтрации 3)

- Результаты с `relevance_score < 0.3` не отображаются
- Бейджи типа канала: обсуждение (зелёный), канал (синий), магазин (красный), смешанный (жёлтый)

## Telethon — авторизация

1. **StringSession** — передаётся через `TELEGRAM_SESSION_STRING` в .env.
2. Генерируется локально: `python gen_session.py` (интерактивно: номер телефона + код из Telegram)
3. В контейнере: `client.connect()` (не `client.start()`) — StringSession уже содержит auth key.
4. **FloodWaitError** — обрабатывается автоматически (sleep на указанное время + retry).
5. **AuthKeyDuplicatedError** — при повторном использовании сессии с разных IP. Нужно перегенерировать через `gen_session.py`.

### Генерация новой сессии

```bash
cd "/Users/andrejkuvsinov/TG Source Radar"
python3 gen_session.py
# Ввести номер телефона, получить код в Telegram, скопировать SESSION_STRING
```

## RouterAI — промпт

```json
{
  "model": "xiaomi/mimo-v2.5",
  "messages": [
    {
      "role": "system",
      "content": "Ты — аналитик Telegram-чатов. Оцени, насколько чат релевантен заданной теме и является ли он живым сообществом. Ответь ТОЛЬКО валидным JSON.\n\nКритерии оценки:\n- Канал должен быть community/дискуссионным (люди задают вопросы, обсуждают), а НЕ broadcast/коммерческим (односторонняя реклама, продажи)\n- Если канал — чистый магазин/реклама/продажи → relevance_score ≤ 0.2\n- Если канал — обсуждение темы с активностью → relevance_score ≥ 0.5\n- Если канал — смешанный (есть обсуждения, но много рекламы) → relevance_score 0.3-0.5"
    },
    {
      "role": "user",
      "content": "Оцени релевантность чата к теме:\n\nТема: «...»\nКлючевые слова: ...\n\nДанные чата:\n- Название: ...\n- Описание: ...\n- Участников: ...\n\nФормат ответа:\n{\"relevance_score\": 0.0-1.0, \"topic_match\": \"...\", \"category\": \"...\", \"language\": \"ru|en|other\", \"channel_type\": \"discussion|broadcast|commercial|mixed\", \"is_community\": true|false}"
    }
  ],
  "response_format": {"type": "json_object"},
  "temperature": 0.1
}
```

## Деплой

### Локальная разработка

```bash
cd "/Users/andrejkuvsinov/TG Source Radar"
docker compose up --build
```

Приложение: `http://localhost:8010`

Ярлык на Desktop: `TG Source Radar.app` (двойной клик → открывает Terminal → запускает Docker).

### Продакшн (Coolify)

- **Сервер**: `p699718` (`178.208.66.153`)
- **Coolify UI**: `https://<IP>:8000`
- **Домен**: через Coolify (автоматический SSL)
- **Git**: `https://github.com/andkuv001-ui/tg-source-radar.git` (ветка `main`)
- **Coolify Application ID**: `p4sogzwnpm5876ego8om8lou`
- **Container**: `p4sogzwnpm5876ego8om8lou-*` (имя меняется при ребилде)

#### Деплой через Coolify

1. Запушить изменения в GitHub: `git push origin main`
2. Coolify автоматически подтянет и пересоберёт (или нажать **Redeploy** в UI)

#### Environment Variables (Coolify UI)

Важно: Coolify перезаписывает `.env` в контейнере из UI-переменных при каждом деплое. Менять файл `.env` на диске бессмысленно.

**КРИТИЧНО**: `SUPABASE_KEY` и `TELEGRAM_SESSION_STRING` — не путать! Ранее `sed` случайно записал Telegram-сессию в `SUPABASE_KEY`.

| Переменная | Описание |
|-----------|----------|
| `TELEGRAM_API_ID` | ID приложения Telegram |
| `TELEGRAM_API_HASH` | Hash приложения Telegram |
| `TELEGRAM_SESSION_STRING` | StringSession (генерируется через `gen_session.py`) |
| `SUPABASE_URL` | `https://supabase.pro-n01.ru` |
| `SUPABASE_KEY` | service_role key (JWT) |
| `SUPABASE_SCHEMA` | `public` |
| `ROUTER_AI_BASE_URL` | `https://routerai.ru/api/v1` |
| `ROUTER_AI_KEY` | Ключ API RouterAI |
| `ROUTER_AI_MODEL` | `xiaomi/mimo-v2.5` |
| `MIN_PARTICIPANTS` | `50` |
| `MAX_INACTIVE_DAYS` | `90` |
| `APP_ENV` | `production` |
| `APP_PORT` | `8000` |

#### Обновление .env на сервере (ручное)

```bash
# Найти Coolify app ID
ls /data/coolify/applications/

# Редактировать .env
nano /data/coolify/applications/<app-id>/.env

# Перезапустить контейнер
docker restart $(docker ps -a --format '{{.Names}}' | grep <app-id>)
```

#### Полезные команды на сервере

```bash
# Статус контейнеров
docker ps -a --format '{{.Names}} {{.Status}}' | head -10

# Логи приложения
docker logs $(docker ps -a --format '{{.Names}}' | grep p4s) 2>&1 | tail -30

# Ошибки
docker logs $(docker ps -a --format '{{.Names}}' | grep p4s) 2>&1 | grep -i "error\|exception" | tail -10

# Pre-filter логи
docker logs $(docker ps -a --format '{{.Names}}' | grep p4s) 2>&1 | grep -i "pre-filter"

# Проверка переменных в контейнере
docker exec <container> env | grep TELEGRAM_SESSION_STRING | head -c 50

# Проверка данных в БД
docker exec <container> python -c "
import os
from supabase import create_client, ClientOptions
url = os.environ.get('SUPABASE_URL','')
key = os.environ.get('SUPABASE_KEY','')
c = create_client(url, key, options=ClientOptions(schema='public'))
q = c.table('search_queries').select('*').order('created_at', desc=True).limit(3).execute()
for r in q.data:
    print(r['id'], r['status'], r.get('total_found'), r.get('total_scored'), r['topic'][:50])
"
```

## Известные проблемы / TODO

- [ ] Нет авторизации на веб-интерфсе (MVP — открытый доступ)
- [ ] n8n не используется (можно добавить для периодических поисков/уведомлений)
- [ ] Rate limits Telegram Search API — FloodWait при массовом поиске (добавлен retry)
- [ ] `completed_at` теперь `datetime.now(UTC).isoformat()` (не SQL `now()`)
- [ ] Параллельная оценка: `CONCURRENCY = 5` в search_pipeline.py
- [ ] Supabase URL в .env: `https://supabase.pro-n01.ru` (self-hosted)
- [ ] DNS нестабилен на сервере — Docker-сеть иногда не резолвит
- [ ] Старый контейнер `app-j10ay869l4xurjhioljd8ez5` (tg-lead-parser) — остановлен, но не удалён
