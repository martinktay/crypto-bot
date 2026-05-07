"""Ingest a PDF document into the knowledge base.

Splits the PDF into overlapping text chunks, embeds each chunk with the
configured ``EmbeddingProvider`` (OpenAI when ``OPENAI_API_KEY`` is set,
otherwise the local hashed-bigram fallback), and inserts each chunk as its
own ``KnowledgeDocument`` via ``StateRepository.ingest_knowledge_document``.

Usage::

    python scripts/ingest_pdf.py path/to/file.pdf --title "The Candlestick Trading Bible" --source-type book

Re-running is safe: each invocation creates new ``KnowledgeDocument`` rows.
Use ``--dry-run`` to extract and chunk without touching the database.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_pdf")


def extract_pdf_text(pdf_path: Path) -> str:
    """Return the full text of ``pdf_path``. Prefers pdfplumber, falls back to pypdf."""
    try:
        import pdfplumber

        pages: list[str] = []
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                try:
                    txt = page.extract_text() or ""
                except Exception as exc:
                    logger.warning("pdfplumber page %d failed: %s", i, exc.__class__.__name__)
                    txt = ""
                pages.append(txt)
        return "\n\n".join(pages)
    except ImportError:
        pass

    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


_WS_RE = re.compile(r"[ \t]+")
_MULTIBLANK_RE = re.compile(r"\n{3,}")


def normalize_text(text: str) -> str:
    """Collapse whitespace and obvious de-hyphenation artifacts from PDF extraction."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"-\n(\w)", r"\1", text)
    text = _WS_RE.sub(" ", text)
    text = _MULTIBLANK_RE.sub("\n\n", text)
    return text.strip()


def chunk_text(
    text: str, *, chunk_chars: int = 2000, overlap_chars: int = 200
) -> list[str]:
    """Split ``text`` into overlapping chunks on paragraph boundaries.

    Each chunk targets ``chunk_chars`` characters with ``overlap_chars`` of
    trailing context carried into the next chunk so semantic search can match
    across paragraph splits.
    """
    if chunk_chars <= 0:
        raise ValueError("chunk_chars must be positive")
    if overlap_chars >= chunk_chars:
        raise ValueError("overlap_chars must be smaller than chunk_chars")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    buf: list[str] = []
    buf_len = 0

    def flush() -> None:
        nonlocal buf, buf_len
        if not buf:
            return
        chunk = "\n\n".join(buf).strip()
        if chunk:
            chunks.append(chunk)
        if overlap_chars > 0 and len(chunk) > overlap_chars:
            tail = chunk[-overlap_chars:]
            buf = [tail]
            buf_len = len(tail)
        else:
            buf = []
            buf_len = 0

    for para in paragraphs:
        if buf_len + len(para) + 2 > chunk_chars and buf:
            flush()
        buf.append(para)
        buf_len += len(para) + 2

        # If a single paragraph is enormous, hard-split it.
        while buf_len > chunk_chars:
            joined = "\n\n".join(buf)
            head = joined[:chunk_chars]
            chunks.append(head.strip())
            remainder = joined[chunk_chars - overlap_chars:]
            buf = [remainder]
            buf_len = len(remainder)

    flush()
    return [c for c in chunks if c]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Path to the PDF file to ingest")
    parser.add_argument(
        "--title",
        default=None,
        help="Title for the document (defaults to the file name without extension)",
    )
    parser.add_argument(
        "--source-type",
        default="book",
        help="source_type tag stored on each chunk (default: %(default)s)",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=2000,
        help="Target chunk size in characters (default: %(default)s)",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=200,
        help="Overlap between consecutive chunks in characters (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract and chunk only — do not write to the database",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit number of chunks ingested (useful for smoke tests)",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf).expanduser().resolve()
    if not pdf_path.is_file():
        logger.error("PDF not found: %s", pdf_path)
        return 2

    title = args.title or pdf_path.stem
    logger.info("Extracting text from %s", pdf_path)
    raw = extract_pdf_text(pdf_path)
    text = normalize_text(raw)
    if not text:
        logger.error("No text extracted from PDF (scanned image-only PDF?)")
        return 3

    chunks = chunk_text(
        text, chunk_chars=args.chunk_chars, overlap_chars=args.overlap_chars
    )
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]
    total_chars = sum(len(c) for c in chunks)
    logger.info(
        "Prepared %d chunks (%.1fk total chars; first chunk %d chars)",
        len(chunks),
        total_chars / 1000.0,
        len(chunks[0]) if chunks else 0,
    )

    if args.dry_run:
        preview = chunks[0][:400].replace("\n", " ") if chunks else ""
        logger.info("Dry run — first chunk preview: %s...", preview)
        return 0

    from app.db.session import SessionLocal
    from app.db.repository import StateRepository
    from app.knowledge_base.embeddings import EmbeddingProvider

    embedder = EmbeddingProvider()
    logger.info("Embedding mode: %s", embedder.mode)

    file_size = pdf_path.stat().st_size
    base_meta = {
        "source_path": str(pdf_path),
        "source_filename": pdf_path.name,
        "source_size_bytes": file_size,
        "total_chunks": len(chunks),
        "embedding_mode": embedder.mode,
    }

    inserted = 0
    skipped = 0
    db = SessionLocal()
    try:
        repo = StateRepository(db)
        for idx, chunk in enumerate(chunks, start=1):
            try:
                vector = embedder.embed(chunk)
                repo.ingest_knowledge_document(
                    title=f"{title} — chunk {idx}/{len(chunks)}",
                    content=chunk,
                    source_type=args.source_type,
                    vector=vector,
                    metadata={**base_meta, "chunk_index": idx},
                )
                inserted += 1
                if idx % 20 == 0 or idx == len(chunks):
                    logger.info(" ingested %d/%d chunks", idx, len(chunks))
            except Exception as exc:
                skipped += 1
                logger.warning(
                    "Chunk %d skipped: %s: %s", idx, exc.__class__.__name__, exc
                )
    finally:
        db.close()

    logger.info(
        "Done. inserted=%d skipped=%d title=%r source_type=%r",
        inserted,
        skipped,
        title,
        args.source_type,
    )
    return 0 if inserted > 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
