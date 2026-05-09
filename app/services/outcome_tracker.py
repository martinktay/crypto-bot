"""Outcome tracker.

Periodically walks broadcast signals whose outcome is still ``pending`` and
resolves them by replaying subsequent OHLCV against the signal's stop-loss /
take-profit. Realized PnL and max-adverse excursion are persisted on the
``signals`` row so the dashboard KPIs are grounded in *actual* price paths.

Per **closed** bar after the signal timestamp:

- ``LONG`` : SL when ``low <= stop``; TP when ``high >= take_profit``
- ``SHORT``: SL when ``high >= stop``; TP when ``low <= take_profit``

When **both** SL and TP are crossed inside the same candle and tick data is
unavailable, resolution uses an **open-distance heuristic**: whichever level
is nearer to the bar's **open** is assumed to have been tagged first. Equal
distance falls back to SL (pessimistic tie-break). This is less biased than
always choosing SL or always choosing TP.

If neither side is crossed before ``max_age_hours`` (and the fetch window
ends), status is ``expired`` with MTM PnL at the last close.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Literal

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import SignalDirection
from app.db.repository import StateRepository
from app.market_data.provider import MarketDataProvider
from app.models.entities import Signal

logger = logging.getLogger(__name__)


class OutcomeTracker:
    """Resolves pending signal outcomes against live OHLCV history."""

    def __init__(self, market_data: MarketDataProvider | None = None) -> None:
        self.market_data = market_data or MarketDataProvider()

    def run(self, db: Session) -> dict[str, int]:
        repo = StateRepository(db)
        max_age = settings.outcome_tracker_max_age_hours
        signals = repo.list_open_broadcast_signals(max_age_hours=max_age)

        counters = {"resolved": 0, "expired": 0, "skipped": 0, "errors": 0}

        for sig in signals:
            try:
                resolution = self._resolve_signal(sig, max_age_hours=max_age)
            except Exception as exc:
                counters["errors"] += 1
                logger.warning(
                    "Outcome tracker failed for signal %s (%s %s): %s",
                    sig.id,
                    sig.symbol,
                    sig.timeframe,
                    exc.__class__.__name__,
                )
                continue

            if resolution is None:
                counters["skipped"] += 1
                continue

            status, pnl_pct, max_dd_pct = resolution
            repo.record_signal_outcome(
                signal_id=sig.id,
                outcome_status=status,
                pnl_percent=pnl_pct,
                max_drawdown_percent=max_dd_pct,
            )
            counters["resolved"] += 1
            if status == "expired":
                counters["expired"] += 1

        if counters["resolved"] or counters["errors"]:
            logger.info("Outcome tracker pass: %s", counters)
        return counters

    def _resolve_signal(
        self, sig: Signal, max_age_hours: int
    ) -> tuple[str, float, float] | None:
        signal_ts_utc = sig.timestamp.replace(tzinfo=timezone.utc)
        since_ms = int(signal_ts_utc.timestamp() * 1000)

        # Re-fetch from the *same* exchange the signal originated on, so a
        # signal generated against bybit candles isn't being resolved
        # against binance candles. Fall back to the default exchange when
        # an old row didn't have exchange_id stored.
        qualified = (
            f"{sig.exchange_id}:{sig.symbol}" if sig.exchange_id else sig.symbol
        )
        candles = self.market_data.fetch_ohlcv(
            qualified, sig.timeframe, limit=500, since=since_ms
        )
        if len(candles) > 1:
            candles = candles[:-1]

        candles = [c for c in candles if c[0] > since_ms]
        if not candles:
            age_hours = (
                datetime.now(timezone.utc) - signal_ts_utc
            ).total_seconds() / 3600.0
            if age_hours >= max_age_hours:
                return ("expired", 0.0, 0.0)
            return None

        return _walk_candles(
            sig.signal,
            entry=sig.entry_price,
            stop=sig.stop_loss,
            take=sig.take_profit,
            candles=candles,
        )


def _dual_hit_resolution(
    direction: SignalDirection, open_: float, stop: float, take: float
) -> Literal["sl", "tp"]:
    """When SL and TP are both inside range of the same bar, pick ordering."""
    if direction == SignalDirection.LONG:
        d_sl = abs(open_ - stop)
        d_tp = abs(take - open_)
        if d_sl < d_tp:
            return "sl"
        if d_tp < d_sl:
            return "tp"
        return "sl"
    d_sl = abs(stop - open_)
    d_tp = abs(open_ - take)
    if d_sl < d_tp:
        return "sl"
    if d_tp < d_sl:
        return "tp"
    return "sl"


def _walk_candles(
    direction: SignalDirection,
    *,
    entry: float,
    stop: float,
    take: float,
    candles: Iterable[list[float]],
) -> tuple[str, float, float]:
    if entry in (None, 0):
        return ("expired", 0.0, 0.0)

    long_side = direction == SignalDirection.LONG
    max_adverse_excursion = 0.0
    last_close = entry

    for _ts, open_, high, low, close, _v in candles:
        last_close = close

        if long_side:
            adverse = (entry - low) / entry * 100.0
        else:
            adverse = (high - entry) / entry * 100.0
        if adverse > max_adverse_excursion:
            max_adverse_excursion = adverse

        sl_hit = low <= stop if long_side else high >= stop
        tp_hit = high >= take if long_side else low <= take

        if sl_hit and tp_hit:
            first = _dual_hit_resolution(direction, open_, stop, take)
            if first == "sl":
                pnl = ((stop - entry) / entry * 100.0) if long_side else (
                    (entry - stop) / entry * 100.0
                )
                return ("sl_hit", pnl, max_adverse_excursion)
            pnl = ((take - entry) / entry * 100.0) if long_side else (
                (entry - take) / entry * 100.0
            )
            return ("tp_hit", pnl, max_adverse_excursion)
        if sl_hit:
            pnl = ((stop - entry) / entry * 100.0) if long_side else (
                (entry - stop) / entry * 100.0
            )
            return ("sl_hit", pnl, max_adverse_excursion)
        if tp_hit:
            pnl = ((take - entry) / entry * 100.0) if long_side else (
                (entry - take) / entry * 100.0
            )
            return ("tp_hit", pnl, max_adverse_excursion)

    running_pnl = (
        (last_close - entry) / entry * 100.0
        if long_side
        else (entry - last_close) / entry * 100.0
    )
    return ("expired", running_pnl, max_adverse_excursion)
