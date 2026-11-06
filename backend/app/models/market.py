"""Ramavtal, avrop och leverantorer."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Record, enum_col
from .enums import ProviderRole


class FrameworkAgreement(Record):
    """Ett ramavtal.

    valid_to ar den intressanta kolumnen. Ett ramavtal som loper ut inom ett ar
    betyder en kommande upphandling, och en kommande upphandling betyder ofta ett
    interimbehov hos kopande myndighet.
    """

    __tablename__ = "framework_agreements"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    agreement_number: Mapped[str | None] = mapped_column(String(64))
    owner_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("organisations.id")
    )
    area: Mapped[str | None] = mapped_column(Text)
    valid_from: Mapped[dt.date | None] = mapped_column(Date)
    valid_to: Mapped[dt.date | None] = mapped_column(Date)
    # Forlangningsoption i manader. Ett avtal som loper ut om tre manader men har
    # 24 manaders option ar inte en affarsmojlighet an.
    extension_months: Mapped[int | None] = mapped_column(Integer)
    extension_note: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str | None] = mapped_column(String(64))

    suppliers: Mapped[list[FrameworkAgreementSupplier]] = relationship(
        back_populates="agreement", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("agreement_number", name="uq_framework_agreements_number"),
        Index("ix_framework_agreements_valid_to", "valid_to"),
    )

    def __repr__(self) -> str:
        return f"<FrameworkAgreement {self.agreement_number} {self.name!r} -> {self.valid_to}>"


class FrameworkAgreementSupplier(Record):
    """Leverantor pa ett ramavtal, med rangordning dar sadan finns."""

    __tablename__ = "framework_agreement_suppliers"

    framework_agreement_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True),
        ForeignKey("framework_agreements.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[ProviderRole] = mapped_column(
        enum_col(ProviderRole), default=ProviderRole.SUPPLIER, nullable=False
    )
    rank_position: Mapped[int | None] = mapped_column(Integer)

    agreement: Mapped[FrameworkAgreement] = relationship(back_populates="suppliers")

    __table_args__ = (
        UniqueConstraint("framework_agreement_id", "provider_id", name="uq_fa_supplier_pair"),
    )


class CallOff(Record):
    """Ett avrop pa ett ramavtal.

    Avropen ar dar interimuppdragen faktiskt ligger. De syns samtidigt sammst i
    annonsdatabaserna, vilket ar skalet till att de har en egen tabell och inte
    bara ar en sorts procurement_notice.
    """

    __tablename__ = "call_offs"

    framework_agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("framework_agreements.id")
    )
    buyer_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("organisations.id")
    )
    winning_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("providers.id")
    )
    title: Mapped[str | None] = mapped_column(Text)
    value_sek: Mapped[int | None] = mapped_column()
    awarded_at: Mapped[dt.date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_call_offs_buyer_awarded", "buyer_organisation_id", "awarded_at"),)
