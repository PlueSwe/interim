"""Jobben. Skrivna som vanliga funktioner mot en session.

Anledningen till att de inte ar Celery-uppgifter direkt: de ska ga att kora fran
CLI och fran tester utan broker. tasks/celery_app.py lindar dem.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..core import appointments as appt
from ..core import foi
from ..core.decision_search import search_for_decision
from ..core.ingest import ingest_run
from ..models import (
    AppointedPerson,
    Appointment,
    AppointmentStatus,
    Authority,
    FrameworkAgreement,
    InformationRequest,
    JobAd,
    Notification,
    NotificationKind,
    NotificationStatus,
    Opportunity,
    Organisation,
    PublicDocument,
    SourceRegistry,
    SourceStatus,
)
from ..sources import get_adapter

# Hur nara en deadline ar nar det ar vart att paminna.
DEADLINE_WARNING_DAYS = 7
# Ramavtal som loper ut inom detta antal dagar ar en affarsmojlighet.
AGREEMENT_WARNING_DAYS = 365


def collect_source(session: Session, source_key: str, **kwargs) -> dict:
    """Kor en kalla och bearbeta resultatet."""
    adapter = get_adapter(source_key)
    resultat = adapter.run(**kwargs)
    korning, stats = ingest_run(session, resultat, triggered_by="schedule")
    return {
        "source": source_key,
        "status": korning.status.value,
        "found": stats.found,
        "new": stats.new,
        "changed": stats.changed,
        "duplicate": stats.duplicate,
        "irrelevant": stats.irrelevant,
        "excluded": stats.excluded,
        "review": stats.review,
        "errors": stats.errors,
    }


def collect_authority_pages(session: Session, *, limit: int = 20) -> dict:
    """Las karriarsidor for de myndigheter som ar verifierade.

    Bara ACTIVE-myndigheter med en vacancies_url. En myndighet vars sida inte
    ar verifierad lasas inte, eftersom resultatet da inte gar att lita pa.
    """
    rader = session.scalars(
        select(Authority)
        .where(Authority.status == SourceStatus.ACTIVE, Authority.vacancies_url.is_not(None))
        .order_by(Authority.last_checked_at.asc().nulls_first())
        .limit(limit)
    ).all()

    resultat = []
    for myndighet in rader:
        org = session.get(Organisation, myndighet.organisation_id)
        try:
            resultat.append(
                collect_source(
                    session,
                    "authority_pages",
                    url=myndighet.vacancies_url,
                    organisation_name=org.name if org else None,
                )
            )
        except Exception as e:
            resultat.append({"source": "authority_pages", "errors": 1, "detail": str(e)})
        myndighet.last_checked_at = dt.datetime.now(dt.UTC)
    session.flush()
    return {"checked": len(rader), "results": resultat}


def follow_up_appointments(
    session: Session, *, search_web: bool = True, limit: int = 50, now=None
) -> dict:
    """Folj upp rekryteringar som avslutats.

    Tva steg per arende: flytta tillstandet dit fakta rackar, och for de som
    behover det, leta efter ett beslut pa myndighetens webbplats.

    Hittas en kandidat skapas ett PublicDocument och arendet flyttas till
    APPOINTMENT_IDENTIFIED -- men bara nar kandidaten har verifieringsniva 1-3,
    och aldrig med ett namn som systemet gissat fram. Namnet laggs in av en
    manniska, eller av AI med citat ur handlingen.
    """
    nu = now or dt.datetime.now(dt.UTC)
    arenden = session.scalars(
        select(Appointment)
        .where(Appointment.status.not_in(list(appt.TERMINAL_STATES)))
        .order_by(Appointment.status_changed_at.asc())
        .limit(limit)
    ).all()

    flyttade, sokta, kandidater, begaranden = [], 0, 0, 0

    for arende in arenden:
        annons = session.get(JobAd, arende.job_ad_id)
        if annons is None:
            continue
        myndighet = session.get(Authority, arende.authority_id) if arende.authority_id else None

        # Steg 1: flytta sa langt fakta rackar. Flera overgangar kan behovas.
        for _ in range(4):
            resultat = appt.evaluate(session, arende, annons, myndighet, now=nu)
            if resultat is None or not resultat.changed:
                break
            flyttade.append(
                f"{annons.title[:45]}: {resultat.from_status.value} -> {resultat.to_status.value}"
            )

        # Steg 2: leta beslut pa webben.
        if search_web and appt.needs_web_search(arende, myndighet, now=nu):
            org = (
                session.get(Organisation, annons.organisation_id)
                if annons.organisation_id
                else None
            )
            utfall = search_for_decision(
                authority_website=(org.website if org else None),
                position_title=annons.title,
                published_at=annons.published_at,
            )
            sokta += 1
            arende.last_searched_at = utfall.searched_at

            anvandbara = [k for k in utfall.candidates if k.can_verify]
            kandidater += len(anvandbara)
            if anvandbara:
                bast = anvandbara[0]
                dokument = PublicDocument(
                    authority_id=arende.authority_id,
                    document_type=bast.document_type,
                    title=bast.title,
                    url=bast.url,
                    diary_number=bast.diary_number,
                    extracted_text=bast.quote,
                    acquisition="WEB_SEARCH",
                )
                session.add(dokument)
                session.flush()
                try:
                    resultat = appt.transition(
                        session,
                        arende,
                        AppointmentStatus.APPOINTMENT_IDENTIFIED,
                        reason=(
                            f"Kandidat hittad: {bast.reason}. Niva "
                            f"{bast.suggested_verification_level}. Namnet pa den anstallda "
                            f"ar inte utlast ur handlingen och maste bekraftas."
                        ),
                        evidence_document_id=dokument.id,
                        verification_level=bast.suggested_verification_level,
                        diary_number=bast.diary_number,
                        now=nu,
                    )
                    flyttade.append(
                        f"{annons.title[:45]}: {resultat.from_status.value} -> "
                        f"{resultat.to_status.value}"
                    )
                except appt.TransitionError:
                    # Overgangen var inte tillaten fran nuvarande lage. Dokumentet
                    # finns kvar for granskning; arendet star dar det star.
                    pass

        # Steg 3: skapa utkast till begaran nar arendet ar redo.
        if arende.status is AppointmentStatus.REQUEST_READY and myndighet is not None:
            finns = session.scalar(
                select(InformationRequest).where(InformationRequest.appointment_id == arende.id)
            )
            if finns is None:
                org = (
                    session.get(Organisation, annons.organisation_id)
                    if annons.organisation_id
                    else None
                )
                foi.create_request(
                    session,
                    appointment=arende,
                    job_ad=annons,
                    authority=myndighet,
                    organisation=org,
                )
                begaranden += 1
                _queue(
                    session,
                    NotificationKind.RECRUITMENT_CLOSED,
                    f"appt:{arende.id}",
                    f"Begaran redo: {annons.title}",
                    {"appointment_id": str(arende.id), "title": annons.title},
                    nu,
                )

    session.flush()
    return {
        "examined": len(arenden),
        "transitions": flyttade,
        "web_searches": sokta,
        "candidates_found": kandidater,
        "requests_drafted": begaranden,
    }


def check_deadlines(session: Session, *, now=None) -> dict:
    """Kolagg paminnelser om deadlines som narmar sig."""
    nu = now or dt.datetime.now(dt.UTC)
    grans = nu + dt.timedelta(days=DEADLINE_WARNING_DAYS)
    rader = session.execute(
        select(JobAd, Opportunity)
        .join(Opportunity, Opportunity.job_ad_id == JobAd.id)
        .where(
            JobAd.application_deadline.is_not(None),
            JobAd.application_deadline > nu,
            JobAd.application_deadline <= grans,
            JobAd.depublished_at.is_(None),
            Opportunity.exclusion_status != "EXCLUDED",
        )
    ).all()
    antal = 0
    for annons, uppdrag in rader:
        if _queue(
            session,
            NotificationKind.DEADLINE_APPROACHING,
            f"deadline:{annons.id}",
            f"Sista ansokningsdag {annons.application_deadline:%Y-%m-%d}: {annons.title}",
            {
                "job_ad_id": str(annons.id),
                "score": uppdrag.match_score,
                "deadline": annons.application_deadline.isoformat(),
            },
            nu,
        ):
            antal += 1
    session.flush()
    return {"found": len(rader), "queued": antal}


def check_framework_agreements(session: Session, *, now=None) -> dict:
    """Ramavtal som loper ut.

    Den starkaste tidiga signalen i hela systemet: ett ramavtal som narmar sig
    slutdatum betyder en kommande upphandling, och en kommande upphandling
    betyder ofta ett interimbehov hos den kopande myndigheten.
    """
    nu = now or dt.datetime.now(dt.UTC)
    grans = (nu + dt.timedelta(days=AGREEMENT_WARNING_DAYS)).date()
    avtal = session.scalars(
        select(FrameworkAgreement).where(
            FrameworkAgreement.valid_to.is_not(None),
            FrameworkAgreement.valid_to <= grans,
            FrameworkAgreement.valid_to >= nu.date(),
        )
    ).all()
    antal = 0
    for a in avtal:
        if _queue(
            session,
            NotificationKind.FRAMEWORK_AGREEMENT_EXPIRING,
            f"fa:{a.id}",
            f"Ramavtal loper ut {a.valid_to}: {a.name}",
            {"framework_agreement_id": str(a.id), "valid_to": a.valid_to.isoformat()},
            nu,
        ):
            antal += 1
    session.flush()
    return {"found": len(avtal), "queued": antal}


def check_source_health(session: Session, *, now=None) -> dict:
    """Avisera om kallor som slutat svara."""
    nu = now or dt.datetime.now(dt.UTC)
    trasiga = session.scalars(
        select(SourceRegistry).where(SourceRegistry.status == SourceStatus.FAILING)
    ).all()
    for k in trasiga:
        _queue(
            session,
            NotificationKind.SOURCE_FAILING,
            f"src:{k.key}:{nu:%Y-%W}",  # en avisering per kalla och vecka
            f"Kallan {k.key} svarar inte: {(k.last_error or '')[:120]}",
            {"source_key": k.key, "failures": k.consecutive_failures},
            nu,
        )
    session.flush()
    return {"failing": [k.key for k in trasiga]}


def enforce_retention(session: Session, *, dry_run: bool = False, now=None) -> dict:
    """Radera personuppgifter som passerat lagringstiden.

    SECURITY.md: beslutsdatum + 5 ar. Arendet och handlingen behalls, men namnet
    tas bort och resolution_note skrivs om sa att det gar att se att raden
    raderats enligt rutin och inte forsvunnit av misstag.
    """
    nu = now or dt.datetime.now(dt.UTC)
    personer = session.scalars(
        select(AppointedPerson).where(AppointedPerson.retention_until < nu.date())
    ).all()
    raderade = []
    for person in personer:
        raderade.append({"id": str(person.id), "retention_until": str(person.retention_until)})
        if dry_run:
            continue
        for arende in session.scalars(
            select(Appointment).where(Appointment.appointed_person_id == person.id)
        ).all():
            arende.appointed_person_id = None
            arende.resolution_note = (
                arende.resolution_note or ""
            ) + f" [Personuppgift raderad {nu.date()} enligt lagringstid.]"
        session.delete(person)
    session.flush()
    return {
        "expired": len(personer),
        "deleted": 0 if dry_run else len(personer),
        "dry_run": dry_run,
        "details": raderade,
    }


def send_notifications(session: Session, *, limit: int = 50) -> dict:
    """Skicka koade aviseringar.

    Utan SMTP-uppgifter skickas ingenting och raderna star kvar som QUEUED. Det
    ar avsiktligt: en avisering som tysts bort ar varre an en som vantar.
    """
    if not settings.smtp_host or not settings.notify_to:
        antal = session.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.status == NotificationStatus.QUEUED)
        )
        return {
            "sent": 0,
            "queued": antal,
            "note": "SMTP_HOST eller NOTIFY_TO saknas. Aviseringarna star kvar i kon.",
        }

    import smtplib
    from email.message import EmailMessage

    koade = session.scalars(
        select(Notification)
        .where(Notification.status == NotificationStatus.QUEUED)
        .order_by(Notification.queued_at)
        .limit(limit)
    ).all()

    skickade, fel = 0, 0
    for avisering in koade:
        try:
            mejl = EmailMessage()
            mejl["Subject"] = f"[Interim Radar] {avisering.subject}"
            mejl["From"] = settings.notify_from
            mejl["To"] = settings.notify_to
            mejl.set_content(
                f"{avisering.subject}\n\n"
                + "\n".join(f"{k}: {v}" for k, v in (avisering.payload or {}).items())
            )
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
                server.starttls()
                if settings.smtp_user and settings.smtp_password:
                    server.login(settings.smtp_user, settings.smtp_password.get_secret_value())
                server.send_message(mejl)
            avisering.status = NotificationStatus.SENT
            avisering.sent_at = dt.datetime.now(dt.UTC)
            skickade += 1
        except Exception as e:
            avisering.attempts += 1
            avisering.error = f"{type(e).__name__}: {e}"
            if avisering.attempts >= 5:
                avisering.status = NotificationStatus.FAILED
            fel += 1
    session.flush()
    return {"sent": skickade, "errors": fel}


def _queue(session: Session, kind, dedupe_key: str, subject: str, payload: dict, nu) -> bool:
    """Kolagg en avisering. False nar den redan finns."""
    if session.scalar(
        select(Notification).where(Notification.kind == kind, Notification.dedupe_key == dedupe_key)
    ):
        return False
    session.add(
        Notification(
            kind=kind,
            dedupe_key=dedupe_key,
            subject=subject,
            payload=payload,
            queued_at=nu,
        )
    )
    return True
