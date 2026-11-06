"""Tillsattningar, begaranden om allman handling och personuppgifter.

Den del av API:et dar det gar att gora skada. Reglerna:

- Ett namn gar inte att lagga in utan att peka pa en handling.
- Verifieringsniva 4-5 ger ingen personpost, bara en anteckning.
- En begaran kan inte skickas utan att en ADMIN godkant den.
- Varje atgard har hamnar i audit_logs.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..core import appointments as appt
from ..core import foi
from ..core.decision_search import search_for_decision
from ..deps import AdminUser, CurrentUser, SessionDep, write_audit
from ..models import (
    MAX_VERIFIED_LEVEL,
    VERIFICATION_LEVELS,
    AppointedPerson,
    Appointment,
    AppointmentStatus,
    Authority,
    InformationRequest,
    JobAd,
    LegalBasis,
    Organisation,
    PublicDocument,
    RequestStatus,
)
from ..schemas import (
    AppointmentDetail,
    AppointmentHistoryOut,
    AppointmentOut,
    DocumentIn,
    DocumentOut,
    IdentifyPersonIn,
    InformationRequestOut,
    JobAdOut,
    MarkSentIn,
    RegisterResponseIn,
    RequestPatch,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _authority_name(session: Session, authority_id: uuid.UUID | None) -> str | None:
    if authority_id is None:
        return None
    myndighet = session.get(Authority, authority_id)
    if myndighet is None:
        return None
    org = session.get(Organisation, myndighet.organisation_id)
    return org.name if org else None


def _out(session: Session, arende: Appointment) -> AppointmentOut:
    data = AppointmentOut.model_validate(arende)
    annons = session.get(JobAd, arende.job_ad_id)
    if annons:
        ad = JobAdOut.model_validate(annons)
        org = session.get(Organisation, annons.organisation_id) if annons.organisation_id else None
        ad.organisation_name = org.name if org else None
        data.job_ad = ad
    data.authority_name = _authority_name(session, arende.authority_id)
    if arende.verification_level:
        data.verification_label = VERIFICATION_LEVELS.get(arende.verification_level)

    # Namnet lamnas bara ut nar tillsattningen ar verifierad. Ett arende som
    # star i APPOINTMENT_IDENTIFIED med niva 2 har en kandidat, inte ett svar,
    # och granssnittet ska inte visa den som faktum.
    if arende.status is AppointmentStatus.APPOINTMENT_VERIFIED and arende.appointed_person_id:
        person = session.get(AppointedPerson, arende.appointed_person_id)
        if person:
            data.appointed_person_name = person.full_name
            data.appointed_person_previous_role = person.previous_role
    return data


@router.get("", response_model=dict)
def list_appointments(
    session: SessionDep,
    user: CurrentUser,
    status_filter: AppointmentStatus | None = Query(None, alias="status"),
    unresolved_only: bool = False,
    authority_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    fraga = select(Appointment)
    if status_filter is not None:
        fraga = fraga.where(Appointment.status == status_filter)
    if unresolved_only:
        # Arenden dar vi inte vet vem som fick tjansten. Detta ar listan som
        # faktiskt ar vard att titta pa.
        fraga = fraga.where(
            Appointment.status.in_(
                [
                    AppointmentStatus.APPOINTMENT_NOT_FOUND,
                    AppointmentStatus.REQUEST_READY,
                    AppointmentStatus.REQUEST_SENT,
                    AppointmentStatus.RESPONSE_RECEIVED,
                    AppointmentStatus.CLOSED_UNRESOLVED,
                ]
            )
        )
    if authority_id is not None:
        fraga = fraga.where(Appointment.authority_id == authority_id)

    total = session.scalar(select(func.count()).select_from(fraga.subquery()))
    rader = session.scalars(
        fraga.order_by(Appointment.status_changed_at.desc()).limit(limit).offset(offset)
    ).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_out(session, a) for a in rader],
    }


@router.get("/{appointment_id}", response_model=AppointmentDetail)
def get_appointment(appointment_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")
    data = AppointmentDetail.model_validate(_out(session, arende).model_dump())
    data.history = [
        AppointmentHistoryOut.model_validate(h)
        for h in sorted(arende.history, key=lambda h: h.changed_at)
    ]
    begaran = session.scalar(
        select(InformationRequest).where(InformationRequest.appointment_id == arende.id)
    )
    data.information_request_id = begaran.id if begaran else None
    if arende.decision_document_id:
        dok = session.get(PublicDocument, arende.decision_document_id)
        data.decision_document_url = dok.url if dok else None
    return data


@router.post("/{appointment_id}/search-decision", response_model=dict)
def search_decision(appointment_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    """Leta efter ett tillsattningsbeslut nu, pa begaran.

    Returnerar kandidater for granskning. Flyttar inte arendet och namnger
    ingen; det kraver /identify med en handling.
    """
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")
    annons = session.get(JobAd, arende.job_ad_id)
    org = (
        session.get(Organisation, annons.organisation_id)
        if annons and annons.organisation_id
        else None
    )
    myndighet = session.get(Authority, arende.authority_id) if arende.authority_id else None

    if myndighet and myndighet.appointment_publication_mode.value == "PHYSICAL_NOTICE_BOARD":
        return {
            "searched": False,
            "reason": (
                f"{org.name if org else 'Myndigheten'} anslar anstallningsbeslut pa "
                f"fysisk anslagstavla"
                + (
                    f" ({myndighet.notice_board_location})"
                    if myndighet.notice_board_location
                    else ""
                )
                + ". Beslutet finns inte digitalt; en begaran om allman handling ar vagen."
            ),
            "candidates": [],
        }

    utfall = search_for_decision(
        authority_website=(org.website if org else None),
        position_title=(annons.title if annons else ""),
        published_at=(annons.published_at if annons else None),
    )
    arende.last_searched_at = utfall.searched_at
    session.commit()
    return {
        "searched": True,
        "pages_checked": utfall.pages_checked,
        "skipped_reason": utfall.skipped_reason,
        "candidates": [
            {
                "url": k.url,
                "title": k.title,
                "document_type": k.document_type.value,
                "verification_level": k.suggested_verification_level,
                "verification_label": VERIFICATION_LEVELS.get(k.suggested_verification_level),
                "can_verify": k.can_verify,
                "reason": k.reason,
                "quote": k.quote,
                "diary_number": k.diary_number,
            }
            for k in utfall.candidates
        ],
    }


@router.post("/{appointment_id}/identify", response_model=AppointmentDetail)
def identify_person(
    appointment_id: uuid.UUID,
    data: IdentifyPersonIn,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Registrera vem som fick tjansten.

    Kraver en handling i public_documents. Niva 4-5 ger ingen personpost: da
    skrivs uppgiften som anteckning pa arendet utan namn, enligt SECURITY.md.
    Ett LinkedIn-fynd ar ett uppslag, inte ett belagg.
    """
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")

    dokument = session.get(PublicDocument, data.document_id)
    if dokument is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "document_id pekar inte på någon handling. En tillsättning kan inte "
            "registreras utan den handling uppgiften kommer ur.",
        )

    if data.verification_level > MAX_VERIFIED_LEVEL:
        # Ingen personpost. Arendet far en anteckning och stannar.
        arende.resolution_note = (
            f"Uppgift pa niva {data.verification_level} "
            f"({VERIFICATION_LEVELS[data.verification_level]}): se {dokument.url}. "
            f"Racker inte som belagg; inget namn registrerat."
        )
        arende.verification_level = data.verification_level
        arende.last_searched_at = dt.datetime.now(dt.UTC)
        write_audit(
            session,
            user=admin,
            action="identify_rejected_low_level",
            object_type="appointment",
            object_id=str(arende.id),
            after={"verification_level": data.verification_level},
            request=request,
        )
        session.commit()
        return get_appointment(appointment_id, session, admin)

    beslutsdatum = data.decision_date or dokument.document_date or dt.date.today()
    person = AppointedPerson(
        full_name=data.full_name,
        previous_role=data.previous_role,
        previous_organisation=data.previous_organisation,
        legal_basis=(
            LegalBasis.PUBLIC_DOCUMENT
            if data.verification_level <= 2
            else LegalBasis.LEGITIMATE_INTEREST
        ),
        source_document_id=dokument.id,
        retention_until=beslutsdatum.replace(
            year=beslutsdatum.year + settings.person_retention_years
        ),
    )
    session.add(person)
    session.flush()

    try:
        appt.transition(
            session,
            arende,
            AppointmentStatus.APPOINTMENT_IDENTIFIED,
            reason=f"Tillsattning registrerad ur {dokument.document_type.value}.",
            changed_by=f"USER:{admin.email}",
            evidence_document_id=dokument.id,
            verification_level=data.verification_level,
            appointed_person_id=person.id,
            decision_date=data.decision_date,
            start_date=data.start_date,
            diary_number=data.diary_number,
        )
        appt.transition(
            session,
            arende,
            AppointmentStatus.APPOINTMENT_VERIFIED,
            reason=(
                f"Verifierad pa niva {data.verification_level}: "
                f"{VERIFICATION_LEVELS[data.verification_level]}."
            ),
            changed_by=f"USER:{admin.email}",
            evidence_document_id=dokument.id,
            verification_level=data.verification_level,
        )
    except appt.TransitionError as e:
        session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None

    write_audit(
        session,
        user=admin,
        action="identify_person",
        object_type="appointment",
        object_id=str(arende.id),
        after={
            "verification_level": data.verification_level,
            "document_id": str(dokument.id),
            "legal_basis": person.legal_basis.value,
            "retention_until": str(person.retention_until),
        },
        request=request,
    )
    session.commit()
    return get_appointment(appointment_id, session, admin)


@router.post("/{appointment_id}/close-unresolved", response_model=AppointmentDetail)
def close_unresolved(
    appointment_id: uuid.UUID,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
    reason: str = Query(..., min_length=5),
):
    """Avsluta ett arende utan svar. Ett giltigt och vanligt utfall."""
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")
    try:
        appt.transition(
            session,
            arende,
            AppointmentStatus.CLOSED_UNRESOLVED,
            reason=reason,
            changed_by=f"USER:{admin.email}",
        )
    except appt.TransitionError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None
    write_audit(
        session,
        user=admin,
        action="close_unresolved",
        object_type="appointment",
        object_id=str(arende.id),
        after={"reason": reason},
        request=request,
    )
    session.commit()
    return get_appointment(appointment_id, session, admin)


@router.get("/{appointment_id}/appointed-person")
def get_appointed_person(appointment_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    """Personposten for ett arende, eller null.

    Finns for att en rattelse och en radering behover radens id. Namnet lamnas
    ut pa samma villkor som i AppointmentOut: bara nar tillsattningen ar
    verifierad. Ar den inte det far man id och rattighetsuppgifterna, vilket ar
    det raderingen behover.
    """
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")
    if arende.appointed_person_id is None:
        return None
    person = session.get(AppointedPerson, arende.appointed_person_id)
    if person is None:
        return None
    verifierad = arende.status is AppointmentStatus.APPOINTMENT_VERIFIED
    return {
        "id": str(person.id),
        "full_name": person.full_name if verifierad else None,
        "previous_role": person.previous_role if verifierad else None,
        "previous_organisation": person.previous_organisation if verifierad else None,
        "source_document_id": str(person.source_document_id),
        "legal_basis": person.legal_basis.value
        if hasattr(person.legal_basis, "value")
        else str(person.legal_basis),
        "retention_until": person.retention_until.isoformat() if person.retention_until else None,
    }


# --- Handlingar -------------------------------------------------------------


def _document_out(dokument: PublicDocument) -> DocumentOut:
    data = DocumentOut.model_validate(dokument)
    # Texten kan vara lang och behovs inte i en lista. Att den finns behovs.
    data.has_text = bool(dokument.extracted_text)
    return data


@router.get("/{appointment_id}/documents", response_model=list[DocumentOut])
def list_documents(appointment_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    """Handlingar som kan bevisa den har tillsattningen.

    Handlingar hanger pa myndigheten och inte pa arendet, eftersom ett
    anstallningsbeslut ofta kommer i en samling tillsammans med andra. Listan
    ar darfor myndighetens handlingar, nyast forst, och det ar anvandaren som
    valjer vilken som galler tjansten.
    """
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")
    rader = session.scalars(
        select(PublicDocument)
        .where(PublicDocument.authority_id == arende.authority_id)
        .order_by(PublicDocument.created_at.desc())
        .limit(100)
    ).all()
    return [_document_out(d) for d in rader]


@router.post("/{appointment_id}/documents", response_model=DocumentOut, status_code=201)
def add_document(
    appointment_id: uuid.UUID,
    data: DocumentIn,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Registrera en handling som hamtats for hand.

    Det har ar vagen in for en myndighet som anslar anstallningsbeslut pa en
    fysisk anslagstavla. Utan den skulle just de arendena sta olosta for
    alltid, oavsett hur bra webbsokningen blev.

    Handlingen registreras som den ar. Den flyttar inte arendet och namnger
    ingen -- det gors med /identify, som kraver handlingens id.
    """
    arende = session.get(Appointment, appointment_id)
    if arende is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ärendet finns inte.")

    dokument = PublicDocument(
        authority_id=arende.authority_id,
        document_type=data.document_type,
        title=data.title,
        url=data.url,
        diary_number=data.diary_number,
        document_date=data.document_date,
        extracted_text=data.extracted_text,
        acquisition=data.acquisition,
    )
    session.add(dokument)
    session.flush()
    write_audit(
        session,
        user=admin,
        action="document_add_manual",
        object_type="public_document",
        object_id=str(dokument.id),
        after={
            "appointment_id": str(appointment_id),
            "document_type": data.document_type.value,
            "acquisition": data.acquisition,
            "diary_number": data.diary_number,
        },
        request=http_request,
    )
    session.commit()
    return _document_out(dokument)


# --- Begaranden om allman handling -----------------------------------------

requests_router = APIRouter(prefix="/information-requests", tags=["appointments"])


@requests_router.get("", response_model=dict)
def list_requests(
    session: SessionDep,
    user: CurrentUser,
    status_filter: RequestStatus | None = Query(None, alias="status"),
):
    fraga = select(InformationRequest)
    if status_filter is not None:
        fraga = fraga.where(InformationRequest.status == status_filter)
    rader = session.scalars(fraga.order_by(InformationRequest.created_at.desc())).all()
    return {
        "total": len(rader),
        "items": [InformationRequestOut.model_validate(r) for r in rader],
    }


@requests_router.get("/{request_id}", response_model=InformationRequestOut)
def get_request(request_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    begaran = session.get(InformationRequest, request_id)
    if begaran is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Begäran finns inte.")
    return begaran


@requests_router.patch("/{request_id}", response_model=InformationRequestOut)
def patch_request(
    request_id: uuid.UUID,
    data: RequestPatch,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Redigera utkastet. Bara medan det ar DRAFT.

    Ett godkant eller skickat utkast gar inte att andra. Annars skulle
    audit-loggen visa en annan text an den som faktiskt skickades.
    """
    begaran = session.get(InformationRequest, request_id)
    if begaran is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Begäran finns inte.")
    if begaran.status is not RequestStatus.DRAFT:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Bara utkast kan redigeras. Denna har status {begaran.status.value}.",
        )
    fore = {"subject": begaran.subject, "recipient": begaran.recipient_email}
    for falt, varde in data.model_dump(exclude_unset=True).items():
        if varde is not None:
            setattr(begaran, falt, varde)
    write_audit(
        session,
        user=admin,
        action="request_edit",
        object_type="information_request",
        object_id=str(begaran.id),
        before=fore,
        after={"subject": begaran.subject, "recipient": begaran.recipient_email},
        request=http_request,
    )
    session.commit()
    return begaran


@requests_router.post("/{request_id}/approve", response_model=InformationRequestOut)
def approve_request(
    request_id: uuid.UUID, http_request: Request, session: SessionDep, admin: AdminUser
):
    """Godkann utkastet. Kravs innan det kan skickas.

    Hela textens innehall hamnar i audit_logs. Det som godkanns ar den texten
    och ingen annan.
    """
    begaran = session.get(InformationRequest, request_id)
    if begaran is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Begäran finns inte.")
    try:
        foi.approve(session, begaran, user_id=admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
    write_audit(
        session,
        user=admin,
        action="request_approve",
        object_type="information_request",
        object_id=str(begaran.id),
        after={
            "recipient": begaran.recipient_email,
            "subject": begaran.subject,
            "body": begaran.body,
        },
        request=http_request,
    )
    session.commit()
    return begaran


@requests_router.post("/{request_id}/mark-sent", response_model=InformationRequestOut)
def mark_request_sent(
    request_id: uuid.UUID,
    data: MarkSentIn,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Markera som skickad.

    Systemet skickar inte mejlet. Anvandaren skickar det fran sin egen e-post
    och markerar det har. Det ar ett medvetet val: ett mejl som gar fran en
    server i anvandarens namn utan att anvandaren sett det ar inte ett
    bekvamlighetsfunktion.
    """
    begaran = session.get(InformationRequest, request_id)
    if begaran is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Begäran finns inte.")
    try:
        foi.mark_sent(session, begaran, channel=data.channel)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from None

    if begaran.appointment_id:
        arende = session.get(Appointment, begaran.appointment_id)
        if arende and appt.can_transition(arende.status, AppointmentStatus.REQUEST_SENT):
            appt.transition(
                session,
                arende,
                AppointmentStatus.REQUEST_SENT,
                reason=f"Begaran skickad till {begaran.recipient_email} ({data.channel}).",
                changed_by=f"USER:{admin.email}",
            )
    write_audit(
        session,
        user=admin,
        action="request_mark_sent",
        object_type="information_request",
        object_id=str(begaran.id),
        after={"channel": data.channel},
        request=http_request,
    )
    session.commit()
    return begaran


@requests_router.post("/{request_id}/register-response", response_model=InformationRequestOut)
def register_response(
    request_id: uuid.UUID,
    data: RegisterResponseIn,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Registrera myndighetens svar.

    Skapar en handling av typen REGISTRAR_REPLY. Namnet laggs inte in har --
    det gors med /appointments/{id}/identify som kraver handlingens id, sa att
    kedjan fran svar till namn gar att folja.
    """
    begaran = session.get(InformationRequest, request_id)
    if begaran is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Begäran finns inte.")
    if begaran.approved_by_user_id is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Begäran är inte godkänd och kan därför inte ha besvarats."
        )

    from ..models import DocumentType

    dokument = PublicDocument(
        authority_id=begaran.authority_id,
        document_type=DocumentType.REGISTRAR_REPLY,
        title=f"Svar pa begaran {begaran.id}",
        diary_number=data.diary_number,
        document_date=data.decision_date,
        extracted_text=data.note,
        acquisition="REGISTRAR_REPLY",
    )
    session.add(dokument)
    session.flush()

    begaran.status = RequestStatus.ANSWERED
    begaran.response_document_id = dokument.id
    begaran.response_note = data.note

    if begaran.appointment_id:
        arende = session.get(Appointment, begaran.appointment_id)
        if arende and appt.can_transition(arende.status, AppointmentStatus.RESPONSE_RECEIVED):
            appt.transition(
                session,
                arende,
                AppointmentStatus.RESPONSE_RECEIVED,
                reason=(
                    "Svar fran registrator registrerat."
                    + (
                        f" Angiven anstalld: {data.appointed_name}. Registrera med "
                        f"/identify och handlingens id for att spara namnet."
                        if data.appointed_name
                        else " Inget namn angivet i svaret."
                    )
                ),
                changed_by=f"USER:{admin.email}",
                evidence_document_id=dokument.id,
                diary_number=data.diary_number,
            )
    write_audit(
        session,
        user=admin,
        action="request_register_response",
        object_type="information_request",
        object_id=str(begaran.id),
        after={"document_id": str(dokument.id), "note": data.note},
        request=http_request,
    )
    session.commit()
    return begaran


# --- Personuppgifter -------------------------------------------------------

persons = APIRouter(prefix="/appointed-persons", tags=["gdpr"])


@persons.patch("/{person_id}", response_model=dict)
def correct_person(
    person_id: uuid.UUID,
    payload: dict,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Rattelse enligt GDPR art. 16."""
    person = session.get(AppointedPerson, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Personen finns inte.")
    fore = {
        "full_name": person.full_name,
        "previous_role": person.previous_role,
        "previous_organisation": person.previous_organisation,
    }
    for falt in ("full_name", "previous_role", "previous_organisation"):
        if falt in payload:
            setattr(person, falt, payload[falt])
    write_audit(
        session,
        user=admin,
        action="person_correct",
        object_type="appointed_person",
        object_id=str(person.id),
        before=fore,
        after={
            "full_name": person.full_name,
            "previous_role": person.previous_role,
            "previous_organisation": person.previous_organisation,
        },
        request=http_request,
    )
    session.commit()
    return {"ok": True, "id": str(person.id)}


@persons.delete("/{person_id}", response_model=dict)
def erase_person(
    person_id: uuid.UUID,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
    reason: str = Query("radering pa begaran", min_length=3),
):
    """Radering enligt GDPR art. 17.

    Arendet behalls utan namn, och handlingen behalls -- den ar en allmän
    handling hos myndigheten och inte var att radera. Vad som raderas ar var
    kopia av personuppgiften.
    """
    person = session.get(AppointedPerson, person_id)
    if person is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Personen finns inte.")
    nu = dt.datetime.now(dt.UTC)
    for arende in session.scalars(
        select(Appointment).where(Appointment.appointed_person_id == person.id)
    ).all():
        arende.appointed_person_id = None
        arende.resolution_note = (
            arende.resolution_note or ""
        ) + f" [Personuppgift raderad {nu.date()}: {reason}]"
    write_audit(
        session,
        user=admin,
        action="person_erase",
        object_type="appointed_person",
        object_id=str(person.id),
        before={"had_name": True, "legal_basis": person.legal_basis.value},
        after={"reason": reason},
        request=http_request,
    )
    session.delete(person)
    session.commit()
    return {"ok": True, "erased": str(person_id), "reason": reason}
