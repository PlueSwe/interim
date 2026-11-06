# Interim Radar

Privat bevakningsplattform för svenska chefsrekryteringar, interimuppdrag och
offentliga upphandlingar inom IT och digitalisering.

Fyra områden:

1. **Opportunities** – interimuppdrag, konsultuppdrag, avrop och direktupphandlingar.
2. **Government Careers** – fasta och tidsbegränsade chefsrekryteringar hos
   myndigheter, regioner, kommuner och lärosäten.
3. **Executive Appointments** – vem fick egentligen tjänsten. Följer en rekrytering
   efter att annonsen tagits ner, och genererar en begäran om allmän handling när
   svaret inte går att hitta.
4. **Market Intelligence** – ramavtal, leverantörer, förmedlare och chefsbyten.

## Snabbstart

Kräver Docker och Docker Compose.

```bash
cp .env.example .env
# sätt SECRET_KEY och FIELD_ENCRYPTION_KEY, se nedan
docker compose up -d db redis
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.cli seed
docker compose run --rm api python -m app.cli create-user --email du@exempel.se --role ADMIN
docker compose up -d
```

Dashboard på http://localhost:3000, API-dokumentation på http://localhost:8000/docs.

Nycklar:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"            # SECRET_KEY
python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # FIELD_ENCRYPTION_KEY
```

`ANTHROPIC_API_KEY` är frivillig och `AI_PROVIDER=none` är standard.
Exkluderingsfiltret och poängsättningen är regelstyrda och behöver ingen modell.
AI:n ger en andra bedömning av annonser som regelmotorn själv flaggat som
tvetydiga, och den kan bara skärpa utfallet: ett förslag om exkludering utan
ordagrant citat ur annonsen förkastas, och ett `PASS` från modellen kan aldrig
slå ut en flagga som en regel satt. Se `backend/app/ai/classify.py`.

## Utan Docker

```bash
cd backend
python -m venv .venv && . .venv/Scripts/activate      # Windows
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://...          # eller sqlite för test
alembic upgrade head
python -m app.cli seed
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

## Köra insamling

```bash
# en källa, en gång
docker compose run --rm api python -m app.cli collect jobtech_live

# alla källor som har läge OPEN_API eller PUBLIC_HTML
docker compose run --rm api python -m app.cli collect --all

# visa vilka källor som fungerar
docker compose run --rm api python -m app.cli sources

# kontrollera källor mot robots.txt på nytt
docker compose run --rm api python -m scripts.probe_sources
```

Schemalagd insamling sköts av `worker` och `beat`. Scheman i
`backend/app/tasks/celery_app.py`.

## Tester

```bash
cd backend
pytest -q                 # 138 tester mot SQLite, kräver ingen databas
pytest -q -m integration  # 6 tester mot verkliga API:er, kräver nätverk
```

Integrationstesterna hämtar från JobTech och TED. De är avmarkerade som standard
(`addopts = ["-m", "not integration"]` i `pyproject.toml`) så att en röd svit
alltid betyder ett fel i koden och inte en driftstörning hos någon annan. Senast
körda 2026-11-06: 6 gröna på 188 sekunder.

## Skript

| Skript | Vad det gör |
|---|---|
| `backend/scripts/probe_sources.py` | Provar varje källa på riktigt och skriver ut vad den svarade. Kontaktar inte källor som står som `MANUAL_ONLY` eller `BLOCKED`. |
| `backend/scripts/gen_enums.py` | Genererar `frontend/lib/enums.ts` ur `app/models/enums.py`. |
| `backend/scripts/gen_migration.py` | Genererar `alembic/versions/0001_initial.py` ur modellerna. |
| `backend/scripts/harvest_authorities.py` | Bygger myndighetsregistret ur verkliga JobTech-annonser. |
| `scripts/backup.sh` | `pg_dump` till `backups/`, med gallring. |
| `scripts/restore_test.sh` | Återställer senaste dumpen i en tillfällig databas och räknar rader. En säkerhetskopia ingen har återställt är inte en säkerhetskopia. |

### Kodgenerering

Två filer är genererade och ska inte ändras för hand:

```bash
cd backend
python -m scripts.gen_enums      # frontend/lib/enums.ts
python -m scripts.gen_migration  # alembic/versions/0001_initial.py
```

`enums.ts` genereras därför att handskrivna TypeScript-unioner glider från
Python-enumarna utan att något går sönder: fem av dem hade fel värden, och
`tsc` kunde inte se det. När unionerna är genererade blir en felstavad etikett
ett kompileringsfel i stället för en tom ruta i gränssnittet.

`0001_initial.py` genereras därför att `alembic revision --autogenerate` kräver
en databas att jämföra mot, och den första revisionen har ingen. Alternativet –
en migrering som anropar `create_all()` – lämnar ingen DDL att läsa i
granskningen. `gen_migration.py` vägrar köra utan `pgvector` installerat,
eftersom modellerna annars faller tillbaka på `JSON` och migreringen skulle
skapa `embedding JSON` i stället för `embedding VECTOR(1024)`.

## Kända begränsningar i utvecklingsmiljön

Inget av det här påverkar driften, men det förklarar vad som är otestat.

- **`cryptography` på Windows ARM64.** Det finns inget färdigt wheel, så
  fältkrypteringen av personuppgifter kunde inte köras under utvecklingen.
  Importen är därför lat (`app/security.py`) och systemet startar utan paketet,
  men krypteringen är otestad. Containern bygger för linux/amd64 där wheelet finns.
- **`npm install` på en Google Drive-sökväg.** Drive-klienten släpper filer mitt
  i installationen och npm faller på `EPERM`, `ENOTEMPTY` eller `EBADF`.
  `node_modules` måste ligga på en lokal disk. Frontend byggdes och verifierades
  därför utanför projektmappen; `package-lock.json` är kopierad in så att
  `npm ci` i Dockerfilen är reproducerbar.
- **Docker-demonen gick inte att starta** på utvecklingsmaskinen, så
  containerbilderna är aldrig byggda och migreringen är aldrig körd mot en
  riktig PostgreSQL. `docker compose config` går igenom utan fel.

## Kontinuerlig integration

Tre arbetsflöden i `.github/workflows/`. De finns för att täcka precis det som
inte går att prova på en Windows-maskin utan Docker.

| Flöde | När | Vad det provar |
|---|---|---|
| `ci.yml` | varje push och PR | ruff, 138 tester mot SQLite, att de genererade filerna är i fas med modellerna, och `alembic upgrade head` mot **PostgreSQL 17 med pgvector** – inklusive att `opportunities.embedding` blir `vector` och inte `json`, att check-villkoren vägrar ett `EXCLUDED` utan citat, och att `alembic downgrade base` lämnar schemat tomt |
| `stack.yml` | push som rör koden, samt söndagar | bygger båda containerbilderna, startar alla sex tjänsterna, kör migreringen i containern, seedar, loggar in genom `web → api`, kontrollerar att IVO-ärendet står kvar som obesvarat och att en begäran inte kan markeras som skickad utan godkännande, och kör **säkerhetskopia plus återställningsprov** på riktigt |
| `kallor.yml` | måndagar | `probe_sources.py` och de 6 integrationstesterna mot JobTech och TED. Öppnar ett ärende när en källa som står som `ACTIVE` slutat svara |

Uppdelningen är avsiktlig. `kallor.yml` får gå rött utan att blockera något –
ett rött bygge där betyder "någon annans server har ändrat sig", inte att koden
är trasig. Det är den signal man vill ha, och den syns inte i en testsvit som
kör mot inspelade svar.

Alla tre går att starta för hand under fliken Actions, eller med
`gh workflow run ci.yml`.

## Vad systemet inte gör

Det hittar inte på uppgifter. Varje annons, varje tillsättning och varje
exkluderingsbeslut pekar på rådata i `source_snapshots` med sha256 och
hämtningstidpunkt. Går en uppgift inte att spåra till en källa finns den inte i
databasen.

Det skickar inga mejl själv. En begäran om allmän handling blir ett utkast. Att gå
till `SENT` kräver en inloggad administratörs godkännande, och det är ett
check-villkor i databasen, inte bara en kontroll i koden.

Det antar inte att en tjänst är tillsatt för att annonsen försvunnit. En nedtagen
annons kan betyda att tjänsten drogs tillbaka, förlängdes eller tillsattes internt.
Därför finns statusarna `POSITION_CANCELLED` och `CLOSED_UNRESOLVED`.

Det skrapar inte Mercell, TendSign, Kommers Annons eller Opic. Deras användarvillkor
förbjuder det, och samma data finns att få lagligt via TED och myndigheternas egna
sidor. Se DATA_SOURCES.md.

## IVO-testärendet

Systemet seedar ett verkligt rekryteringsärende: IVO:s **verksamhetsområdeschef
Digitalisering och IT**, publicerad 2026-08-20, sista ansökningsdag 2026-09-20,
hanterad med hjälp av Poolia.

Annonsen är hämtad från JobTechs historiska API (`a39c3a5d587a793cd6fbbef95cdf635a8bd83268`)
och ligger som snapshot i `backend/data/snapshots/` med sha256. IVO anslår
anställningsbeslut på sin fysiska anslagstavla vid Torsplan i Stockholm, så ärendet
går till `REQUEST_READY` med ett färdigt utkast till registrator.

Vem som fick tjänsten står inte i systemet, eftersom det inte går att ta reda på
digitalt. Det är hela poängen med testärendet.

```bash
docker compose run --rm api python -m app.cli ivo-case --show
```

## Dokumentation

| Fil | Innehåll |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Komponenter, dataflöden, designval |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | Alla tabeller, index, check-villkor |
| [DATA_SOURCES.md](DATA_SOURCES.md) | Varje källa med verifierat läge och datum |
| [SECURITY.md](SECURITY.md) | Autentisering, GDPR, insamlingsetik, backup |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Status per fas och vad som återstår |
