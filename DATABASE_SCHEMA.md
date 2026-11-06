# Databasschema – Interim Radar

PostgreSQL 17 med `pgvector` och svensk fulltextkonfiguration. Definitionerna finns i
`backend/app/models/` och migreringen i `backend/migrations/versions/`. Tabellerna nedan
är grupperade efter vad de svarar på, inte efter skapandeordning.

Alla tidsstämplar är `timestamptz` och lagras i UTC. Visning i svensk lokaltid sker i
frontend. Alla tabeller har `id` (UUID), `created_at` och `updated_at`.

## Organisationer

### `organisations`
Gemensam stam för allt som kan vara en arbetsgivare eller en köpare.

| Kolumn | Typ | Not |
|---|---|---|
| `name` | text | |
| `org_number` | text unik | 10 siffror utan bindestreck |
| `org_type` | enum | `STATE_AGENCY`, `REGION`, `MUNICIPALITY`, `UNIVERSITY`, `MUNICIPAL_COMPANY`, `OTHER_PUBLIC`, `PRIVATE` |
| `website` | text | |
| `county_code` | text | SCB:s länskod |
| `municipality_code` | text | SCB:s kommunkod |

### `authorities`
Det som bara gäller myndigheter, inklusive universitet och högskolor. 1:1 mot
`organisations`.

| Kolumn | Typ | Not |
|---|---|---|
| `organisation_id` | uuid FK | |
| `careers_url` | text | karriärsidan |
| `vacancies_url` | text | sidan som faktiskt listar tjänster |
| `registrar_email` | text | registrator |
| `recruitment_platform` | enum | `VARBI`, `REACHMEE`, `TEAMTAILOR`, `VISMA_RECRUIT`, `JOBYLON`, `OWN_HTML`, `PLATSBANKEN_ONLY`, `UNKNOWN` |
| `collection_method` | enum | `JOBTECH`, `SITEMAP`, `RSS`, `JSON_API`, `HTML_SCRAPE`, `MANUAL` |
| `appointment_publication_mode` | enum | `DIGITAL`, `PHYSICAL_NOTICE_BOARD`, `BOTH`, `UNKNOWN` |
| `notice_board_location` | text | adress, när beslut anslås fysiskt |
| `last_checked_at` | timestamptz | |
| `status` | enum | `ACTIVE`, `FAILING`, `MANUAL_ONLY`, `RETIRED` |

`municipalities` och `regions` är vyer över `organisations` filtrerade på `org_type`,
med SCB-koderna som nyckel. De finns som egna tabeller i specen men ger ingen egen
data utöver organisationsraden, så de implementeras som vyer för att undvika två
sanningar om samma kommun.

## Uppdrag och annonser

### `job_ads`
En annons som den såg ut när vi hittade den. Gäller både konsultuppdrag och fasta
tjänster.

| Kolumn | Typ | Not |
|---|---|---|
| `source_key` | text | `jobtech_live`, `ted`, `manual`, ... |
| `external_id` | text | källans eget id |
| `organisation_id` | uuid FK | |
| `title` | text | |
| `title_normalised` | text | gemener, utan skiljetecken, för dubblettkontroll |
| `description` | text | |
| `employment_type` | enum | `PERMANENT`, `FIXED_TERM`, `INTERIM_CONSULTANT`, `SUBSTITUTE`, `UNKNOWN` |
| `role_family` | enum | `CIO`, `IT_DIRECTOR`, `IT_MANAGER`, `DIGITALISATION_MANAGER`, `CTO`, `ARCHITECTURE_MANAGER`, `OPERATIONS_MANAGER`, `OTHER_IT_LEADERSHIP`, `NOT_RELEVANT` |
| `published_at` | timestamptz | |
| `application_deadline` | timestamptz | |
| `depublished_at` | timestamptz | när annonsen försvann från källan |
| `workplace_municipality` | text | |
| `url` | text | originallänk |
| `recruiter_id` | uuid FK null | förmedlare, när en sådan nämns |
| `snapshot_id` | uuid FK | **obligatorisk**, pekar på rådatan |

Unikt index på (`source_key`, `external_id`). Index på `title_normalised`,
`published_at`, `organisation_id`. GIN-index för fulltext på `title || description`
med konfiguration `swedish`. `embedding vector(1024)` för semantisk sökning, null när
AI saknas.

### `job_ad_versions`
Varje gång en annons ändras i källan skrivs den gamla versionen hit. Gör det möjligt
att se att en deadline förlängdes eller att en kravprofil skrevs om.

`job_ad_id`, `snapshot_id`, `valid_from`, `valid_to`, `changed_fields jsonb`.

### `opportunities`
Det som är intressant att agera på. En `opportunity` kan ha en `job_ad` som grund,
eller ett `procurement_notice`, eller båda.

| Kolumn | Typ | Not |
|---|---|---|
| `kind` | enum | `INTERIM_ASSIGNMENT`, `CONSULTING_ASSIGNMENT`, `FRAMEWORK_CALL_OFF`, `DIRECT_PROCUREMENT`, `PERMANENT_POSITION` |
| `job_ad_id` / `procurement_notice_id` | uuid FK null | |
| `status` | enum | `OPEN`, `CLOSED`, `AWARDED`, `CANCELLED`, `UNKNOWN` |
| `exclusion_status` | enum | `PASS`, `REVIEW_REQUIRED`, `EXCLUDED` |
| `match_score` | int null | 0–100, null när exkluderad |
| `duration_months` / `fee_sek_per_hour` | int null | |

### `procurement_notices`
Upphandlingsannonser. `notice_type` (`CONTRACT_NOTICE`, `AWARD_NOTICE`,
`FRAMEWORK_CALL_OFF`, `PRIOR_INFORMATION`, `DIRECT_AWARD`), `cpv_codes text[]`,
`buyer_organisation_id`, `estimated_value_sek`, `tender_deadline`,
`framework_agreement_id`, `snapshot_id`.

## Exkludering

### `exclusion_records`
En rad per bedömning, aldrig överskriven. Detta är systemets bevisbok.

| Kolumn | Typ | Not |
|---|---|---|
| `opportunity_id` | uuid FK | |
| `verdict` | enum | `PASS`, `REVIEW_REQUIRED`, `EXCLUDED` |
| `rule_id` | text | vilken regel som slog, t.ex. `SEC_CLEARANCE_EXPLICIT` |
| `matched_quote` | text | **exakt** formulering ur underlaget |
| `quote_offset` | int | tecken från dokumentets början |
| `document_url` | text | |
| `page_number` | int null | för PDF |
| `assessed_at` | timestamptz | |
| `assessor` | enum | `RULE`, `AI`, `HUMAN` |
| `ai_model` | text null | |
| `ai_reasoning` | text null | |
| `overridden_by_user_id` | uuid FK null | manuell överprövning |
| `override_reason` | text null | |

En post utan `matched_quote` kan inte ha `verdict = 'EXCLUDED'`; det är ett
check-villkor i databasen.

## Tillsättningar

### `appointments`
Ett rekryteringsärende som följs från annons till svar.

| Kolumn | Typ | Not |
|---|---|---|
| `job_ad_id` | uuid FK | |
| `authority_id` | uuid FK | |
| `status` | enum | de tolv statusarna i ARCHITECTURE.md |
| `status_changed_at` | timestamptz | |
| `diary_number` | text null | diarienummer när det är känt |
| `decision_date` / `start_date` | date null | |
| `verification_level` | int null | 1–5 |
| `appointed_person_id` | uuid FK null | |
| `resolution_note` | text | varför ärendet står där det står |

### `appointed_persons`
Den personuppgiftskänsliga tabellen. Innehåller `full_name`, `previous_role`,
`previous_organisation`, och ingenting annat om personen.

Plus, obligatoriskt per rad: `legal_basis` (enum, `PUBLIC_DOCUMENT` eller
`LEGITIMATE_INTEREST`), `source_document_id` (FK till `public_documents`, **inte
null**), `retention_until` (date), `erasure_requested_at`. Se SECURITY.md.

En rad får inte skapas utan ett dokument. Det är det som gör skillnad på en verifierad
tillsättning och ett rykte.

### `appointment_status_history`
`appointment_id`, `from_status`, `to_status`, `changed_at`, `changed_by`, `reason`,
`evidence_document_id`. Hela kedjan går att läsa i efterhand.

### `public_documents`
Hämtade handlingar. `authority_id`, `document_type` (`EMPLOYMENT_DECISION`,
`PRESS_RELEASE`, `BOARD_MINUTES`, `REGISTRAR_REPLY`, `WEB_PAGE`, `OTHER`), `title`,
`url`, `diary_number`, `document_date`, `file_path`, `sha256`, `extracted_text`,
`snapshot_id`.

### `information_requests`
Begäran om allmän handling. `authority_id`, `appointment_id`, `recipient_email`,
`subject`, `body`, `status` (`DRAFT`, `APPROVED`, `SENT`, `ANSWERED`, `REFUSED`,
`ABANDONED`), `approved_by_user_id`, `approved_at`, `sent_at`, `response_document_id`.

`status` kan bara bli `SENT` om `approved_by_user_id` inte är null. Check-villkor i
databasen, inte bara i applikationen.

## Marknad

`framework_agreements` (`name`, `agreement_number`, `owner_organisation_id`,
`valid_from`, `valid_to`, `extension_options`, `area`, `url`) med
`framework_agreement_suppliers` som kopplingstabell mot `suppliers` och
`rank_position`.

`providers` är konsultmäklare och bemanningsföretag, `suppliers` är leverantörer på
ramavtal, `recruiters` är rekryteringsföretag som IVO:s Poolia. Tre tabeller eftersom
samma bolag kan ha alla tre rollerna och vi vill kunna säga vilken roll det hade i ett
givet ärende.

`call_offs` kopplar `framework_agreement_id`, `buyer_organisation_id`,
`winning_supplier_id`, `value_sek`, `awarded_at`.

## System

`source_registry` – en rad per källa: `key`, `name`, `access_mode`, `base_url`,
`legal_note`, `robots_checked_at`, `status`, `last_success_at`, `last_error`,
`consecutive_failures`, `schedule_cron`.

`source_snapshots` – `source_key`, `external_id`, `fetched_at`, `http_status`,
`content_type`, `sha256`, `raw` (bytea eller filsökväg), `url`. Unikt index på
(`source_key`, `external_id`, `sha256`) så att oförändrad data inte sparas två gånger.

`collection_runs` – en rad per körning: `source_key`, `started_at`, `finished_at`,
`items_found`, `items_new`, `items_changed`, `errors`, `status`, `error_detail`.
Detta är vad dashboardens källhälsa läser.

`consultant_profiles` – redigerbar profil med `experiences jsonb`, `skills jsonb`,
`preferences jsonb`, `weights jsonb`. Vikterna ligger i profilen, inte i koden, så att
de kan ändras utan omstart.

`matching_results` – `opportunity_id`, `profile_id`, `score`, `subscores jsonb`,
`explanation`, `confidence`, `computed_at`, `engine_version`. Historik, så att en
ändrad vikt inte skriver över gamla bedömningar.

`confidence` är hur stor del av viktningen som faktiskt hade stöd i annonstexten,
0–100. En annons som varken anger arvode eller uppdragslängd kan inte få 100, hur hög
poängen än blir. Utan fältet ser en poäng byggd på gissningar precis ut som en poäng
byggd på text, och då är poängen inte värd något.

`notifications` – `kind`, `payload jsonb`, `status`, `sent_at`, `error`.

`users` – `email`, `password_hash` (argon2id), `role` (`ADMIN`, `ANALYST`), `is_active`,
`last_login_at`. Ingen publik registrering.

`audit_logs` – `user_id`, `action`, `object_type`, `object_id`, `before jsonb`,
`after jsonb`, `ip`, `at`. Skrivs för varje manuell överprövning, varje godkänd
begäran och varje profiländring.

`saved_searches` – `user_id`, `name`, `filters jsonb`.

## Index som faktiskt behövs

Utöver primär- och främmandenycklar:

- `job_ads (source_key, external_id)` unikt – dubblettspärr på källnivå
- `job_ads` GIN på `to_tsvector('swedish', title || ' ' || description)` – fritextsök
- `job_ads (published_at desc)` – dashboardens senaste-lista
- `job_ads (application_deadline)` partiellt där `depublished_at is null` – kommande deadlines
- `opportunities (match_score desc)` partiellt där `exclusion_status = 'PASS'` – topplistan
- `appointments (status, status_changed_at)` – ärenden som står still
- `framework_agreements (valid_to)` – avtal som löper ut
- `source_snapshots (source_key, external_id, sha256)` unikt – oförändrad data
- `job_ads` ivfflat på `embedding` – semantisk sökning, skapas först när embeddings finns
