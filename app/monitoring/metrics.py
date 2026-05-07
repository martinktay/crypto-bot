from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

from app.core.security import ApiKeyDep

metrics_router = APIRouter()

signals_generated = Counter("signals_generated_total", "Signals generated")
trade_rejections = Counter("trade_rejections_total", "Trades rejected")
live_orders_placed = Counter("live_orders_placed_total", "Live orders placed successfully")
live_orders_failed = Counter("live_orders_failed_total", "Live orders failed")
notifications_failed = Counter(
    "notifications_failed_total",
    "Notification deliveries that failed",
    ["kind"],
)
approval_decisions = Counter(
    "approval_decisions_total",
    "Approval decisions resolved",
    ["status"],
)


@metrics_router.get("/metrics")
def metrics(_: None = ApiKeyDep) -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
