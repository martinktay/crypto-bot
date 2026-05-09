import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import ApiKeyDep
from app.db.session import get_db
from app.db.repository import StateRepository

router = APIRouter()

# Setup templates directory relative to this file
templates_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the main dashboard page."""
    repo = StateRepository(db)
    state = repo.get_runtime_state_snapshot()
    outcomes = repo.get_recent_outcomes()
    backtests = repo.get_backtest_history(limit=5)
    summary = repo.get_signal_performance_summary()
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "state": state,
            "outcomes": outcomes,
            "backtests": backtests,
            "summary": summary,
            "app_name": settings.app_display_name,
            "api_auth_enabled": settings.api_auth_enabled,
            "api_auth_header": settings.api_auth_header,
            "ws_auth_enabled": settings.ws_auth_enabled,
        }
    )

@router.get("/api/dashboard/data")
async def dashboard_data(db: Session = Depends(get_db), _: None = ApiKeyDep):
    """API endpoint for UI to refresh data (if not using WebSocket)."""
    repo = StateRepository(db)
    state = repo.get_runtime_state_snapshot()
    outcomes = repo.get_recent_outcomes()
    summary = repo.get_signal_performance_summary()
    
    return {
        "app_name": settings.app_display_name,
        "summary": summary,
        "execution_mode": state.execution_mode,
        "paused": state.paused,
        "recent_signals": outcomes[:10]
    }
