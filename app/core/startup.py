"""Startup guards that enforce strict MVP scope and safety defaults."""

from app.core.config import Settings
from app.core.enums import TradingMode


SUPPORTED_TIMEFRAMES = {"15m"}
SUPPORTED_SYMBOLS = {"BTC/USDT"}


def validate_runtime_settings(settings: Settings) -> None:
    if settings.default_mode == TradingMode.AUTO_TRADE_LIVE:
        raise ValueError("auto_trade_live is disabled for MVP; use manual_approval or paper_trading")
    if not settings.symbol_list:
        raise ValueError("At least one symbol must be configured")
    if not settings.timeframe_list:
        raise ValueError("At least one timeframe must be configured")

    unsupported_symbols = [s for s in settings.symbol_list if s not in SUPPORTED_SYMBOLS]
    if unsupported_symbols:
        raise ValueError(f"Unsupported symbols for MVP: {unsupported_symbols}")

    unsupported_timeframes = [tf for tf in settings.timeframe_list if tf not in SUPPORTED_TIMEFRAMES]
    if unsupported_timeframes:
        raise ValueError(f"Unsupported timeframes for MVP: {unsupported_timeframes}")
