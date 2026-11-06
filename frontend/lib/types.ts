// Typer som speglar app/schemas.py i backend.
//
// Strangunionerna ar inte skrivna har: de genereras ur backendens enums av
// backend/scripts/gen_enums.py till lib/enums.ts, och reexporteras nedan. Fem
// av dem hade fel varden nar de var handskrivna, och ett felstavat varde i en
// strangunion ar fortfarande giltig TypeScript -- det syns bara som ett filter
// som aldrig traffar.

export type {
  AccessMode,
  AppointmentPublicationMode,
  AppointmentStatus,
  Assessor,
  CollectionMethod,
  DocumentType,
  EmploymentType,
  ExclusionVerdict,
  LegalBasis,
  NoticeType,
  OpportunityKind,
  OpportunityStatus,
  OrgType,
  ProviderRole,
  RecruitmentPlatform,
  RequestStatus,
  RoleFamily,
  RunStatus,
  SourceStatus,
  UserRole,
} from "./enums";

import type {
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
} from "./enums";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  last_login_at: string | null;
}

export interface JobAd {
  id: string;
  source_key: string;
  external_id: string;
  title: string;
  description: string | null;
  organisation_name: string | null;
  employment_type: EmploymentType;
  role_family: RoleFamily;
  occupation_label: string | null;
  published_at: string | null;
  application_deadline: string | null;
  depublished_at: string | null;
  workplace_municipality: string | null;
  workplace_region: string | null;
  url: string | null;
  snapshot_id: string;
}

export interface Exclusion {
  verdict: ExclusionVerdict;
  rule_id: string | null;
  matched_quote: string | null;
  quote_offset: number | null;
  document_url: string | null;
  page_number: number | null;
  assessed_at: string;
  assessor: string;
  ai_model: string | null;
  ai_reasoning: string | null;
  override_reason: string | null;
}

export interface Match {
  score: number;
  confidence: number | null;
  explanation: string | null;
  subscores: Record<
    string,
    {
      label: string;
      weight: number;
      score: number;
      points: number;
      unknown: boolean;
      evidence: string[];
    }
  > | null;
}

export interface Opportunity {
  id: string;
  kind: OpportunityKind;
  status: OpportunityStatus;
  exclusion_status: ExclusionVerdict;
  match_score: number | null;
  duration_months: number | null;
  fee_sek_per_hour: number | null;
  job_ad: JobAd | null;
  created_at: string;
}

export interface OpportunityDetail extends Opportunity {
  exclusion: Exclusion | null;
  matching: Match | null;
  appointment_id: string | null;
}

export interface AppointmentHistory {
  from_status: AppointmentStatus | null;
  to_status: AppointmentStatus;
  changed_at: string;
  changed_by: string;
  reason: string | null;
}

export interface Appointment {
  id: string;
  status: AppointmentStatus;
  status_changed_at: string;
  diary_number: string | null;
  decision_date: string | null;
  start_date: string | null;
  verification_level: number | null;
  verification_label: string | null;
  resolution_note: string | null;
  last_searched_at: string | null;
  job_ad: JobAd | null;
  authority_name: string | null;
  appointed_person_name: string | null;
  appointed_person_previous_role: string | null;
}

export interface AppointmentDetail extends Appointment {
  history: AppointmentHistory[];
  information_request_id: string | null;
  decision_document_url: string | null;
}

export interface PublicDocument {
  id: string;
  document_type: DocumentType;
  title: string | null;
  url: string | null;
  diary_number: string | null;
  document_date: string | null;
  acquisition: string | null;
  sha256: string | null;
  has_text: boolean;
  created_at: string;
}

export interface InformationRequest {
  id: string;
  authority_id: string;
  appointment_id: string | null;
  recipient_email: string | null;
  subject: string;
  body: string;
  status: RequestStatus;
  approved_at: string | null;
  sent_at: string | null;
  sent_channel: string | null;
  response_note: string | null;
  response_document_id: string | null;
}

export interface Organisation {
  id: string;
  name: string;
  org_number: string | null;
  org_type: OrgType;
  website: string | null;
}

export interface Authority {
  id: string;
  organisation_id: string;
  organisation_name: string | null;
  careers_url: string | null;
  vacancies_url: string | null;
  registrar_email: string | null;
  recruitment_platform: string;
  collection_method: string;
  appointment_publication_mode: AppointmentPublicationMode;
  notice_board_location: string | null;
  status: SourceStatus;
  verified_at: string | null;
  verification_source: string | null;
  last_checked_at: string | null;
}

export interface FrameworkAgreement {
  id: string;
  name: string;
  agreement_number: string | null;
  area: string | null;
  valid_from: string | null;
  valid_to: string | null;
  extension_months: number | null;
  url: string | null;
  days_left: number | null;
}

export interface Provider {
  id: string;
  name: string;
  org_number: string | null;
  website: string | null;
  assignment_count: number | null;
}

export interface Source {
  key: string;
  name: string;
  access_mode: AccessMode;
  status: SourceStatus;
  base_url: string | null;
  legal_note: string | null;
  robots_allows: boolean | null;
  robots_checked_at: string | null;
  schedule_cron: string | null;
  last_success_at: string | null;
  last_attempt_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
}

export interface Run {
  id: string;
  source_key: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  items_found: number;
  items_new: number;
  items_changed: number;
  items_duplicate: number;
  errors: number;
  error_detail: string | null;
}

export interface Profile {
  id: string;
  name: string;
  is_active: boolean;
  headline: string | null;
  experiences: Array<Record<string, unknown>> | null;
  skills: string[] | null;
  preferences: Record<string, unknown> | null;
  weights: Record<string, number> | null;
}

export interface ChartPoint {
  label?: string;
  period?: string;
  count: number;
}

export interface Dashboard {
  new_opportunities_7d: number;
  active_interim: number;
  permanent_positions: number;
  recruitments_closed: number;
  appointments_identified: number;
  appointments_verified: number;
  appointments_unresolved: number;
  requests_awaiting_approval: number;
  excluded_count: number;
  review_required_count: number;
  top_matches: Opportunity[];
  upcoming_deadlines: Opportunity[];
  expiring_agreements: FrameworkAgreement[];
  recent_appointments: Appointment[];
  failing_sources: Source[];
  charts: {
    ads_per_week: ChartPoint[];
    by_org_type: ChartPoint[];
    recruitments_per_authority: ChartPoint[];
    appointments_over_time: ChartPoint[];
    by_recruiter: ChartPoint[];
    by_region: ChartPoint[];
  };
}

export interface MarketIntelligence {
  window_months: number;
  recurring_interim_buyers: Array<{ organisation: string; org_type: string; assignments: number }>;
  frequent_recruiters: Array<{ organisation: string; org_type: string; positions: number }>;
  brokers_by_volume: Array<{ provider: string; assignments: number }>;
  suppliers_winning_call_offs: Array<{
    provider: string;
    call_offs: number;
    total_value_sek: number;
  }>;
  expiring_agreements: FrameworkAgreement[];
  organisations_with_leadership_turnover: Array<{ organisation: string; recruitments: number }>;
  caveat: string;
}

export interface Coverage {
  authorities_total: number;
  authorities_active: number;
  authorities_unverified: number;
  with_vacancies_url: number;
  with_registrar_email: number;
  physical_notice_board: number;
  note?: string;
}

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface ExclusionRuleInfo {
  rule_id: string;
  category: string;
  pattern: string;
  description: string;
}
