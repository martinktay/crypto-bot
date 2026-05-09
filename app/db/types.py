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
    """A database-agnostic vector type.

    Uses ``pgvector.sqlalchemy.Vector`` on PostgreSQL and JSON on every other
    dialect (so SQLite-backed tests can still create the schema). The
    custom ``Comparator`` exposes pgvector's three distance operators
    (``<->`` L2, ``<=>`` cosine, ``<#>`` max inner product) directly on
    the ORM column — without it, ``embedding.l2_distance(query_vec)`` raises
    ``AttributeError`` because ``TypeDecorator`` doesn't proxy through to
    the dialect impl's comparator.
    """

    impl = JSON
    cache_ok = True

    class Comparator(TypeDecorator.Comparator):
        """Wires pgvector distance operators onto the typed column.

        Each method returns a SQL expression that pgvector will evaluate
        on Postgres; on other dialects the ``op()`` call still produces a
        valid expression so the schema test path doesn't blow up — but
        ``search_similar_insights`` already takes a different code path
        outside Postgres, so these operators are only reached on PG.
        """

        def l2_distance(self, other):
            return self.op("<->")(other)

        def cosine_distance(self, other):
            return self.op("<=>")(other)

        def max_inner_product(self, other):
            return self.op("<#>")(other)

    comparator_factory = Comparator

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
