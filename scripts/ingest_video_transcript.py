"""Transcribe a video or audio file and ingest the text into the knowledge base.

Steps:

1. **Extract** mono 16 kHz WAV from video (requires ``imageio-ffmpeg``, which
   bundles a portable ``ffmpeg`` binary — no system install needed).
2. **Segment** the WAV into parts under OpenAI's ~25 MB ``whisper-1`` limit
   (default 600 s per part).
3. **Transcribe** each segment with the OpenAI Audio API (``OPENAI_API_KEY``).
4. **Chunk** the full transcript and embed each chunk like :mod:`ingest_pdf`.

Example::

    pip install imageio-ffmpeg
    python scripts/ingest_video_transcript.py path/to/record.mp4 \\
        --title "Strategy walkthrough" --source-type video_transcript

Use ``--audio`` to skip extraction if you already have a WAV/MP3. Use
``--dry-run`` to transcribe and print stats without writing to the database.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ingest_video_transcript")

# Re-use PDF chunking helpers (single source of truth).
_spec = importlib.util.spec_from_file_location(
    "_ingest_pdf", ROOT / "scripts" / "ingest_pdf.py"
)
_ingest_pdf = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_ingest_pdf)
normalize_text = _ingest_pdf.normalize_text
chunk_text = _ingest_pdf.chunk_text


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg as iof

    return iof.get_ffmpeg_exe()


def extract_wav_mono16k(input_path: Path, output_wav: Path) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(output_wav),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg extract failed:\n%s", proc.stderr[-2000:])
        proc.check_returncode()


def segment_wav(
    input_wav: Path, out_dir: Path, segment_seconds: int = 600
) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "part%03d.wav")
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(input_wav),
        "-f",
        "segment",
        "-segment_time",
        str(segment_seconds),
        "-reset_timestamps",
        "1",
        "-c",
        "copy",
        pattern,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        logger.error("ffmpeg segment failed:\n%s", proc.stderr[-2000:])
        proc.check_returncode()
    return sorted(out_dir.glob("part*.wav"))


def transcribe_segments(segment_paths: list[Path], *, language: str | None) -> str:
    from openai import OpenAI

    from app.core.config import settings

    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required for Whisper transcription. "
            "Set it in the environment or .env file."
        )

    client = OpenAI(api_key=settings.openai_api_key)
    parts: list[str] = []
    for i, seg in enumerate(segment_paths, start=1):
        logger.info("Transcribing segment %d/%d (%s)", i, len(segment_paths), seg.name)
        with open(seg, "rb") as audio_file:
            if language:
                tr = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                )
            else:
                tr = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                )
        text = (tr.text or "").strip()
        parts.append(f"--- Segment {i}/{len(segment_paths)} ---\n\n{text}")

    return "\n\n".join(parts)


def ensure_schema() -> None:
    from app.db.base import Base
    from app.db.session import engine

    import app.models.entities  # noqa: F401 — register ORM metadata

    Base.metadata.create_all(engine)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="Path to a video file (mp4, mov, …)")
    src.add_argument("--audio", help="Path to an audio file (wav, mp3, …)")
    parser.add_argument(
        "--title",
        default=None,
        help="Title for knowledge documents (default: source file stem)",
    )
    parser.add_argument(
        "--source-type",
        default="video_transcript",
        help="source_type tag on each chunk (default: %(default)s)",
    )
    parser.add_argument(
        "--segment-seconds",
        type=int,
        default=600,
        help="Max seconds per Whisper request (default 600 ≈ under 25 MB at 16 kHz mono)",
    )
    parser.add_argument(
        "--language",
        default=None,
        help="ISO-639-1 language code (e.g. en). Omit for auto-detect.",
    )
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=2000,
        help="Target KB chunk size (default: %(default)s)",
    )
    parser.add_argument(
        "--overlap-chars",
        type=int,
        default=200,
        help="Overlap between KB chunks (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Transcribe and show stats only; do not write to the database",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Limit number of KB chunks inserted (after chunking)",
    )
    parser.add_argument(
        "--save-transcript",
        type=Path,
        default=None,
        help="Optional path to save the full normalized transcript as UTF-8 text",
    )
    args = parser.parse_args()

    if args.video:
        src_path = Path(args.video).expanduser().resolve()
    else:
        src_path = Path(args.audio).expanduser().resolve()

    if not src_path.is_file():
        logger.error("Source file not found: %s", src_path)
        return 2

    title = args.title or src_path.stem

    with tempfile.TemporaryDirectory(prefix="transcribe_") as tmp:
        tmp_path = Path(tmp)
        if args.video:
            wav_path = tmp_path / "full.wav"
            logger.info("Extracting audio → %s", wav_path)
            extract_wav_mono16k(src_path, wav_path)
        else:
            wav_path = tmp_path / "full.wav"
            logger.info("Converting audio → mono 16 kHz WAV")
            extract_wav_mono16k(src_path, wav_path)

        seg_dir = tmp_path / "segments"
        segs = segment_wav(wav_path, seg_dir, segment_seconds=args.segment_seconds)
        if not segs:
            logger.error("No audio segments produced")
            return 3

        logger.info("Split into %d segment(s) for Whisper", len(segs))
        raw_transcript = transcribe_segments(segs, language=args.language)
        n_whisper_segments = len(segs)

    text = normalize_text(raw_transcript)
    # Remove decorative segment headers for cleaner RAG (keep breaks as paragraphs).
    text = re.sub(
        r"--- Segment \d+/\d+ ---\s*",
        "",
        text,
    )
    text = normalize_text(text)

    if args.save_transcript:
        args.save_transcript.parent.mkdir(parents=True, exist_ok=True)
        args.save_transcript.write_text(text, encoding="utf-8")
        logger.info("Wrote transcript to %s (%d chars)", args.save_transcript, len(text))

    if not text:
        logger.error("Transcript is empty")
        return 4

    chunks = chunk_text(
        text, chunk_chars=args.chunk_chars, overlap_chars=args.overlap_chars
    )
    if args.max_chunks:
        chunks = chunks[: args.max_chunks]

    logger.info(
        "Prepared %d KB chunks from transcript (%.1fk chars)",
        len(chunks),
        len(text) / 1000.0,
    )

    if args.dry_run:
        preview = text[:500].replace("\n", " ")
        logger.info("Dry run — preview: %s...", preview)
        return 0

    ensure_schema()

    from app.db.session import SessionLocal
    from app.db.repository import StateRepository
    from app.knowledge_base.embeddings import EmbeddingProvider

    embedder = EmbeddingProvider()
    logger.info("Embedding mode: %s", embedder.mode)

    base_meta = {
        "source_path": str(src_path),
        "source_filename": src_path.name,
        "source_size_bytes": src_path.stat().st_size,
        "total_chunks": len(chunks),
        "embedding_mode": embedder.mode,
        "transcript_chars": len(text),
        "whisper_segments": n_whisper_segments,
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
    return 0 if inserted > 0 else 5


if __name__ == "__main__":
    raise SystemExit(main())
