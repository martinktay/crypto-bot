from sqlalchemy import JSON, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect

try:
    from pgvector.sqlalchemy import Vector
    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False
    Vector = None


class VectorType(TypeDecorator):
    """
    A database-agnostic vector type.
    Uses pgvector.sqlalchemy.Vector on PostgreSQL and JSON on others.
    """
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql" and HAS_PGVECTOR:
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(JSON)

    def process_bind_param(self, value, dialect: Dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return value # JSON serializes list automatically

    def process_result_value(self, value, dialect: Dialect):
        if value is None:
            return None
        return value
