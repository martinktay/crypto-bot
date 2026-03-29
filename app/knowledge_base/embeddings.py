from collections.abc import Sequence


class EmbeddingProvider:
    """Light adapter; replace with OpenAI embedding client in production."""

    def embed(self, text: str) -> list[float]:
        # deterministic pseudo-embedding for local MVP
        values = [float((ord(ch) % 31) / 31) for ch in text[:64]]
        if len(values) < 64:
            values += [0.0] * (64 - len(values))
        return values

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]
