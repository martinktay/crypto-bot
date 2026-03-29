from app.knowledge_base.embeddings import EmbeddingProvider
from app.models.entities import KnowledgeDocument


class Retriever:
    def __init__(self, embedder: EmbeddingProvider):
        self.embedder = embedder

    def rank_by_similarity(self, query: str, docs: list[KnowledgeDocument], top_k: int = 3) -> list[KnowledgeDocument]:
        query_vec = self.embedder.embed(query)

        def score(doc: KnowledgeDocument) -> float:
            doc_vec = self.embedder.embed(doc.content)
            return sum(a * b for a, b in zip(query_vec, doc_vec, strict=False))

        return sorted(docs, key=score, reverse=True)[:top_k]
