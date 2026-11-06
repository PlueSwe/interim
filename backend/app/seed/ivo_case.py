"""IVO-testarendet.

Bestallningens obligatoriska testarende: IVO:s verksamhetsomradeschef
Digitalisering och IT, publicerad 2026-08-20, sista ansokningsdag 2026-09-20,
rekryteringen hanterad med hjalp av Poolia.

Annonsen ar **verklig** och hamtad fran kallan, inte skriven av hand. Den ligger
i data/snapshots/ivo-vochef-digitalisering-it-2026-08-20.json, hamtad fran
JobTechs historiska API 2026-11-06, annons-id
a39c3a5d587a793cd6fbbef95cdf635a8bd83268, sha256
d5e2a3b5d0708ccccf0c2e08d987749089323cf958c1b4c74270717e65811e64.

Vad annonsen bekraftade, och alltsa inte behover tas pa tro:

  publicerad          2026-08-20T13:25:44
  sista ansokningsdag 2026-09-20T23:59:59
  yrkesbegrepp        Chief Digital Officer/CDO
  arbetsplats         Solnavagen 4/Torsplan, 11365 Stockholm
  anstallningsform    tillsvidare med sex manaders provanstallning
  sista raden         "Den har rekryteringen hanteras med hjalp av Poolia."

Vad som INTE ar verifierat mot kallan:

  Att IVO anslar anstallningsbeslut pa sin fysiska anslagstavla vid Torsplan.
  Den uppgiften kommer fran anvandarens underlag. Jag hittade inget stod for
  den pa ivo.se vid kontrollen 2026-11-06. Annonsens arbetsplatsadress
  bekraftar att IVO sitter vid Torsplan, men inte att besluten anslas dar.
  Darfor star uppgiften i databasen med sin harkomst angiven, och inte som ett
  faktum systemet sjalvt har kontrollerat.

Och det viktigaste: **vem som fick tjansten star inte i systemet.** Inte som
tom strang, inte som gissning, inte som "sannolikt". Arendet hamnar i
REQUEST_READY med ett fardigt utkast till registrator@ivo.se, och dar star det
tills en manniska skickar begaran och registrerar svaret. Det ar inte ett
ofullstandigt test. Det ar testets resultat.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import appointments as appt
from ..core import foi
from ..core.exclusion import assess
from ..core.ingest import IngestStats, ingest_item
from ..core.matching import score_opportunity
from ..models import (
    Appointment,
    AppointmentPublicationMode,
    AppointmentStatus,
    Authority,
    CollectionMethod,
    InformationRequest,
    JobAd,
    Opportunity,
    Organisation,
    OrgType,
    Provider,
    RecruitmentPlatform,
    SourceStatus,
)
from ..sources.jobtech import _to_raw_item

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "snapshots"
    / "ivo-vochef-digitalisering-it-2026-08-20.json"
)

AD_ID = "a39c3a5d587a793cd6fbbef95cdf635a8bd83268"
IVO_ORGNR = "2021006537"
# Myndighetens namn som det stavas av myndigheten sjalv. JobTech har tva
# varianter, varav en i Titelkasus ("Inspektionen För Vård och Omsorg"). Den
# varianten duger i en traffista men inte i ett brev till registrator, sa namnet
# satts om har aven nar skorden redan skapat organisationen.
IVO_NAME = "Inspektionen för vård och omsorg"

# Verifierad pa https://www.ivo.se/kontakt/ 2026-11-06.
IVO_REGISTRAR = "registrator@ivo.se"

NOTICE_BOARD = "Torsplan, Solnavägen 4, Stockholm"
NOTICE_BOARD_PROVENANCE = (
    "Uppgift från användarens underlag, inte verifierad mot ivo.se 2026-11-06. "
    "Annonsens arbetsplatsadress (Solnavägen 4/Torsplan) bekräftar att IVO sitter "
    "vid Torsplan, men inte att anställningsbeslut anslås där."
)

# Befattningen som den star i annonstexten. Rubriken sager bara
# "Verksamhetsomradeschef"; vilket verksamhetsomrade framgar av forsta raden i
# beskrivningen. Det ar den som ska sta i begaran till registrator.
POSITION_TITLE = "verksamhetsområdeschef digitalisering och IT"


def load_snapshot() -> dict:
    if not SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"{SNAPSHOT_PATH} saknas. Hamta annonsen med:\n  python -m app.cli fetch-ad {AD_ID}"
        )
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def seed_ivo_case(session: Session, *, now: dt.datetime | None = None) -> dict:
    """Lagg in arendet och kor hela arbetsflodet pa det.

    Idempotent: kors den igen returneras det befintliga arendet.
    """
    nu = now or dt.datetime.now(dt.UTC)
    annons_data = load_snapshot()

    # --- Organisation och myndighet ---
    org = session.scalar(select(Organisation).where(Organisation.org_number == IVO_ORGNR))
    if org is None:
        org = Organisation(
            name=IVO_NAME,
            org_number=IVO_ORGNR,
            org_type=OrgType.STATE_AGENCY,
            website="https://www.ivo.se/",
        )
        session.add(org)
        session.flush()

    myndighet = session.scalar(select(Authority).where(Authority.organisation_id == org.id))
    if myndighet is None:
        myndighet = Authority(organisation_id=org.id)
        session.add(myndighet)
    org.name = IVO_NAME
    myndighet.careers_url = "https://www.ivo.se/om-ivo/arbeta-hos-oss/"
    myndighet.registrar_email = IVO_REGISTRAR
    myndighet.postal_address = "Box 45184, 104 30 Stockholm"
    myndighet.recruitment_platform = RecruitmentPlatform.PLATSBANKEN_ONLY
    myndighet.collection_method = CollectionMethod.JOBTECH
    # Detta falt ar vad som gor att arendet gar direkt till REQUEST_READY i
    # stallet for att systemet noter pa ivo.se i manader.
    myndighet.appointment_publication_mode = AppointmentPublicationMode.PHYSICAL_NOTICE_BOARD
    myndighet.notice_board_location = NOTICE_BOARD
    myndighet.status = SourceStatus.ACTIVE
    myndighet.verified_at = dt.date(2026, 11, 6)
    myndighet.verification_source = (
        f"Registratorsadress verifierad pa https://www.ivo.se/kontakt/ 2026-11-06. "
        f"Anslagstavla: {NOTICE_BOARD_PROVENANCE}"
    )
    session.flush()

    # --- Formedlare ---
    # Sista raden i annonsen: "Den har rekryteringen hanteras med hjalp av Poolia."
    poolia = session.scalar(select(Provider).where(Provider.name == "Poolia"))
    if poolia is None:
        poolia = Provider(
            name="Poolia",
            website="https://www.poolia.se/",
            note="Angiven i IVO-annonsens sista rad som rekryteringsstod.",
        )
        session.add(poolia)
        session.flush()

    # --- Annonsen ---
    befintlig = session.scalar(
        select(JobAd).where(JobAd.source_key == "jobtech_hist", JobAd.external_id == AD_ID)
    )
    if befintlig is None:
        post = _to_raw_item(annons_data, historical=True)
        post.recruiter_name = "Poolia"
        stats = IngestStats()
        annons = ingest_item(session, post, "jobtech_hist", stats=stats, now=nu)
        if annons is None:
            raise RuntimeError(
                "IVO-annonsen klassades som icke-relevant. Det ar ett fel i "
                "core/classify.py, inte i datan."
            )
    else:
        annons = befintlig

    uppdrag = session.scalar(select(Opportunity).where(Opportunity.job_ad_id == annons.id))
    arende = session.scalar(select(Appointment).where(Appointment.job_ad_id == annons.id))
    if arende is None:
        arende = appt.open_case(session, annons, myndighet, now=nu)

    # --- Kor arbetsflodet tills det stannar ---
    # Flera overgangar i foljd: ADVERTISEMENT_FOUND -> APPLICATION_CLOSED ->
    # REQUEST_READY. Loopen kors tills ingenting mer andras.
    steg = []
    for _ in range(6):
        resultat = appt.evaluate(session, arende, annons, myndighet, now=nu)
        if resultat is None or not resultat.changed:
            break
        steg.append(f"{resultat.from_status.value} -> {resultat.to_status.value}")

    # --- Begaran om allman handling ---
    begaran = session.scalar(
        select(InformationRequest).where(InformationRequest.appointment_id == arende.id)
    )
    if begaran is None and arende.status is AppointmentStatus.REQUEST_READY:
        begaran = foi.create_request(
            session,
            appointment=arende,
            job_ad=annons,
            authority=myndighet,
            organisation=org,
            position_title=POSITION_TITLE,
        )

    session.flush()
    return {
        "job_ad_id": str(annons.id),
        "ad_external_id": AD_ID,
        "title": annons.title,
        "position_title": POSITION_TITLE,
        "published_at": annons.published_at.isoformat() if annons.published_at else None,
        "application_deadline": annons.application_deadline.isoformat()
        if annons.application_deadline
        else None,
        "depublished_at": annons.depublished_at.isoformat() if annons.depublished_at else None,
        "occupation_label": annons.occupation_label,
        "employment_type": annons.employment_type.value,
        "role_family": annons.role_family.value,
        "recruiter": "Poolia",
        "exclusion_status": uppdrag.exclusion_status.value if uppdrag else None,
        "match_score": uppdrag.match_score if uppdrag else None,
        "appointment_id": str(arende.id),
        "appointment_status": arende.status.value,
        "transitions": steg,
        "resolution_note": arende.resolution_note,
        "appointed_person": None,  # och det ar poangen
        "verification_level": arende.verification_level,
        "information_request_id": str(begaran.id) if begaran else None,
        "information_request_status": begaran.status.value if begaran else None,
        "information_request_recipient": begaran.recipient_email if begaran else None,
        "notice_board": NOTICE_BOARD,
        "notice_board_provenance": NOTICE_BOARD_PROVENANCE,
    }


def describe(session: Session) -> dict:
    """Las upp arendet som det star nu. Anvands av app.cli ivo-case --show."""
    annons = session.scalar(
        select(JobAd).where(JobAd.source_key == "jobtech_hist", JobAd.external_id == AD_ID)
    )
    if annons is None:
        return {"error": "IVO-arendet ar inte seedat. Kor: python -m app.cli seed"}
    arende = session.scalar(select(Appointment).where(Appointment.job_ad_id == annons.id))
    uppdrag = session.scalar(select(Opportunity).where(Opportunity.job_ad_id == annons.id))
    begaran = (
        session.scalar(
            select(InformationRequest).where(InformationRequest.appointment_id == arende.id)
        )
        if arende
        else None
    )
    bedomning = assess(annons.description, title=annons.title)
    # Samma profil som insamlingen anvander, annars ger describe en annan poang
    # an den som star pa uppdraget och det ser ut som en bugg.
    from ..models import ConsultantProfile

    profil = session.scalar(select(ConsultantProfile).where(ConsultantProfile.is_active.is_(True)))
    poang = score_opportunity(
        title=annons.title,
        description=annons.description,
        role_family=annons.role_family,
        employment_type=annons.employment_type,
        occupation_label=annons.occupation_label,
        municipality=annons.workplace_municipality,
        region=annons.workplace_region,
        profile_weights=(profil.weights if profil else None),
        profile_preferences=(profil.preferences if profil else None),
    )
    return {
        "ad": {
            "external_id": annons.external_id,
            "title": annons.title,
            "position": POSITION_TITLE,
            "published_at": str(annons.published_at),
            "application_deadline": str(annons.application_deadline),
            "depublished_at": str(annons.depublished_at),
            "occupation_label": annons.occupation_label,
            "url": annons.url,
            "workplace": annons.workplace_address,
        },
        "exclusion": {"verdict": bedomning.verdict.value, "reason": bedomning.reason},
        "matching": {"score": poang.score, "confidence": poang.confidence},
        "opportunity_status": uppdrag.status.value if uppdrag else None,
        "appointment": {
            "status": arende.status.value if arende else None,
            "resolution_note": arende.resolution_note if arende else None,
            "appointed_person": None,
            "verification_level": arende.verification_level if arende else None,
            "history": [
                f"{h.changed_at:%Y-%m-%d %H:%M} {h.from_status or 'START'}"
                f" -> {h.to_status}: {h.reason}"
                for h in sorted(arende.history, key=lambda h: h.changed_at)
            ]
            if arende
            else [],
        },
        "information_request": {
            "status": begaran.status.value,
            "recipient": begaran.recipient_email,
            "subject": begaran.subject,
            "body": begaran.body,
            "approved_by": str(begaran.approved_by_user_id)
            if begaran.approved_by_user_id
            else None,
            "sent_at": str(begaran.sent_at) if begaran.sent_at else None,
        }
        if begaran
        else None,
    }
