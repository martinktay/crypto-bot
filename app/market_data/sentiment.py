"""Lightweight news / sentiment feature for trading signals.

Default backend is CryptoPanic's public posts endpoint (free tier) — it
requires a free ``auth_token`` from cryptopanic.com but no paid plan. Set
``CRYPTOPANIC_AUTH_TOKEN`` to enable; otherwise the provider returns a
neutral score and the strategy effectively ignores sentiment.

The feature is intentionally tiny:

* ``SentimentProvider.score(symbol)`` returns ``(score, n_posts)`` where
  ``score`` is in ``[-1.0, +1.0]``. Positive means bullish-leaning headlines.
* A small TTL cache (default 10 minutes) keeps API calls bounded.
* All errors are swallowed and logged at WARNING — sentiment is a tie-breaker,
  never a hard gate.

This is a *signal*, not a strategy. A separate sentiment-aware strategy or
a confidence-tweak in existing strategies decides what to do with it.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from threading import Lock

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


_BULLISH_VOTE_KEYS = ("positive",)
_BEARISH_VOTE_KEYS = ("negative", "toxic", "saved")
_BULLISH_KIND = {"good"}
_BEARISH_KIND = {"bad"}


class SentimentProvider:
    """Pluggable sentiment provider with TTL cache. Default backend: CryptoPanic."""

    def __init__(
        self,
        ttl_seconds: int | None = None,
        cache_size: int = 256,
    ) -> None:
        self.ttl_seconds = (
            ttl_seconds
            if ttl_seconds is not None
            else settings.sentiment_cache_ttl_seconds
        )
        self.cache_size = cache_size
        self._cache: "OrderedDict[str, tuple[float, float, int]]" = OrderedDict()
        self._lock = Lock()

    @property
    def enabled(self) -> bool:
        return bool(settings.sentiment_enabled and settings.cryptopanic_auth_token)

    def score(self, symbol: str) -> tuple[float, int]:
        """Return ``(score, n_posts)`` for the base asset of ``symbol``.

        ``score`` is in ``[-1, +1]``. ``(0.0, 0)`` is the neutral default
        when sentiment is disabled or the call fails.
        """
        if not self.enabled:
            return (0.0, 0)

        base = _base_asset(symbol)
        if not base:
            return (0.0, 0)

        cached = self._cache_get(base)
        if cached is not None:
            return cached

        result = self._fetch_cryptopanic(base)
        self._cache_put(base, result)
        return result

    def _fetch_cryptopanic(self, base_asset: str) -> tuple[float, int]:
        token = settings.cryptopanic_auth_token
        url = "https://cryptopanic.com/api/v1/posts/"
        params = {
            "auth_token": token,
            "currencies": base_asset,
            "kind": "news",
            "public": "true",
        }
        try:
            resp = httpx.get(url, params=params, timeout=settings.sentiment_request_timeout)
        except Exception as exc:
            logger.warning(
                "Sentiment fetch failed for %s: %s",
                base_asset,
                exc.__class__.__name__,
            )
            return (0.0, 0)

        if resp.status_code != 200:
            logger.warning(
                "Sentiment HTTP %d for %s",
                resp.status_code,
                base_asset,
            )
            return (0.0, 0)

        try:
            posts = resp.json().get("results", [])
        except Exception as exc:
            logger.warning("Sentiment parse failed: %s", exc.__class__.__name__)
            return (0.0, 0)

        return _aggregate_cryptopanic_posts(posts)

    def _cache_get(self, key: str) -> tuple[float, int] | None:
        now = time.time()
        with self._lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            ts, score, n = entry
            if now - ts > self.ttl_seconds:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            return (score, n)

    def _cache_put(self, key: str, value: tuple[float, int]) -> None:
        score, n = value
        with self._lock:
            self._cache[key] = (time.time(), score, n)
            self._cache.move_to_end(key)
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)


def _aggregate_cryptopanic_posts(posts: list[dict]) -> tuple[float, int]:
    """Combine CryptoPanic vote/kind metadata into a single net score."""
    if not posts:
        return (0.0, 0)

    pos_votes = 0
    neg_votes = 0
    pos_kind = 0
    neg_kind = 0
    n = 0

    for post in posts:
        n += 1
        votes = post.get("votes") or {}
        for k in _BULLISH_VOTE_KEYS:
            pos_votes += int(votes.get(k) or 0)
        for k in _BEARISH_VOTE_KEYS:
            neg_votes += int(votes.get(k) or 0)
        kind = (post.get("kind") or "").lower()
        if kind in _BULLISH_KIND:
            pos_kind += 1
        elif kind in _BEARISH_KIND:
            neg_kind += 1

    total_votes = pos_votes + neg_votes
    total_kind = pos_kind + neg_kind

    score_votes = (pos_votes - neg_votes) / total_votes if total_votes else 0.0
    score_kind = (pos_kind - neg_kind) / total_kind if total_kind else 0.0

    if total_votes and total_kind:
        score = 0.5 * score_votes + 0.5 * score_kind
    elif total_votes:
        score = score_votes
    else:
        score = score_kind

    score = max(-1.0, min(1.0, score))
    return (score, n)


def _base_asset(symbol: str) -> str:
    """Derive the base asset code from a CCXT-style symbol like ``BTC/USDT:USDT``."""
    if not symbol:
        return ""
    head = symbol.split(":", 1)[0]
    base = head.split("/", 1)[0]
    return base.strip().upper()


_provider_singleton: SentimentProvider | None = None


def get_sentiment_provider() -> SentimentProvider:
    global _provider_singleton
    if _provider_singleton is None:
        _provider_singleton = SentimentProvider()
    return _provider_singleton
