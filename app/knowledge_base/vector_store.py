from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import KnowledgeDocument


class VectorStore:
    def __init__(self, db: Session):
        self.db = db

    def fetch_documents(self, limit: int = 25) -> list[KnowledgeDocument]:
        return list(self.db.execute(select(KnowledgeDocument).limit(limit)).scalars())
