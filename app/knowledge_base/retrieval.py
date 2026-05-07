from sqlalchemy.orm import Session
from app.db.repository import StateRepository
from app.knowledge_base.embeddings import EmbeddingProvider


class Retriever:
    def __init__(self, db: Session, embedder: EmbeddingProvider):
        self.repo = StateRepository(db)
        self.embedder = embedder

    def get_relevant_context(self, query: str, limit: int = 3) -> list[str]:
        """Fetch relevant knowledge documents using vector similarity search in DB."""
        query_vec = self.embedder.embed(query)
        return self.repo.search_similar_insights(query_vec, limit=limit)
