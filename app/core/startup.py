import logging

from app.core.config import Settings
from app.strategies.registry import STRATEGIES
from app.utils.timeframes import is_alltime_token

logger = logging.getLogger(__name__)

SUPPORTED_TIMEFRAMES = {"5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"}


def validate_runtime_settings(settings: Settings) -> None:
    """Validate configuration at startup. Raises ValueError on invalid config."""
    if not settings.symbol_list:
        raise ValueError("At least one symbol must be configured")

    if not settings.timeframe_list:
        raise ValueError("At least one timeframe must be configured")

    unsupported = [tf for tf in settings.timeframe_list if tf not in SUPPORTED_TIMEFRAMES]
    if unsupported:
        raise ValueError(f"Unsupported timeframes: {unsupported}")

    if settings.htf_alignment_enabled and settings.htf_alignment_timeframes.strip():
        bad_htf = [
            t
            for t in settings.htf_alignment_timeframe_list
            if not is_alltime_token(t) and t not in SUPPORTED_TIMEFRAMES
        ]
        if bad_htf:
            raise ValueError(
                f"Unsupported HTF_ALIGNMENT_TIMEFRAMES entries: {bad_htf}. "
                f"Supported: {sorted(SUPPORTED_TIMEFRAMES)} plus all, alltime."
            )

    if settings.strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{settings.strategy}'. Supported: {list(STRATEGIES)}")

    if settings.telegram_bot_token and not (settings.telegram_admin_user_id or "").strip():
        logger.warning(
            "TELEGRAM_BOT_TOKEN is set but TELEGRAM_ADMIN_USER_ID is empty — "
            "/status, /signals, and other admin commands will not run until "
            "TELEGRAM_ADMIN_USER_ID (or TELEGRAM_USER_ID) is set to your numeric user id."
        )
