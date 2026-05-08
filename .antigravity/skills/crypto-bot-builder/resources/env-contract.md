# Environment Variable Contract

Every environment variable used by the application. This is the authoritative reference for types, defaults, validation rules, and consumers.

---

## Reference: `.env.example`

```env
# Application
APP_ENV=local
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO

# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/crypto_bot
REDIS_URL=redis://redis:6379/0

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ADMIN_USER_ID=

# Exchange
EXCHANGE_NAME=binance
EXCHANGE_TESTNET=true

# Trading modes
DEFAULT_MODE=signal_only
APPROVAL_MODE=manual_approval

# Risk management
RISK_PER_TRADE=0.01
MAX_DAILY_LOSS_PERCENT=3.0
MAX_OPEN_POSITIONS=3
SIGNAL_COOLDOWN_MINUTES=45
MIN_RISK_REWARD_RATIO=1.2

# Paper trading
PAPER_STARTING_BALANCE=10000.0

# AI / Knowledge base
OPENAI_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
REASONING_MODEL=gpt-4.1-mini

# Trading pairs
SYMBOLS=BTC/USDT
TIMEFRAMES=15m

# Strategy
STRATEGY=ema_rsi
EMA_FAST=12
EMA_SLOW=26
RSI_PERIOD=14
RSI_LONG_THRESHOLD=70
RSI_SHORT_THRESHOLD=30
TAKE_PROFIT_R_MULTIPLE=2.0
STOP_LOSS_BUFFER_PERCENT=1.0

# Approval & scheduling
MANUAL_APPROVAL_TIMEOUT_SECONDS=300
SCAN_INTERVAL_SECONDS=300
```

---

## Variable Reference

### Application

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `APP_ENV` | `str` | `local` | No | `config.py` | Environment name: `local`, `staging`, `production`. Informational only in MVP. |
| `API_HOST` | `str` | `0.0.0.0` | No | `config.py` | Bind address for uvicorn. |
| `API_PORT` | `int` | `8000` | No | `config.py` | Bind port for uvicorn. |
| `LOG_LEVEL` | `str` | `INFO` | No | `config.py` → `utils/logging.py` | Python logging level. Valid: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`. |

### Database

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | `str` | — | **Yes** | `config.py` → `db/session.py` | PostgreSQL connection string. Must use `postgresql+psycopg://` scheme for psycopg3. No default — app fails at startup if missing. |
| `REDIS_URL` | `str` | — | No | Not yet consumed | Reserved for future caching/pubsub. Declared in docker-compose but not read by `Settings` yet. |

### Telegram

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `str` | `""` | No* | `config.py` → `telegram_bot/` | BotFather token. Empty string disables Telegram features gracefully. |
| `TELEGRAM_CHAT_ID` | `str` | `""` | No* | `config.py` → `telegram_bot/` | Default chat for notifications. |
| `TELEGRAM_ADMIN_USER_ID` | `str` | `""` | No* | `config.py` → `telegram_bot/middleware.py` | Telegram user ID for admin authorization. All sensitive commands and callbacks check this. |

> \* Required once Telegram handlers are active. Bot skips initialization if token is empty.

### Exchange

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `EXCHANGE_NAME` | `str` | `binance` | No | `config.py` → `market_data/provider.py` | Must be a valid CCXT exchange name. Only `binance` tested in MVP. |
| `EXCHANGE_TESTNET` | `bool` | `true` | No | `config.py` → exchange client | Routes to sandbox/testnet URLs. **Must be `true` unless production deployment.** |

### Trading Modes

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `DEFAULT_MODE` | `str` | `signal_only` | No | `config.py` → `state.py` | Execution mode: `signal_only`, `paper`. Validated at startup. |
| `APPROVAL_MODE` | `str` | `manual_approval` | No | `config.py` → `state.py`, `signal_service.py` | Approval mode: `auto`, `manual_approval`. |

### Risk Management

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `RISK_PER_TRADE` | `float` | `0.01` | No | `config.py` → `risk_management/engine.py` | Fraction of balance risked per trade (1% default). Used by `position_size()`. |
| `MAX_DAILY_LOSS_PERCENT` | `float` | `3.0` | No | `config.py` → `risk_management/engine.py` | Daily loss cap as percentage of starting balance. Shuts down trading for the day when exceeded. |
| `MAX_OPEN_POSITIONS` | `int` | `3` | No | `config.py` → `risk_management/engine.py` | Maximum concurrent open positions. |
| `SIGNAL_COOLDOWN_MINUTES` | `int` | `45` | No | `config.py` → `risk_management/engine.py` | Minimum minutes between same-symbol same-direction signals. |
| `MIN_RISK_REWARD_RATIO` | `float` | `1.2` | No | `config.py` → `risk_management/engine.py` | Minimum risk-reward ratio for a signal to be executable. |

### Paper Trading

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `PAPER_STARTING_BALANCE` | `float` | `10000.0` | No | `config.py` → `execution/engine.py` | Starting balance for paper trading simulation. |

### AI / Knowledge Base

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `OPENAI_API_KEY` | `str` | `""` | No | `config.py` → `knowledge_base/` | Required for real embeddings/reasoning. Stubs active when empty. |
| `EMBEDDING_MODEL` | `str` | `text-embedding-3-small` | No | `config.py` → `knowledge_base/embeddings.py` | OpenAI embedding model name. |
| `REASONING_MODEL` | `str` | `gpt-4.1-mini` | No | `config.py` → `knowledge_base/reasoning.py` | OpenAI reasoning model name. |

### Trading Pairs & Timeframes

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `SYMBOLS` | `str` | `BTC/USDT` | No | `config.py` | Comma-separated trading pairs. Parsed into list by `symbol_list` property. Must have ≥1 value. |
| `TIMEFRAMES` | `str` | `15m` | No | `config.py` → `startup.py` | Comma-separated candle timeframes. Must all be in `{5m, 15m, 1h, 4h}`. |

### Strategy Configuration

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `STRATEGY` | `str` | `ema_rsi` | No | `config.py` → `strategies/registry.py` | Default strategy name. Must be a key in `STRATEGIES` dict. |
| `EMA_FAST` | `int` | `12` | No | `config.py` → `strategies/ema_rsi.py` | Fast EMA period for crossover. |
| `EMA_SLOW` | `int` | `26` | No | `config.py` → `strategies/ema_rsi.py` | Slow EMA period for crossover. |
| `RSI_PERIOD` | `int` | `14` | No | `config.py` → `strategies/ema_rsi.py` | RSI calculation window. |
| `RSI_LONG_THRESHOLD` | `int` | `70` | No | `config.py` → `strategies/ema_rsi.py` | RSI must be below this for LONG signals. |
| `RSI_SHORT_THRESHOLD` | `int` | `30` | No | `config.py` → `strategies/ema_rsi.py` | RSI must be above this for SHORT signals. |
| `TAKE_PROFIT_R_MULTIPLE` | `float` | `2.0` | No | `config.py` → `strategies/ema_rsi.py` | Take-profit distance as a multiple of the stop-loss distance. |
| `STOP_LOSS_BUFFER_PERCENT` | `float` | `1.0` | No | `config.py` → `strategies/ema_rsi.py` | Stop-loss distance from entry price as a percentage. |

### Approval & Scheduling

| Variable | Type | Default | Required | Consumed By | Notes |
|---|---|---|---|---|---|
| `MANUAL_APPROVAL_TIMEOUT_SECONDS` | `int` | `300` | No | `config.py` → `approval_workflow/service.py` | Seconds before a pending approval expires. Default 5 minutes. |
| `SCAN_INTERVAL_SECONDS` | `int` | `300` | No | `config.py` → `services/scheduler.py` | Interval between scheduled signal cycles. Default 5 minutes. |

---

## Startup Validation Rules

Defined in `app/core/startup.py`. The app must refuse to start if any of these fail:

1. **Symbols required**: `SYMBOLS` must parse to at least one non-empty value
2. **Timeframes required**: `TIMEFRAMES` must parse to at least one non-empty value
3. **Supported timeframes**: every timeframe must be in `{5m, 15m, 1h, 4h}`
4. **Strategy exists**: `STRATEGY` must be a key in the strategy registry

Violations raise `ValueError`, preventing app startup.

---

## Adding a New Environment Variable

1. Add the field to `app/core/config.py` → `Settings` class with `Field(default=..., alias="VAR_NAME")`
2. Add it to `.env.example` with a sensible default
3. If it requires startup validation, add a check to `app/core/startup.py`
4. Update **this document** with the variable's type, default, consumer, and notes
5. If it impacts Docker, update `docker-compose.yml` environment section
