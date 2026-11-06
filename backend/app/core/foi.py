"""Begaran om allman handling.

Genererar ett fardigt utkast. Skickar aldrig nagot.

Att systemet inte kan skicka sjalvt ar sakrat pa tre niva: funktionen har
returnerar status DRAFT, API:et kraver en inloggad ADMIN for att godkanna, och
databasen har ett check-villkor som vagrar status SENT utan approved_by_user_id.
Det ar medvetet overdrivet. Ett mejl som gar till en myndighet i anvandarens
namn utan att anvandaren vet om det ar inte ett buggat flode utan en skada.

Standardtexten ar den som bestallningen anger, ordagrant. Den ar kort med flit:
en begaran om allman handling behover inte motiveras, och enligt
tryckfrihetsforordningen far myndigheten inte heller fraga varfor.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from ..models import (
    Appointment,
    AppointmentPublicationMode,
    Authority,
    InformationRequest,
    JobAd,
    Organisation,
    RequestStatus,
)

# Ordagrant ur bestallningen.
#
# Observera: till skillnad fran kommentarer och interna strangar i den har
# koden ar texterna nedan skrivna med korrekt svensk stavning. De lamnar
# systemet och lases av en registrator vid en myndighet. En begaran stavad
# "Jag onskar ta del av anstallningsbeslutet" ser ut som skrap och ger ett
# samre bemotande, oavsett att den ar formellt giltig.
STANDARD_BODY = (
    "Jag önskar ta del av anställningsbeslutet avseende rekryteringen av "
    "{befattning} vid {myndighet}.\n\n"
    "Jag önskar även få uppgift om vem som anställdes, beslutsdatum, "
    "tillträdesdatum och diarienummer.\n\n"
    "Jag önskar få handlingarna digitalt."
)

# Kontext om annonsen. Hjalper registrator att hitta rätt arende och minskar
# risken for en motfraga som kostar en vecka.
AD_CONTEXT = (
    "Rekryteringen utannonserades {publicerad} med sista ansökningsdag {sista_dag}.{annonslank}"
)

# Tillagg nar beslutet anslas pa en fysisk anslagstavla. Da vet vi redan att
# svaret inte finns pa webben, och det ar hyfs att saga att vi vet det.
NOTICE_BOARD_NOTE = (
    "Jag har noterat att myndigheten anslår anställningsbeslut på anslagstavla"
    "{plats}. Eftersom beslutet därmed inte är tillgängligt digitalt begär jag "
    "att få det utlämnat enligt tryckfrihetsförordningen."
)

CLOSING = (
    "Om någon del inte kan lämnas ut ber jag att resten lämnas ut, och att jag "
    "får ett beslut med uppgift om skälen för den del som inte lämnas ut."
)

SUBJECT = "Begäran om allmän handling – anställningsbeslut {befattning}"


@dataclass
class RequestDraft:
    subject: str
    body: str
    recipient_email: str | None
    missing: list[str]

    @property
    def is_sendable(self) -> bool:
        """Gar utkastet att skicka nar nagon godkant det?

        Nej utan mottagare. Da behover registratorsadressen letas upp forst, och
        det sags i missing i stallet for att utkastet tyst blir oanvandbart.
        """
        return self.recipient_email is not None


def _fmt_date(value: dt.datetime | dt.date | None) -> str:
    if value is None:
        return "okänt datum"
    d = value.date() if isinstance(value, dt.datetime) else value
    return d.isoformat()


def build_draft(
    *,
    job_ad: JobAd,
    authority: Authority | None,
    organisation: Organisation | None,
    position_title: str | None = None,
) -> RequestDraft:
    """Bygg utkastet. Gissar aldrig fram en mottagare eller en befattning."""
    saknas: list[str] = []

    myndighet = organisation.name if organisation else None
    if not myndighet:
        myndighet = "[myndighet saknas i registret]"
        saknas.append("myndighetens namn")

    befattning = position_title or job_ad.title
    if not befattning:
        befattning = "[befattning saknas]"
        saknas.append("befattning")

    mottagare = authority.registrar_email if authority else None
    if not mottagare:
        saknas.append("registratorsadress")

    if job_ad.application_deadline is None:
        saknas.append("sista ansokningsdag")

    delar = [STANDARD_BODY.format(befattning=befattning, myndighet=myndighet)]

    delar.append(
        AD_CONTEXT.format(
            publicerad=_fmt_date(job_ad.published_at),
            sista_dag=_fmt_date(job_ad.application_deadline),
            annonslank=f" Annonsen: {job_ad.url}" if job_ad.url else "",
        )
    )

    if authority and authority.appointment_publication_mode in (
        AppointmentPublicationMode.PHYSICAL_NOTICE_BOARD,
        AppointmentPublicationMode.BOTH,
    ):
        plats = f" vid {authority.notice_board_location}" if authority.notice_board_location else ""
        delar.append(NOTICE_BOARD_NOTE.format(plats=plats))

    delar.append(CLOSING)

    return RequestDraft(
        subject=SUBJECT.format(befattning=befattning),
        body="\n\n".join(delar),
        recipient_email=mottagare,
        missing=saknas,
    )


def create_request(
    session,
    *,
    appointment: Appointment,
    job_ad: JobAd,
    authority: Authority,
    organisation: Organisation | None,
    position_title: str | None = None,
) -> InformationRequest:
    """Skapa begaran i databasen som DRAFT.

    Tar inte emot nagon parameter for att skicka direkt. Det ar inte ett
    forbiseende -- det finns ingen sadan vag genom den har funktionen.
    """
    utkast = build_draft(
        job_ad=job_ad,
        authority=authority,
        organisation=organisation,
        position_title=position_title,
    )
    begaran = InformationRequest(
        authority_id=authority.id,
        appointment_id=appointment.id,
        recipient_email=utkast.recipient_email,
        subject=utkast.subject,
        body=utkast.body,
        status=RequestStatus.DRAFT,
        response_note=(
            "Uppgifter som saknas i utkastet: " + ", ".join(utkast.missing)
            if utkast.missing
            else None
        ),
    )
    session.add(begaran)
    session.flush()
    return begaran


def approve(
    session,
    request: InformationRequest,
    *,
    user_id,
    now: dt.datetime | None = None,
) -> InformationRequest:
    """Godkann ett utkast. Kravs innan det kan skickas."""
    if request.status is not RequestStatus.DRAFT:
        raise ValueError(f"bara utkast kan godkannas, denna ar {request.status.value}")
    if not request.recipient_email:
        raise ValueError(
            "mottagare saknas. Registratorsadressen maste fyllas i for myndigheten "
            "innan begaran kan godkannas."
        )
    request.status = RequestStatus.APPROVED
    request.approved_by_user_id = user_id
    request.approved_at = now or dt.datetime.now(dt.UTC)
    session.flush()
    return request


def mark_sent(
    session,
    request: InformationRequest,
    *,
    channel: str = "EMAIL",
    now: dt.datetime | None = None,
) -> InformationRequest:
    """Markera som skickad.

    Anropas efter att mejlet faktiskt gatt ivag, eller nar anvandaren skickat
    det sjalv fran sin egen e-post. Kraver godkannande; check-villkoret i
    databasen sager samma sak.
    """
    if request.approved_by_user_id is None:
        raise ValueError("Begäran måste godkännas innan den markeras som skickad.")
    request.status = RequestStatus.SENT
    request.sent_at = now or dt.datetime.now(dt.UTC)
    request.sent_channel = channel
    session.flush()
    return request
