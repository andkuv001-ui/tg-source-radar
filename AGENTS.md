# TG Source Radar — Project Context

## О проекте

**Telegram Chat Discovery Platform** — поисковик Telegram-чатов по теме с веб-интерфейсом и LLM-оценкой релевантности.

Это НЕ парсер сообщений. Это поиск каналов/групп Telegram по тематике с автоматической оценкой релевантности через RouterAI.

## Стек

- **Backend**: FastAPI (Python 3.11)
- **Telegram API**: Telethon (StringSession, авторизация через session string)
- **БД**: Supabase (PostgreSQL) — self-hosted на `supabase.pro-n01.ru`
- **LLM**: RouterAI (`routerai.ru/api/v1/chat/completions`, модель `router`)
- **Шаблоны**: Jinja2 (серверный рендеринг, тёмная тема)
- **Деплой**: Docker → Coolify

## Структура файлов

```
TG Source Radar/
├── sql/
│   └── 001_schema.sql          # SQL-схема (запускать в Supabase SQL Editor)
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + lifespan (connect/disconnect Telethon)
│   ├── config.py               # Pydantic Settings из .env
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic модели
│   ├── services/
│   │   ├── __init__.py
│   │   ├── db.py               # Supabase client wrapper (ClientOptions с schema)
│   │   ├── telegram_search.py  # Telethon: поиск чатов через SearchRequest
│   │   ├── llm_evaluator.py    # RouterAI: оценка релевантности
│   │   └── search_pipeline.py  # Оркестрация: поиск → upsert → LLM → сохранение
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── search.py           # API: POST /api/search, GET /api/results/{id}, GET /api/status/{id}
│   │   └── pages.py            # HTML: /, /results/{id}, /history
│   └── templates/
│       ├── base.html           # Layout (тёмная тема, навигация)
│       ├── index.html          # Форма поиска + JS-поллинг статуса
│       ├── results.html        # Таблица результатов с цветовыми бейджами
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
ROUTER_AI_MODEL=router

# App
APP_ENV=production
APP_PORT=8000
```

## Supabase — важные замечания

1. **Схема**: Supabase self-hosted экспонирует только `public, storage, graphql_public, tg_lead_parser`. Используем `public`.
2. **service_role key** — обходит RLS, работает с `public` схемой.
3. **Таблицы** в `public`: `search_queries`, `found_chats`, `chat_evaluations`.
4. **VIEW** `search_results` — удобный JOIN всех трёх таблиц.
5. **RLS** выключен (service_role обходит).

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
  → Параллельная LLM-оценка (Semaphore=5):
      → UPSERT found_chats
      → RouterAI: evaluate_chat_relevance
      → INSERT chat_evaluations
      → UPDATE total_scored (прогресс)
  → status=completed, completed_at=datetime.now(UTC)
```

## Telethon — авторизация

1. **StringSession** — передаётся через `TELEGRAM_SESSION_STRING` в .env.
2. Генерируется локально: `python -c "from telethon.sync import TelegramClient; c=TelegramClient('session', API_ID, API_HASH); c.start(); print(c.session.save())"`
3. В контейнере: `client.connect()` (не `client.start()`) — StringSession уже содержит auth key.
4. **FloodWaitError** — обрабатывается автоматически (sleep на указанное время).

## RouterAI — промпт

```json
{
  "model": "router",
  "messages": [
    {"role": "system", "content": "Ты — аналитик Telegram-чатов. Оцени, насколько чат релевантен заданной теме. Ответь ТОЛЬКО валидным JSON."},
    {"role": "user", "content": "Оцени релевантность чата к теме:\n\nТема: «...»\nКлючевые слова: ...\n\nДанные чата:\n- Название: ...\n- Описание: ...\n- Участников: ...\n\nФормат ответа:\n{\"relevance_score\": 0.0-1.0, \"topic_match\": \"...\", \"category\": \"...\", \"language\": \"ru|en|other\"}"}
  ],
  "response_format": {"type": "json_object"},
  "temperature": 0.1
}
```

## Деплой

```bash
cd "/Users/andrejkuvsinov/TG Source Radar"
docker compose up --build
```

Приложение: `http://localhost:8010`

Ярлык на Desktop: `TG Source Radar.app` (двойной клик → открывает Terminal → запускает Docker).

## Известные проблемы / TODO

- [ ] Нет авторизации на веб-интерфсе (MVP — открытый доступ)
- [ ] n8n не используется (можно добавить для периодических поисков/уведомлений)
- [ ] Rate limits Telegram Search API — FloodWait при массовом поиске
- [ ] `completed_at` теперь `datetime.now(UTC).isoformat()` (не SQL `now()`)
- [ ] Параллельная оценка: `CONCURRENCY = 5` в search_pipeline.py
- [ ] Supabase URL в .env: `https://supabase.pro-n01.ru` (self-hosted)
