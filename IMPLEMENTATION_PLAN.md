# Genomförandeplan – Interim Radar

Planen följer den ordning som beställningen anger, med en ändring: ordningen är
styrd av vilka källor som visade sig fungera, inte av hur listan råkade skrivas.
JobTechs historiska API visade sig vara nyckeln till tillsättningsspårningen, och det
flyttar fas 4 närmare början.

Status per 2026-11-06. Alla tal nedan är räknade i koden eller i databasen, inte
uppskattade. Kommandot som ger talet står inom parentes där det inte är självklart.

## Fas 1 – Grundplattform  ✅ KLAR

- [x] Projektstruktur, backend och frontend
- [x] Databasmodell, **25 tabeller**, Alembic-migrering `0001_initial`
      (32 index, 8 check-villkor)
- [x] Inloggning med argon2id och JWT i httpOnly-cookie
- [x] Källregister med lägen OPEN_API / PUBLIC_HTML / MANUAL_ONLY / BLOCKED
- [x] Snapshot-lager med sha256 och dubblettspärr
- [x] Exkluderingsfilter med tre utfall och citatkrav
- [x] Matchningsmotor 0–100 med delpoäng, förklaring och `confidence`: hur stor
      del av viktningen som faktiskt hade stöd i annonstexten
- [x] Redigerbar konsultprofil med vikter i databasen
- [x] Manuell import
- [x] Dashboard med tio menyposter och sex diagram, 13 sidor

## Fas 2 – Automatisk insamling  ✅ KLAR för de källor som får läsas

- [x] `jobtech_live` – annonser som är publicerade nu
- [x] `jobtech_hist` – avpublicerade annonser, med avpubliceringsdatum
- [x] `ted` – EU-upphandling, expert-query
- [x] Dubblettkontroll i tre steg
- [x] Versionshistorik per annons
- [x] Celery-scheman och retry
- [ ] `authority_pages` – ramverket är klart och testat mot verklig HTML, men
      **ingen** myndighets listningssida är verifierad ännu. Alla 384 rader står
      som `MANUAL_ONLY`, och `careers_url` är tom överallt utom för IVO. Se
      *Rättelse* nedan.
- [ ] Brainville, Ework, Poolia, Bemannia – robots tillåter, men ingen listningssida
      är verifierad ännu. Står som `MANUAL_ONLY`.

Mercell, TendSign, Kommers och Opic skrapas inte. Se DATA_SOURCES.md för varför, och
för vad som används i stället.

Senaste kontroll av källorna (`python -m scripts.probe_sources`, 2026-11-06):
3 svarar 200, 1 svarar 405 på GET därför att den bara tar POST (TED), 15 provas
inte med flit eftersom de är `MANUAL_ONLY` eller `BLOCKED`.

Senaste skarpa insamling (`python -m app.cli collect jobtech_live`): 1 078 annonser
lästa → 132 nya, 11 ändrade, 11 dubbletter, 935 irrelevanta roller, 46 exkluderade,
6 kräver granskning, 0 fel.

## Fas 3 – Government Careers  🟡 DELVIS

- [x] Myndighetsregister som datamodell med registrator, karriärsida,
      rekryteringsplattform, insamlingsmetod och publiceringssätt för beslut
- [x] **384 organisationer** seedade ur verklig annonsdata: 124 statliga
      myndigheter, 31 lärosäten, 20 regioner, 209 kommuner. Organisationsnumren
      är filtrerade på Skatteverkets nummerserier (2021/2120/2321) och tagna ur
      JobTech-annonser. Inget nummer är gissat.
- [x] Fasta tjänster identifieras (`employment_type = PERMANENT`)
- [x] Historiska annonser via JobTech
- [x] Rekryteringsstatus
- [ ] **Kontaktuppgifter och sidor per myndighet.** Det här är den största luckan
      i systemet, och den syns i `GET /authorities/coverage`:
      1 av 384 rader har registratorsadress (IVO), 0 har verifierad karriärsida,
      0 har `vacancies_url`, och plattformen är igenkänd på URL-mönster för 10
      rader (9 Varbi, 1 bara Platsbanken). Resten står som `UNKNOWN`, vilket är
      sant: vi vet inte.

### Rättelse 2026-11-06

Seedningen skrev tidigare in organisationens startsida som `careers_url`. Det var
ett påstående utan täckning – `https://www.forsvarsmakten.se/` är inte en
karriärsida – och 225 rader såg verifierade ut utan att vara det. Fältet sätts nu
bara när någon faktiskt har verifierat sidan med
`python -m app.cli verify-authority --url ... --name ...`. Adressen ur annonsen
ligger kvar på organisationen, i `organisations.website`, där den hör hemma.

### Rättelse 2026-11-06, rollklassificeringen

Sex matlagningsannonser låg i uppdragslistan som IT-ledning: *Förste Kock /
sous-chef*, *Junior Sous Chef*, *Executive Chef – Facility Management*,
*Executive Head Chef*, *Sous Chef till Mr.Bronck* och en *Head Chef* i
Reykjavik. Orsaken är att *chef* betyder två olika saker: titeln matchade
`chef` och brödtexten nämnde kassasystem, vilket räckte för att regeln
"chefsroll med IT-innehåll i texten" skulle slå till.

`WRONG_KIND_OF_CHEF` i `app/core/classify.py` prövas nu på titeln först av allt,
och en träff är definitiv – ingen brödtext kan göra en kock till IT-chef. Tio
tester i `tests/test_matching.py` provar både att köksyrkena faller bort och att
spärren inte tar med sig riktiga chefsroller. De sex annonserna är rensade ur
databasen; snapshotten ligger kvar, så det går att se att de passerade och
varför de sorterades bort.

### Rättelse 2026-11-06, villkorade säkerhetskrav och insamlingsvägen

Rapporterat av användaren: Statens fastighetsverk sökte i oktober 2026 en
**vikarierande enhetschef för enheten IT-arkitektur och IT-säkerhet** – en tjänst
mitt i målgruppen, med verksamhets-, personal- och budgetansvar för 20
medarbetare, vikariat till 2027-06-30, Stockholm. Den fanns inte i systemet.
Tre separata fel, alla verifierade mot källan:

1. **Villkorade krav behandlades som uttryckliga.** Annonsen innehåller statens
   standardformulering: *"Innan ett beslut om anställning fattas kan en
   säkerhetsprövning enligt säkerhetsskyddslagen (2018:585) komma att
   genomföras."* Filtret läste det som ett krav och satte `EXCLUDED`. Samma text
   står i en stor del av statens annonser, så felet tog bort en hel kategori.
   `app/core/exclusion.py` skiljer nu på uttryckligt och villkorat: `kan komma
   att`, `i vissa fall`, `om anställningen avser` och liknande ger
   `REVIEW_REQUIRED` med citatet sparat, aldrig `PASS` och aldrig automatisk
   exkludering. Villkorsordet måste stå i samma sats som kravet – annars smittar
   ett *"lönen kan komma att förhandlas"* ner nästa mening. Finns både ett
   villkorat och ett ovillkorat krav gäller det ovillkorade. Fem tester i
   `tests/test_exclusion.py`.
2. **Den historiska källan hade aldrig körts.** `collection_runs` visade en enda
   körning: `jobtech_live`. Annonsen avpublicerades 2026-10-26, innan systemet
   fanns, och finns därför bara i `historical`-API:et. Den källan saknade
   dessutom tidsfönster, och `q="IT-chef"` ger 4 656 träffar sedan 2016 – med
   pagineringstaket hämtas 1 000 av dem, och API:ets ordning avgjorde vilka.
   `HISTORICAL_DAYS = 180` gör sökningen uttömmande för den period som betyder
   något.
3. **Insamlingen gick bara via sökord.** 19 fritextfraser och 2 yrkesbegrepp var
   enda vägen in. Statens titlar ser ut som *"Chef till enheten för IT-arkitektur
   och IT-säkerhet"* och *"Verksamhetsområdeschef Digitalisering och IT"*, och en
   sökordslista träffar dem bara av tur. `collect --authorities` sveper i stället
   myndighetsregistret per organisationsnummer och låter klassificeringen avgöra
   vad som är en ledningsroll. Schemalagt nattligt i `beat` för båda källorna.
   Samtidigt rättades att `employer=202100-4474` med bindestreck ger 0 träffar
   **utan felkod** – värsta sortens svar, eftersom det ser ut som att myndigheten
   inte annonserar något.

Och en fjärde sak som följde av den första: en rättad regel är värd noll så länge
den bara gäller nya annonser. Insamlingen hoppar över en annons vars snapshot är
oförändrad, så de redan exkluderade låg kvar. `python -m app.cli reassess` kör
filtret igen på sparade uppdrag, skriver en **ny** bedömningsrad i stället för att
skriva över historiken, och rör aldrig ett utfall som en människa har satt. Första
körningen flyttade fyra uppdrag från `EXCLUDED` till `REVIEW_REQUIRED`.

**Vad myndighetssvepet visade om regeln.** Svepet hämtade 51 063 historiska och
9 451 aktuella annonser från 384 myndigheter: 1 032 nya uppdrag, 182 ändrade.
Databasen innehåller nu 1 161 uppdrag, 61 572 snapshottar och 709 organisationer,
och först då fanns underlag nog att se om villkorsregeln dög. Ett stickprov på de
exkluderade visade tre formuleringar till som regeln inte tog, alla ordagrant ur
statliga annonser:

- *"Därför kan vi komma att behöva genomföra en säkerhetsprövning"* – orden mellan
  `kan` och `komma att` bröt mönstret.
- *"Vissa befattningar är placerade i säkerhetsklass och då kommer en
  säkerhetsprövning att genomföras"* – gäller kravet bara vissa tjänster vet vi
  inte om det gäller den här.
- *"Vi gör även personutredningar"* – Kriminalvården, Socialstyrelsen och
  socialtjänsten **utför** personutredningar. Det är arbetsuppgiften, inte ett
  krav på den sökande. Regeln exkluderade dem på deras egen
  verksamhetsbeskrivning. Ordet kräver nu närhet till rekryteringen
  (`anställ`, `rekryter`, `befattning`, `kandidat`, `sökande`, `konsult`, 200
  tecken); utan den närheten fångas det i stället av `PERSONAL_VETTING_PLAIN` och
  blir manuell bedömning, så det blir aldrig ett tyst `PASS`.

`ENGINE_VERSION` är `excl-3` och fungerar som staleness-markör: `reassess` bedömde
om alla 1 161 och flyttade 83 uppdrag. Fördelningen gick från 548 `PASS` / 518
`EXCLUDED` / 95 `REVIEW_REQUIRED` till **546 / 439 / 176**. De 439 som står kvar
som exkluderade har ovillkorliga krav – stickprov: *"kommer att genomföras innan
beslut om anställning fattas"*, *"kommer att genomföras före anställning"*,
*"behöver du kunna uppvisa ett giltigt utdrag ur belastningsregistret innan du
börjar arbeta"*. Fyra tester till i `tests/test_exclusion.py`, byggda på de
verkliga meningarna.

## Fas 4 – Executive Appointments  ✅ KLAR

- [x] Tillståndsmaskin med tolv statusar och spärrar mot otillåtna övergångar
- [x] Vägrar `APPOINTMENT_IDENTIFIED` utan dokument
- [x] Verifieringsnivå 1–5, bara 1–3 räknas som verifierad
- [x] Söker beslut på myndighetens webbplats och i pressmeddelanden
- [x] Registratorregister
- [x] Generering av begäran om allmän handling, alltid som utkast
- [x] Stöd för fysisk anslagstavla som publiceringssätt, inklusive
      `POST /appointments/{id}/documents` för en handling som hämtats manuellt
- [x] **IVO-testärendet**, med verklig annons hämtad från källa
- [x] Historik per statusbyte

## Fas 5 – Market Intelligence  🟡 DELVIS

- [x] Datamodell för ramavtal, leverantörer, avrop, förmedlare
- [x] Analyser: myndigheter som ofta rekryterar IT-chefer, ramavtal som löper ut,
      förmedlare per uppdrag, tillsättningar över tid
- [ ] Automatisk insamling av ramavtal från Avropa.se. Modellen finns, adaptern
      inte. Sidan svarar 200 och robots tillåter läsning, så det är gjort arbete
      som återstår, inte en spärr.
- [ ] Prognoser. Medvetet uppskjutet: en prognos från några månaders data skulle
      vara en siffra utan täckning. Byggs när det finns minst ett års historik.

## Fas 6 – Produktion  🟡 DELVIS

- [x] `docker-compose.yml` med sex tjänster (db, redis, api, worker, beat, web),
      `backend/Dockerfile`, `frontend/Dockerfile`, `.env.example`
- [x] `alembic.ini`, `migrations/env.py` och `0001_initial`, genererad ur modellerna
      av `scripts/gen_migration.py`
- [x] Schemaläggning via Celery beat
- [x] Aviseringar med tröskel, köade i `notifications`
- [x] Säkerhet: rate limit, argon2id, check-villkor i databasen, audit-logg
- [x] **157 tester**: 151 som kör mot SQLite utan beroenden, 6 integrationstester
      mot verkliga API:er. Täcker exkluderingsfiltret, matchningen,
      rollklassificeringen, dubblettkontrollen, tillståndsmaskinen,
      JobTech-normaliseringen, begäranden, AI-kontraktet och hela IVO-flödet.
- [x] Backup- och återställningsskript (`scripts/backup.sh`,
      `scripts/restore_test.sh`)
- [x] Dokumentation
- [ ] Utskick av avisering kräver SMTP-uppgifter. Kön fylls, leveransen är inte
      testad mot en verklig server.
- [ ] TLS och reverse proxy. Compose-filen binder portarna till 127.0.0.1;
      Caddy-konfiguration behövs vid driftsättning.

## Vad som är verifierat och vad som inte är det

Det här avsnittet finns för att skillnaden ska gå att se utan att läsa koden.

**Verifierat mot verkliga data, 2026-11-06**

| Vad | Hur |
|---|---|
| JobTech live och historiskt, TED | 6 integrationstester, `pytest -m integration`, 188 s, alla gröna |
| Källornas tillgänglighet | `python -m scripts.probe_sources` |
| Insamling, dubbletter, exkludering, matchning | 1 078 verkliga annonser genom hela kedjan |
| IVO-ärendet | Genomgånget i webbläsaren: status `REQUEST_READY`, inget namn registrerat, utkast till registrator med rätt text |
| Hela API:et | 41 slutpunkter, 151 tester |
| Frontend | 13 sidor byggda, 0 sårbarheter i `npm audit` |
| Compose-filen | `docker compose config` utan fel |

**Flyttat till CI i stället för att stå som otestat**

Docker-demonen gick inte att starta på utvecklingsmaskinen, så tre saker kunde
inte provas här. De provas nu av en Linux-körare i GitHub Actions, vilket är
bättre än att de provas en gång för hand: `.github/workflows/ci.yml` kör
migreringen mot PostgreSQL 17 med pgvector, och `.github/workflows/stack.yml`
bygger bilderna, startar alla sex tjänsterna och kör återställningsprovet.
Status syns under fliken Actions.

Arbetsflödena är validerade lokalt – YAML:en tolkas, varje `run`-steg passerar
`bash -n`, och alla nio inbäddade Python-snuttar kompilerar – men de har inte
kört en enda gång, eftersom projektet ännu inte är pushat. Till dess står
raderna nedan kvar som otestade.

**Inte verifierat**

| Vad | Varför inte, och vad som krävs |
|---|---|
| `alembic upgrade head` mot PostgreSQL | Provas av `ci.yml`, jobbet *migrering*, så snart projektet är pushat. |
| Containerbilderna | Provas av `stack.yml`, jobbet *bygg*. |
| `restore_test.sh` | Provas av `stack.yml`, sista steget. |
| SMTP-leverans | Inga uppgifter att testa mot. |
| AI-leverantörerna | `AI_PROVIDER=none` är standard. Anthropic- och den lokala adaptern är skrivna men aldrig anropade mot ett riktigt API; kontraktet runt dem är däremot testat med 20 tester. |
| Fältkryptering | `cryptography` gick inte att installera på utvecklingsmaskinen (Windows ARM64, inget färdigt wheel). Importen är därför lat, och koden körs utan den – men krypteringen är otestad. Fungerar på den linux/amd64 som containern bygger för. |

## Vad som återstår, i den ordning jag skulle ta det

1. **Driftsätt och kör migreringen.** Allt annat i listan blir lättare när det
   finns en riktig PostgreSQL. `docker compose up -d db redis` och
   `alembic upgrade head`, sedan `restore_test.sh` samma dag.
2. **Registratorsadresser.** 1 av 384 rader har en. Utan dem kan en begäran om
   allmän handling inte godkännas, och det är den funktion som gör
   tillsättningsspårningen användbar. Adresserna står på myndigheternas egna
   sidor och går att samla in med `authority_pages`-ramverket.
3. **Verifiera karriärsidorna**, en myndighet i taget, med
   `python -m app.cli verify-authority`. Börja med de 124 statliga myndigheterna.
4. **Ramavtalsadapter mot Avropa.se.** Ger ramavtal som löper ut, vilket är den
   starkaste tidiga signalen för kommande interimbehov.
5. **SMTP och leveranstest** av aviseringar.
6. **Prognoser**, när historiken räcker.

## Avgränsningar som är medvetna

- **Inga skrapade kommersiella annonsdatabaser.** Se DATA_SOURCES.md.
- **Inga prognoser utan data.** En uppskattning märkt som uppskattning är ändå
  värdelös om underlaget är tre månader långt.
- **Inga gissade uppgifter i myndighetsregistret.** 384 rader med belagda
  organisationsnummer och tomma kontaktfält slår 384 rader där adresserna är
  konstruerade ur ett URL-mönster.
- **Ingen inloggning å användarens vägnar** hos konsultmäklare.
- **AI kan skärpa men aldrig mildra.** En språkmodell får flytta ett ärende från
  `PASS` till `REVIEW_REQUIRED`, aldrig åt andra hållet, och ett förslag om
  exkludering utan ordagrant citat ur annonsen förkastas. Se `backend/app/ai/`.
