"""Shared OHLCV helpers (timestamps aligned with exchange ``ts`` column)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def candle_close_timestamp(row: pd.Series | None) -> datetime:
    """Convert the OHLCV ``ts`` column (ms epoch) to a tz-aware UTC datetime."""
    if row is None or "ts" not in row.index:
        return datetime.now(timezone.utc)
    ts = row["ts"]
    try:
        return datetime.fromtimestamp(int(ts) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)
