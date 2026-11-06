"""Annonser, upphandlingar, uppdrag, exkludering och matchning."""

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
    UniqueConstraint,
)
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import JSONType, Record, StrArray, enum_col, vector_type
from .enums import (
    Assessor,
    EmploymentType,
    ExclusionVerdict,
    NoticeType,
    OpportunityKind,
    OpportunityStatus,
    RoleFamily,
)


class JobAd(Record):
    """En annons som den sag ut nar vi hittade den."""

    __tablename__ = "job_ads"

    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("source_snapshots.id"), nullable=False
    )
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("organisations.id")
    )
    recruiter_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("providers.id")
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Gemener, utan skiljetecken och utan ortsnamn. Finns som egen kolumn och
    # inte som uttryck i indexet, for att samma normalisering ska anvandas av
    # dubblettkontrollen i Python och av databasen.
    title_normalised: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    employment_type: Mapped[EmploymentType] = mapped_column(
        enum_col(EmploymentType), default=EmploymentType.UNKNOWN, nullable=False
    )
    role_family: Mapped[RoleFamily] = mapped_column(
        enum_col(RoleFamily), default=RoleFamily.NOT_RELEVANT, nullable=False
    )
    # JobTechs yrkesbegrepp, nar kallan ger det. Battre an fritext pa titeln:
    # IVO:s annons har concept_id for Chief Digital Officer/CDO aven om titeln
    # bara sager "Verksamhetsomradeschef".
    occupation_concept_id: Mapped[str | None] = mapped_column(String(32))
    occupation_label: Mapped[str | None] = mapped_column(Text)

    published_at: Mapped[dt.datetime | None] = mapped_column()
    application_deadline: Mapped[dt.datetime | None] = mapped_column()
    # Nar annonsen forsvann fran kallan. Satt betyder inte att tjansten ar
    # tillsatt -- se core/appointments.py.
    depublished_at: Mapped[dt.datetime | None] = mapped_column()

    workplace_municipality: Mapped[str | None] = mapped_column(Text)
    workplace_region: Mapped[str | None] = mapped_column(Text)
    workplace_address: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)

    embedding = mapped_column(vector_type(1024), nullable=True)

    versions: Mapped[list[JobAdVersion]] = relationship(
        back_populates="job_ad", cascade="all, delete-orphan"
    )
    opportunity: Mapped[Opportunity | None] = relationship(back_populates="job_ad", uselist=False)

    __table_args__ = (
        UniqueConstraint("source_key", "external_id", name="uq_job_ads_source_external"),
        Index("ix_job_ads_published_at", "published_at"),
        Index("ix_job_ads_title_normalised", "title_normalised"),
        Index("ix_job_ads_organisation", "organisation_id"),
        Index("ix_job_ads_role_employment", "role_family", "employment_type"),
    )

    def __repr__(self) -> str:
        return f"<JobAd {self.source_key}/{self.external_id} {self.title!r}>"


class JobAdVersion(Record):
    """Tidigare version av en annons.

    Behovs for att se att en deadline forlangdes eller att en kravprofil skrevs
    om efter publicering. Utan det later en andrad annons som en ny annons.
    """

    __tablename__ = "job_ad_versions"

    job_ad_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("job_ads.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("source_snapshots.id"), nullable=False
    )
    valid_from: Mapped[dt.datetime] = mapped_column(nullable=False)
    valid_to: Mapped[dt.datetime | None] = mapped_column()
    changed_fields: Mapped[dict | None] = mapped_column(JSONType)

    job_ad: Mapped[JobAd] = relationship(back_populates="versions")

    __table_args__ = (Index("ix_job_ad_versions_ad_from", "job_ad_id", "valid_from"),)


class ProcurementNotice(Record):
    """Upphandlingsannons, i praktiken fran TED."""

    __tablename__ = "procurement_notices"

    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("source_snapshots.id"), nullable=False
    )
    buyer_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("organisations.id")
    )
    framework_agreement_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("framework_agreements.id")
    )

    notice_type: Mapped[NoticeType] = mapped_column(enum_col(NoticeType), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_normalised: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    buyer_name_raw: Mapped[str | None] = mapped_column(Text)
    cpv_codes = mapped_column(StrArray, nullable=True)
    estimated_value_sek: Mapped[int | None] = mapped_column()
    currency: Mapped[str | None] = mapped_column(String(3))
    published_at: Mapped[dt.datetime | None] = mapped_column()
    tender_deadline: Mapped[dt.datetime | None] = mapped_column()
    url: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "source_key", "external_id", name="uq_procurement_notices_source_external"
        ),
        Index("ix_procurement_notices_published", "published_at"),
        Index("ix_procurement_notices_deadline", "tender_deadline"),
    )


class Opportunity(Record):
    """Det som ar intressant att agera pa.

    Grundas pa en annons, en upphandling eller bada. Darfor ar bada nycklarna
    nullbara, med ett check-villkor som kraver minst en.
    """

    __tablename__ = "opportunities"

    kind: Mapped[OpportunityKind] = mapped_column(enum_col(OpportunityKind), nullable=False)
    job_ad_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("job_ads.id", ondelete="CASCADE"), unique=True
    )
    procurement_notice_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("procurement_notices.id", ondelete="CASCADE")
    )

    status: Mapped[OpportunityStatus] = mapped_column(
        enum_col(OpportunityStatus), default=OpportunityStatus.UNKNOWN, nullable=False
    )
    exclusion_status: Mapped[ExclusionVerdict] = mapped_column(
        enum_col(ExclusionVerdict), default=ExclusionVerdict.REVIEW_REQUIRED, nullable=False
    )
    # Null nar posten ar exkluderad. En exkluderad post matchas inte, och en
    # poang pa en exkluderad post skulle bara locka nagon att titta pa den.
    match_score: Mapped[int | None] = mapped_column(Integer)

    duration_months: Mapped[int | None] = mapped_column(Integer)
    fee_sek_per_hour: Mapped[int | None] = mapped_column(Integer)
    extent_percent: Mapped[int | None] = mapped_column(Integer)
    starts_at: Mapped[dt.date | None] = mapped_column(Date)

    job_ad: Mapped[JobAd | None] = relationship(back_populates="opportunity")
    exclusion_records: Mapped[list[ExclusionRecord]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "job_ad_id is not null or procurement_notice_id is not null",
            name="has_source_object",
        ),
        CheckConstraint(
            "match_score is null or (match_score >= 0 and match_score <= 100)",
            name="score_range",
        ),
        Index(
            "ix_opportunities_score",
            "match_score",
            postgresql_where=sa_text("exclusion_status = 'PASS'"),
        ),
        Index("ix_opportunities_kind_status", "kind", "status"),
    )

    def __repr__(self) -> str:
        return f"<Opportunity {self.kind} {self.exclusion_status} score={self.match_score}>"


class ExclusionRecord(Record):
    """En bedomning av bakgrundskontrollfiltret. Aldrig overskriven.

    Varje rad ar ett bevis: vilken regel som slog, vilket citat som utlost den,
    var i dokumentet det stod. Check-villkoret nedan ar karnan i hela filtret --
    ett EXCLUDED utan citat ar en asikt, inte ett beslut.
    """

    __tablename__ = "exclusion_records"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    verdict: Mapped[ExclusionVerdict] = mapped_column(enum_col(ExclusionVerdict), nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(64))
    matched_quote: Mapped[str | None] = mapped_column(Text)
    quote_offset: Mapped[int | None] = mapped_column(Integer)
    document_url: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)

    assessed_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    assessor: Mapped[Assessor] = mapped_column(enum_col(Assessor), nullable=False)
    ai_model: Mapped[str | None] = mapped_column(String(64))
    ai_reasoning: Mapped[str | None] = mapped_column(Text)

    overridden_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("users.id")
    )
    override_reason: Mapped[str | None] = mapped_column(Text)

    opportunity: Mapped[Opportunity] = relationship(back_populates="exclusion_records")

    __table_args__ = (
        # Ett EXCLUDED maste peka pa en formulering i underlaget.
        CheckConstraint(
            "verdict <> 'EXCLUDED' or matched_quote is not null",
            name="excluded_needs_quote",
        ),
        Index("ix_exclusion_records_opportunity", "opportunity_id", "assessed_at"),
        Index("ix_exclusion_records_verdict", "verdict"),
    )

    def __repr__(self) -> str:
        return f"<Exclusion {self.verdict} rule={self.rule_id} by={self.assessor}>"


class ConsultantProfile(Record):
    """Anvandarens profil. Vikterna ligger har, inte i koden.

    Specen ger en vikttabell som summerar till 100. Den ar en utgangspunkt, inte
    en sanning, och anvandaren ska kunna andra den utan omstart.
    """

    __tablename__ = "consultant_profiles"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    headline: Mapped[str | None] = mapped_column(Text)
    experiences: Mapped[list | None] = mapped_column(JSONType)
    skills: Mapped[list | None] = mapped_column(JSONType)
    preferences: Mapped[dict | None] = mapped_column(JSONType)
    weights: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:
        return f"<Profile {self.name!r} active={self.is_active}>"


class MatchingResult(Record):
    """Historik over matchningar.

    Egen tabell och inte bara en kolumn pa opportunities, sa att en andrad vikt
    inte skriver over gamla bedomningar. Att kunna se att en post fick 84 i
    oktober och 61 i november nar vikterna andrades ar sjalva poangen.
    """

    __tablename__ = "matching_results"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("consultant_profiles.id"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Hur stor del av viktningen som faktiskt hade stod i annonstexten, 0-100.
    # Utan den gar 84 av 100 pa en utforlig annons inte att skilja fran 84 pa
    # en annons dar halva underlaget gissades.
    confidence: Mapped[int | None] = mapped_column(Integer)
    subscores: Mapped[dict | None] = mapped_column(JSONType)
    explanation: Mapped[str | None] = mapped_column(Text)
    computed_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    engine_version: Mapped[str] = mapped_column(String(16), nullable=False)

    __table_args__ = (
        Index("ix_matching_results_opportunity", "opportunity_id", "computed_at"),
        CheckConstraint("score >= 0 and score <= 100", name="score_range"),
    )
