"""FastAPI application bound to 127.0.0.1 and protected by a per-launch token.

The desktop shell generates a random token at every launch and passes it to the
core via the environment. Requests without it are rejected, as are requests whose
Host header is not loopback (DNS-rebinding defence).
"""

from __future__ import annotations

import hmac
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from huntly import __version__
from huntly.api.routes import analytics, applications, companies, jobs, system
from huntly.context import AppContext
from huntly.security.vault import VaultLocked

log = logging.getLogger(__name__)

ALLOWED_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost", "http://localhost:1420", "http://127.0.0.1:1420"]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


def create_app(ctx: AppContext, api_token: str) -> FastAPI:
    app = FastAPI(title="Huntly Core", version=__version__, docs_url=None, redoc_url=None, openapi_url="/openapi.json")
    app.state.ctx = ctx

    @app.middleware("http")
    async def guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0]
        if host not in LOOPBACK_HOSTS:
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
        if request.method != "OPTIONS":
            auth = request.headers.get("authorization", "")
            supplied = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
            if not supplied or not hmac.compare_digest(supplied.encode(), api_token.encode()):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

    # Added after the guard so CORS headers wrap every response, including 401s.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["authorization", "content-type"],
    )

    @app.exception_handler(VaultLocked)
    async def _locked(_: Request, exc: VaultLocked):
        return JSONResponse({"detail": str(exc)}, status_code=423)

    @app.exception_handler(OperationalError)
    async def _busy(_: Request, exc: OperationalError):
        if "locked" in str(exc.orig):
            log.warning("database busy: %s", exc.orig)
            return JSONResponse({"detail": "Huntly is busy saving search results. Try again in a few seconds."}, status_code=503)
        log.exception("unhandled error")
        return JSONResponse({"detail": f"Internal error: {type(exc).__name__}"}, status_code=500)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return JSONResponse({"detail": f"Internal error: {type(exc).__name__}"}, status_code=500)

    for r in (system.router, jobs.router, companies.router, applications.router, analytics.router):
        app.include_router(r, prefix="/api")
    return app
