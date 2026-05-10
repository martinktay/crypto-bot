"""CCXT-style timeframe ordering for multi-timeframe alignment."""

from __future__ import annotations

ALLTIME_ALIASES = frozenset({"all", "alltime"})


def timeframe_to_minutes(tf: str) -> int | None:
    """Approximate bar length in minutes for ordering TFs.

    ``1M`` is one *month* (capital ``M``). ``1m`` / ``15m`` are minutes (lowercase ``m``).
    """
    s = (tf or "").strip()
    if not s:
        return None
    if len(s) >= 2 and s[-1] == "M" and _is_numeric_head(s[:-1]):
        return int(float(s[:-1])) * 43200
    last = s[-1].lower()
    head = s[:-1]
    if not _is_numeric_head(head):
        return None
    n = float(head)
    if last == "m":
        return int(n)
    if last == "h":
        return int(n * 60)
    if last == "d":
        return int(n * 1440)
    if last == "w":
        return int(n * 10080)
    return None


def _is_numeric_head(head: str) -> bool:
    if not head:
        return True
    try:
        float(head)
    except ValueError:
        return False
    return True


def is_alltime_token(token: str) -> bool:
    return token.strip().lower() in ALLTIME_ALIASES


def normalize_alignment_timeframe(token: str) -> str | None:
    """Map config tokens to a CCXT timeframe string."""
    t = token.strip()
    if not t:
        return None
    if is_alltime_token(t):
        return "1M"
    return t


def normalize_user_timeframe_token(token: str) -> str:
    """Normalize a single ``TIMEFRAMES`` entry from ``.env``.

    - Bare integers become minute bars (``15`` → ``15m``), or hours/days when
      they match common bar sizes (``60`` → ``1h``, ``240`` → ``4h``).
    - Friendly aliases: ``1day`` → ``1d``, ``1week`` → ``1w``, ``1month`` → ``1M``.
    - Preserves ``…M`` month notation (capital ``M``) for CCXT.
    """
    s = (token or "").strip()
    if not s:
        return s
    key = s.lower().replace(" ", "")
    word_aliases: dict[str, str] = {
        "1day": "1d",
        "1week": "1w",
        "1month": "1M",
        "1mo": "1M",
    }
    if key in word_aliases:
        return word_aliases[key]
    if len(s) >= 2 and s[-1] == "M" and _is_numeric_head(s[:-1]):
        return s
    if s.isdigit():
        n = int(s)
        # Minute count → standard higher-TF labels when unambiguous
        table = {
            60: "1h",
            120: "2h",
            180: "3h",
            240: "4h",
            360: "6h",
            480: "8h",
            720: "12h",
            1440: "1d",
            10080: "1w",
        }
        if n in table:
            return table[n]
        return f"{n}m"
    return s.lower()
