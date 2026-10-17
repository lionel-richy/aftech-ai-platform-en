"""API key authentication and CORS configuration.

The expected key ALWAYS comes from an environment variable
(BACKEND_API_KEY), never a value hardcoded in the code — that's what lets
it be changed without touching the code, and never committed to Git.
"""

import os

from fastapi import Header, HTTPException, status


def get_cors_origins() -> list[str]:
    """List of allowed origins (CORS), configured via
    BACKEND_CORS_ORIGINS (one or more URLs separated by commas). Default:
    only the Next.js frontend in local development."""
    raw = os.environ.get("BACKEND_CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def verify_api_key(authorization: str | None = Header(default=None)) -> None:
    """FastAPI dependency: checks the `Authorization: Bearer <key>` header.

    Used on every route except /health (which must stay reachable by a
    plain monitoring check, with no secret).
    """
    expected = os.environ.get("BACKEND_API_KEY")
    if not expected:
        # No key configured server-side: reject rather than accept any
        # request without a check.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="BACKEND_API_KEY is not configured on the server.",
        )

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key.")

    presented = authorization.removeprefix("Bearer ").strip()
    if presented != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key.")
