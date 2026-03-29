from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.enums import TradingMode
from app.core.state import get_runtime_state
from app.services.signal_service import SignalPipeline

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="UTC")


def start_scheduler(pipeline: SignalPipeline) -> None:
    if scheduler.running:
        return

    def _run_cycle() -> None:
        state = get_runtime_state()
        if state.paused or state.mode == TradingMode.SIGNAL_ONLY:
            return
        try:
            pipeline.run_cycle(state)
        except Exception as exc:  # runtime safety logging
            logger.exception("Scheduled cycle failed: %s", exc)

    scheduler.add_job(_run_cycle, "interval", minutes=5, id="signal_cycle", replace_existing=True)
    scheduler.start()


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
