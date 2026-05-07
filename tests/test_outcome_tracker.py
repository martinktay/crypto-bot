"""Unit tests for outcome replay / dual-hit resolution."""

from app.core.enums import SignalDirection
from app.services.outcome_tracker import _dual_hit_resolution, _walk_candles


def test_dual_hit_long_sl_first_when_stop_closer_to_open() -> None:
    assert (
        _dual_hit_resolution(SignalDirection.LONG, open_=100.0, stop=98.0, take=109.0)
        == "sl"
    )


def test_dual_hit_long_tp_first_when_tp_closer_to_open() -> None:
    assert (
        _dual_hit_resolution(SignalDirection.LONG, open_=103.0, stop=98.0, take=104.0)
        == "tp"
    )


def test_dual_hit_short_stop_closer_from_open() -> None:
    assert (
        _dual_hit_resolution(SignalDirection.SHORT, open_=102.0, stop=106.0, take=96.0)
        == "sl"
    )


def test_dual_hit_short_take_closer_from_open() -> None:
    assert (
        _dual_hit_resolution(SignalDirection.SHORT, open_=95.0, stop=106.0, take=94.0)
        == "tp"
    )


def test_walk_tp_before_sl_dual_bar_long() -> None:
    # LONG entry 101, SL 98, TP 104. One bar near TP from open triggers TP-first.
    entry, stop, take = 101.0, 98.0, 104.0
    candles = [
        [
            1,
            103.0,
            106.0,
            96.5,
            103.8,
            1.0,
        ],
    ]
    status, pnl, _ae = _walk_candles(
        SignalDirection.LONG,
        entry=entry,
        stop=stop,
        take=take,
        candles=candles,
    )
    assert status == "tp_hit"
    assert pnl > 0


def test_walk_sl_dual_bar_long() -> None:
    entry, stop, take = 101.0, 98.0, 109.0
    candles = [
        [
            1,
            100.0,
            109.5,
            96.8,
            97.5,
            1.0,
        ],
    ]
    status, pnl, _ae = _walk_candles(
        SignalDirection.LONG,
        entry=entry,
        stop=stop,
        take=take,
        candles=candles,
    )
    assert status == "sl_hit"
