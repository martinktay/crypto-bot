from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, generate_latest

metrics_router = APIRouter()

signals_generated = Counter("signals_generated_total", "Signals generated")
trade_rejections = Counter("trade_rejections_total", "Trades rejected")


@metrics_router.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
