"""Pydantic-scheman for API:et.

Halls medvetet nara modellerna. Det som skiljer ar att scheman aldrig lamnar ut
mer an nodvandigt: AppointmentOut har inget namnfalt forran tillsattningen ar
verifierad, och UserOut har inget losenordsfalt alls.
"""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models.enums import (
    AccessMode,
    AppointmentPublicationMode,
    AppointmentStatus,
    DocumentType,
    EmploymentType,
    ExclusionVerdict,
    OpportunityKind,
    OpportunityStatus,
    OrgType,
    RequestStatus,
    RoleFamily,
    SourceStatus,
    UserRole,
)


class Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Auth ---


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserOut(Base):
    id: uuid.UUID
    email: str
    role: UserRole
    last_login_at: dt.datetime | None = None


# --- Organisationer ---


class OrganisationOut(Base):
    id: uuid.UUID
    name: str
    org_number: str | None = None
    org_type: OrgType
    website: str | None = None


class AuthorityOut(Base):
    id: uuid.UUID
    organisation_id: uuid.UUID
    organisation_name: str | None = None
    careers_url: str | None = None
    vacancies_url: str | None = None
    registrar_email: str | None = None
    recruitment_platform: str
    collection_method: str
    appointment_publication_mode: AppointmentPublicationMode
    notice_board_location: str | None = None
    status: SourceStatus
    verified_at: dt.date | None = None
    verification_source: str | None = None
    last_checked_at: dt.datetime | None = None


class AuthorityPatch(BaseModel):
    vacancies_url: str | None = None
    registrar_email: EmailStr | None = None
    appointment_publication_mode: AppointmentPublicationMode | None = None
    notice_board_location: str | None = None
    status: SourceStatus | None = None


# --- Annonser och uppdrag ---


class JobAdOut(Base):
    id: uuid.UUID
    source_key: str
    external_id: str
    title: str
    description: str | None = None
    organisation_name: str | None = None
    employment_type: EmploymentType
    role_family: RoleFamily
    occupation_label: str | None = None
    published_at: dt.datetime | None = None
    application_deadline: dt.datetime | None = None
    depublished_at: dt.datetime | None = None
    workplace_municipality: str | None = None
    workplace_region: str | None = None
    url: str | None = None
    snapshot_id: uuid.UUID


class ExclusionOut(Base):
    verdict: ExclusionVerdict
    rule_id: str | None = None
    matched_quote: str | None = None
    quote_offset: int | None = None
    document_url: str | None = None
    page_number: int | None = None
    assessed_at: dt.datetime
    assessor: str
    ai_model: str | None = None
    ai_reasoning: str | None = None
    override_reason: str | None = None


class MatchOut(BaseModel):
    score: int
    confidence: int | None = None
    explanation: str | None = None
    subscores: dict | None = None


class OpportunityOut(Base):
    id: uuid.UUID
    kind: OpportunityKind
    status: OpportunityStatus
    exclusion_status: ExclusionVerdict
    match_score: int | None = None
    duration_months: int | None = None
    fee_sek_per_hour: int | None = None
    job_ad: JobAdOut | None = None
    created_at: dt.datetime


class OpportunityDetail(OpportunityOut):
    exclusion: ExclusionOut | None = None
    matching: MatchOut | None = None
    appointment_id: uuid.UUID | None = None


class ExclusionOverrideIn(BaseModel):
    verdict: ExclusionVerdict
    reason: str = Field(min_length=10, description="varfor beslutet andras")


# --- Tillsattningar ---


class AppointmentHistoryOut(Base):
    from_status: AppointmentStatus | None = None
    to_status: AppointmentStatus
    changed_at: dt.datetime
    changed_by: str
    reason: str | None = None


class AppointmentOut(Base):
    id: uuid.UUID
    status: AppointmentStatus
    status_changed_at: dt.datetime
    diary_number: str | None = None
    decision_date: dt.date | None = None
    start_date: dt.date | None = None
    verification_level: int | None = None
    verification_label: str | None = None
    resolution_note: str | None = None
    last_searched_at: dt.datetime | None = None
    job_ad: JobAdOut | None = None
    authority_name: str | None = None
    # Namnet lamnas bara ut nar tillsattningen ar verifierad pa niva 1-3.
    # Scheman ar sista stallet dar en halvsaker uppgift kan slinka ut till
    # granssnittet, sa kontrollen sker i routen och faltet ar None annars.
    appointed_person_name: str | None = None
    appointed_person_previous_role: str | None = None


class AppointmentDetail(AppointmentOut):
    history: list[AppointmentHistoryOut] = []
    information_request_id: uuid.UUID | None = None
    decision_document_url: str | None = None


class IdentifyPersonIn(BaseModel):
    """Registrera vem som fick tjansten.

    document_id ar obligatoriskt. Det ar inte mojligt att namnge en person via
    API:et utan att peka pa handlingen uppgiften kommer ur.
    """

    full_name: str = Field(min_length=2)
    document_id: uuid.UUID
    verification_level: int = Field(ge=1, le=5)
    previous_role: str | None = None
    previous_organisation: str | None = None
    decision_date: dt.date | None = None
    start_date: dt.date | None = None
    diary_number: str | None = None


# --- Begaran om allman handling ---


class InformationRequestOut(Base):
    id: uuid.UUID
    authority_id: uuid.UUID
    appointment_id: uuid.UUID | None = None
    recipient_email: str | None = None
    subject: str
    body: str
    status: RequestStatus
    approved_at: dt.datetime | None = None
    sent_at: dt.datetime | None = None
    sent_channel: str | None = None
    response_note: str | None = None
    # Handlingens id behovs for att kunna registrera namnet med /identify.
    # Utan det gar kedjan svar -> namn inte att fullfolja fran granssnittet.
    response_document_id: uuid.UUID | None = None


class RequestPatch(BaseModel):
    recipient_email: EmailStr | None = None
    subject: str | None = None
    body: str | None = None


class MarkSentIn(BaseModel):
    channel: str = "EMAIL"


class RegisterResponseIn(BaseModel):
    note: str
    appointed_name: str | None = None
    decision_date: dt.date | None = None
    diary_number: str | None = None


# --- Handlingar ---


class DocumentOut(Base):
    id: uuid.UUID
    document_type: DocumentType
    title: str | None = None
    url: str | None = None
    diary_number: str | None = None
    document_date: dt.date | None = None
    acquisition: str | None = None
    sha256: str | None = None
    has_text: bool = False
    created_at: dt.datetime


class DocumentIn(BaseModel):
    """Registrera en handling som inte gick att hamta automatiskt.

    Behovs for myndigheter som anslar anstallningsbeslut pa en fysisk
    anslagstavla, och for handlingar som kommit per post. Utan den vagen skulle
    just de tillsattningarna aldrig kunna avgoras.
    """

    document_type: DocumentType
    title: str = Field(min_length=3)
    url: str | None = None
    diary_number: str | None = None
    document_date: dt.date | None = None
    acquisition: str = Field(
        min_length=3,
        description="hur handlingen kom in, t.ex. NOTICE_BOARD_VISIT, POST, REGISTRAR_REPLY",
    )
    extracted_text: str | None = Field(
        default=None, description="handlingens text eller ett referat av den"
    )


# --- Profil ---


class ProfileOut(Base):
    id: uuid.UUID
    name: str
    is_active: bool
    headline: str | None = None
    experiences: list | None = None
    skills: list | None = None
    preferences: dict | None = None
    weights: dict | None = None


class ProfilePatch(BaseModel):
    headline: str | None = None
    experiences: list | None = None
    skills: list | None = None
    preferences: dict | None = None
    weights: dict | None = None


# --- Kallor ---


class SourceOut(Base):
    key: str
    name: str
    access_mode: AccessMode
    status: SourceStatus
    base_url: str | None = None
    legal_note: str | None = None
    robots_allows: bool | None = None
    robots_checked_at: dt.date | None = None
    schedule_cron: str | None = None
    last_success_at: dt.datetime | None = None
    last_attempt_at: dt.datetime | None = None
    last_error: str | None = None
    consecutive_failures: int


class RunOut(Base):
    id: uuid.UUID
    source_key: str
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    status: str
    items_found: int
    items_new: int
    items_changed: int
    items_duplicate: int
    errors: int
    error_detail: str | None = None


class ManualImportIn(BaseModel):
    content: str = Field(min_length=1, description="CSV eller JSON")
    filename: str | None = None
    source_key: str = "manual"


# --- Marknad ---


class FrameworkAgreementOut(Base):
    id: uuid.UUID
    name: str
    agreement_number: str | None = None
    area: str | None = None
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None
    extension_months: int | None = None
    url: str | None = None
    days_left: int | None = None


class ProviderOut(Base):
    id: uuid.UUID
    name: str
    org_number: str | None = None
    website: str | None = None
    assignment_count: int | None = None


# --- Dashboard ---


class DashboardOut(BaseModel):
    new_opportunities_7d: int
    active_interim: int
    permanent_positions: int
    recruitments_closed: int
    appointments_identified: int
    appointments_verified: int
    appointments_unresolved: int
    requests_awaiting_approval: int
    excluded_count: int
    review_required_count: int
    top_matches: list[OpportunityOut]
    upcoming_deadlines: list[OpportunityOut]
    expiring_agreements: list[FrameworkAgreementOut]
    recent_appointments: list[AppointmentOut]
    failing_sources: list[SourceOut]
    charts: dict


class Page(BaseModel):
    total: int
    limit: int
    offset: int
