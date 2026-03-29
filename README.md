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
  - Manual control: `/pause`, `/resume`
  - Approval workflow: `/approvals`, `/approvals/{approval_id}`
- Default operation mode is paper-trading oriented and live trading remains disabled unless explicitly enabled.
- Signal cycle orchestration using market data + EMA/RSI strategy + risk validation + execution routing.
- Manual approval flow for `manual_approval` mode with expiring approvals.
- Knowledge-base scaffolding for explainable advisory context.

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
3. Add robust retry/backoff and circuit-breakers around exchange and Telegram APIs.
4. Complete requested DB tables (`orders`, `risk_events`, `audit_logs`, `system_logs`, etc.) and migrations.
5. Integrate real OpenAI embeddings/reasoning with strict timeout budgets.
6. Add integration tests for end-to-end signal, approval, and paper-trade lifecycle.
