# Exchange Interaction Safety Model

This document defines the safety rules, testnet configuration, and guard mechanisms for all interactions with cryptocurrency exchanges via CCXT.

---

## Safety Hierarchy (5 Layers)

The system uses a **layered defense** to prevent accidental live trading:

```
Layer 1: ENABLE_LIVE_TRADING=false (default)
    │
    ▼
Layer 2: Startup validation — blocks DEFAULT_MODE=live if Layer 1 is false
    │                        — blocks EXCHANGE_TESTNET=false if Layer 1 is false
    │                        — requires EXCHANGE_API_KEY + EXCHANGE_API_SECRET for live
    │
    ▼
Layer 3: Execution engine — checks ENABLE_LIVE_TRADING again at execution time
    │
    ▼
Layer 4: EXCHANGE_TESTNET=true — routes to sandbox by default
    │
    ▼
Layer 5: Live adapter not built — returns "not configured" even if all guards pass
```

All five layers must be intentionally disabled for a real trade to execute. This is **by design**.

---

## Non-Negotiable Safety Rules (from SKILL.md)

- Never default to live trading
- Never bypass risk rules
- Never hardcode secrets
- Never commit credentials
- Do not execute live trades unless `ENABLE_LIVE_TRADING=true` AND exchange credentials are present
- Paper trading must be working before live mode is implemented
- Manual approval flow must work before any auto-trade live path is enabled

---

## Current Exchange Integration

### MarketDataProvider (`app/market_data/provider.py`)

The only current exchange interaction is **public market data**:

```python
class MarketDataProvider:
    def __init__(self, exchange_name: str = "binance"):
        exchange_cls = getattr(ccxt, exchange_name)
        self.exchange = exchange_cls({"enableRateLimit": True, "timeout": 10000})
    
    def fetch_ohlcv(self, symbol, timeframe, limit=200):
        # 3 attempts with linear backoff (1s, 2s, 3s)
    
    def fetch_ticker(self, symbol):
        # 3 attempts with linear backoff
```

**Key properties:**
- No API keys passed → only public endpoints work
- `enableRateLimit: True` → CCXT manages rate limiting
- `timeout: 10000` (10s) → prevents hanging connections
- 3 retry attempts with `time.sleep(attempt)` linear backoff

### What's Not Built

- Authenticated exchange client (requires API key/secret)
- Order placement (`create_order`, `create_limit_order`)
- Order management (`cancel_order`, `edit_order`)
- Balance queries (`fetch_balance`)
- Position queries (`fetch_positions`)

---

## Paper Trading Model

Paper trading simulates execution against `PAPER_STARTING_BALANCE`:

- **Slippage**: `entry_price × 0.0005` (0.05%)
- **Fee**: `entry_price × 0.001` (0.1%)
- Position sizing uses `RiskEngine.position_size()` with paper balance
- Track paper P&L per position and cumulative
- Paper balance decrements/increments on simulated fills

Paper trading must be fully functional **before** any live adapter is built.

---

## Testnet Configuration

When building the live execution adapter, the exchange client **must** respect the testnet flag:

```python
def create_exchange(settings: Settings):
    """Create an authenticated CCXT exchange client."""
    exchange_cls = getattr(ccxt, settings.exchange_name)
    config = {
        "apiKey": settings.exchange_api_key,
        "secret": settings.exchange_api_secret,
        "enableRateLimit": True,
        "timeout": 15000,
    }
    
    exchange = exchange_cls(config)
    
    if settings.exchange_testnet:
        exchange.set_sandbox_mode(True)  # Routes to testnet URLs
    
    return exchange
```

### Exchange Testnet URLs

| Exchange | Testnet Support | Notes |
|---|---|---|
| Binance | ✅ `testnet.binance.vision` | Spot testnet; futures testnet separate |
| Bybit | ✅ `testnet.bybit.com` | Unified testnet |
| OKX | ✅ (demo account mode) | Uses demo trading flag |

**Startup validation rule**: `EXCHANGE_TESTNET=false` requires `ENABLE_LIVE_TRADING=true`. This prevents accidentally routing to production exchange APIs.

---

## Execution Safety Checks

### Check 1: Double-Check Live Trading Flag

`ENABLE_LIVE_TRADING` is verified at **two independent points**:

1. **Startup** (`app/core/startup.py`) — prevents starting in live mode without the flag
2. **Execution** (`app/execution/engine.py`) — blocks live execution even if mode is changed at runtime

Both checks must remain. Never consolidate into a single checkpoint.

### Check 2: Credentials Required

When `ENABLE_LIVE_TRADING=true`, startup validation must verify:
- `EXCHANGE_API_KEY` is non-empty
- `EXCHANGE_API_SECRET` is non-empty

Without credentials, the exchange client cannot authenticate.

### Check 3: Risk Validation Before Every Execution

```
Signal → RiskEngine.validate_signal()
       → RiskEngine.validate_runtime_limits()
       → RiskEngine.validate_daily_loss()
       → ExecutionEngine.execute()
```

No execution path may skip risk validation. This includes:
- Scheduled cycles via APScheduler
- Manual triggers via `POST /signals/run`
- Telegram callback approvals
- API-based approval decisions

### Check 4: Configurable Risk Parameters

All risk thresholds come from environment variables:

| Check | Variable | Default |
|---|---|---|
| Risk-reward ratio | `MIN_RISK_REWARD_RATIO` | `1.2` |
| Max positions | `MAX_OPEN_POSITIONS` | `3` |
| Signal cooldown | `SIGNAL_COOLDOWN_MINUTES` | `45` |
| Daily loss cap | `MAX_DAILY_LOSS_PERCENT` | `3.0` |
| Per-trade risk | `RISK_PER_TRADE` | `0.01` (1%) |

### Check 5: Position Sizing

```python
risk_amount = balance * settings.risk_per_trade     # e.g., 10000 × 0.01 = $100
per_unit_risk = abs(entry_price - stop_loss)         # e.g., |50000 - 49500| = $500
quantity = risk_amount / per_unit_risk               # e.g., $100 / $500 = 0.2 BTC
```

For live mode, `balance` must come from `exchange.fetch_balance()`. Never use hardcoded or estimated values.

---

## Strategy Parameters as Env Vars

The EMA/RSI strategy uses configurable parameters rather than hardcoded values:

| Parameter | Variable | Default | Purpose |
|---|---|---|---|
| Fast EMA | `EMA_FAST` | `12` | Short-term trend |
| Slow EMA | `EMA_SLOW` | `26` | Long-term trend |
| RSI period | `RSI_PERIOD` | `14` | RSI calculation window |
| Long threshold | `RSI_LONG_THRESHOLD` | `70` | RSI must be below this for LONG |
| Short threshold | `RSI_SHORT_THRESHOLD` | `30` | RSI must be above this for SHORT |
| Take profit | `TAKE_PROFIT_R_MULTIPLE` | `2.0` | TP = R-multiple × stop distance |
| Stop loss | `STOP_LOSS_BUFFER_PERCENT` | `1.0` | SL distance from entry as % |

These must be read from `Settings` in the strategy, not hardcoded.

---

## Error Handling for Exchange Operations

```python
try:
    order = exchange.create_limit_order(symbol, side, quantity, price)
except ccxt.InsufficientFunds:
    # Log and reject — do NOT retry
except ccxt.InvalidOrder:
    # Log and reject — order params are wrong
except ccxt.AuthenticationError:
    # Log and reject — do NOT retry, credentials are bad
except ccxt.RateLimitExceeded:
    # Wait and retry (CCXT handles if enableRateLimit=True)
except ccxt.NetworkError:
    # Retry with backoff (same pattern as MarketDataProvider)
except ccxt.ExchangeError:
    # Log the full error, reject the trade
```

**Rules:**
- Retry only on `NetworkError` (timeouts, connection drops)
- Never retry `AuthenticationError`, `InsufficientFunds`, `InvalidOrder`
- Maximum 3 attempts with linear backoff
- Log every retry attempt
- Every failure must be reflected in `ExecutionResult`

---

## Retry & Backoff Pattern

Established in `MarketDataProvider`, apply consistently:

```python
def _retry(self, operation, *args, attempts=3):
    for attempt in range(1, attempts + 1):
        try:
            return operation(*args)
        except ccxt.NetworkError:
            if attempt == attempts:
                raise
            time.sleep(attempt)  # linear: 1s, 2s, 3s
        except (ccxt.ExchangeError, ccxt.AuthenticationError):
            raise  # don't retry logic errors
    return None
```

---

## Checklist: Building the Live Execution Adapter

Prerequisites (must all be complete before starting):
- [ ] Paper trading fully working with P&L tracking
- [ ] Manual approval flow working via Telegram
- [ ] Daily loss cap enforced in RiskEngine
- [ ] All risk rules passing tests

Implementation:
- [ ] Create authenticated exchange client with API key/secret from Settings
- [ ] Respect `EXCHANGE_TESTNET` via `set_sandbox_mode()`
- [ ] Add startup validation: credentials required when `ENABLE_LIVE_TRADING=true`
- [ ] Add startup validation: `EXCHANGE_TESTNET=false` requires `ENABLE_LIVE_TRADING=true`
- [ ] Use `fetch_balance()` for real position sizing
- [ ] Use limit orders only (no market orders for MVP)
- [ ] Handle all CCXT exception types individually
- [ ] Log every order attempt (symbol, side, quantity, price)
- [ ] Store results in `Trade` and `Position` SQLAlchemy models
- [ ] Add Prometheus counters: `live_orders_placed_total`, `live_orders_failed_total`
- [ ] Write integration test against exchange testnet
- [ ] Add order status monitoring (poll `fetch_order()`)
- [ ] Send Telegram notifications for live order fills/failures
