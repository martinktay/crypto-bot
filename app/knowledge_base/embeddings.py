"""Embedding provider — OpenAI API with a hashed-bigram local fallback.

The previous local fallback embedded each character into ``ord(c) % 31 / 31``,
which produced near-identical vectors for any English text and made the
local RAG path effectively useless. The fallback below uses signed
feature-hashing over unigrams + bigrams which produces stable, content-aware
embeddings that respond to cosine/L2 similarity.

Set ``OPENAI_API_KEY`` in production for the real embedding model — the
fallback is only intended for offline / CI / local development.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import threading
from collections import OrderedDict
from collections.abc import Sequence

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


class EmbeddingProvider:
    """Embeddings adapter. Uses OpenAI when API key is set, else hashed bag-of-bigrams.

    A small thread-safe LRU cache keyed by SHA-256(model + text) avoids re-embedding
    the same chunk twice — relevant for the RAG path which re-queries the same
    signal context across cycles, and for batch ingestion of book chapters.
    """

    def __init__(self, dimension: int = 1536, cache_size: int | None = None):
        self.dimension = dimension
        self._warned_about_fallback = False
        self._cache_size = cache_size if cache_size is not None else settings.embedding_cache_size
        self._cache: "OrderedDict[str, list[float]]" = OrderedDict()
        self._cache_lock = threading.Lock()
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def mode(self) -> str:
        return "openai" if settings.openai_api_key else "local_hashed"

    @property
    def cache_stats(self) -> dict[str, int]:
        with self._cache_lock:
            return {
                "hits": self._cache_hits,
                "misses": self._cache_misses,
                "size": len(self._cache),
                "max_size": self._cache_size,
            }

    def embed(self, text: str) -> list[float]:
        if not text:
            return self._sanitize_vector([])

        cache_key = self._cache_key(text)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if settings.openai_api_key:
            vec = self._openai_embed(text)
        else:
            if not self._warned_about_fallback:
                logger.warning(
                    "OPENAI_API_KEY not set — using local hashed-bigram embedding "
                    "fallback. Similarity quality will be limited."
                )
                self._warned_about_fallback = True
            vec = self._hashed_embed(text)

        vec = self._sanitize_vector(vec)
        self._cache_put(cache_key, vec)
        return vec

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]

    def _cache_key(self, text: str) -> str:
        h = hashlib.sha256()
        h.update(self.mode.encode("utf-8"))
        h.update(b"\x00")
        h.update(settings.embedding_model.encode("utf-8"))
        h.update(b"\x00")
        h.update(text.encode("utf-8", errors="ignore"))
        return h.hexdigest()

    def _cache_get(self, key: str) -> list[float] | None:
        if self._cache_size <= 0:
            return None
        with self._cache_lock:
            vec = self._cache.get(key)
            if vec is None:
                self._cache_misses += 1
                return None
            self._cache.move_to_end(key)
            self._cache_hits += 1
            return list(vec)

    def _cache_put(self, key: str, vec: list[float]) -> None:
        if self._cache_size <= 0:
            return
        with self._cache_lock:
            self._cache[key] = list(vec)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)

    def _openai_embed(self, text: str) -> list[float]:
        """Call OpenAI embedding API."""
        try:
            import httpx

            resp = httpx.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embedding_model, "input": text[:8000]},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()["data"][0]["embedding"]
            logger.warning("OpenAI embedding failed: %d", resp.status_code)
        except Exception as exc:
            logger.error("OpenAI embedding error: %s", exc.__class__.__name__)
        return self._hashed_embed(text)

    def _hashed_embed(self, text: str) -> list[float]:
        """Signed feature hashing over unigrams + bigrams.

        For each token (and each adjacent pair of tokens) we derive a stable
        bucket and sign from SHA-256 and accumulate into the embedding.
        Final vector is L2-normalized so cosine similarity behaves sensibly.
        """
        vec = [0.0] * self.dimension
        if not text:
            return vec

        tokens = _TOKEN_RE.findall(text.lower())
        if not tokens:
            return vec

        for tok in tokens:
            self._add_feature(vec, tok)
        for a, b in zip(tokens, tokens[1:]):
            self._add_feature(vec, f"{a}_{b}")

        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec

    def _add_feature(self, vec: list[float], feature: str) -> None:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % self.dimension
        sign = 1.0 if (digest[4] & 1) == 0 else -1.0
        vec[bucket] += sign

    def _sanitize_vector(self, vec: list[float]) -> list[float]:
        """Ensure the vector matches self.dimension by trimming or padding."""
        if len(vec) > self.dimension:
            return vec[: self.dimension]
        if len(vec) < self.dimension:
            return vec + [0.0] * (self.dimension - len(vec))
        return vec
