"""Inloggning. Ingen publik registrering."""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..config import settings
from ..deps import ACCESS_COOKIE, REFRESH_COOKIE, CurrentUser, SessionDep, write_audit
from ..models import User
from ..schemas import LoginIn, UserOut
from ..security import create_token, decode_token, hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

# Enkel rate limit i minnet. Redis anvands i drift via slowapi (se main.py);
# detta ar ett extra lager per konto som halls aven utan Redis.
_attempts: dict[str, list[dt.datetime]] = {}


def _rate_limited(key: str) -> bool:
    nu = dt.datetime.now(dt.UTC)
    fonster = nu - dt.timedelta(minutes=settings.login_window_minutes)
    forsok = [t for t in _attempts.get(key, []) if t > fonster]
    _attempts[key] = forsok
    return len(forsok) >= settings.login_attempts_per_window


def _record_attempt(key: str) -> None:
    _attempts.setdefault(key, []).append(dt.datetime.now(dt.UTC))


def _set_cookies(response: Response, email: str) -> None:
    gemensamt = {
        "httponly": True,
        "secure": settings.cookie_secure,
        "samesite": "lax",
        "path": "/",
    }
    response.set_cookie(
        ACCESS_COOKIE,
        create_token(email, kind="access"),
        max_age=settings.access_token_minutes * 60,
        **gemensamt,
    )
    response.set_cookie(
        REFRESH_COOKIE,
        create_token(email, kind="refresh"),
        max_age=settings.refresh_token_days * 86400,
        **gemensamt,
    )


@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, request: Request, session: SessionDep):
    nyckel = data.email.lower()
    if _rate_limited(nyckel):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"För många försök. Vänta {settings.login_window_minutes} minuter.",
        )

    anvandare = session.scalar(select(User).where(User.email == data.email))
    # Samma svar oavsett om kontot finns eller losenordet var fel. Skillnaden
    # vore annars ett satt att ta reda pa vilka adresser som har konto.
    if (
        anvandare is None
        or not anvandare.is_active
        or not verify_password(data.password, anvandare.password_hash)
    ):
        _record_attempt(nyckel)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Fel e-post eller lösenord.")

    if needs_rehash(anvandare.password_hash):
        anvandare.password_hash = hash_password(data.password)

    anvandare.last_login_at = dt.datetime.now(dt.UTC)
    _attempts.pop(nyckel, None)
    write_audit(
        session,
        user=anvandare,
        action="login",
        object_type="user",
        object_id=str(anvandare.id),
        request=request,
    )
    session.commit()
    _set_cookies(response, anvandare.email)
    return anvandare


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, session: SessionDep):
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Ingen uppdateringstoken.")
    try:
        data = decode_token(token, expect="refresh")
    except Exception as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Ogiltig token: {e}") from None
    anvandare = session.scalar(select(User).where(User.email == data["sub"]))
    if anvandare is None or not anvandare.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kontot finns inte.")
    _set_cookies(response, anvandare.email)
    return anvandare


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
