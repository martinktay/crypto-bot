# Crypto Telegram Bot MVP (Phase 1 Scope-Locked)

This repository is intentionally scoped to a **working MVP only**:

- Pair: `BTC/USDT`
- Timeframe: `15m`
- Strategy: `EMA crossover + RSI`
- Modes: `signal_only`, `manual_approval`, `paper_trading`
- Live trading: **disabled in MVP**

## What works end-to-end right now

1. Signal cycle fetches BTC/USDT 15m candles from CCXT.
2. EMA+RSI strategy produces a normalized signal contract.
3. Risk checks run (RR filter, cooldown, max open position checks).
4. Signal is sent to Telegram (if bot token + chat id are configured).
5. In manual approval mode, approval is created and can be accepted/rejected via API.
6. In paper mode (or approved manual mode), paper trades are recorded.
7. Trade memory and strategy docs are included in signal context for explainability.
8. Signals and paper trades are persisted through SQLAlchemy repositories when DB is available.

## API endpoints

- `GET /health`
- `GET /status`
- `GET /signals`
- `POST /signals/run`
- `GET /trades`
- `GET /positions`
- `POST /mode`
- `POST /symbols` (MVP supports BTC/USDT only)
- `POST /strategy/config` (MVP supports ema_rsi only)
- `GET /approvals`
- `POST /approvals/{approval_id}`
- `GET /why/{index}`
- `GET /insights`
- `POST /pause`
- `POST /resume`
- `GET /metrics`

## Local run

```bash
cp .env.example .env
pip install -e .[dev]
uvicorn app.main:app --reload
```

## Docker run

```bash
docker compose up --build
```

## Telegram setup

Set in `.env`:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If these are missing, the app still runs but Telegram delivery is skipped.

## Admin protection

- Set `ADMIN_API_TOKEN` in `.env`.
- For control endpoints (`/signals/run`, `/mode`, `/symbols`, `/strategy/config`, `/approvals/{id}`, `/pause`, `/resume`), pass header:
  - `X-Admin-Token: <ADMIN_API_TOKEN>`

## Safety

- `auto_trade_live` mode is blocked at startup and runtime in this MVP.
- Live exchange execution is intentionally not implemented in MVP.

## Secret hygiene

- Never commit real API keys/tokens to git.
- Run local secret scan before pushing:

```bash
python scripts/check_secrets.py
```


## What is intentionally deferred

- Live trading adapters
- Multi-symbol and multi-timeframe operation
- Full Telegram bot command/callback UX
- Complete production risk policy suite and portfolio analytics
