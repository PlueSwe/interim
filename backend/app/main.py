"""FastAPI-applikationen."""

from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .deps import require_same_origin

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("interim_radar")

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Privat bevakning av svenska chefsrekryteringar, interimuppdrag och "
        "offentliga upphandlingar. Ingen publik registrering; inloggning kravs."
    ),
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,  # kravs for httpOnly-cookien
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# --- Rate limiting ---
# slowapi mot Redis i drift. Saknas Redis kors applikationen anda, men utan
# global rate limit; inloggningen har en egen granskontroll i routes_auth.py
# som inte beror pa Redis.
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address

    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[settings.api_rate_limit],
        storage_uri=settings.redis_url,
    )
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
except Exception as e:  # pragma: no cover
    log.warning("rate limiting avstangd: %s", e)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    svar = await call_next(request)
    svar.headers["X-Content-Type-Options"] = "nosniff"
    svar.headers["X-Frame-Options"] = "DENY"
    svar.headers["Referrer-Policy"] = "no-referrer"
    if settings.environment == "prod":
        svar.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return svar


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Oväntade fel loggas men lacker inte sin text till klienten.

    Ett stacktrace i svaret berattar om filsokvagar och bibliotek. Loggen har
    uppgiften; klienten far veta att det gick fel.
    """
    log.exception("ohanterat fel pa %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "internt fel. Se serverloggen."},
    )


# --- Routes ---

from .api import (  # noqa: E402
    routes_admin,
    routes_appointments,
    routes_auth,
    routes_dashboard,
    routes_opportunities,  # noqa: E402
)

PREFIX = "/api/v1"
SKYDD = [Depends(require_same_origin)]

app.include_router(routes_auth.router, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_dashboard.router, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_dashboard.market, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_dashboard.orgs, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_dashboard.authorities, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_opportunities.router, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_opportunities.saved, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_opportunities.providers, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_appointments.router, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_appointments.requests_router, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_appointments.persons, prefix=PREFIX, dependencies=SKYDD)
app.include_router(routes_admin.router, prefix=PREFIX, dependencies=SKYDD)


@app.get("/health", tags=["system"])
def health():
    """Halsokontroll. Svarar aven nar databasen ar nere, med status degraded."""
    from sqlalchemy import text

    from .db import engine

    try:
        with engine.connect() as anslutning:
            anslutning.execute(text("select 1"))
        db = "ok"
    except Exception as e:
        db = f"fel: {type(e).__name__}"
    return {
        "status": "ok" if db == "ok" else "degraded",
        "database": db,
        "ai_enabled": settings.ai_enabled,
        "environment": settings.environment,
        "version": "0.1.0",
    }
