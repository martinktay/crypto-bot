from fastapi import FastAPI

from app.api.routes import router
from app.core.config import settings
from app.core.startup import validate_runtime_settings
from app.core.state import init_runtime_state
from app.monitoring.metrics import metrics_router
from app.utils.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="Crypto Telegram Bot", version="0.2.0")
    validate_runtime_settings(settings)
    init_runtime_state(settings.default_mode, settings.symbol_list, settings.timeframe_list)
    app.include_router(router)
    app.include_router(metrics_router)
    return app


app = create_app()
