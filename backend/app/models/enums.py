"""Alla uppraknade varden, samlade sa att de inte driftar isar mellan modell,
schema och frontend.

Varden ar strangar och inte heltal. Det gor en databasdump lasbar utan koden.
"""

from __future__ import annotations

import enum


class Str(str, enum.Enum):
    def __str__(self) -> str:
        return self.value


# --- Organisationer ---


class OrgType(Str):
    STATE_AGENCY = "STATE_AGENCY"
    REGION = "REGION"
    MUNICIPALITY = "MUNICIPALITY"
    UNIVERSITY = "UNIVERSITY"
    MUNICIPAL_COMPANY = "MUNICIPAL_COMPANY"
    OTHER_PUBLIC = "OTHER_PUBLIC"
    PRIVATE = "PRIVATE"


class RecruitmentPlatform(Str):
    VARBI = "VARBI"
    REACHMEE = "REACHMEE"
    TEAMTAILOR = "TEAMTAILOR"
    VISMA_RECRUIT = "VISMA_RECRUIT"
    JOBYLON = "JOBYLON"
    OWN_HTML = "OWN_HTML"
    PLATSBANKEN_ONLY = "PLATSBANKEN_ONLY"
    UNKNOWN = "UNKNOWN"


class CollectionMethod(Str):
    JOBTECH = "JOBTECH"
    SITEMAP = "SITEMAP"
    RSS = "RSS"
    JSON_API = "JSON_API"
    HTML_SCRAPE = "HTML_SCRAPE"
    MANUAL = "MANUAL"


class AppointmentPublicationMode(Str):
    """Hur myndigheten publicerar anstallningsbeslut.

    PHYSICAL_NOTICE_BOARD ar inte en kuriositet. Det avgor om ett arende
    overhuvudtaget kan losas digitalt, och darmed om systemet ska leta vidare pa
    webben eller ga direkt till en begaran om allman handling.
    """

    DIGITAL = "DIGITAL"
    PHYSICAL_NOTICE_BOARD = "PHYSICAL_NOTICE_BOARD"
    BOTH = "BOTH"
    UNKNOWN = "UNKNOWN"


class SourceStatus(Str):
    ACTIVE = "ACTIVE"
    FAILING = "FAILING"
    MANUAL_ONLY = "MANUAL_ONLY"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class AccessMode(Str):
    OPEN_API = "OPEN_API"
    PUBLIC_HTML = "PUBLIC_HTML"
    MANUAL_ONLY = "MANUAL_ONLY"
    BLOCKED = "BLOCKED"


# --- Annonser och uppdrag ---


class EmploymentType(Str):
    PERMANENT = "PERMANENT"
    FIXED_TERM = "FIXED_TERM"
    INTERIM_CONSULTANT = "INTERIM_CONSULTANT"
    SUBSTITUTE = "SUBSTITUTE"
    UNKNOWN = "UNKNOWN"


class RoleFamily(Str):
    CIO = "CIO"
    IT_DIRECTOR = "IT_DIRECTOR"
    IT_MANAGER = "IT_MANAGER"
    DIGITALISATION_MANAGER = "DIGITALISATION_MANAGER"
    CTO = "CTO"
    ARCHITECTURE_MANAGER = "ARCHITECTURE_MANAGER"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    OTHER_IT_LEADERSHIP = "OTHER_IT_LEADERSHIP"
    NOT_RELEVANT = "NOT_RELEVANT"


class OpportunityKind(Str):
    INTERIM_ASSIGNMENT = "INTERIM_ASSIGNMENT"
    CONSULTING_ASSIGNMENT = "CONSULTING_ASSIGNMENT"
    FRAMEWORK_CALL_OFF = "FRAMEWORK_CALL_OFF"
    DIRECT_PROCUREMENT = "DIRECT_PROCUREMENT"
    PERMANENT_POSITION = "PERMANENT_POSITION"


class OpportunityStatus(Str):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    AWARDED = "AWARDED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class NoticeType(Str):
    CONTRACT_NOTICE = "CONTRACT_NOTICE"
    AWARD_NOTICE = "AWARD_NOTICE"
    FRAMEWORK_CALL_OFF = "FRAMEWORK_CALL_OFF"
    PRIOR_INFORMATION = "PRIOR_INFORMATION"
    DIRECT_AWARD = "DIRECT_AWARD"


# --- Exkludering ---


class ExclusionVerdict(Str):
    """Tre utfall, aldrig tva.

    REVIEW_REQUIRED finns for att en osaker annons inte far bli PASS. Ett
    tvavagsfilter tvingar koden att gissa, och gissningen blir alltid PASS
    eftersom det ar det bekvama svaret.
    """

    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    EXCLUDED = "EXCLUDED"


class Assessor(Str):
    RULE = "RULE"
    AI = "AI"
    HUMAN = "HUMAN"


# --- Tillsattningar ---


class AppointmentStatus(Str):
    ADVERTISEMENT_FOUND = "ADVERTISEMENT_FOUND"
    APPLICATION_OPEN = "APPLICATION_OPEN"
    APPLICATION_CLOSED = "APPLICATION_CLOSED"
    RECRUITMENT_ONGOING = "RECRUITMENT_ONGOING"
    APPOINTMENT_NOT_FOUND = "APPOINTMENT_NOT_FOUND"
    REQUEST_READY = "REQUEST_READY"
    REQUEST_SENT = "REQUEST_SENT"
    RESPONSE_RECEIVED = "RESPONSE_RECEIVED"
    APPOINTMENT_IDENTIFIED = "APPOINTMENT_IDENTIFIED"
    APPOINTMENT_VERIFIED = "APPOINTMENT_VERIFIED"
    POSITION_CANCELLED = "POSITION_CANCELLED"
    CLOSED_UNRESOLVED = "CLOSED_UNRESOLVED"


# Verifieringsnivaer. Bara 1-3 raknas som verifierad tillsattning; se
# core/appointments.py och SECURITY.md.
VERIFICATION_LEVELS: dict[int, str] = {
    1: "Officiellt anstallningsbeslut",
    2: "Officiell myndighetsbekraftelse",
    3: "Bekraftelse fran registrator",
    4: "Offentlig professionell presentation",
    5: "Obekraftad uppgift",
}
MAX_VERIFIED_LEVEL = 3


class LegalBasis(Str):
    PUBLIC_DOCUMENT = "PUBLIC_DOCUMENT"
    LEGITIMATE_INTEREST = "LEGITIMATE_INTEREST"


class DocumentType(Str):
    EMPLOYMENT_DECISION = "EMPLOYMENT_DECISION"
    PRESS_RELEASE = "PRESS_RELEASE"
    BOARD_MINUTES = "BOARD_MINUTES"
    REGISTRAR_REPLY = "REGISTRAR_REPLY"
    WEB_PAGE = "WEB_PAGE"
    OTHER = "OTHER"


class RequestStatus(Str):
    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    SENT = "SENT"
    ANSWERED = "ANSWERED"
    REFUSED = "REFUSED"
    ABANDONED = "ABANDONED"


# --- Marknad ---


class ProviderRole(Str):
    CONSULTANCY_BROKER = "CONSULTANCY_BROKER"
    STAFFING = "STAFFING"
    RECRUITER = "RECRUITER"
    SUPPLIER = "SUPPLIER"


# --- System ---


class UserRole(Str):
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"


class RunStatus(Str):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class NotificationKind(Str):
    HIGH_MATCH_OPPORTUNITY = "HIGH_MATCH_OPPORTUNITY"
    NEW_PERMANENT_POSITION = "NEW_PERMANENT_POSITION"
    RECRUITMENT_CLOSED = "RECRUITMENT_CLOSED"
    APPOINTMENT_VERIFIED = "APPOINTMENT_VERIFIED"
    DEADLINE_APPROACHING = "DEADLINE_APPROACHING"
    FRAMEWORK_AGREEMENT_EXPIRING = "FRAMEWORK_AGREEMENT_EXPIRING"
    SOURCE_FAILING = "SOURCE_FAILING"


class NotificationStatus(Str):
    QUEUED = "QUEUED"
    SENT = "SENT"
    FAILED = "FAILED"
    SUPPRESSED = "SUPPRESSED"
