# Säkerhet och GDPR – Interim Radar

## Hotbilden

Detta är en privat applikation för en person. Den stora risken är inte en angripare
som vill in, utan att systemet självt gör något fel utåt: skickar ett mejl till en
myndighet utan att användaren vet om det, eller pekar ut en namngiven person som
innehavare av en tjänst hen inte fått.

Säkerhetsarbetet handlar därför om två saker i den ordningen: att inga utgående
åtgärder sker utan godkännande, och att personuppgifter om tillsatta chefer hanteras
rätt.

## Autentisering

- Ingen publik registrering. Användare skapas med `python -m app.cli create-user`.
- Argon2id för lösenord (`argon2-cffi`), parametrar i `app/security.py`.
- JWT i `httpOnly`, `Secure`, `SameSite=Lax`-cookie. Åtkomsttoken 30 min,
  uppdateringstoken 14 dagar och rullande.
- Rate limit på inloggning: 5 försök per 15 min per IP och konto, i Redis.
- `users.role` är `ADMIN` eller `ANALYST`. Bara `ADMIN` får godkänna utgående
  begäranden och ändra exkluderingsbeslut.

## Utgående åtgärder

Systemet skickar ingenting självt. En `information_request` skapas som `DRAFT`. För
att bli `SENT` krävs:

1. En inloggad `ADMIN` godkänner i gränssnittet.
2. `approved_by_user_id` och `approved_at` sätts.
3. Databasen har ett check-villkor: `status = 'SENT'` kräver
   `approved_by_user_id is not null`.
4. Raden hamnar i `audit_logs` med fullständig text av det som skickades.

Punkt 3 finns för att applikationskod ändras och glömmer. Databasen glömmer inte.

E-postavisering till användaren själv är inte en utgående åtgärd i den här meningen
och kräver inget godkännande.

## Personuppgifter

### Vad som sparas

`appointed_persons` innehåller endast:

- namn
- tidigare roll och organisation, när det framgår av handlingen
- koppling till tjänsten och till det dokument uppgiften kommer från

Ingen kontaktinformation, inget personnummer, ingen bostadsort, inga uppgifter om
privatliv, ingen lön. Att en uppgift är offentlig gör den inte nödvändig.

### Laglig grund

Per rad, i kolumnen `legal_basis`:

- `PUBLIC_DOCUMENT` – uppgiften kommer ur en allmän handling som myndigheten lämnat
  ut. Behandlingen vilar på berättigat intresse enligt art. 6.1 f, och intresset är
  att kunna bedöma marknaden för chefsuppdrag i offentlig sektor. Att veta vem som
  leder IT-verksamheten vid en myndighet är en yrkesmässig uppgift om en person i en
  offentlig ledningsfunktion.
- `LEGITIMATE_INTEREST` – uppgiften kommer från myndighetens egen publicering, till
  exempel ett pressmeddelande.

Verifieringsnivå 4 och 5 (offentlig professionell presentation, obekräftad uppgift)
får **inte** ge en rad i `appointed_persons`. De stannar som en anteckning på
`appointments.resolution_note` utan namn. Ett LinkedIn-fynd är ett uppslag, inte ett
belägg, och ska inte bli en personuppgiftspost.

### Lagringstid

`retention_until` sätts till beslutsdatum + 5 år. En nattlig uppgift raderar rader
som passerat tiden. Fem år eftersom syftet är marknadsanalys över tid: vilka
myndigheter byter IT-chef ofta, och hur rör sig personer mellan dem. Längre än så
tillför inget.

### Rättelse och radering

`DELETE /api/v1/appointed-persons/{id}` raderar personraden, behåller `appointments`
med `appointed_person_id = null` och `resolution_note` uppdaterad, och loggar i
`audit_logs`. Själva handlingen i `public_documents` finns kvar, eftersom den är en
allmän handling och inte vår uppgift att radera.

`PATCH` på samma resurs rättar namn eller roll, med `audit_logs` som visar före och
efter.

### Ingen profilering

Systemet matchar uppdrag mot användarens egen profil. Det bygger inga profiler över
tillsatta chefer, gör inga bedömningar av dem som personer, och fattar inga beslut om
dem.

## Känsliga uppgifter i uppdragsunderlag

Exkluderingsfiltret läser texter som kan innehålla uppgifter om säkerhetsskydd.
`exclusion_records.matched_quote` sparar ett citat ur underlaget, och citatet
begränsas till 500 tecken runt träffen. Hela dokument sparas bara när källan är
offentlig.

Ett underlag som är sekretessbelagt ska inte in i systemet över huvud taget.
Manuell import varnar när ett dokument innehåller `SEKRETESS`, `BEGRÄNSAD
SPRIDNING`, `HEMLIG` eller säkerhetsskyddsklassificering, och kräver bekräftelse.

## Teknisk säkerhet

- **SQL injection**: endast SQLAlchemy med parametriserade uttryck. Ingen
  strängkonkatenering av SQL. Fritextsökning går genom `plainto_tsquery`, inte
  interpolation.
- **XSS**: React escapar som standard. `dangerouslySetInnerHTML` används inte. Text
  från annonser renderas som text, aldrig som HTML, även när källan är HTML.
- **CSRF**: `SameSite=Lax` plus `Origin`-kontroll på alla muterande anrop.
- **Rate limiting**: `slowapi` mot Redis, 120 anrop/min per konto, 5/15 min på
  inloggning.
- **Hemligheter**: läses ur miljövariabler via `pydantic-settings`. `.env` är i
  `.gitignore`. `ANTHROPIC_API_KEY`, `SECRET_KEY` och databaslösenordet finns aldrig i
  loggar; `app/config.py` maskerar dem i `repr`.
- **Kryptering i vila**: `appointed_persons.full_name` och
  `information_requests.body` krypteras med AES-GCM via `cryptography`, nyckel i
  `FIELD_ENCRYPTION_KEY`. Resten av databasen förlitar sig på diskkryptering på
  VPS:en.
- **TLS**: Caddy eller nginx framför, HSTS på, inga okrypterade portar utåt. Postgres
  och Redis exponeras inte utanför Docker-nätverket.
- **Beroenden**: `pip-audit` och `npm audit` i CI.

## Insamlingsetik

- Tydlig User-Agent som identifierar systemet och ger en kontaktväg.
- `robots.txt` läses och respekteras före varje ny källa, och resultatet sparas i
  `source_registry.robots_checked_at`. En källa med `Disallow` får läget `BLOCKED` och
  adaptern vägrar köra.
- Minst 2 sekunder mellan anrop mot samma värd, 5 sekunder för HTML-sidor.
- Inga försök att kringgå inloggning, betalvägg, CAPTCHA eller åtkomstkontroll.
- Hämtar inte om innehållet är oförändrat, kontrollerat på sha256.

Se DATA_SOURCES.md för vilka källor som faktiskt får läsas.

## Loggning

`audit_logs` skrivs för: inloggning, manuell överprövning av exkluderingsbeslut,
godkännande och avsändning av begäran, ändring av konsultprofil och vikter, radering
av personuppgift, och ändring av källregistret.

Applikationsloggen är strukturerad JSON utan personuppgifter och utan hemligheter.
Rådata i `source_snapshots` är inte en logg utan bevis och omfattas av
lagringstiderna ovan.

## Backup

`pg_dump --format=custom` nattligen till en krypterad volym, 30 dagars historik, plus
en veckovis kopia utanför servern. Återställning testas med
`scripts/restore_test.sh`, som läser in senaste dumpen i en tillfällig databas,
kontrollerar att schemat har minst 25 tabeller, att `alembic_version` pekar på en
revision, och att de tabeller som bär systemets innehåll inte är tomma. En backup som
aldrig återställts är en förhoppning.

Skriptet skapar `vector`-tillägget i provdatabasen innan `pg_restore` körs, och kör
med `--exit-on-error`. Båda av samma skäl: det vanliga felet är att dumpen går igenom
men återställningen faller på ett saknat tillägg, och utan `--exit-on-error` skriver
`pg_restore` varningar och returnerar noll – ett trasigt prov ser då ut som ett
lyckat.

**Status 2026-11-06:** skriptet är syntaxkontrollerat men inte kört, eftersom det
kräver en körande `db`-tjänst. Det ska köras samma dag systemet driftsätts.
