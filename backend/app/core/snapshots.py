"""Snapshot-lagret: radata med sha256, sa att varje uppgift gar att spara.

Varje annons och varje upphandling pekar pa en rad har. Gar en uppgift inte att
spara till ett snapshot ar den en gissning, och gissningar hor inte hemma i
databasen.

sha256 tjanar tva syften. Det ar bevis pa att innehallet inte andrats sedan vi
laste det, och det ar ocksa dubblettspärren: en nattlig korning mot en kalla som
inte andrats skriver ingenting.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import SourceSnapshot

# Storre svar an detta hamnar pa disk i stallet for i databasen. Granssen ar
# satt sa att en vanlig annons ryms i raw-kolumnen medan en PDF pa nagra
# megabyte inte sprangar en databasdump.
INLINE_MAX_BYTES = 256 * 1024


def sha256_of(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: Any) -> str:
    """Stabil JSON, sa att samma objekt alltid ger samma sha256.

    sort_keys ar inte kosmetik: utan den byter sha256 vart gang kallan
    returnerar falten i annan ordning, och da ser oforandrad data ut som ny.
    """
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def store_snapshot(
    session: Session,
    *,
    source_key: str,
    external_id: str | None,
    payload: Any,
    url: str | None = None,
    http_status: int | None = 200,
    content_type: str | None = "application/json",
    fetched_at: dt.datetime | None = None,
) -> tuple[SourceSnapshot, bool]:
    """Spara radata. Returnerar (snapshot, ar_ny).

    Finns samma sha256 redan for samma kalla och id returneras den befintliga
    raden med ar_ny=False. Anroparen anvander det for att veta om nagot behover
    bearbetas om.
    """
    text = payload if isinstance(payload, str) else canonical_json(payload)
    data = text.encode("utf-8")
    digest = sha256_of(data)

    befintlig = session.scalar(
        select(SourceSnapshot).where(
            SourceSnapshot.source_key == source_key,
            SourceSnapshot.external_id == external_id,
            SourceSnapshot.sha256 == digest,
        )
    )
    if befintlig is not None:
        return befintlig, False

    snapshot = SourceSnapshot(
        source_key=source_key,
        external_id=external_id,
        url=url,
        fetched_at=fetched_at or dt.datetime.now(dt.UTC),
        http_status=http_status,
        content_type=content_type,
        sha256=digest,
        byte_size=len(data),
    )

    if len(data) <= INLINE_MAX_BYTES:
        snapshot.raw = text
    else:
        katalog = Path(settings.snapshot_dir) / source_key
        katalog.mkdir(parents=True, exist_ok=True)
        sokvag = katalog / f"{digest}.bin"
        sokvag.write_bytes(data)
        snapshot.file_path = str(sokvag)

    session.add(snapshot)
    session.flush()
    return snapshot, True


def read_snapshot(snapshot: SourceSnapshot) -> str | None:
    """Las tillbaka radatan, oavsett om den ligger inline eller pa disk."""
    if snapshot.raw is not None:
        return snapshot.raw
    if snapshot.file_path:
        sokvag = Path(snapshot.file_path)
        if sokvag.exists():
            return sokvag.read_text(encoding="utf-8", errors="replace")
    return None


def verify_snapshot(snapshot: SourceSnapshot) -> bool:
    """Stammer innehallet med sha256?

    Anvands av administrationsvyn. En snapshot som inte verifierar ar inte langre
    ett bevis, och det ar battre att veta det an att tro motsatsen.
    """
    innehall = read_snapshot(snapshot)
    if innehall is None:
        return False
    return sha256_of(innehall) == snapshot.sha256
