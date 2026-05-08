"""Session-scoped NDJSON debug log for Cursor debug mode (no secrets)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path

_SESSION = "0a5440"
_LOG_PATH = Path(__file__).resolve().parents[2] / f"debug-{_SESSION}.log"
_INGEST_URL = "http://127.0.0.1:7570/ingest/40e0f0b0-65dd-419e-8658-5cdac73f330d"
_log = logging.getLogger(__name__)


def agent_debug_log(
    location: str, message: str, hypothesis_id: str, **data: object
) -> None:
    # #region agent log
    payload = {
        "sessionId": _SESSION,
        "timestamp": int(time.time() * 1000),
        "location": location,
        "message": message,
        "data": {"hypothesisId": hypothesis_id, **data},
    }
    line = json.dumps(payload, default=str)
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        _log.warning("agent_debug_log file write failed path=%s err=%s", _LOG_PATH, exc)
    try:
        req = urllib.request.Request(
            _INGEST_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Debug-Session-Id": _SESSION,
            },
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
    except (urllib.error.URLError, TimeoutError, OSError):
        pass
    # #endregion
