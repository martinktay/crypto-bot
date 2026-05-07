from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import ApprovalMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Application
    app_env: str = Field(default="local", alias="APP_ENV")
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

    # Telegram
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_admin_chat_id: str = Field(default="", alias="TELEGRAM_ADMIN_CHAT_ID")
    telegram_group_chat_id: str = Field(default="", alias="TELEGRAM_GROUP_CHAT_ID")
    telegram_admin_user_id: str = Field(default="", alias="TELEGRAM_ADMIN_USER_ID")

    # Exchange
    exchange_name: str = Field(default="binance", alias="EXCHANGE_NAME")
    exchange_testnet: bool = Field(default=True, alias="EXCHANGE_TESTNET")
    # "spot" | "swap" | "future" — must match the products you actually want to trade.
    # Mismatched markets between the scanner and the signal pipeline will produce
    # signals on instruments you can't trade, so this is unified for both paths.
    exchange_market_type: str = Field(default="swap", alias="EXCHANGE_MARKET_TYPE")
    # Maximum tolerated drift between the closed-bar price the strategy used and
    # the live ticker at the moment of broadcast (in percent). Above this, the
    # signal is rejected at approval time.
    max_broadcast_drift_percent: float = Field(default=0.75, alias="MAX_BROADCAST_DRIFT_PERCENT")

    # Signal settings
    approval_mode: ApprovalMode = Field(
        default=ApprovalMode.MANUAL_APPROVAL, alias="APPROVAL_MODE"
    )

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
    # B: Auto-gate (approve/reject) before manual approval/broadcast
    tradingagents_mode_b_enabled: bool = Field(default=False, alias="TRADINGAGENTS_MODE_B_ENABLED")
    tradingagents_gate_min_score: float = Field(default=65.0, alias="TRADINGAGENTS_GATE_MIN_SCORE")

    # Trading pairs
    symbols: str = Field(default="BTC/USDT", alias="SYMBOLS")
    timeframes: str = Field(default="15m", alias="TIMEFRAMES")

    # Strategy
    strategy: str = Field(default="ema_rsi", alias="STRATEGY")
    ema_fast: int = Field(default=12, alias="EMA_FAST")
    ema_slow: int = Field(default=26, alias="EMA_SLOW")
    rsi_period: int = Field(default=14, alias="RSI_PERIOD")
    rsi_long_threshold: int = Field(default=70, alias="RSI_LONG_THRESHOLD")
    rsi_short_threshold: int = Field(default=30, alias="RSI_SHORT_THRESHOLD")
    take_profit_r_multiple: float = Field(default=2.0, alias="TAKE_PROFIT_R_MULTIPLE")
    stop_loss_buffer_percent: float = Field(default=1.0, alias="STOP_LOSS_BUFFER_PERCENT")
    


    # Approval & scheduling
    manual_approval_timeout_seconds: int = Field(default=300, alias="MANUAL_APPROVAL_TIMEOUT_SECONDS")
    scan_interval_seconds: int = Field(default=300, alias="SCAN_INTERVAL_SECONDS")

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

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip() for item in self.symbols.split(",") if item.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [item.strip() for item in self.timeframes.split(",") if item.strip()]

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


settings = Settings()  # type: ignore[call-arg]
