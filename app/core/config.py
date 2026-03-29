from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.enums import TradingMode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field(default="local", alias="APP_ENV")
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    database_url: str = Field(alias="DATABASE_URL")

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")
    telegram_admin_user_id: str = Field(default="", alias="TELEGRAM_ADMIN_USER_ID")

    exchange_name: str = Field(default="binance", alias="EXCHANGE_NAME")
    exchange_api_key: str = Field(default="", alias="EXCHANGE_API_KEY")
    exchange_api_secret: str = Field(default="", alias="EXCHANGE_API_SECRET")
    exchange_testnet: bool = Field(default=True, alias="EXCHANGE_TESTNET")

    enable_live_trading: bool = Field(default=False, alias="ENABLE_LIVE_TRADING")
    default_mode: TradingMode = Field(default=TradingMode.PAPER_TRADING, alias="DEFAULT_MODE")

    risk_per_trade: float = Field(default=0.01, alias="RISK_PER_TRADE")
    max_daily_loss_percent: float = Field(default=3.0, alias="MAX_DAILY_LOSS_PERCENT")
    max_open_positions: int = Field(default=3, alias="MAX_OPEN_POSITIONS")
    signal_cooldown_minutes: int = Field(default=45, alias="SIGNAL_COOLDOWN_MINUTES")

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    reasoning_model: str = Field(default="gpt-4.1-mini", alias="REASONING_MODEL")

    symbols: str = Field(default="BTC/USDT", alias="SYMBOLS")
    timeframes: str = Field(default="15m", alias="TIMEFRAMES")

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip() for item in self.symbols.split(",") if item.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [item.strip() for item in self.timeframes.split(",") if item.strip()]


settings = Settings()  # type: ignore[call-arg]
