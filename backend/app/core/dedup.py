"""Dubblettkontroll i tre steg.

Samma tjanst dyker upp flera ganger: i Platsbanken, pa myndighetens egen sida,
hos en forsmedlare, och ibland som en ny annons nar deadline forlangs. Utan
dubblettkontroll blir dashboarden en lista pa samma uppdrag om och om igen.

Stegen, i ordning, fran sakrast till minst saker:

1. **Samma kalla och samma externa id.** Ingen tvekan; det ar samma annons.
2. **Samma organisation, samma normaliserade titel, samma publiceringsdag.**
   Tackar samma tjanst publicerad via tva kallor samma dag.
3. **Samma organisation och hog titellikhet inom ett tidsfonster.** Tackar
   omformuleringar och forlangda deadlines.

Steg 3 kan ha fel, sa trosklarna ar satta hogt och traffen rapporteras med
anledning sa att en manniska kan se varfor tva annonser slogs ihop.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import JobAd
from .text import jaccard, normalise_title

# Hur lika titlarna maste vara i steg 3. 0.85 pa ordmangder betyder i praktiken
# att hogst ett ord av sju skiljer.
TITLE_SIMILARITY_THRESHOLD = 0.85
# Hur langt ifran varandra tva publiceringar far ligga for att vara samma
# tjanst. En manad racker for forlangda deadlines utan att slanga samman tva
# riktiga rekryteringar ett halvar isar.
WINDOW_DAYS = 31


class DuplicateKind(str, Enum):
    NONE = "NONE"
    SAME_SOURCE_ID = "SAME_SOURCE_ID"
    SAME_TITLE_ORG_DATE = "SAME_TITLE_ORG_DATE"
    SIMILAR_TITLE_ORG = "SIMILAR_TITLE_ORG"


@dataclass
class DuplicateMatch:
    kind: DuplicateKind
    job_ad_id: UUID | None = None
    similarity: float | None = None
    reason: str = ""

    @property
    def found(self) -> bool:
        return self.kind is not DuplicateKind.NONE


def find_duplicate(
    session: Session,
    *,
    source_key: str,
    external_id: str,
    title: str,
    organisation_id: UUID | None,
    published_at: dt.datetime | None,
) -> DuplicateMatch:
    # Steg 1
    traff = session.scalar(
        select(JobAd).where(JobAd.source_key == source_key, JobAd.external_id == external_id)
    )
    if traff is not None:
        return DuplicateMatch(
            DuplicateKind.SAME_SOURCE_ID,
            traff.id,
            1.0,
            f"samma kalla och id ({source_key}/{external_id})",
        )

    if organisation_id is None:
        # Utan organisation gar steg 2 och 3 inte att gora utan att riskera att
        # sla samman tva myndigheters "IT-chef". Hellre en dubblett an en
        # felaktig sammanslagning.
        return DuplicateMatch(DuplicateKind.NONE, reason="organisation okand, steg 2-3 hoppas over")

    normaliserad = normalise_title(title)

    # Steg 2
    if published_at is not None:
        dagens_start = published_at.replace(hour=0, minute=0, second=0, microsecond=0)
        kandidater = session.scalars(
            select(JobAd).where(
                JobAd.organisation_id == organisation_id,
                JobAd.title_normalised == normaliserad,
                JobAd.published_at >= dagens_start,
                JobAd.published_at < dagens_start + dt.timedelta(days=1),
            )
        ).all()
        if kandidater:
            return DuplicateMatch(
                DuplicateKind.SAME_TITLE_ORG_DATE,
                kandidater[0].id,
                1.0,
                f"samma organisation, titel och publiceringsdag ({dagens_start.date()})",
            )

    # Steg 3
    fran = tom = None
    if published_at is not None:
        fran = published_at - dt.timedelta(days=WINDOW_DAYS)
        tom = published_at + dt.timedelta(days=WINDOW_DAYS)

    fraga = select(JobAd).where(JobAd.organisation_id == organisation_id)
    if fran is not None:
        fraga = fraga.where(JobAd.published_at >= fran, JobAd.published_at <= tom)

    bast: tuple[float, JobAd] | None = None
    for kandidat in session.scalars(fraga).all():
        likhet = jaccard(title, kandidat.title)
        if likhet >= TITLE_SIMILARITY_THRESHOLD and (bast is None or likhet > bast[0]):
            bast = (likhet, kandidat)

    if bast is not None:
        likhet, kandidat = bast
        return DuplicateMatch(
            DuplicateKind.SIMILAR_TITLE_ORG,
            kandidat.id,
            round(likhet, 3),
            f"titellikhet {likhet:.2f} mot {kandidat.title!r} inom {WINDOW_DAYS} dagar",
        )

    return DuplicateMatch(DuplicateKind.NONE, reason="ingen dubblett hittad")


def changed_fields(existing: JobAd, new_values: dict) -> dict:
    """Vilka falt skiljer sig? Underlag till job_ad_versions.changed_fields.

    Bara falt som betyder nagot foljs. Att en kalla skriver om ett blanksteg i
    beskrivningen ska inte skapa en ny version, men en andrad deadline ska.
    """
    folj = (
        "title",
        "description",
        "application_deadline",
        "employment_type",
        "role_family",
        "depublished_at",
        "url",
    )
    diff: dict = {}
    for falt in folj:
        if falt not in new_values:
            continue
        gammalt = getattr(existing, falt, None)
        nytt = new_values[falt]
        bada_text = isinstance(gammalt, str) and isinstance(nytt, str)
        if bada_text and " ".join(gammalt.split()) == " ".join(nytt.split()):
            continue
        if gammalt != nytt:
            diff[falt] = {
                "from": str(gammalt) if gammalt is not None else None,
                "to": str(nytt) if nytt is not None else None,
            }
    return diff
