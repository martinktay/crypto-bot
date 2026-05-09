"""Push SYMBOLS / TIMEFRAMES / STRATEGY from .env into bot_settings.

``BotSetting.symbols`` is a JSON column seeded from ``settings.symbol_list``
the first time :meth:`StateRepository.get_or_create_settings` runs, after
which the in-DB value is the source of truth (so admin updates via the API
aren't clobbered on every restart). When the operator edits ``.env`` to add
new pairs or exchanges, this script forces the DB row back in sync.

Usage::

    python scripts/resync_symbols.py            # dry-run (prints what would change)
    python scripts/resync_symbols.py --apply    # writes the new values
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any

from app.core.config import settings
from app.db.session import SessionLocal
from app.db.repository import StateRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("resync_symbols")


def _diff(label: str, current: Any, target: Any) -> bool:
    if current != target:
        logger.info(
            "%s changed:\n  current: %s\n  target : %s",
            label,
            json.dumps(current),
            json.dumps(target),
        )
        return True
    logger.info("%s already in sync (%s)", label, json.dumps(current))
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes (default is dry-run).",
    )
    args = parser.parse_args()

    target_symbols = settings.symbol_list
    target_timeframes = settings.timeframe_list
    target_strategy = settings.strategy

    with SessionLocal() as db:
        repo = StateRepository(db)
        setting = repo.get_or_create_settings()

        logger.info(
            "Resyncing bot_settings(id=%s) from .env (default exchange=%s, registry=%s)",
            setting.id,
            settings.exchange_name,
            settings.exchange_list,
        )

        changed = False
        changed |= _diff("SYMBOLS", list(setting.symbols), target_symbols)
        changed |= _diff("TIMEFRAMES", list(setting.timeframes), target_timeframes)
        changed |= _diff("STRATEGY", setting.strategy, target_strategy)

        if not changed:
            logger.info("Nothing to do.")
            return 0

        if not args.apply:
            logger.info("Dry-run: re-run with --apply to persist these changes.")
            return 0

        repo.update_symbols_timeframes_strategy(
            symbols=target_symbols,
            timeframes=target_timeframes,
            strategy=target_strategy,
        )
        logger.info("Applied. The next signal cycle will use the new universe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
