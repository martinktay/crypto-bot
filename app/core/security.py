from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings


def require_api_key(request: Request) -> None:
    """
    Minimal shared-secret auth for the HTTP API.

    Controlled by:
    - API_AUTH_ENABLED
    - API_AUTH_TOKEN
    - API_AUTH_HEADER
    """
    if not settings.api_auth_enabled:
        return

    header_name = settings.api_auth_header
    provided = request.headers.get(header_name) or ""
    expected = settings.api_auth_token or ""

    if not expected:
        # Fail closed if auth is enabled but misconfigured.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API auth is enabled but API_AUTH_TOKEN is not set",
        )

    if not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


ApiKeyDep = Depends(require_api_key)

