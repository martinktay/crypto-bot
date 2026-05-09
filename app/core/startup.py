import logging

from app.core.config import Settings
from app.strategies.registry import STRATEGIES

logger = logging.getLogger(__name__)

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

    if settings.telegram_bot_token and not (settings.telegram_admin_user_id or "").strip():
        logger.warning(
            "TELEGRAM_BOT_TOKEN is set but TELEGRAM_ADMIN_USER_ID is empty — "
            "/status, /signals, and other admin commands will not run until "
            "TELEGRAM_ADMIN_USER_ID (or TELEGRAM_USER_ID) is set to your numeric user id."
        )
