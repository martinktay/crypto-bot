from app.core.config import Settings
from app.core.enums import TradingMode


SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "4h"}


def validate_runtime_settings(settings: Settings) -> None:
    if settings.default_mode == TradingMode.AUTO_TRADE_LIVE and not settings.enable_live_trading:
        raise ValueError("DEFAULT_MODE cannot be auto_trade_live unless ENABLE_LIVE_TRADING=true")
    if not settings.symbol_list:
        raise ValueError("At least one symbol must be configured")
    if not settings.timeframe_list:
        raise ValueError("At least one timeframe must be configured")

    unsupported = [tf for tf in settings.timeframe_list if tf not in SUPPORTED_TIMEFRAMES]
    if unsupported:
        raise ValueError(f"Unsupported timeframes: {unsupported}")
