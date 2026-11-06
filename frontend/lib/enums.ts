// GENERERAD FIL -- andra inte har.
//
// Skapad av backend/scripts/gen_enums.py ur app/models/enums.py.
// Kor om efter en andring i backendens enums:
//
//     cd backend && python -m scripts.gen_enums
//
// Etiketterna pa svenska ligger i lib/format.ts. De ar skrivna som
// Record<Union, string>, sa tsc sager till om ett varde har lagts till eller
// tagits bort.


export type AccessMode =
  | "OPEN_API"
  | "PUBLIC_HTML"
  | "MANUAL_ONLY"
  | "BLOCKED";

export type AppointmentPublicationMode =
  | "DIGITAL"
  | "PHYSICAL_NOTICE_BOARD"
  | "BOTH"
  | "UNKNOWN";

export type AppointmentStatus =
  | "ADVERTISEMENT_FOUND"
  | "APPLICATION_OPEN"
  | "APPLICATION_CLOSED"
  | "RECRUITMENT_ONGOING"
  | "APPOINTMENT_NOT_FOUND"
  | "REQUEST_READY"
  | "REQUEST_SENT"
  | "RESPONSE_RECEIVED"
  | "APPOINTMENT_IDENTIFIED"
  | "APPOINTMENT_VERIFIED"
  | "POSITION_CANCELLED"
  | "CLOSED_UNRESOLVED";

export type Assessor = "RULE" | "AI" | "HUMAN";

export type CollectionMethod =
  | "JOBTECH"
  | "SITEMAP"
  | "RSS"
  | "JSON_API"
  | "HTML_SCRAPE"
  | "MANUAL";

export type DocumentType =
  | "EMPLOYMENT_DECISION"
  | "PRESS_RELEASE"
  | "BOARD_MINUTES"
  | "REGISTRAR_REPLY"
  | "WEB_PAGE"
  | "OTHER";

export type EmploymentType =
  | "PERMANENT"
  | "FIXED_TERM"
  | "INTERIM_CONSULTANT"
  | "SUBSTITUTE"
  | "UNKNOWN";

export type ExclusionVerdict = "PASS" | "REVIEW_REQUIRED" | "EXCLUDED";

export type LegalBasis = "PUBLIC_DOCUMENT" | "LEGITIMATE_INTEREST";

export type NoticeType =
  | "CONTRACT_NOTICE"
  | "AWARD_NOTICE"
  | "FRAMEWORK_CALL_OFF"
  | "PRIOR_INFORMATION"
  | "DIRECT_AWARD";

export type OpportunityKind =
  | "INTERIM_ASSIGNMENT"
  | "CONSULTING_ASSIGNMENT"
  | "FRAMEWORK_CALL_OFF"
  | "DIRECT_PROCUREMENT"
  | "PERMANENT_POSITION";

export type OpportunityStatus =
  | "OPEN"
  | "CLOSED"
  | "AWARDED"
  | "CANCELLED"
  | "UNKNOWN";

export type OrgType =
  | "STATE_AGENCY"
  | "REGION"
  | "MUNICIPALITY"
  | "UNIVERSITY"
  | "MUNICIPAL_COMPANY"
  | "OTHER_PUBLIC"
  | "PRIVATE";

export type ProviderRole =
  | "CONSULTANCY_BROKER"
  | "STAFFING"
  | "RECRUITER"
  | "SUPPLIER";

export type RecruitmentPlatform =
  | "VARBI"
  | "REACHMEE"
  | "TEAMTAILOR"
  | "VISMA_RECRUIT"
  | "JOBYLON"
  | "OWN_HTML"
  | "PLATSBANKEN_ONLY"
  | "UNKNOWN";

export type RequestStatus =
  | "DRAFT"
  | "APPROVED"
  | "SENT"
  | "ANSWERED"
  | "REFUSED"
  | "ABANDONED";

export type RoleFamily =
  | "CIO"
  | "IT_DIRECTOR"
  | "IT_MANAGER"
  | "DIGITALISATION_MANAGER"
  | "CTO"
  | "ARCHITECTURE_MANAGER"
  | "OPERATIONS_MANAGER"
  | "OTHER_IT_LEADERSHIP"
  | "NOT_RELEVANT";

export type RunStatus =
  | "RUNNING"
  | "SUCCESS"
  | "PARTIAL"
  | "FAILED"
  | "SKIPPED";

export type SourceStatus =
  | "ACTIVE"
  | "FAILING"
  | "MANUAL_ONLY"
  | "BLOCKED"
  | "RETIRED";

export type UserRole = "ADMIN" | "ANALYST";
