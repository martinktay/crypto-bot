from app.core.config import Settings
from app.strategies.registry import STRATEGIES

SUPPORTED_TIMEFRAMES = {"5m", "15m", "1h", "4h"}


def validate_runtime_settings(settings: Settings) -> None:
    """Validate configuration at startup. Raises ValueError on invalid config."""
    if not settings.symbol_list:
        raise ValueError("At least one symbol must be configured")

    if not settings.timeframe_list:
        raise ValueError("At least one timeframe must be configured")

    unsupported = [tf for tf in settings.timeframe_list if tf not in SUPPORTED_TIMEFRAMES]
    if unsupported:
        raise ValueError(f"Unsupported timeframes: {unsupported}")

    if settings.strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{settings.strategy}'. Supported: {list(STRATEGIES)}")
