"""Classic candlestick pattern checks (OHLC) for strategy gates.

Uses standard technical definitions aligned with widely taught references
(e.g. Nison/Candlestick Bible style terminology). These are *deterministic*
rules — the RAG layer still supplies book context for AI explanations only.
"""

from __future__ import annotations

import pandas as pd

from app.core.config import settings


def _ohlc(row: pd.Series) -> tuple[float, float, float, float]:
    return (
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
    )


def _body(o: float, c: float) -> float:
    return abs(c - o)


def _rng(h: float, l: float) -> float:
    return max(h - l, 1e-12)


def _bullish(o: float, c: float) -> bool:
    return c > o


def _bearish(o: float, c: float) -> bool:
    return c < o


def _bullish_engulfing(o1: float, c1: float, o2: float, c2: float) -> bool:
    """Bar 1 = prev, bar 2 = last; bullish engulfing on bar 2."""
    return _bearish(o1, c1) and _bullish(o2, c2) and o2 < c1 and c2 > o1


def _bearish_engulfing(o1: float, c1: float, o2: float, c2: float) -> bool:
    return _bullish(o1, c1) and _bearish(o2, c2) and o2 > c1 and c2 < o1


def _hammer(o: float, h: float, l: float, c: float) -> bool:
    body = _body(o, c)
    rng = _rng(h, l)
    if rng < body * 3:
        return False
    lower = min(o, c) - l
    upper = h - max(o, c)
    return lower >= 2 * max(body, 1e-9) and upper <= max(body, 1e-9) * 1.5


def _shooting_star(o: float, h: float, l: float, c: float) -> bool:
    body = _body(o, c)
    rng = _rng(h, l)
    if body > 0.35 * rng:
        return False
    upper = h - max(o, c)
    lower = min(o, c) - l
    return upper >= 2 * max(body, 1e-9) and lower <= max(body, 1e-9) * 1.5


def _dark_cloud_cover(
    o0: float, h0: float, l0: float, c0: float, o1: float, h1: float, l1: float, c1: float
) -> bool:
    if not (_bullish(o0, c0) and _bearish(o1, c1)):
        return False
    mid = (o0 + c0) / 2
    return o1 >= h0 and c1 < mid and c1 > o0


def _piercing_line(
    o0: float, h0: float, l0: float, c0: float, o1: float, h1: float, l1: float, c1: float
) -> bool:
    if not (_bearish(o0, c0) and _bullish(o1, c1)):
        return False
    mid = (o0 + c0) / 2
    return o1 <= l0 and c1 > mid and c1 < o0


def _evening_star(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
    o3: float, h3: float, l3: float, c3: float,
) -> bool:
    """Three-bar bearish reversal: strong bull, small star, bearish close past mid of day 1."""
    if not (_bullish(o1, c1) and _bearish(o3, c3)):
        return False
    b1 = _body(o1, c1)
    b2 = _body(o2, c2)
    if b1 < _rng(h1, l1) * 0.25:
        return False
    if b2 > b1 * 0.6:
        return False
    return c3 < (o1 + c1) / 2


def _morning_star(
    o1: float, h1: float, l1: float, c1: float,
    o2: float, h2: float, l2: float, c2: float,
    o3: float, h3: float, l3: float, c3: float,
) -> bool:
    if not (_bearish(o1, c1) and _bullish(o3, c3)):
        return False
    b1 = _body(o1, c1)
    b2 = _body(o2, c2)
    if b1 < _rng(h1, l1) * 0.25:
        return False
    if b2 > b1 * 0.6:
        return False
    return c3 > (o1 + c1) / 2


def _uptrend_recent(df: pd.DataFrame, n: int = 3) -> bool:
    if len(df) < n:
        return False
    closes = df["close"].iloc[-n:].astype(float)
    return bool(closes.iloc[-1] > closes.iloc[0])


def _downtrend_recent(df: pd.DataFrame, n: int = 3) -> bool:
    if len(df) < n:
        return False
    closes = df["close"].iloc[-n:].astype(float)
    return bool(closes.iloc[-1] < closes.iloc[0])


def describe_active_patterns(df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return (bearish_labels, bullish_labels) matched on the last 1–3 closed bars."""
    bearish: list[str] = []
    bullish: list[str] = []
    n = len(df)
    if n < 2:
        return bearish, bullish

    o0, h0, l0, c0 = _ohlc(df.iloc[-2])
    o1, h1, l1, c1 = _ohlc(df.iloc[-1])

    if _bearish_engulfing(o0, c0, o1, c1):
        bearish.append("bearish engulfing")
    if _bullish_engulfing(o0, c0, o1, c1):
        bullish.append("bullish engulfing")
    if _dark_cloud_cover(o0, h0, l0, c0, o1, h1, l1, c1):
        bearish.append("dark cloud cover")
    if _piercing_line(o0, h0, l0, c0, o1, h1, l1, c1):
        bullish.append("piercing line")

    if _shooting_star(o1, h1, l1, c1) and _uptrend_recent(df, 4):
        bearish.append("shooting star")
    if _hammer(o1, h1, l1, c1) and _downtrend_recent(df, 4):
        bullish.append("hammer")

    if _hammer(o1, h1, l1, c1) and _uptrend_recent(df, 4):
        bearish.append("hanging man")

    if n >= 3:
        oa, ha, la, ca = _ohlc(df.iloc[-3])
        ob, hb, lb, cb = _ohlc(df.iloc[-2])
        oc, hc, lc, cc = _ohlc(df.iloc[-1])
        if _evening_star(oa, ha, la, ca, ob, hb, lb, cb, oc, hc, lc, cc):
            bearish.append("evening star")
        if _morning_star(oa, ha, la, ca, ob, hb, lb, cb, oc, hc, lc, cc):
            bullish.append("morning star")

    return bearish, bullish


def veto_long(df: pd.DataFrame) -> tuple[bool, str]:
    """True when a bearish reversal pattern argues against a new long."""
    bearish, _ = describe_active_patterns(df)
    if not bearish:
        return False, ""
    return True, "; ".join(dict.fromkeys(bearish))


def veto_short(df: pd.DataFrame) -> tuple[bool, str]:
    """True when a bullish reversal pattern argues against a new short."""
    _, bullish = describe_active_patterns(df)
    if not bullish:
        return False, ""
    return True, "; ".join(dict.fromkeys(bullish))


def supporting_summary(df: pd.DataFrame, direction: str) -> str:
    """Short tag for aligned patterns (LONG -> bullish, SHORT -> bearish)."""
    bearish, bullish = describe_active_patterns(df)
    if direction == "LONG" and bullish:
        return "candles: " + ", ".join(dict.fromkeys(bullish))
    if direction == "SHORT" and bearish:
        return "candles: " + ", ".join(dict.fromkeys(bearish))
    return ""


def require_confirmation(direction: str, df: pd.DataFrame) -> tuple[bool, str]:
    """Strict mode: need at least one same-direction classic pattern."""
    bearish, bullish = describe_active_patterns(df)
    if direction == "LONG":
        if bullish:
            return True, ", ".join(dict.fromkeys(bullish))
        return False, "no bullish candlestick confirmation"
    if direction == "SHORT":
        if bearish:
            return True, ", ".join(dict.fromkeys(bearish))
        return False, "no bearish candlestick confirmation"
    return True, ""


def gate_for_direction(df: pd.DataFrame, direction: str) -> tuple[bool, str, str]:
    """Pattern layer for strategies: ``(blocked, block_reason, reason_suffix)``.

    When not blocked, ``reason_suffix`` may cite supportive patterns for logging.
    """
    if not settings.candlestick_patterns_enabled:
        return False, "", ""
    if direction == "LONG":
        veto, why = veto_long(df)
        if veto:
            return True, why, ""
        if settings.candlestick_patterns_strict:
            ok, msg = require_confirmation("LONG", df)
            if not ok:
                return True, msg, ""
        return False, "", supporting_summary(df, "LONG")
    if direction == "SHORT":
        veto, why = veto_short(df)
        if veto:
            return True, why, ""
        if settings.candlestick_patterns_strict:
            ok, msg = require_confirmation("SHORT", df)
            if not ok:
                return True, msg, ""
        return False, "", supporting_summary(df, "SHORT")
    return False, "", ""
