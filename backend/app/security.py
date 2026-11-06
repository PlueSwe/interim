"""Losenord, tokens och faltkryptering."""

from __future__ import annotations

import base64
import datetime as dt
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from .config import settings

# Argon2id med standardparametrarna fran argon2-cffi. De ar rimliga for en
# applikation med fa anvandare; hojer man dem blir inloggningen seg utan att
# nagon angripare brys sig.
_hasher = PasswordHasher()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, Exception):
        return False


def needs_rehash(password_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(password_hash)
    except Exception:
        return False


def create_token(subject: str, *, kind: str = "access", extra: dict[str, Any] | None = None) -> str:
    nu = dt.datetime.now(dt.UTC)
    livstid = (
        dt.timedelta(minutes=settings.access_token_minutes)
        if kind == "access"
        else dt.timedelta(days=settings.refresh_token_days)
    )
    payload = {
        "sub": subject,
        "typ": kind,
        "iat": int(nu.timestamp()),
        "exp": int((nu + livstid).timestamp()),
        "jti": str(uuid.uuid4()),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.secret_key.get_secret_value(), algorithm=ALGORITHM)


def decode_token(token: str, *, expect: str = "access") -> dict[str, Any]:
    """Avkoda och kontrollera typ.

    Typkontrollen finns for att en uppdateringstoken inte ska ga att anvanda
    som atkomsttoken. Utan den racker en 14 dagar gammal token for att komma at
    API:et.
    """
    data = jwt.decode(token, settings.secret_key.get_secret_value(), algorithms=[ALGORITHM])
    if data.get("typ") != expect:
        raise jwt.InvalidTokenError(f"token av typ {data.get('typ')!r}, vantade {expect!r}")
    return data


# --- Faltkryptering ---------------------------------------------------------
#
# Anvands for appointed_persons.full_name och information_requests.body. Bada
# ar uppgifter dar en lackt databasdump gor verklig skada: ett namn pa en
# person i en offentlig roll, och text som ska skickas i anvandarens namn.


def _key() -> bytes | None:
    if settings.field_encryption_key is None:
        return None
    rått = settings.field_encryption_key.get_secret_value()
    try:
        nyckel = base64.urlsafe_b64decode(rått)
    except Exception:
        nyckel = rått.encode()
    if len(nyckel) != 32:
        raise ValueError(
            "FIELD_ENCRYPTION_KEY maste vara 32 byte base64. Skapa en med:\n"
            '  python -c "import os,base64; '
            'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
        )
    return nyckel


def encrypt_field(plaintext: str | None) -> str | None:
    """AES-GCM. Returnerar texten oforandrad nar ingen nyckel ar satt.

    Att falla tillbaka pa klartext i stallet for att krascha ar ett val: en
    utvecklingsmiljo utan nyckel ska fungera, och SECURITY.md sager att nyckeln
    kravs i drift. Att returnera None hade tappat data tyst.
    """
    if plaintext is None:
        return None
    nyckel = _key()
    if nyckel is None:
        return plaintext
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    ct = AESGCM(nyckel).encrypt(nonce, plaintext.encode("utf-8"), None)
    return "enc:v1:" + base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_field(value: str | None) -> str | None:
    if value is None or not value.startswith("enc:v1:"):
        return value
    nyckel = _key()
    if nyckel is None:
        raise ValueError("faltet ar krypterat men FIELD_ENCRYPTION_KEY saknas")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    rått = base64.urlsafe_b64decode(value.removeprefix("enc:v1:"))
    return AESGCM(nyckel).decrypt(rått[:12], rått[12:], None).decode("utf-8")
