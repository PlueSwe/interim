"""FastAPI-beroenden: session, inloggad anvandare, rollkontroll, revisionslogg."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_session
from .models import AuditLog, User, UserRole
from .security import decode_token

SessionDep = Annotated[Session, Depends(get_session)]

ACCESS_COOKIE = "ir_access"
REFRESH_COOKIE = "ir_refresh"


def current_user(
    session: SessionDep,
    ir_access: Annotated[str | None, Cookie(alias=ACCESS_COOKIE)] = None,
) -> User:
    """Las inloggad anvandare ur cookien.

    Token i httpOnly-cookie och inte i Authorization-header, sa att JavaScript
    i frontend inte kommer at den. Priset ar att CSRF maste hanteras, vilket
    sker i require_same_origin nedan.
    """
    if not ir_access:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inte inloggad.")
    try:
        data = decode_token(ir_access, expect="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessionen har gått ut.") from None
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Ogiltig token: {e}") from None

    anvandare = session.scalar(select(User).where(User.email == data["sub"]))
    if anvandare is None or not anvandare.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Kontot finns inte eller är avstängt.")
    return anvandare


CurrentUser = Annotated[User, Depends(current_user)]


def require_admin(user: CurrentUser) -> User:
    """Bara ADMIN far godkanna utgaende begaranden och andra beslut."""
    if user.role is not UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Kräver rollen ADMIN. Att godkänna en begäran om allmän handling eller "
            "ändra ett exkluderingsbeslut är inte en analytikeråtgärd.",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def require_same_origin(request: Request) -> None:
    """CSRF-skydd for muterande anrop.

    SameSite=Lax pa cookien stoppar det mesta, men inte en POST fran en annan
    sida i vissa aldre lagen. Origin-kontrollen ar billig och tacker resten.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    from .config import settings

    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin is None:
        # Anrop utan Origin kommer fran CLI eller tester, inte fran en webblasare.
        return
    if not any(origin.startswith(o) for o in settings.cors_origins):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Otillåten origin: {origin}")


def write_audit(
    session: Session,
    *,
    user: User | None,
    action: str,
    object_type: str,
    object_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    request: Request | None = None,
) -> None:
    """Skriv revisionslogg. Anropas vid varje manuell andring som paverkar ett beslut."""
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            ip=(request.client.host if request and request.client else None),
            at=dt.datetime.now(dt.UTC),
        )
    )
