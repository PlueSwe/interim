"""Seedar organisationer och myndigheter ur skordad data.

Datan i authorities_data.json ar inte handskriven. Den ar skordad ur
JobTech-annonser med scripts/harvest_authorities.py, dar varje
organisationsnummer kommer fran Arbetsformedlingens egen uppgift om
arbetsgivaren. Inget nummer ar gissat; se DATA_SOURCES.md.

Varje myndighet far status MANUAL_ONLY tills nagon verifierat att dess
karriarsida gar att lasa (`app.cli verify-authority`). Att satta 384
organisationer till ACTIVE direkt hade gett en dashboard som ser ut att bevaka
allt och i praktiken bevakar ingenting.

Annonserna hamtas anda for dem alla, via jobtech-adaptern. Skillnaden ar om
systemet ocksa laser myndighetens egen sida.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Authority,
    CollectionMethod,
    Organisation,
    OrgType,
    RecruitmentPlatform,
    SourceStatus,
)

DATA_FILE = Path(__file__).resolve().parent / "authorities_data.json"

PLATFORM_FROM_URL: tuple[tuple[RecruitmentPlatform, str], ...] = (
    (RecruitmentPlatform.VARBI, r"varbi\.com"),
    (RecruitmentPlatform.REACHMEE, r"reachmee"),
    (RecruitmentPlatform.TEAMTAILOR, r"teamtailor"),
    (RecruitmentPlatform.VISMA_RECRUIT, r"visma"),
    (RecruitmentPlatform.JOBYLON, r"jobylon"),
)


def _platform(url: str | None) -> RecruitmentPlatform:
    """Rekryteringsplattform ur webbplatsfaltet.

    Ett bonusfynd ur skorden: nar en myndighet anger `kriminalvarden.varbi.com`
    som arbetsgivarens URL i annonsen har den avslojat vilket
    rekryteringssystem den kor. Det ar kallans egen uppgift och battre an att
    prova sig fram.
    """
    if not url:
        return RecruitmentPlatform.UNKNOWN
    for plattform, monster in PLATFORM_FROM_URL:
        if re.search(monster, url, re.IGNORECASE):
            return plattform
    return RecruitmentPlatform.UNKNOWN


def load_data() -> dict:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"{DATA_FILE} saknas. Kor: python scripts/harvest_authorities.py")
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def seed_authorities(session: Session, *, limit: int | None = None) -> dict[str, int]:
    """Skriv organisationer och myndighetsrader. Idempotent."""
    data = load_data()
    rader = data["authorities"][:limit] if limit else data["authorities"]
    skapade = {"organisations": 0, "authorities": 0, "uppdaterade": 0}

    for rad in rader:
        orgnr = rad["org_number"]
        org = session.scalar(select(Organisation).where(Organisation.org_number == orgnr))
        if org is None:
            org = Organisation(
                name=rad["name"],
                org_number=orgnr,
                org_type=OrgType(rad["org_type"]),
                website=rad.get("website"),
                note=(
                    f"Skordad ur JobTech {rad['verified_at']}: {rad['ad_count']} annonser, "
                    f"senast {rad.get('latest_ad')}"
                ),
            )
            session.add(org)
            session.flush()
            skapade["organisations"] += 1
        else:
            if not org.website and rad.get("website"):
                org.website = rad["website"]
                skapade["uppdaterade"] += 1

        # Bara offentliga organisationer far en myndighetsrad. En kommun ar inte
        # en myndighet i modellens mening men har samma behov av registrator och
        # karriarsida, sa den far ocksa en rad.
        if org.org_type is OrgType.PRIVATE:
            continue

        myndighet = session.scalar(select(Authority).where(Authority.organisation_id == org.id))
        if myndighet is not None:
            continue

        plattform = _platform(rad.get("website"))
        session.add(
            Authority(
                organisation_id=org.id,
                # Bada satts forst nar nagon verifierat vilken sida som ar
                # vilken. Adressen ur annonsen ar organisationens startsida,
                # och att skriva in den som karriarsida vore ett pastaende vi
                # inte har tackning for -- den star kvar pa organisationen
                # (organisations.website) dar den faktiskt hor hemma.
                careers_url=None,
                vacancies_url=None,
                recruitment_platform=plattform,
                # JOBTECH eftersom annonserna kommer darifran redan. Byts till
                # HTML_SCRAPE eller SITEMAP nar karriarsidan ar verifierad.
                collection_method=CollectionMethod.JOBTECH,
                status=SourceStatus.MANUAL_ONLY,
                verified_at=dt.date.fromisoformat(rad["verified_at"]),
                verification_source=rad["verification_source"],
            )
        )
        skapade["authorities"] += 1

    session.flush()
    return skapade


def coverage(session: Session) -> dict:
    """Vad registret faktiskt tacker. Lases av GET /authorities/coverage.

    Finns for att gora luckorna synliga. Ett register dar 384 rader ar
    MANUAL_ONLY ska inte se ut som fullstandig bevakning.
    """
    rader = session.scalars(select(Authority)).all()
    per_status: dict[str, int] = {}
    per_plattform: dict[str, int] = {}
    for a in rader:
        per_status[a.status.value] = per_status.get(a.status.value, 0) + 1
        per_plattform[a.recruitment_platform.value] = (
            per_plattform.get(a.recruitment_platform.value, 0) + 1
        )
    per_typ: dict[str, int] = {}
    for org in session.scalars(select(Organisation)).all():
        per_typ[org.org_type.value] = per_typ.get(org.org_type.value, 0) + 1

    return {
        "authorities_total": len(rader),
        "by_status": per_status,
        "by_platform": per_plattform,
        "organisations_by_type": per_typ,
        "with_registrar_email": sum(1 for a in rader if a.registrar_email),
        "with_verified_careers_url": sum(1 for a in rader if a.careers_url),
        "with_verified_vacancies_url": sum(1 for a in rader if a.vacancies_url),
        "note": (
            "Organisationsnumren är skördade ur JobTech-annonser, inte gissade. "
            "En myndighet med status MANUAL_ONLY bevakas via Platsbanken men inte "
            "via sin egen karriärsida. Karriärsida och registratorsadress sätts "
            "först när någon verifierat dem, så tomma fält betyder att uppgiften "
            "inte är kontrollerad – inte att den saknas. Registret är inte "
            "komplett över samtliga statliga myndigheter; det täcker de som "
            "annonserat i Platsbanken."
        ),
    }
