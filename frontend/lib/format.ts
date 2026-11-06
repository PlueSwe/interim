// Visning av datum, tid och etiketter.
//
// Databasen lagrar allt i UTC. Allt som visas ska visas i svensk lokaltid, och
// det ar den har filen som gor omvandlingen -- inte varje sida for sig, och
// inte webblasarens tidszon, som kan vara en annan.

import type {
  AccessMode,
  DocumentType,
  OpportunityStatus,
  RunStatus,
  AppointmentPublicationMode,
  AppointmentStatus,
  EmploymentType,
  ExclusionVerdict,
  OpportunityKind,
  OrgType,
  RequestStatus,
  RoleFamily,
  SourceStatus,
} from "./enums";

const TIDSZON = "Europe/Stockholm";

const datumtid = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TIDSZON,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const datumformat = new Intl.DateTimeFormat("sv-SE", {
  timeZone: TIDSZON,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** UTC-tidsstampel till svensk lokaltid. */
export function visaDatumTid(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return datumtid.format(d).replace(",", "");
}

export function visaDatum(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "–";
  return datumformat.format(d);
}

/** Dagar kvar till en deadline, rakt uttryckt. */
export function dagarKvar(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const dagar = Math.ceil((d.getTime() - Date.now()) / 86_400_000);
  if (dagar < 0) return `${Math.abs(dagar)} dagar sedan`;
  if (dagar === 0) return "i dag";
  if (dagar === 1) return "i morgon";
  return `${dagar} dagar kvar`;
}

export function visaKronor(belopp: number | null | undefined): string {
  if (belopp === null || belopp === undefined) return "–";
  return new Intl.NumberFormat("sv-SE", {
    style: "currency",
    currency: "SEK",
    maximumFractionDigits: 0,
  }).format(belopp);
}

export function visaTal(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  return new Intl.NumberFormat("sv-SE").format(n);
}

// --- Etiketter -------------------------------------------------------------
// Backend lamnar ut enum-varden pa engelska. Oversattningen hor i gransnittet,
// sa att databasvardena forblir stabila.

export const VERDICT_TEXT: Record<ExclusionVerdict, string> = {
  PASS: "Godkänd",
  REVIEW_REQUIRED: "Kräver granskning",
  EXCLUDED: "Exkluderad",
};

export const STATUS_TEXT: Record<AppointmentStatus, string> = {
  ADVERTISEMENT_FOUND: "Annons hittad",
  APPLICATION_OPEN: "Ansökan öppen",
  APPLICATION_CLOSED: "Ansökan stängd",
  RECRUITMENT_ONGOING: "Rekrytering pågår",
  APPOINTMENT_NOT_FOUND: "Tillsättning ej funnen",
  REQUEST_READY: "Begäran förberedd",
  REQUEST_SENT: "Begäran skickad",
  RESPONSE_RECEIVED: "Svar inkommet",
  APPOINTMENT_IDENTIFIED: "Tillsättning identifierad",
  APPOINTMENT_VERIFIED: "Tillsättning verifierad",
  POSITION_CANCELLED: "Tjänsten återkallad",
  CLOSED_UNRESOLVED: "Avslutad utan svar",
};

export const REQUEST_TEXT: Record<RequestStatus, string> = {
  DRAFT: "Utkast",
  APPROVED: "Godkänd",
  SENT: "Skickad",
  ANSWERED: "Besvarad",
  REFUSED: "Avslagen",
  ABANDONED: "Avbruten",
};

export const KIND_TEXT: Record<OpportunityKind, string> = {
  INTERIM_ASSIGNMENT: "Interimuppdrag",
  CONSULTING_ASSIGNMENT: "Konsultuppdrag",
  FRAMEWORK_CALL_OFF: "Avrop på ramavtal",
  DIRECT_PROCUREMENT: "Direktupphandling",
  PERMANENT_POSITION: "Anställning",
};

export const OPPORTUNITY_STATUS_TEXT: Record<OpportunityStatus, string> = {
  OPEN: "Öppen",
  CLOSED: "Stängd",
  AWARDED: "Tilldelad",
  CANCELLED: "Återkallad",
  UNKNOWN: "Okänd",
};

export const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  RUNNING: "Pågår",
  SUCCESS: "Klar",
  PARTIAL: "Delvis",
  FAILED: "Misslyckad",
  SKIPPED: "Överhoppad",
};

export const EMPLOYMENT_TEXT: Record<EmploymentType, string> = {
  PERMANENT: "Tillsvidare",
  FIXED_TERM: "Tidsbegränsad",
  INTERIM_CONSULTANT: "Interim/konsult",
  SUBSTITUTE: "Vikariat",
  UNKNOWN: "Okänd",
};

export const ROLE_TEXT: Record<RoleFamily, string> = {
  CIO: "CIO",
  IT_DIRECTOR: "IT-direktör",
  IT_MANAGER: "IT-chef",
  DIGITALISATION_MANAGER: "Digitaliseringschef",
  CTO: "CTO",
  ARCHITECTURE_MANAGER: "Arkitekturchef",
  OPERATIONS_MANAGER: "Driftchef",
  OTHER_IT_LEADERSHIP: "Annan IT-ledning",
  NOT_RELEVANT: "Ej relevant",
};

export const ORG_TEXT: Record<OrgType, string> = {
  STATE_AGENCY: "Statlig myndighet",
  REGION: "Region",
  MUNICIPALITY: "Kommun",
  UNIVERSITY: "Universitet/högskola",
  MUNICIPAL_COMPANY: "Kommunalt bolag",
  OTHER_PUBLIC: "Övrig offentlig",
  PRIVATE: "Privat",
};

export const ACCESS_TEXT: Record<AccessMode, string> = {
  OPEN_API: "Öppet API",
  PUBLIC_HTML: "Publik webbsida",
  MANUAL_ONLY: "Endast manuell import",
  BLOCKED: "Blockerad",
};

export const SOURCE_STATUS_TEXT: Record<SourceStatus, string> = {
  ACTIVE: "Aktiv",
  FAILING: "Fel",
  MANUAL_ONLY: "Endast manuell",
  BLOCKED: "Blockerad",
  RETIRED: "Avställd",
};

export const PUBLICATION_TEXT: Record<AppointmentPublicationMode, string> = {
  DIGITAL: "Digitalt",
  PHYSICAL_NOTICE_BOARD: "Fysisk anslagstavla",
  BOTH: "Digitalt och anslagstavla",
  UNKNOWN: "Okänt",
};

/** Verifieringsnivaerna, med den viktiga gransen markerad. */
export const VERIFIERING: Record<number, { text: string; racker: boolean }> = {
  1: { text: "Officiellt anställningsbeslut", racker: true },
  2: { text: "Officiell bekräftelse från myndigheten", racker: true },
  3: { text: "Bekräftelse från registrator", racker: true },
  4: { text: "Offentlig yrkespresentation", racker: false },
  5: { text: "Obekräftad uppgift", racker: false },
};

export const DOCUMENT_TEXT: Record<DocumentType, string> = {
  EMPLOYMENT_DECISION: "Anställningsbeslut",
  PRESS_RELEASE: "Pressmeddelande",
  BOARD_MINUTES: "Protokoll",
  REGISTRAR_REPLY: "Svar från registrator",
  WEB_PAGE: "Webbsida",
  OTHER: "Övrig handling",
};

export function etikett<T extends string>(karta: Record<T, string>, varde: T | null | undefined) {
  if (!varde) return "–";
  return karta[varde] ?? varde;
}
