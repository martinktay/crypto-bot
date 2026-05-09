from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = Field(default="local", alias="APP_ENV")
    app_display_name: str = Field(default="Zobo Signal Bot", alias="APP_DISPLAY_NAME")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="text", alias="LOG_FORMAT")

    # Database
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/crypto_bot",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # API auth (recommended if exposed beyond localhost)
    api_auth_enabled: bool = Field(default=False, alias="API_AUTH_ENABLED")
    api_auth_header: str = Field(default="X-API-Key", alias="API_AUTH_HEADER")
    api_auth_token: str = Field(default="", alias="API_AUTH_TOKEN")

    # WebSocket auth (dashboard)
    ws_auth_enabled: bool = Field(default=False, alias="WS_AUTH_ENABLED")
    ws_auth_token: str = Field(default="", alias="WS_AUTH_TOKEN")

    # Telegram — use TELEGRAM_* names below. Legacy: TELEGRAM_CHAT_ID maps to admin DM chat;
    # TELEGRAM_USER_ID maps to admin user (same as TELEGRAM_ADMIN_USER_ID).
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_chat_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEGRAM_ADMIN_CHAT_ID",
            "TELEGRAM_CHAT_ID",
        ),
    )
    telegram_group_chat_id: str = Field(default="", alias="TELEGRAM_GROUP_CHAT_ID")
    telegram_admin_user_id: str = Field(
        default="",
        validation_alias=AliasChoices(
            "TELEGRAM_ADMIN_USER_ID",
            "TELEGRAM_USER_ID",
        ),
    )

    @model_validator(mode="after")
    def strip_telegram_secrets(self) -> "Settings":
        """Trim .env typos (trailing spaces/quotes) that break API calls and admin checks."""
        self.telegram_bot_token = self.telegram_bot_token.strip()
        self.telegram_admin_chat_id = self.telegram_admin_chat_id.strip()
        self.telegram_group_chat_id = self.telegram_group_chat_id.strip()
        self.telegram_admin_user_id = self.telegram_admin_user_id.strip()
        return self

    # Exchange — single default exchange used when a SYMBOLS entry has no
    # explicit ``exchange:`` prefix. The full list of exchanges the bot is
    # allowed to fetch from is in ``EXCHANGES`` below. Keeping ``EXCHANGE_NAME``
    # as a backwards-compatible alias means existing single-exchange .env
    # files keep working without changes.
    exchange_name: str = Field(default="binance", alias="EXCHANGE_NAME")
    # Comma-separated list of exchanges the MarketDataProvider should
    # initialise. Symbols in ``SYMBOLS`` may be qualified with one of these
    # ids, e.g. ``binance:BTC/USDT, bybit:SOL/USDT, mexc:DOGE/USDT``.
    # Unqualified symbols default to ``EXCHANGE_NAME``. Examples:
    #   EXCHANGES=binance              (single-exchange — default)
    #   EXCHANGES=binance,bybit,mexc   (wider universe)
    exchanges: str = Field(default="", alias="EXCHANGES")
    exchange_testnet: bool = Field(default=True, alias="EXCHANGE_TESTNET")
    # "spot" | "swap" | "future" — must match the products you actually want to trade.
    # Mismatched markets between the scanner and the signal pipeline will produce
    # signals on instruments you can't trade, so this is unified for both paths.
    exchange_market_type: str = Field(default="swap", alias="EXCHANGE_MARKET_TYPE")
    # Optional outbound proxy. Set when the host network blocks exchange APIs
    # (Bybit / MEXC are commonly blocked by UK/EU consumer ISPs and corporate
    # DNS filters). ccxt's underlying ``requests`` session honours these via
    # ``exchange.proxies``; urllib's reachability probes pick them up from
    # the env vars automatically. Either form works:
    #   HTTPS_PROXY=http://user:pass@proxy.example.com:8080
    #   HTTPS_PROXY=socks5://127.0.0.1:1080
    http_proxy: str = Field(default="", alias="HTTP_PROXY")
    https_proxy: str = Field(default="", alias="HTTPS_PROXY")
    # Maximum tolerated drift between the closed-bar price the strategy used and
    # the live ticker at the moment of broadcast (in percent). Above this, the
    # signal is filtered out and not broadcast.
    max_broadcast_drift_percent: float = Field(default=0.75, alias="MAX_BROADCAST_DRIFT_PERCENT")

    # Risk management
    signal_cooldown_minutes: int = Field(default=45, alias="SIGNAL_COOLDOWN_MINUTES")
    min_risk_reward_ratio: float = Field(default=1.2, alias="MIN_RISK_REWARD_RATIO")



    # AI / Knowledge base
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    reasoning_model: str = Field(default="gpt-4.1-mini", alias="REASONING_MODEL")
    # Number of recent embeddings to cache in-memory (0 disables caching).
    embedding_cache_size: int = Field(default=512, alias="EMBEDDING_CACHE_SIZE")
    # Skip the reasoning call entirely for HOLD signals — they can't be broadcast,
    # and the explanation is never read by users. Saves a chat completion per HOLD.
    skip_reasoning_on_hold: bool = Field(default=True, alias="SKIP_REASONING_ON_HOLD")

    # LLM provider (chat completions). Embeddings stay on OpenAI by default.
    # provider: "openai" | "deepseek" | "anthropic". Empty -> use OpenAI with openai_api_key.
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    llm_api_key: str = Field(default="", alias="LLM_API_KEY")
    llm_base_url: str = Field(default="", alias="LLM_BASE_URL")
    llm_model: str = Field(default="", alias="LLM_MODEL")
    llm_request_timeout: float = Field(default=15.0, alias="LLM_REQUEST_TIMEOUT")

    # Optional: TradingAgents reviewer/gate
    tradingagents_enabled: bool = Field(default=False, alias="TRADINGAGENTS_ENABLED")
    tradingagents_provider: str = Field(default="openai", alias="TRADINGAGENTS_PROVIDER")
    tradingagents_model: str = Field(default="gpt-4.1-mini", alias="TRADINGAGENTS_MODEL")
    tradingagents_reasoning_effort: str = Field(default="medium", alias="TRADINGAGENTS_REASONING_EFFORT")
    # A: Add critique/score to explanations
    tradingagents_mode_a_enabled: bool = Field(default=False, alias="TRADINGAGENTS_MODE_A_ENABLED")
    # B: Auto-gate (approve/reject) before broadcast
    tradingagents_mode_b_enabled: bool = Field(default=False, alias="TRADINGAGENTS_MODE_B_ENABLED")
    tradingagents_gate_min_score: float = Field(default=65.0, alias="TRADINGAGENTS_GATE_MIN_SCORE")

    # Trading pairs
    symbols: str = Field(default="BTC/USDT", alias="SYMBOLS")
    # Comma-separated CCXT timeframes, e.g. 15m,1h,4h or TIMEFRAMES=15,60,240 (normalized to 15m,1h,4h).
    timeframes: str = Field(default="15m", alias="TIMEFRAMES")

    @field_validator("timeframes", mode="before")
    @classmethod
    def _normalize_timeframes_string(cls, v: object) -> object:
        if not isinstance(v, str):
            return v
        from app.utils.timeframes import normalize_user_timeframe_token

        parts = [
            normalize_user_timeframe_token(p)
            for p in v.split(",")
            if str(p).strip()
        ]
        return ",".join(parts)

    # Strategy
    strategy: str = Field(default="ema_rsi", alias="STRATEGY")
    ema_fast: int = Field(default=12, alias="EMA_FAST")
    ema_slow: int = Field(default=26, alias="EMA_SLOW")
    rsi_period: int = Field(default=14, alias="RSI_PERIOD")
    rsi_long_threshold: int = Field(default=70, alias="RSI_LONG_THRESHOLD")
    rsi_short_threshold: int = Field(default=30, alias="RSI_SHORT_THRESHOLD")
    take_profit_r_multiple: float = Field(default=2.0, alias="TAKE_PROFIT_R_MULTIPLE")
    stop_loss_buffer_percent: float = Field(default=1.0, alias="STOP_LOSS_BUFFER_PERCENT")
    # Classic OHLC candlestick gates (Bible-style patterns: engulfing, stars, hammer, etc.).
    # Veto = block entries against a strong opposing pattern; strict = require a confirming pattern.
    candlestick_patterns_enabled: bool = Field(default=True, alias="CANDLESTICK_PATTERNS_ENABLED")
    candlestick_patterns_strict: bool = Field(default=False, alias="CANDLESTICK_PATTERNS_STRICT")



    # Scheduling
    scan_interval_seconds: int = Field(default=300, alias="SCAN_INTERVAL_SECONDS")
    # Process at most this many SYMBOLS entries per scheduler tick (round-robin).
    # When 0 or ≥ len(SYMBOLS), every pair runs each tick (can be slow / rate-limit
    # heavy with large universes). Typical: 50–120 for full Bybit+MEXC USDT lists.
    scan_symbols_batch_size: int = Field(default=80, alias="SCAN_SYMBOLS_BATCH_SIZE")
    # If true, each app startup updates ``bot_settings`` timeframes + strategy from
    # ``.env`` when they differ. ``SYMBOLS`` is not changed (use ``resync_symbols.py``).
    sync_runtime_timeframes_from_env: bool = Field(
        default=True,
        alias="SYNC_RUNTIME_TIMEFRAMES_FROM_ENV",
    )

    # Outcome tracking — periodically resolves open broadcast signals against
    # subsequent OHLCV (TP/SL hit, time-stop) and records realized PnL.
    outcome_tracker_interval_seconds: int = Field(default=600, alias="OUTCOME_TRACKER_INTERVAL_SECONDS")
    outcome_tracker_max_age_hours: int = Field(default=72, alias="OUTCOME_TRACKER_MAX_AGE_HOURS")

    # Sentiment (free CryptoPanic public posts). Used as a tie-breaker —
    # never as a hard gate. When the score opposes a signal direction by
    # more than ``sentiment_block_threshold``, the strategy nudges confidence
    # down by ``sentiment_confidence_penalty`` (and labels the reason).
    sentiment_enabled: bool = Field(default=False, alias="SENTIMENT_ENABLED")
    cryptopanic_auth_token: str = Field(default="", alias="CRYPTOPANIC_AUTH_TOKEN")
    sentiment_cache_ttl_seconds: int = Field(default=600, alias="SENTIMENT_CACHE_TTL_SECONDS")
    sentiment_request_timeout: float = Field(default=8.0, alias="SENTIMENT_REQUEST_TIMEOUT")
    sentiment_block_threshold: float = Field(
        default=0.4, alias="SENTIMENT_BLOCK_THRESHOLD"
    )
    sentiment_confidence_penalty: float = Field(
        default=15.0, alias="SENTIMENT_CONFIDENCE_PENALTY"
    )
    sentiment_min_posts: int = Field(default=3, alias="SENTIMENT_MIN_POSTS")

    # Multi-timeframe confirmation. The strategy's base timeframe must be aligned
    # with the higher-timeframe trend (EMA200 above/below). Map format:
    #   "5m=1h,15m=4h,1h=4h,4h=1d"
    # Pairs missing from the map disable the higher-TF check for that base TF.
    higher_timeframe_map: str = Field(
        default="5m=1h,15m=4h,1h=4h,4h=1d",
        alias="HIGHER_TIMEFRAME_MAP",
    )
    higher_timeframe_enabled: bool = Field(default=True, alias="HIGHER_TIMEFRAME_ENABLED")
    # Number of higher-timeframe bars to request — must be > EMA span (200).
    higher_timeframe_lookback: int = Field(default=300, alias="HIGHER_TIMEFRAME_LOOKBACK")
    # When enabled, fetch each listed TF strictly above the scan's base TF and
    # require EMA200 alignment on *all* (any bearish TF blocks LONG; any bullish blocks SHORT).
    # ``all`` / ``alltime`` map to ``1M`` with ``HTF_ALLTIME_LOOKBACK`` (max with HIGHER_TIMEFRAME_LOOKBACK).
    htf_alignment_timeframes: str = Field(
        default="1h,4h,1d,1w,1M,all",
        alias="HTF_ALIGNMENT_TIMEFRAMES",
    )
    htf_alignment_enabled: bool = Field(default=True, alias="HTF_ALIGNMENT_ENABLED")
    htf_alltime_lookback: int = Field(default=500, alias="HTF_ALLTIME_LOOKBACK")

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip() for item in self.symbols.split(",") if item.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [item.strip() for item in self.timeframes.split(",") if item.strip()]

    @property
    def exchange_list(self) -> list[str]:
        """Distinct exchange ids the MarketDataProvider should initialise.

        Includes every exchange explicitly listed in ``EXCHANGES`` plus the
        default ``EXCHANGE_NAME`` (so an unqualified symbol always has a
        provider to route to). Lower-cased to match ccxt's id convention.
        """
        explicit = [
            item.strip().lower()
            for item in (self.exchanges or "").split(",")
            if item.strip()
        ]
        seen: list[str] = []
        for ex in [self.exchange_name.lower(), *explicit]:
            if ex and ex not in seen:
                seen.append(ex)
        return seen

    def parse_symbol(self, raw: str) -> tuple[str, str]:
        """Split an entry from ``SYMBOLS`` into ``(exchange_id, raw_symbol)``.

        Accepts either ``"BTC/USDT"`` (uses default exchange) or
        ``"binance:BTC/USDT"`` / ``"bybit:SOL/USDT"`` etc. The exchange id is
        always lower-cased to match ccxt. We only treat the prefix as an
        exchange id if it contains no slash — that avoids accidentally
        eating the leading segment of a symbol like ``"USDT:USDT"``.
        """
        item = (raw or "").strip()
        if not item:
            return (self.exchange_name.lower(), "")
        if ":" in item:
            head, _, tail = item.partition(":")
            if head and tail and "/" not in head:
                return (head.strip().lower(), tail.strip())
        return (self.exchange_name.lower(), item)

    @property
    def higher_timeframe_pairs(self) -> dict[str, str]:
        """Parse ``HIGHER_TIMEFRAME_MAP`` into ``{base_tf: higher_tf}``."""
        if not self.higher_timeframe_enabled or not self.higher_timeframe_map:
            return {}
        pairs: dict[str, str] = {}
        for entry in self.higher_timeframe_map.split(","):
            entry = entry.strip()
            if not entry or "=" not in entry:
                continue
            base, higher = entry.split("=", 1)
            base = base.strip()
            higher = higher.strip()
            if base and higher and base != higher:
                pairs[base] = higher
        return pairs

    def higher_timeframe_for(self, base_tf: str) -> str | None:
        return self.higher_timeframe_pairs.get(base_tf)

    @property
    def htf_alignment_timeframe_list(self) -> list[str]:
        if not self.htf_alignment_enabled or not self.htf_alignment_timeframes.strip():
            return []
        return [
            x.strip()
            for x in self.htf_alignment_timeframes.split(",")
            if x.strip()
        ]


settings = Settings()  # type: ignore[call-arg]
