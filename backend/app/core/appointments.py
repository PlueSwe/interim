"""Tillstandsmaskin for tillsattningsarenden.

Systemets svaraste del, eftersom det ratta svaret oftast ar "vi vet inte an".

Den centrala regeln: **en nedtagen annons betyder ingenting.** Tjansten kan ha
tillsatts, dragits tillbaka, forlangts, eller tillsatts internt utan att nagot
publicerats. Koden far darfor aldrig ga fran APPLICATION_CLOSED till nagot som
antyder en tillsattning utan ett dokument som sager det.

Spärrarna finns pa tre stallen med flit:

1. ALLOWED_TRANSITIONS -- vilka steg som alls ar mojliga.
2. Guard-funktionerna har -- vilka villkor som maste vara uppfyllda.
3. Check-villkor i databasen (se models/appointment.py) -- sista utposten, for
   den dag nagon skriver om den har filen.

Verifieringsnivaerna 1-5 ar inte en kvalitetsgradering utan en gräns. Niva 1-3
ar officiella kallor och far markeras som verifierad tillsattning. Niva 4, en
offentlig professionell presentation, ar ett uppslag: att nagon skrivit en ny
titel pa LinkedIn ar inte ett anstallningsbeslut. Niva 5 ar ett rykte. Varken 4
eller 5 far ge en rad i appointed_persons; de stannar som anteckning.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import (
    MAX_VERIFIED_LEVEL,
    Appointment,
    AppointmentPublicationMode,
    AppointmentStatus,
    AppointmentStatusHistory,
    Authority,
    JobAd,
)
from .timeutil import to_utc

S = AppointmentStatus

ALLOWED_TRANSITIONS: dict[AppointmentStatus, set[AppointmentStatus]] = {
    S.ADVERTISEMENT_FOUND: {S.APPLICATION_OPEN, S.APPLICATION_CLOSED, S.POSITION_CANCELLED},
    S.APPLICATION_OPEN: {S.APPLICATION_CLOSED, S.POSITION_CANCELLED},
    S.APPLICATION_CLOSED: {
        S.RECRUITMENT_ONGOING,
        S.APPOINTMENT_NOT_FOUND,
        S.APPOINTMENT_IDENTIFIED,
        S.REQUEST_READY,
        S.POSITION_CANCELLED,
    },
    S.RECRUITMENT_ONGOING: {
        S.APPOINTMENT_NOT_FOUND,
        S.APPOINTMENT_IDENTIFIED,
        S.REQUEST_READY,
        S.POSITION_CANCELLED,
        S.CLOSED_UNRESOLVED,
    },
    S.APPOINTMENT_NOT_FOUND: {
        S.REQUEST_READY,
        S.APPOINTMENT_IDENTIFIED,
        S.RECRUITMENT_ONGOING,
        S.CLOSED_UNRESOLVED,
        S.POSITION_CANCELLED,
    },
    S.REQUEST_READY: {S.REQUEST_SENT, S.APPOINTMENT_IDENTIFIED, S.CLOSED_UNRESOLVED},
    S.REQUEST_SENT: {S.RESPONSE_RECEIVED, S.CLOSED_UNRESOLVED},
    S.RESPONSE_RECEIVED: {
        S.APPOINTMENT_IDENTIFIED,
        S.POSITION_CANCELLED,
        S.CLOSED_UNRESOLVED,
        # En myndighet kan svara att beslutet anslas pa anslagstavlan. Da ar
        # arendet tillbaka till att vanta.
        S.REQUEST_READY,
    },
    S.APPOINTMENT_IDENTIFIED: {S.APPOINTMENT_VERIFIED, S.CLOSED_UNRESOLVED},
    # Slutstationer.
    S.APPOINTMENT_VERIFIED: set(),
    S.POSITION_CANCELLED: set(),
    S.CLOSED_UNRESOLVED: set(),
}

TERMINAL_STATES = {S.APPOINTMENT_VERIFIED, S.POSITION_CANCELLED, S.CLOSED_UNRESOLVED}

# Statusar som pastar att nagon fatt tjansten. Kraver dokument.
CLAIMS_APPOINTMENT = {S.APPOINTMENT_IDENTIFIED, S.APPOINTMENT_VERIFIED}

# Hur lange ett arende far sta i RECRUITMENT_ONGOING innan systemet slutar leta
# och foreslar en begaran. Tre manader ar normal handlaggningstid for en
# chefsrekrytering vid en myndighet.
ONGOING_PATIENCE_DAYS = 90
# Hur ofta det ar vart att leta efter beslut pa webben.
SEARCH_INTERVAL_DAYS = 7


class TransitionError(ValueError):
    """Overgangen ar inte tillaten, eller villkoren ar inte uppfyllda."""


@dataclass
class TransitionResult:
    appointment: Appointment
    changed: bool
    from_status: AppointmentStatus
    to_status: AppointmentStatus
    reason: str


def can_transition(current: AppointmentStatus, target: AppointmentStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition(
    session: Session,
    appointment: Appointment,
    target: AppointmentStatus,
    *,
    reason: str,
    changed_by: str = "SYSTEM",
    evidence_document_id: UUID | None = None,
    verification_level: int | None = None,
    appointed_person_id: UUID | None = None,
    decision_date: dt.date | None = None,
    start_date: dt.date | None = None,
    diary_number: str | None = None,
    now: dt.datetime | None = None,
) -> TransitionResult:
    """Flytta ett arende, eller vagra med ett begripligt skal."""
    nu = now or dt.datetime.now(dt.UTC)
    fran = appointment.status

    if fran is target:
        return TransitionResult(appointment, False, fran, target, "redan i det laget")

    if not can_transition(fran, target):
        tillatna = ", ".join(sorted(s.value for s in ALLOWED_TRANSITIONS.get(fran, set())))
        raise TransitionError(
            f"{fran.value} -> {target.value} är inte tillåten. "
            f"Tillåtna från {fran.value}: {tillatna or 'inga (slutstation)'}"
        )

    # Spärr 1: ett pastaende om tillsattning kraver ett dokument.
    if target in CLAIMS_APPOINTMENT:
        dokument = evidence_document_id or appointment.decision_document_id
        if dokument is None:
            raise TransitionError(
                f"{target.value} kräver ett dokument i public_documents. "
                f"Att annonsen försvunnit är inte ett belägg för att tjänsten är tillsatt."
            )

    # Spärr 2: verifierad kraver niva 1-3.
    if target is S.APPOINTMENT_VERIFIED:
        niva = verification_level or appointment.verification_level
        if niva is None:
            raise TransitionError("APPOINTMENT_VERIFIED kräver verifieringsnivå")
        if niva > MAX_VERIFIED_LEVEL:
            raise TransitionError(
                f"Verifieringsnivå {niva} räcker inte för APPOINTMENT_VERIFIED. "
                f"Bara nivå 1–{MAX_VERIFIED_LEVEL} (officiellt beslut, "
                f"myndighetsbekräftelse, registrators svar) får markeras som verifierad. "
                f"Nivå 4–5 är uppslag, inte belägg."
            )

    if target is S.APPOINTMENT_IDENTIFIED and appointed_person_id is None:
        # Inte ett fel -- en handling kan namna att tjansten ar tillsatt utan att
        # namnet gar att lasa ut. Men det ska sta i anteckningen.
        reason = f"{reason} (person inte utläst ur handlingen)"

    appointment.status = target
    appointment.status_changed_at = nu
    if evidence_document_id is not None:
        appointment.decision_document_id = evidence_document_id
    if verification_level is not None:
        appointment.verification_level = verification_level
    if appointed_person_id is not None:
        appointment.appointed_person_id = appointed_person_id
    if decision_date is not None:
        appointment.decision_date = decision_date
    if start_date is not None:
        appointment.start_date = start_date
    if diary_number is not None:
        appointment.diary_number = diary_number
    appointment.resolution_note = reason

    session.add(
        AppointmentStatusHistory(
            appointment_id=appointment.id,
            from_status=fran,
            to_status=target,
            changed_at=nu,
            changed_by=changed_by,
            reason=reason,
            evidence_document_id=evidence_document_id,
        )
    )
    session.flush()
    return TransitionResult(appointment, True, fran, target, reason)


def open_case(
    session: Session,
    job_ad: JobAd,
    authority: Authority | None = None,
    *,
    now: dt.datetime | None = None,
) -> Appointment:
    """Oppna ett arende for en annons, med rätt startlage efter deadline."""
    nu = now or dt.datetime.now(dt.UTC)
    arende = Appointment(
        job_ad_id=job_ad.id,
        authority_id=authority.id if authority else None,
        status=S.ADVERTISEMENT_FOUND,
        status_changed_at=nu,
        resolution_note=f"Annons hittad i {job_ad.source_key}.",
    )
    session.add(arende)
    session.flush()
    session.add(
        AppointmentStatusHistory(
            appointment_id=arende.id,
            from_status=None,
            to_status=S.ADVERTISEMENT_FOUND,
            changed_at=nu,
            changed_by="SYSTEM",
            reason=f"Annons hittad i {job_ad.source_key}.",
        )
    )
    session.flush()
    return arende


def evaluate(
    session: Session,
    appointment: Appointment,
    job_ad: JobAd,
    authority: Authority | None,
    *,
    now: dt.datetime | None = None,
) -> TransitionResult | None:
    """Flytta arendet dit fakta rackar, utan att gissa.

    Kors nattligen. Returnerar None nar ingenting andrats, vilket ar det normala
    och inte ett fel.
    """
    nu = now or dt.datetime.now(dt.UTC)
    if appointment.status in TERMINAL_STATES:
        return None

    # Vardena kan komma tillbaka ur databasen utan tidszon; se core/timeutil.py.
    deadline = to_utc(job_ad.application_deadline)
    avpublicerad = to_utc(job_ad.depublished_at)

    # Annonsen ar oppen.
    if appointment.status is S.ADVERTISEMENT_FOUND and deadline and deadline > nu:
        return transition(
            session,
            appointment,
            S.APPLICATION_OPEN,
            reason=f"Ansökningstiden är öppen till {deadline.date()}.",
            now=nu,
        )

    # Ansokningstiden har gatt ut.
    tiden_ute = (deadline is not None and deadline <= nu) or avpublicerad is not None
    if tiden_ute and appointment.status in (S.ADVERTISEMENT_FOUND, S.APPLICATION_OPEN):
        skal = (
            f"Sista ansökningsdag {deadline.date()} har passerat"
            if deadline
            else f"Annonsen avpublicerades {avpublicerad.date()}"
        )
        # Observera formuleringen: annonsen ar stangd. Ingenting sags om
        # tillsattning, eftersom ingenting ar kant om den.
        return transition(
            session,
            appointment,
            S.APPLICATION_CLOSED,
            reason=f"{skal}. Ingen uppgift om tillsättning.",
            now=nu,
        )

    # Stangd annons: hur gar vi vidare? Har avgor myndighetens publiceringssatt.
    if appointment.status is S.APPLICATION_CLOSED:
        lage = (
            authority.appointment_publication_mode
            if authority
            else AppointmentPublicationMode.UNKNOWN
        )
        if lage is AppointmentPublicationMode.PHYSICAL_NOTICE_BOARD:
            # Myndigheten anslar besluten pa en vagg. Det finns ingenting att
            # hitta pa webben, och att leta vore att slosa anrop pa en sida som
            # aldrig kommer att innehalla svaret.
            plats = authority.notice_board_location if authority else None
            return transition(
                session,
                appointment,
                S.REQUEST_READY,
                reason=(
                    "Myndigheten anslår anställningsbeslut på fysisk anslagstavla"
                    + (f" ({plats})" if plats else "")
                    + ". Beslutet gar inte att kontrollera digitalt, sa en begaran om "
                    "allmän handling är enda vägen. Utkast skapat, väntar på godkännande."
                ),
                now=nu,
            )
        return transition(
            session,
            appointment,
            S.RECRUITMENT_ONGOING,
            reason="Ansökningstiden är ute. Söker efter tillsättningsbeslut.",
            now=nu,
        )

    # Vi har letat lange nog.
    if appointment.status in (S.RECRUITMENT_ONGOING, S.APPOINTMENT_NOT_FOUND):
        dagar = (nu - to_utc(appointment.status_changed_at)).days
        if dagar >= ONGOING_PATIENCE_DAYS and appointment.status is S.RECRUITMENT_ONGOING:
            return transition(
                session,
                appointment,
                S.APPOINTMENT_NOT_FOUND,
                reason=(
                    f"Inget tillsättningsbeslut hittat på {dagar} dagar. "
                    f"Myndigheten publicerar inte beslutet där systemet kan läsa det."
                ),
                now=nu,
            )
        if appointment.status is S.APPOINTMENT_NOT_FOUND:
            return transition(
                session,
                appointment,
                S.REQUEST_READY,
                reason="Beslutet går inte att hitta publikt. Utkast till begäran skapat.",
                now=nu,
            )
    return None


def needs_web_search(appointment: Appointment, authority: Authority | None, *, now=None) -> bool:
    """Ar det vart att leta efter ett beslut pa webben nu?

    Nej for myndigheter som anslar fysiskt, nej for slutstationer, nej om vi
    letade nyligen. Att fraga det har i stallet for att leta varje natt ar
    skillnaden mellan hyfsad och pafrestande bevakning.
    """
    nu = now or dt.datetime.now(dt.UTC)
    if appointment.status in TERMINAL_STATES:
        return False
    if appointment.status not in (
        S.APPLICATION_CLOSED,
        S.RECRUITMENT_ONGOING,
        S.APPOINTMENT_NOT_FOUND,
        S.REQUEST_SENT,
    ):
        return False
    if authority and authority.appointment_publication_mode is (
        AppointmentPublicationMode.PHYSICAL_NOTICE_BOARD
    ):
        return False
    if appointment.last_searched_at is None:
        return True
    return (nu - to_utc(appointment.last_searched_at)).days >= SEARCH_INTERVAL_DAYS
