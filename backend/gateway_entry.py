"""Frozen entry point for the local FastAPI gateway."""

from __future__ import annotations

from os import getenv

import uvicorn

from backend.app.main import app


def gateway_port() -> int:
    try:
        port = int(getenv("DESKTOP_PET_GATEWAY_PORT", "8000"))
    except ValueError:
        return 8000
    return port if 1 <= port <= 65_535 else 8000


def main() -> None:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=gateway_port(),
        log_level="warning",
        access_log=False,
    )


if __name__ == "__main__":
    main()
