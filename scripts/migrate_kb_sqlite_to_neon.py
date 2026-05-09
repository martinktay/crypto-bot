"""One-shot migration: copy knowledge_documents + knowledge_embeddings from a
local SQLite snapshot into the active database (Neon Postgres in production).

Why this script exists
----------------------
The bot's RAG layer (``Retriever`` → ``StateRepository.search_similar_insights``)
queries whatever ``DATABASE_URL`` resolves to. When the project moved from
``debug_json.sqlite`` to Neon, the ingested book + transcript chunks were left
behind in SQLite, so the AI explanation for every signal lost its retrieval
context. This script bridges that gap.

What it does
------------
* Reads every row from ``knowledge_documents`` and ``knowledge_embeddings`` in
  the source SQLite file.
* Skips any chunk whose ``title`` already exists in the destination so the
  script is idempotent — re-running it never duplicates rows.
* Inserts each ``KnowledgeDocument`` + ``KnowledgeEmbedding`` pair via
  SQLAlchemy ORM so pgvector receives a real ``Vector(1536)`` value (lists
  are auto-cast by ``pgvector.sqlalchemy.Vector``).

Why we *copy* embeddings instead of re-computing
------------------------------------------------
The stored vectors were already produced by the same OpenAI model
(``text-embedding-3-small``, 1536 dim) that the bot uses today. Re-embedding
would be a no-op semantically and would also require a working OpenAI quota.
Copying preserves byte-for-byte similarity behaviour.

Usage::

    # Default: source = ./debug_json.sqlite, destination = $DATABASE_URL
    python scripts/migrate_kb_sqlite_to_neon.py

    # Override paths (e.g. dry run against a staging URL)
    python scripts/migrate_kb_sqlite_to_neon.py \\
        --source-db sqlite:///./debug_json.sqlite \\
        --dry-run

Exit code is 0 on success, 2 on argument errors, 3 on source-DB problems.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("migrate_kb")


def _coerce_vector(raw) -> list[float]:
    """Vector column on SQLite stores either JSON-text or a Python list."""
    if isinstance(raw, str):
        return json.loads(raw)
    return list(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-db",
        default="sqlite:///./debug_json.sqlite",
        help="SQLAlchemy URL for the source SQLite DB (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and report counts without writing to the destination DB.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on the number of documents to migrate (debugging).",
    )
    args = parser.parse_args()

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    src_engine = create_engine(args.source_db)
    try:
        with src_engine.connect() as conn:
            doc_count = conn.execute(
                text("SELECT COUNT(*) FROM knowledge_documents")
            ).scalar() or 0
            emb_count = conn.execute(
                text("SELECT COUNT(*) FROM knowledge_embeddings")
            ).scalar() or 0
    except Exception as exc:
        logger.error("Failed to read source DB %s: %s", args.source_db, exc)
        return 3
    logger.info(
        "Source %s — %d knowledge_documents, %d knowledge_embeddings",
        args.source_db,
        doc_count,
        emb_count,
    )

    if doc_count == 0:
        logger.info("Nothing to migrate.")
        return 0

    from app.db.session import SessionLocal, engine as dest_engine
    from app.models.entities import KnowledgeDocument, KnowledgeEmbedding

    logger.info("Destination dialect: %s", dest_engine.dialect.name)

    with src_engine.connect() as src:
        rows = src.execute(
            text(
                """
                SELECT d.id, d.source_type, d.title, d.content,
                       d.metadata_json, d.created_at, e.embedding
                  FROM knowledge_documents AS d
             LEFT JOIN knowledge_embeddings AS e
                    ON e.document_id = d.id
              ORDER BY d.id
                """
            )
        ).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    inserted = 0
    skipped_existing = 0
    skipped_no_embedding = 0
    failed = 0

    db: Session = SessionLocal()
    try:
        # Pre-load existing titles to avoid one round-trip per row on large KBs.
        existing_titles: set[str] = {
            t for (t,) in db.query(KnowledgeDocument.title).all()
        }
        logger.info("Destination already has %d documents", len(existing_titles))

        for src_id, source_type, title, content, metadata_json, created_at, embedding in rows:
            if title in existing_titles:
                skipped_existing += 1
                continue

            if embedding is None:
                skipped_no_embedding += 1
                logger.warning(
                    "Source doc id=%s title=%r has no embedding — skipping",
                    src_id,
                    title,
                )
                continue

            try:
                vector = _coerce_vector(embedding)
            except Exception as exc:
                failed += 1
                logger.warning(
                    "Source doc id=%s title=%r — bad embedding payload: %s",
                    src_id,
                    title,
                    exc,
                )
                continue

            metadata = metadata_json
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata) if metadata else {}
                except json.JSONDecodeError:
                    metadata = {}

            if args.dry_run:
                inserted += 1
                continue

            try:
                doc = KnowledgeDocument(
                    source_type=source_type,
                    title=title,
                    content=content,
                    metadata_json=metadata or {},
                    created_at=created_at,
                )
                db.add(doc)
                db.flush()  # populate doc.id for the FK below

                emb = KnowledgeEmbedding(document_id=doc.id, embedding=vector)
                db.add(emb)
                db.commit()
                existing_titles.add(title)
                inserted += 1

                if inserted % 20 == 0:
                    logger.info(" migrated %d/%d documents", inserted, len(rows))
            except Exception as exc:
                db.rollback()
                failed += 1
                logger.warning(
                    "Insert failed for src id=%s title=%r: %s: %s",
                    src_id,
                    title,
                    exc.__class__.__name__,
                    exc,
                )
    finally:
        db.close()

    logger.info(
        "Done. inserted=%d skipped_existing=%d skipped_no_embedding=%d failed=%d (dry_run=%s)",
        inserted,
        skipped_existing,
        skipped_no_embedding,
        failed,
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
