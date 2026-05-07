# Crypto Telegram Signal Bot

Production-minded **signal-only** Telegram + FastAPI service: live market data (CCXT), strategy signals, risk checks, optional RAG/LLM explanations, manual approval, web dashboard, and outcome tracking. It does **not** place exchange orders; it records and notifies on signals.

Official repository: **[github.com/martinktay/crypto-bot](https://github.com/martinktay/crypto-bot)** (`main` branch).

## Repository continuity

This codebase is the same GitHub project linked above. It evolves the original MVP (FastAPI, strategies, approvals, Telegram) into PostgreSQL-backed runtime settings, a **signal-only** data model (legacy live execution paths removed), hardened HTTP/WebSocket security, and richer strategies/ops. **`git remote origin`** should point at `https://github.com/martinktay/crypto-bot.git`; there is no separate “other repo” expected for day-to-day work.

## Features

- **Strategies** (registry): `ema_rsi`, `breakout_volume`, `hybrid_ai` (RL-assisted direction; ATR-style levels like the other strategies).
- **Market data**: CCXT with configurable `EXCHANGE_MARKET_TYPE` (`spot` | `swap` | `future`).
- **Risk engine**: Risk–reward and runtime limits before any broadcast.
- **Pipeline**: Drops the in-progress OHLCV bar, optional higher-timeframe trend filter, optional sentiment tie-breaker (CryptoPanic), broadcast drift check on manual approval.
- **Knowledge base**: pgvector-friendly embeddings; RAG for signal explanations; ingestion scripts for PDFs and video transcripts.
- **LLM**: Chat via `LLM_PROVIDER` (`openai` | `deepseek` | `anthropic`); embeddings default to OpenAI when `OPENAI_API_KEY` is set.
- **Telegram**: Commands, admin reply keyboard, approval callbacks, structured notifications.
- **Dashboard**: `GET /` Jinja UI; `GET /api/dashboard/data` (API key when enabled); WebSocket `/ws/dashboard` (optional token).
- **Jobs**: APScheduler signal cycle + outcome tracker resolving TP/SL on historical candles.
- **Scanner**: `POST /scanner/run` — top-volume futures scan (honours `EXCHANGE_MARKET_TYPE`).
- **Optimization / backtest**: `POST /optimize`, `POST /backtest`, `GET /backtest/history`.

## Requirements

- Python **3.11+**
- **PostgreSQL** with **pgvector** recommended (`docker-compose.yml` uses `pgvector/pgvector:pg16`).
- Redis in compose for future/cache use (configured via `REDIS_URL`).

## Quick start (local)

```bash
git clone https://github.com/martinktay/crypto-bot.git
cd crypto-bot
cp .env.example .env
# Edit .env: DATABASE_URL, TELEGRAM_* , OPENAI_API_KEY (and/or LLM_*), optional API_AUTH_* / WS_AUTH_*
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Dashboard: [http://localhost:8000/](http://localhost:8000/)
- Health: `GET http://localhost:8000/health`

## Docker (development)

```bash
docker compose up --build
```

Apply migrations inside the API container (or locally against the DB service):

```bash
alembic upgrade head
```

Production-oriented compose without bind-mounting source: **`docker-compose.prod.yml`** — set a strong **`POSTGRES_PASSWORD`** in the environment before `docker compose -f docker-compose.prod.yml up`.

## Configuration

All variables are documented in **`.env.example`**, including:

| Area | Examples |
|------|-----------|
| API | `API_AUTH_ENABLED`, `API_AUTH_HEADER`, `API_AUTH_TOKEN` |
| WebSocket | `WS_AUTH_ENABLED`, `WS_AUTH_TOKEN` |
| Database | `DATABASE_URL` (Postgres URL; SQLite possible for dev with weaker vector search) |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ADMIN_CHAT_ID`, `TELEGRAM_ADMIN_USER_ID`, `TELEGRAM_GROUP_CHAT_ID` |
| Exchange | `EXCHANGE_NAME`, `EXCHANGE_TESTNET`, `EXCHANGE_MARKET_TYPE` |
| Risk / signals | `MIN_RISK_REWARD_RATIO`, `SIGNAL_COOLDOWN_MINUTES`, `APPROVAL_MODE`, `SCAN_INTERVAL_SECONDS` |
| Multi-TF / sentiment | `HIGHER_TIMEFRAME_MAP`, `SENTIMENT_ENABLED`, `CRYPTOPANIC_AUTH_TOKEN` |
| LLM | `LLM_PROVIDER`, `LLM_API_KEY`, `OPENAI_API_KEY`, `SKIP_REASONING_ON_HOLD` |

**Secrets:** Never commit `.env`. Rotate any key that was ever exposed.

## HTTP API overview

Unless noted, endpoints require the API key header when **`API_AUTH_ENABLED=true`** (default header name **`X-API-Key`**). **`GET /health`** stays unauthenticated for load balancers.

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | No API key |
| GET | `/status` | Snapshot + performance summary |
| GET | `/signals` | Recent signals |
| GET | `/why/{index}` | Recent outcome row by index |
| GET | `/insights` | Analytics + KB snippets |
| POST | `/signals/run` | Run one signal cycle |
| POST | `/mode` | Approval mode update |
| POST | `/symbols` | Update symbol list |
| POST | `/strategy/config` | Set strategy name |
| GET | `/approvals` | Pending approvals |
| POST | `/approvals/{approval_id}` | Approve/reject |
| POST | `/pause`, `/resume` | Pause/resume scans |
| POST | `/backtest` | Run backtest |
| GET | `/backtest/history` | Recent backtests |
| POST | `/optimize` | Genetic + RL optimization (async-friendly) |
| POST | `/scanner/run` | Futures scanner |
| GET | `/metrics` | Prometheus metrics (API key if auth enabled) |
| GET | `/` | Dashboard HTML |
| GET | `/api/dashboard/data` | Dashboard JSON |

WebSocket: **`/ws/dashboard`** — optional `?token=` when **`WS_AUTH_ENABLED=true`**.

## Knowledge base ingestion

```bash
pip install -e ".[transcription]"   # video transcription bundles ffmpeg via imageio-ffmpeg
python scripts/ingest_pdf.py path/to/book.pdf --title "Title" --source-type book
python scripts/ingest_video_transcript.py --video path/to/lesson.mp4 --title "Lesson"
```

## Testing

```bash
pytest tests/ -q
```

## Safety

- Signals are advisory; **not financial advice**.
- AI and optional TradingAgents reviewer **do not override** deterministic risk rejection.
- Use **HTTPS**, **API auth**, and **WS token** whenever the stack is reachable beyond localhost.

## License / contributing

Fork and PR against **[martinktay/crypto-bot](https://github.com/martinktay/crypto-bot)**. Keep secrets out of commits.
