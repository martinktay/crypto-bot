from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.outcome_tracker import OutcomeTracker
from app.services.signal_service import SignalPipeline

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")
_outcome_tracker: OutcomeTracker | None = None


def _get_outcome_tracker() -> OutcomeTracker:
    global _outcome_tracker
    if _outcome_tracker is None:
        _outcome_tracker = OutcomeTracker()
    return _outcome_tracker


def start_scheduler(pipeline: SignalPipeline) -> None:
    if scheduler.running:
        return

    def _run_cycle() -> None:
        try:
            with SessionLocal() as db:
                pipeline.run_cycle(db)
        except Exception as exc:
            logger.exception("Scheduled cycle failed: %s", exc)

    def _run_outcome_tracker() -> None:
        try:
            with SessionLocal() as db:
                _get_outcome_tracker().run(db)
        except Exception as exc:
            logger.exception("Outcome tracker cycle failed: %s", exc)

    scheduler.add_job(
        _run_cycle,
        "interval",
        seconds=settings.scan_interval_seconds,
        id="signal_cycle",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_outcome_tracker,
        "interval",
        seconds=settings.outcome_tracker_interval_seconds,
        id="outcome_tracker",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    scheduler.start()
    logger.info(
        "Scheduler started. Signal scan: %ds, outcome tracker: %ds",
        settings.scan_interval_seconds,
        settings.outcome_tracker_interval_seconds,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
