"""Application entry point — FastAPI factory with lifecycle management."""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.ui_routes import router as ui_router
from app.api.ws_routes import ws_router, broadcast_signal
from app.core.config import settings
from app.core.startup import validate_runtime_settings
from app.db.session import SessionLocal
from app.db.repository import StateRepository
from app.knowledge_base.seed import seed_knowledge_base_if_empty
from app.monitoring.metrics import metrics_router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.signal_service import get_pipeline
from app.telegram_bot.service import TelegramNotifier
from app.utils.agent_debug_log import agent_debug_log
from app.utils.logging import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown lifecycle."""
    # #region agent log
    agent_debug_log(
        "main.py:lifespan",
        "lifespan startup entered",
        "L0",
    )
    # #endregion
    # --- Startup ---
    pipeline = get_pipeline()
    loop = asyncio.get_running_loop()

    # Pre-warm settings cache in DB
    try:
        with SessionLocal() as db:
            StateRepository(db).get_or_create_settings()
    except Exception as exc:
        logger.warning("Failed to initialize database settings on startup: %s", exc)

    # Wire Telegram & WebSocket notifications
    notifier = TelegramNotifier()
    
    def unified_notify(event_type: str, **kwargs: Any):
        """Bridge sync callbacks to Telegram and WebSockets."""
        notifier.notify(event_type, **kwargs)

        data: dict[str, Any] = {}
        if "signal" in kwargs:
            data.update(kwargs["signal"].model_dump(mode="json"))

        asyncio.run_coroutine_threadsafe(broadcast_signal(event_type, data), loop)

    pipeline.set_notifier(unified_notify)
    logger.info("Unified (Telegram + WebSocket) notifications enabled")

    # Start scheduler
    start_scheduler(pipeline)

    # Seed knowledge base
    seed_knowledge_base_if_empty()

    # Start Telegram bot (polling) if token is set
    bot_task = None
    # #region agent log
    agent_debug_log(
        "main.py:lifespan",
        "telegram startup branch",
        "H1",
        has_token=bool(settings.telegram_bot_token),
    )
    # #endregion
    if settings.telegram_bot_token:
        from app.telegram_bot.bot import start_bot

        def _log_bot_task_done(t: asyncio.Task) -> None:
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                # #region agent log
                agent_debug_log(
                    "main.py:_log_bot_task_done",
                    "telegram bot task failed",
                    "H2",
                    error_type=type(exc).__name__,
                    error_msg=str(exc)[:400],
                )
                # #endregion
                logger.error(
                    "Telegram bot task crashed - polling stopped",
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

        # Run bot in background to avoid blocking lifespan startup
        bot_task = asyncio.create_task(start_bot(settings.telegram_bot_token))
        bot_task.add_done_callback(_log_bot_task_done)
        logger.info("Telegram bot task created")
        # #region agent log
        agent_debug_log(
            "main.py:lifespan",
            "telegram bot asyncio task created",
            "H1",
            task_created=True,
        )
        # #endregion

    yield

    # --- Shutdown ---
    stop_scheduler()

    if bot_task:
        from app.telegram_bot.bot import stop_bot
        await stop_bot()
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    setup_logging(settings.log_level, settings.log_format)
    validate_runtime_settings(settings)

    app = FastAPI(
        title=settings.app_display_name,
        version="0.4.0",
        lifespan=lifespan,
    )
    
    # Mount static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if not os.path.exists(static_dir):
        os.makedirs(static_dir, exist_ok=True)
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Order matters: UI router (root) usually after API routers or explicitly handled
    app.include_router(router)
    app.include_router(metrics_router)
    app.include_router(ws_router)
    app.include_router(ui_router)
    
    return app


app = create_app()
