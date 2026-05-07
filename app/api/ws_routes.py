import logging
from typing import List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings

logger = logging.getLogger(__name__)

class ConnectionManager:
    """Manages active WebSocket connections for the dashboard."""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.debug("New WebSocket client connected (%d total)", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.debug("WebSocket client disconnected (%d total)", len(self.active_connections))

    async def broadcast(self, message: dict):
        """Send JSON message to all active clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as exc:
                logger.error("Failed to broadcast WebSocket message: %s", exc)

manager = ConnectionManager()
ws_router = APIRouter()

@ws_router.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    if settings.ws_auth_enabled:
        token = websocket.query_params.get("token", "")
        if not settings.ws_auth_token or token != settings.ws_auth_token:
            await websocket.close(code=1008)
            return

    await manager.connect(websocket)
    try:
        while True:
            # Keep the connection open; ignore any client messages.
            await websocket.receive()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        manager.disconnect(websocket)

async def broadcast_signal(event_type: str, data: dict):
    """Bridge function to broadcast signals from other services to the UI."""
    payload = {
        "event": event_type,
        "data": data
    }
    await manager.broadcast(payload)
