# Arkitektur – Interim Radar

## Vad systemet är

En privat bevakningsplattform som läser svenska offentliga källor, hittar chefs- och
interimuppdrag inom IT och digitalisering, och följer en rekrytering vidare efter att
annonsen tagits ner – till och med frågan om vem som faktiskt fick tjänsten.

Plattformen publicerar ingenting utåt. Den skickar inga mejl utan att en människa har
godkänt dem. Den gissar aldrig fram en uppgift som den inte har en källa för.

## Grundprinciper

**1. Varje påstående har en källa.** Varje rad i `opportunities`, `job_ads`,
`appointments` och `exclusion_records` pekar på en rad i `source_snapshots`, som i sin
tur håller rå svarsdata, hämtningstidpunkt, HTTP-status och sha256 av innehållet. Går
det inte att spåra en uppgift till ett snapshot är uppgiften en gissning, och en
gissning hör inte hemma i databasen.

**2. Tyst misslyckande är värre än synligt.** Varje adapter rapporterar ett
`SourceRunResult` med antal träffar, antal fel och en orsak. En källa som inte svarar
får `source_registry.status = 'FAILING'` och syns på dashboarden. Systemet låtsas
aldrig att en insamling gick bra.

**3. Osäkerhet eskalerar till människa.** Exkluderingsfiltret har tre utfall, inte två.
Tillsättningar får verifieringsnivå 1–5 och bara 1–3 räknas som verifierade. En
begäran om allmän handling blir ett utkast, aldrig ett skickat mejl.

**4. Personuppgifter är den känsliga delen.** En tillsättning namnger en verklig
person. Den delen av datamodellen har egna regler: bara yrkesmässiga offentliga
uppgifter, laglig grund dokumenterad per post, och radering som faktiskt fungerar. Se
SECURITY.md.

## Komponenter

```
                     +--------------------------+
                     |  Next.js 16 (App Router) |   dashboard, sökning,
                     |  TypeScript + Tailwind   |   granskningsvyer
                     +------------+-------------+
                                  | REST + JWT (httpOnly cookie)
                     +------------+-------------+
                     |   FastAPI + Pydantic v2  |
                     |   app/api/routes_*.py    |
                     +------------+-------------+
          +-----------------------+-----------------------+
          |                       |                       |
   +------+------+       +--------+--------+     +--------+--------+
   |   core/     |       |   sources/      |     |     ai/         |
   | exclusion   |       | jobtech_live    |     | provider        |
   | matching    |       | jobtech_hist    |     | (anthropic |    |
   | dedup       |       | ted             |     |  lokal | null)  |
   | appointments|       | authority_pages |     | classify        |
   | foi         |       | manual          |     +-----------------+
   | snapshots   |       +--------+--------+
   +------+------+                |
          |              +--------+--------+
          |              | Celery + Redis  |  schemalagd insamling,
          |              | tasks/jobs.py   |  retry, kö
          |              +--------+--------+
     +----+-------------------------+----+
     |  PostgreSQL 17 + pgvector         |
     |  fulltext (svensk konfiguration)  |
     +-----------------------------------+
```

## Dataflödet för ett uppdrag

1. **Insamling.** En adapter i `app/sources/` hämtar från en källa och returnerar
   `RawItem`-objekt. Adaptern avgör inte om något är relevant – den normaliserar bara.
2. **Snapshot.** Rådatan skrivs till `source_snapshots` med sha256. Finns samma sha256
   redan för samma källa och externa id görs inget mer; källan är oförändrad.
3. **Dubblettkontroll.** `core/dedup.py` letar befintlig post på (a) exakt `source` +
   `external_id`, (b) normaliserad titel + organisation + publiceringsdag, (c)
   likhet på normaliserad titel över tröskel. Träff ger en ny `job_ad_versions`-rad
   istället för en ny annons.
4. **Klassificering.** Uppdrag eller fast tjänst? Roll, nivå, område. Regelbaserat
   först, AI bara för det regler inte klarar, och AI-svaret sparas med modellnamn och
   tidpunkt.
5. **Exkluderingsfilter.** `core/exclusion.py` körs alltid, före matchning. Utfall
   PASS, REVIEW_REQUIRED eller EXCLUDED, med citat och regel-id. Filtret skiljer på
   tre saker som är lätta att blanda ihop: ett *uttryckligt* krav på personkontroll
   (exkluderas), ett *villkorat* krav – *"kan komma att genomföras"*, *"i vissa
   fall"* – som blir REVIEW_REQUIRED eftersom det varken är ett krav eller något
   säkert, och *vanliga* säkerhetsord som informationssäkerhet, GDPR och sekretess
   som inte exkluderar något. Villkorsordet räknas bara i samma sats som kravet, och
   ett ovillkorat krav vinner alltid över ett villkorat i samma text.
   `python -m app.cli reassess` kör filtret igen på sparade uppdrag när en regel
   ändrats; varje ombedömning blir en ny rad och ett utfall som en människa satt rörs
   inte.
6. **Matchning.** `core/matching.py` ger 0–100 med delpoäng per kriterium och en
   läsbar förklaring. En EXCLUDED-post matchas inte.
7. **Avisering.** Tröskelstyrd, kö i `notifications`.

## Dataflödet för en tillsättning

Detta är systemets svåraste del, eftersom det ofta inte finns något att hämta.

```
ADVERTISEMENT_FOUND -> APPLICATION_OPEN -> APPLICATION_CLOSED
                                                  |
                                      sök beslut automatiskt
                                                  |
                              +-------------------+-------------------+
                           hittat                              inte hittat
                              |                                     |
                   APPOINTMENT_IDENTIFIED                 APPOINTMENT_NOT_FOUND
                              |                                     |
                     verifieringsnivå 1-3                    REQUEST_READY
                              |                      (utkast, väntar på människa)
                    APPOINTMENT_VERIFIED                            |
                                                      REQUEST_SENT -> RESPONSE_RECEIVED
```

En nedtagen annons betyder ingenting. Tjänsten kan ha dragits tillbaka, förlängts
eller tillsatts internt. Därför finns `POSITION_CANCELLED` och `CLOSED_UNRESOLVED` som
giltiga slutstationer, och `core/appointments.py` vägrar gå till
`APPOINTMENT_IDENTIFIED` utan ett dokument i `public_documents`.

Vissa myndigheter anslår anställningsbeslut på en fysisk anslagstavla. IVO gör det, på
Torsplan i Stockholm. Då finns ingenting att läsa digitalt, och
`authorities.appointment_publication_mode = 'PHYSICAL_NOTICE_BOARD'` gör att ärendet
går direkt till `REQUEST_READY` istället för att nöta på en webbplats som aldrig
kommer att innehålla svaret.

## Varför en adapter per källa

Källorna liknar inte varandra. JobTech är ett öppet REST-API med stabilt schema. TED
har en egen expert-query-syntax och flerspråkiga fält. En myndighets karriärsida kan
vara en Varbi-instans, en sitemap, ett RSS-flöde eller handskriven HTML som ändras
utan förvarning. Flera konsultmäklare ligger bakom inloggning eller har
användarvillkor som förbjuder automatisk hämtning.

Varje adapter deklarerar därför själv hur den får läsas:

```python
class SourceAdapter:
    key: str                  # 'jobtech_live'
    access: AccessMode        # OPEN_API | PUBLIC_HTML | MANUAL_ONLY | BLOCKED
    legal_note: str           # varför den får läsas, eller varför inte
    def fetch(self, cfg) -> SourceRunResult: ...
```

`MANUAL_ONLY` och `BLOCKED` är förstklassiga tillstånd. En källa som kräver inloggning
blir en manuell importrutin i gränssnittet, inte en skrapa som bryter mot villkoren.
DATA_SOURCES.md listar varje källa med verifierat läge och datum för kontrollen.

## AI-användning

AI är en modul, inte en förutsättning. `ai/provider.py` har tre implementationer:
Anthropic API, lokal OpenAI-kompatibel endpoint, och `NullProvider` som svarar att
ingen modell finns. `NullProvider` är standard (`AI_PROVIDER=none`), och det är ett
fullgott läge: exkluderingsfiltret och poängsättningen är deterministiska och behöver
ingen modell.

AI har två jobb i dag: läsa ut vad en annons kräver (`extract_requirements`) och ge en
andra bedömning av annonser där regelmotorn själv satt `needs_ai`
(`assess_exclusion`). Att läsa uppgifter ur ett beslutsdokument är inte byggt.

Kontraktet ligger efter modellen, inte i prompten. En prompt är en önskan; det här är
spärrar:

1. Varje påstående måste ha ett ordagrant citat ur annonsen.
2. Citatet verifieras mot källtexten, normaliserat på blanksteg och skiftläge. Hittas
   det inte förkastas påståendet och hamnar i `dropped`, så att det går att se vad
   modellen försökte påstå.
3. Ett citat kortare än 16 tecken räknas inte. Utan den gränsen kan en modell
   "citera" ordet *chef* och ha rätt varje gång.
4. En AI-bedömning kan bara skärpa regelmotorns utfall. `PASS` → `REVIEW_REQUIRED`
   går; `REVIEW_REQUIRED` → `PASS` går inte. Ett förslag om `EXCLUDED` utan belagt
   citat blir `REVIEW_REQUIRED`, inte exkludering.
5. Regelmotorns bedömningsrad skrivs aldrig över. En skärpning blir en andra rad i
   `exclusion_records` med `assessor = 'AI'` och modellnamnet.

Resultatet är att en hallucination blir synlig i stället för trovärdig. 20 tester i
`tests/test_ai.py` provar just de fallen: hallucinerade citat, omskrivna citat, okända
fält, trasigt JSON och ett utfall som vill mildra en flagga.

## Drift

`docker-compose.yml` med sex tjänster: `db` (`pgvector/pgvector:pg17`), `redis`,
`api`, `worker`, `beat`, `web`. Tänkt för en svensk VPS bakom Caddy eller nginx med
TLS.

`db` och `redis` ligger på ett internt nätverk utan portar ut. `worker` ligger på både
det interna och det publika, eftersom insamlingen går därifrån – `beat` schemalägger
bara och behöver inget nät. Portarna binds till `127.0.0.1` så att bara en omvänd
proxy på samma maskin kommer åt dem; `api`-porten finns med för felsökning och ska
kommenteras bort i drift, eftersom Next skickar vidare `/api/*` till `api` internt.
Det är den vidarebefordran som gör inloggningscookien till en förstahandscookie och
låter CSRF-kontrollen se ett riktigt `Origin`-huvud.

Migreringarna körs av `api` vid uppstart (`alembic upgrade head && uvicorn ...`).
Med en enda api-instans är det entydigt när de kör; skalar man till flera ska
kommandot flyttas till ett eget steg i utrullningen.

Backup via `pg_dump` (`scripts/backup.sh`) och ett återställningsprov som faktiskt
återställer (`scripts/restore_test.sh`), se SECURITY.md.
