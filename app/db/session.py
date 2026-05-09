from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _normalise_db_url(url: str) -> str:
    """Pin Postgres URLs to the psycopg v3 driver.

    This project installs ``psycopg[binary]`` (v3), not ``psycopg2``. SQLAlchemy
    treats bare ``postgres://`` / ``postgresql://`` as an alias for psycopg2 and
    will raise ``ModuleNotFoundError: No module named 'psycopg2'``. Neon's
    connection-details copy button hands out exactly that prefix, so we rewrite
    it here once instead of asking every operator to remember the suffix.
    """
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


engine = create_engine(_normalise_db_url(settings.database_url), pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
