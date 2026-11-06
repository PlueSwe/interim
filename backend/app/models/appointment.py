"""Tillsattningar, handlingar och begaranden om allman handling.

Den mest kansliga delen av datamodellen. En rad i appointed_persons namnger en
verklig person, och darfor har den egna krav: den kan inte skapas utan ett
dokument, laglig grund maste anges, och lagringstiden ar satt per rad.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Record, enum_col
from .enums import AppointmentStatus, DocumentType, LegalBasis, RequestStatus


class PublicDocument(Record):
    """En hamtad handling. Beviset bakom en tillsattning."""

    __tablename__ = "public_documents"

    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("authorities.id")
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("source_snapshots.id")
    )
    document_type: Mapped[DocumentType] = mapped_column(enum_col(DocumentType), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    diary_number: Mapped[str | None] = mapped_column(String(64))
    document_date: Mapped[dt.date | None] = mapped_column(Date)
    file_path: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    # Hur handlingen kom in: hamtad fran webben, bifogad i registrators svar,
    # eller inlagd for hand efter ett besok vid en anslagstavla.
    acquisition: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (
        Index("ix_public_documents_authority_type", "authority_id", "document_type"),
        Index("ix_public_documents_diary", "diary_number"),
    )

    def __repr__(self) -> str:
        return f"<PublicDocument {self.document_type} {self.diary_number or self.url}>"


class AppointedPerson(Record):
    """Den som fick tjansten.

    Innehaller namn, tidigare roll och tidigare organisation. Ingenting annat.
    Att en uppgift ar offentlig gor den inte nodvandig; se SECURITY.md.

    source_document_id ar inte nullbar. Det ar det som skiljer en verifierad
    tillsattning fran ett rykte, och det garanteras av databasen och inte av
    koden eftersom koden kommer att skrivas om.
    """

    __tablename__ = "appointed_persons"

    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    previous_role: Mapped[str | None] = mapped_column(Text)
    previous_organisation: Mapped[str | None] = mapped_column(Text)

    legal_basis: Mapped[LegalBasis] = mapped_column(enum_col(LegalBasis), nullable=False)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("public_documents.id"), nullable=False
    )
    # Beslutsdatum + settings.person_retention_years. En nattlig uppgift raderar
    # rader som passerat tiden.
    retention_until: Mapped[dt.date] = mapped_column(Date, nullable=False)
    erasure_requested_at: Mapped[dt.datetime | None] = mapped_column()

    __table_args__ = (Index("ix_appointed_persons_retention", "retention_until"),)

    def __repr__(self) -> str:
        return f"<AppointedPerson basis={self.legal_basis} until={self.retention_until}>"


class Appointment(Record):
    """Ett rekryteringsarende som foljs fran annons till svar."""

    __tablename__ = "appointments"

    job_ad_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("job_ads.id", ondelete="CASCADE"), nullable=False
    )
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("authorities.id")
    )
    status: Mapped[AppointmentStatus] = mapped_column(
        enum_col(AppointmentStatus),
        default=AppointmentStatus.ADVERTISEMENT_FOUND,
        nullable=False,
    )
    status_changed_at: Mapped[dt.datetime] = mapped_column(nullable=False)

    diary_number: Mapped[str | None] = mapped_column(String(64))
    decision_date: Mapped[dt.date | None] = mapped_column(Date)
    start_date: Mapped[dt.date | None] = mapped_column(Date)

    verification_level: Mapped[int | None] = mapped_column(Integer)
    appointed_person_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("appointed_persons.id", ondelete="SET NULL")
    )
    decision_document_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("public_documents.id")
    )
    # Varfor arendet star dar det star. Fylls alltid, aven nar svaret ar "hittade
    # inget". Ett arende utan forklaring ar oanvandbart om tre manader.
    resolution_note: Mapped[str | None] = mapped_column(Text)
    # Nar systemet senast letade efter ett beslut, sa att det inte letar varje
    # natt pa en myndighet som anslar besluten pa en vagg.
    last_searched_at: Mapped[dt.datetime | None] = mapped_column()

    person: Mapped[AppointedPerson | None] = relationship()
    history: Mapped[list[AppointmentStatusHistory]] = relationship(
        back_populates="appointment", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "verification_level is null or (verification_level >= 1 and verification_level <= 5)",
            name="verification_level_range",
        ),
        # En identifierad tillsattning kraver ett dokument. Statusmaskinen i
        # core/appointments.py vagrar ocksa, men den har raden overlever en
        # omskrivning av statusmaskinen.
        CheckConstraint(
            "status not in ('APPOINTMENT_IDENTIFIED', 'APPOINTMENT_VERIFIED') "
            "or decision_document_id is not null",
            name="identified_needs_document",
        ),
        # Verifierad kraver niva 1-3. Niva 4 (LinkedIn) och 5 (obekraftat) far
        # inte passera.
        CheckConstraint(
            "status <> 'APPOINTMENT_VERIFIED' "
            "or (verification_level is not null and verification_level <= 3)",
            name="verified_needs_level_1_to_3",
        ),
        Index("ix_appointments_status_changed", "status", "status_changed_at"),
        Index("ix_appointments_authority", "authority_id"),
    )

    def __repr__(self) -> str:
        return f"<Appointment {self.status} level={self.verification_level}>"


class AppointmentStatusHistory(Record):
    """Hela kedjan av statusbyten, med skal och eventuellt bevis."""

    __tablename__ = "appointment_status_history"

    appointment_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[AppointmentStatus | None] = mapped_column(enum_col(AppointmentStatus))
    to_status: Mapped[AppointmentStatus] = mapped_column(
        enum_col(AppointmentStatus), nullable=False
    )
    changed_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    changed_by: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence_document_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("public_documents.id")
    )

    appointment: Mapped[Appointment] = relationship(back_populates="history")

    __table_args__ = (Index("ix_appointment_status_history_appt", "appointment_id", "changed_at"),)


class InformationRequest(Record):
    """Begaran om allman handling.

    Skapas alltid som DRAFT. Check-villkoret nedan ar det som gor att systemet
    inte kan skicka nagot av sig sjalvt, oavsett vad en framtida tasks-modul
    rakar gora.
    """

    __tablename__ = "information_requests"

    authority_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("authorities.id"), nullable=False
    )
    appointment_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE")
    )
    recipient_email: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[RequestStatus] = mapped_column(
        enum_col(RequestStatus), default=RequestStatus.DRAFT, nullable=False
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("users.id")
    )
    approved_at: Mapped[dt.datetime | None] = mapped_column()
    sent_at: Mapped[dt.datetime | None] = mapped_column()
    # Hur den skickades. Nar en myndighet bara anslar beslut fysiskt kan svaret
    # komma pa papper, och da ar det en manniska som registrerar det.
    sent_channel: Mapped[str | None] = mapped_column(String(32))
    response_document_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("public_documents.id")
    )
    response_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "status not in ('SENT', 'ANSWERED', 'REFUSED') or approved_by_user_id is not null",
            name="sent_needs_approval",
        ),
        Index("ix_information_requests_status", "status"),
        Index("ix_information_requests_appointment", "appointment_id"),
    )

    def __repr__(self) -> str:
        return f"<InformationRequest {self.status} to={self.recipient_email}>"
