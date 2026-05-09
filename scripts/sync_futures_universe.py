"""Discover all USDT-margined linear perpetuals on Bybit / MEXC and sync DB + .env.

Uses :meth:`MarketDataProvider.usdt_linear_swap_symbols` (ccxt ``load_markets``).
Qualified entries look like ``bybit:BTC/USDT:USDT`` so they match ``SYMBOLS`` format.

The signal scheduler processes ``SCAN_SYMBOLS_BATCH_SIZE`` pairs per tick
(round-robin) so a full exchange listing does not stall one 5-minute job.

Usage::

    python scripts/sync_futures_universe.py              # dry-run counts + sample
    python scripts/sync_futures_universe.py --apply     # write bot_settings.symbols
    python scripts/sync_futures_universe.py --apply --patch-env .env

Re-running ``scripts/resync_symbols.py --apply`` afterwards will **overwrite**
``bot_settings`` from ``SYMBOLS=`` in ``.env`` — keep both in sync or only use
one workflow.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("sync_futures_universe")


def _patch_env_symbols(env_path: Path, symbols_csv: str) -> None:
    text = env_path.read_text(encoding="utf-8")
    if not re.search(r"(?m)^SYMBOLS=", text):
        raise ValueError(f"No SYMBOLS= line found in {env_path}")
    text_new, n = re.subn(
        r"(?m)^SYMBOLS=.*$",
        f"SYMBOLS={symbols_csv}",
        text,
        count=1,
    )
    if n != 1:
        raise ValueError("Failed to replace SYMBOLS= line")
    env_path.write_text(text_new, encoding="utf-8")
    logger.info("Updated SYMBOLS= in %s", env_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exchanges",
        default="bybit,mexc",
        help="Comma-separated ccxt ids (default: %(default)s)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist symbols into bot_settings via Neon/SQLAlchemy.",
    )
    parser.add_argument(
        "--patch-env",
        metavar="PATH",
        nargs="?",
        const=".env",
        default=None,
        help="Replace SYMBOLS= line in this .env file (default: .env if flag alone)",
    )
    args = parser.parse_args()

    ex_ids = [
        x.strip().lower()
        for x in (args.exchanges or "").split(",")
        if x.strip()
    ]
    if not ex_ids:
        logger.error("No exchanges given")
        return 2

    from app.market_data.provider import ExchangeUnavailable, MarketDataProvider

    try:
        md = MarketDataProvider(exchanges=ex_ids)
    except ExchangeUnavailable as exc:
        logger.error("MarketDataProvider init failed: %s", exc)
        return 3

    qualified: list[str] = []
    for ex in ex_ids:
        try:
            raw_syms = md.usdt_linear_swap_symbols(ex)
        except Exception as exc:
            logger.error("%s: discovery failed: %s: %s", ex, type(exc).__name__, exc)
            continue
        for sym in raw_syms:
            qualified.append(f"{ex}:{sym}")
        logger.info("%s: %d USDT linear perpetuals", ex, len(raw_syms))

    qualified.sort()
    if not qualified:
        logger.error("No symbols discovered — check EXCHANGES / network / WARP.")
        return 4

    csv_line = ",".join(qualified)
    logger.info("Total qualified entries: %d (sample: %s …)", len(qualified), qualified[:3])

    if args.patch_env is not None:
        env_path = Path(args.patch_env).resolve()
        if not env_path.is_file():
            logger.error("Env file not found: %s", env_path)
            return 5
        _patch_env_symbols(env_path, csv_line)

    if not args.apply:
        logger.info("Dry-run only. Re-run with --apply to write bot_settings.")
        return 0

    from app.db.repository import StateRepository
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        repo = StateRepository(db)
        repo.update_symbols_timeframes_strategy(symbols=qualified)
        logger.info("bot_settings.symbols updated (%d rows).", len(qualified))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
