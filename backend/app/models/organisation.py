"""Organisationer och myndigheter."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Record, enum_col
from .enums import (
    AppointmentPublicationMode,
    CollectionMethod,
    OrgType,
    RecruitmentPlatform,
    SourceStatus,
)


class Organisation(Record):
    """Gemensam stam for allt som kan vara arbetsgivare eller kopare.

    En kommun ar en organisation, inte en egen tabell. Specen listar
    municipalities och regions separat, men de skulle inte ha nagon egen data
    utover det som star har, och tva tabeller om samma kommun blir tva sanningar
    om samma kommun. Vyer i migreringen ger listorna.
    """

    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Tio siffror utan bindestreck. Normaliseras i core/orgnr.py innan det landar
    # har, sa att 202100-6537 och 2021006537 inte blir tva organisationer.
    org_number: Mapped[str | None] = mapped_column(String(10), unique=True)
    org_type: Mapped[OrgType] = mapped_column(enum_col(OrgType), nullable=False)
    website: Mapped[str | None] = mapped_column(Text)
    county_code: Mapped[str | None] = mapped_column(String(2))
    municipality_code: Mapped[str | None] = mapped_column(String(4))
    # Antal anstallda, nar det framgar av en kalla. Anvands for att vikta hur
    # intressant en myndighet ar, inte for nagon statistik.
    employee_count: Mapped[int | None] = mapped_column()
    note: Mapped[str | None] = mapped_column(Text)

    authority: Mapped[Authority | None] = relationship(
        back_populates="organisation", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_organisations_org_type_name", "org_type", "name"),
        Index("ix_organisations_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Organisation {self.name!r} {self.org_type}>"


class Authority(Record):
    """Det som bara galler myndigheter, inklusive universitet och hogskolor."""

    __tablename__ = "authorities"

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    careers_url: Mapped[str | None] = mapped_column(Text)
    # Sidan som faktiskt listar tjanster. Skiljer sig ofta fran karriarsidan,
    # som brukar vara en saljsida om hur bra det ar att jobba dar.
    vacancies_url: Mapped[str | None] = mapped_column(Text)
    registrar_email: Mapped[str | None] = mapped_column(Text)
    registrar_name: Mapped[str | None] = mapped_column(Text)
    postal_address: Mapped[str | None] = mapped_column(Text)

    recruitment_platform: Mapped[RecruitmentPlatform] = mapped_column(
        enum_col(RecruitmentPlatform), default=RecruitmentPlatform.UNKNOWN, nullable=False
    )
    collection_method: Mapped[CollectionMethod] = mapped_column(
        enum_col(CollectionMethod), default=CollectionMethod.MANUAL, nullable=False
    )
    appointment_publication_mode: Mapped[AppointmentPublicationMode] = mapped_column(
        enum_col(AppointmentPublicationMode),
        default=AppointmentPublicationMode.UNKNOWN,
        nullable=False,
    )
    # Dar beslutet anslas, nar det anslas fysiskt. IVO: Torsplan, Stockholm.
    notice_board_location: Mapped[str | None] = mapped_column(Text)

    status: Mapped[SourceStatus] = mapped_column(
        enum_col(SourceStatus), default=SourceStatus.MANUAL_ONLY, nullable=False
    )
    last_checked_at: Mapped[dt.datetime | None] = mapped_column()
    # Nar raden senast kontrollerades mot en kalla av en manniska. En rad utan
    # verified_at ar en rad nagon har skrivit in pa kansla.
    verified_at: Mapped[dt.date | None] = mapped_column(Date)
    verification_source: Mapped[str | None] = mapped_column(Text)

    organisation: Mapped[Organisation] = relationship(back_populates="authority")

    __table_args__ = (
        Index("ix_authorities_status", "status"),
        Index("ix_authorities_collection_method", "collection_method"),
    )

    def __repr__(self) -> str:
        return f"<Authority org={self.organisation_id} {self.status}>"


class Provider(Record):
    """Konsultmaklare, bemanningsbolag, rekryteringsforetag och leverantorer.

    Specen vill ha providers, suppliers och recruiters som tre tabeller. Samma
    bolag ar ofta alla tre -- Poolia rekryterar, bemannar och ligger pa ramavtal
    -- sa rollen hor till relationen, inte till bolaget. Darfor en tabell har och
    roll pa kopplingen.
    """

    __tablename__ = "providers"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    org_number: Mapped[str | None] = mapped_column(String(10))
    website: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("name", name="uq_providers_name"),
        Index("ix_providers_org_number", "org_number"),
    )

    def __repr__(self) -> str:
        return f"<Provider {self.name!r}>"
