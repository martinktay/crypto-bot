# Crypto Telegram Bot MVP

Production-minded MVP for a Telegram crypto signal bot with optional execution modes and a knowledge base.

## Proposed file tree

```text
crypto-telegram-bot/
  app/
    api/ core/ db/ models/ schemas/ services/ utils/
    market_data/ strategies/ risk_management/ execution/
    telegram_bot/ approval_workflow/ knowledge_base/ monitoring/
  tests/
  alembic/
  docker/
  .env.example
  Dockerfile
  docker-compose.yml
  pyproject.toml
```

## Current MVP capabilities

- FastAPI endpoints:
  - Core: `/health`, `/status`, `/signals`, `/signals/run`, `/trades`, `/positions`, `/mode`, `/symbols`, `/strategy/config`, `/metrics`
  - Operator: `/pause`, `/resume`, `/why/{index}`, `/insights`
  - Approval workflow: `/approvals`, `/approvals/{approval_id}`
- Strategy registry supports pluggable strategy selection (`ema_rsi`, `breakout_volume`).
- Runtime risk limits include signal cooldown and max open positions checks.
- Market data provider includes basic retry/backoff for CCXT failures.
- APScheduler background job runs signal cycle every 5 minutes (except paused or signal-only mode).

## Phase 1 completion checklist

- [x] BTC/USDT + 15m path implemented
- [x] EMA/RSI strategy integrated into execution cycle
- [x] Manual approval objects with expiry and decision endpoint
- [x] Paper trade simulation path
- [x] Live mode blocked by default and guarded by env flag
- [ ] Telegram command/callback handlers (in progress)
- [ ] DB-backed persistence replacing in-memory runtime state
- [ ] Full risk policy coverage (daily loss cap, losing-trade cooldown, duplicate execution windows)

## Local run

```bash
cp .env.example .env
pip install -e .[dev]
uvicorn app.main:app --reload
```

Then open:

- `GET http://localhost:8000/health`
- `POST http://localhost:8000/signals/run`
- `GET http://localhost:8000/approvals`
- `GET http://localhost:8000/insights`

## Docker run

```bash
docker compose up --build
```

## Safety defaults

- `ENABLE_LIVE_TRADING=false` by default.
- Startup validation rejects `DEFAULT_MODE=auto_trade_live` unless live trading is explicitly enabled.
- AI reasoning is advisory only and separate from risk validation.
- Unsupported timeframes are rejected at startup.

## Remaining production hardening tasks

1. Replace in-memory runtime state with PostgreSQL-backed repositories and transactions.
2. Implement full Telegram command handlers and callback button approval integration.
3. Complete requested DB tables (`orders`, `risk_events`, `audit_logs`, `system_logs`, etc.) and migrations.
4. Integrate real OpenAI embeddings/reasoning with strict timeout budgets and robust fallback behavior.
5. Add integration tests for end-to-end signal, approval, and paper-trade lifecycle.
