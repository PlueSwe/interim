# Datakällor – Interim Radar

Kontrollerad **2026-11-06** med `backend/scripts/probe_sources.py`. Kolumnen *Läge* är
inte en ambition utan vad kontrollen visade. Kör skriptet igen för att uppdatera
tabellen; det skriver `backend/data/source_probe.json`.

Fyra lägen:

- **OPEN_API** – dokumenterat öppet API, maskinläsbart, får hämtas automatiskt.
- **PUBLIC_HTML** – öppen webbsida som robots.txt tillåter. Hämtas med låg takt och
  tydlig User-Agent.
- **MANUAL_ONLY** – nåbar för en människa men inte lagligt eller tekniskt lämplig att
  hämta automatiskt. Importeras via gränssnittet.
- **BLOCKED** – robots.txt eller användarvillkor säger nej. Systemet rör den inte.

## Verifierat fungerande

| Källa | Läge | Resultat 2026-11-06 | Not |
|---|---|---|---|
| JobTech Platsbanken (`jobsearch.api.jobtechdev.se`) | OPEN_API | 200, JSON | Arbetsförmedlingens öppna data. Ingen robots.txt, ingen nyckel. Alla annonser som är publicerade just nu. |
| JobTech historiska annonser (`historical.api.jobtechdev.se`) | OPEN_API | 200, JSON | Avpublicerade annonser sedan 2016. **Systemets viktigaste källa för tillsättningsspårning**: här finns annonsen kvar efter att den tagits ner, med avpubliceringsdatum. |
| JobTech taxonomi (`taxonomy.api.jobtechdev.se`) | OPEN_API | 200, JSON | Yrkesbegrepp. Används för att slå `Chief Digital Officer/CDO` och `Avdelningschef, statlig` istället för att gissa på fritext. |
| TED (`api.ted.europa.eu/v3`) | OPEN_API | 200, JSON | EU-upphandling över tröskelvärdena. Kräver expert-query-syntax, se nedan. 16 843 svenska CPV-72-annonser vid kontrollen. |

### TED: frågesyntaxen

TED v3 tar inte fritext med `AND`/`OR` som första försöket antar. Giltig fråga:

```
place-of-performance IN (SWE) AND classification-cpv IN (72000000)
```

Fel syntax ger `QUERY_SYNTAX_ERROR` med kolumnposition, vilket adaptern loggar rakt
ut istället för att svälja felet.

## Öppna sidor, hämtas med låg takt

| Källa | Läge | Resultat | Not |
|---|---|---|---|
| Upphandlingsmyndigheten | PUBLIC_HTML | 200, robots tillåter | Ramavtalsinformation och vägledningar, inte annonser. |
| Avropa.se (Kammarkollegiet) | PUBLIC_HTML | 200, robots tillåter | Statliga ramavtal, giltighetstider, leverantörer. Källa för ramavtalsbevakningen. |
| Kammarkollegiet | PUBLIC_HTML | 200, robots tillåter | |
| Brainville | PUBLIC_HTML | 200, robots tillåter | Konsultuppdrag. Robots tillåter startsidan; uppdragslistan läses med 1 anrop/5 s. |
| Ework Group | PUBLIC_HTML | 200, robots tillåter | |
| Poolia | PUBLIC_HTML | 200, robots tillåter | Relevant för IVO-ärendet: Poolia hanterade den rekryteringen. |
| Bemannia | PUBLIC_HTML | 200, robots tillåter | |
| Myndigheternas egna karriärsidor | PUBLIC_HTML | per myndighet | Se `authorities.collection_method`. |

Att en startsida ger 200 och robots.txt tillåter betyder **inte** att det finns ett
maskinläsbart gränssnitt. För varje källa i den här gruppen krävs att en
listningssida identifieras och att parsningen testas mot verklig HTML innan adaptern
sätts till `ACTIVE`. Tills det är gjort står källan som `MANUAL_ONLY` i
`source_registry`, oavsett vad den här tabellen säger om robots.

## Spärrade av robots.txt

| Källa | Läge | Resultat | Not |
|---|---|---|---|
| e-Avrop | BLOCKED | robots.txt: `Disallow` för vår User-Agent | Får inte hämtas automatiskt. Manuell import. |
| A Society | BLOCKED | robots.txt: `Disallow` | Manuell import. |

Dessa två står som `BLOCKED` i `source_registry` och adaptern vägrar köra. Vill man
ändå ha in deras uppdrag finns manuell import i gränssnittet.

## Kommersiella plattformar: medvetet inte skrapade

Mercell, TendSign, Kommers Annons och Opic svarade alla 200 med robots.txt som
tillåter startsidan. De hämtas ändå **inte** automatiskt, och det är ett val, inte en
lucka:

Deras värde ligger i den aggregerade annonsdatabasen. Den är produkten de säljer, och
användarvillkoren för samtliga förbjuder systematisk maskinell insamling även där
robots.txt är tillåtande. robots.txt är inte ett avtal; användarvillkoren är det.

Samma data finns dessutom i stor utsträckning att få lagligt på annat håll:

- Över tröskelvärdena: **TED**, som är den ursprungliga publiceringen.
- Under tröskelvärdena: **myndighetens egen webbplats**, där annonsen också måste
  publiceras.
- Avrop och förnyad konkurrensutsättning: syns ofta inte alls i annonsdatabaserna,
  utan bara hos den upphandlande myndigheten eller i ramavtalets egen portal.

Det tredje fallet är hela poängen. Avropen är där interimuppdragen faktiskt ligger,
och de syns sämst hos aggregatorerna. Att bygga på TED plus myndigheternas egna sidor
ger därför inte bara en lagligare lösning utan i den här nischen en mer komplett.

Har man ett eget abonnemang hos Mercell eller TendSign är rätt väg deras API mot egen
nyckel, inte skrapning. `sources/manual.py` tar emot CSV- och JSON-export från ett
sådant abonnemang.

## Källor bakom inloggning

Cinode Market, Keyman, Verama och Talmix svarade utan publik robots.txt och kräver
konto för att visa uppdrag. De är `MANUAL_ONLY`. Ett konto som användaren själv har
får användas av användaren; systemet loggar inte in å någons vägnar.

## Myndighetsregistret

| Källa | Resultat | Not |
|---|---|---|
| SCB Myndighetsregistret (`myndighetsregistret.scb.se`) | **SSL: CERTIFICATE_VERIFY_FAILED** | Certifikatkedjan gick inte att verifiera vid kontrollen. Registret hämtas därför inte automatiskt. |
| Statskontorets förvaltningsstatistik | 404 på den djuplänk som provades | Sidstrukturen har ändrats. Länken behöver letas upp på nytt. |

Konsekvens: myndighetsregistret är **inte** hämtat ur något myndighetsregister. Det
är byggt underifrån, ur verklig annonsdata, av
`backend/scripts/harvest_authorities.py`: arbetsgivare ur JobTech-annonser, filtrerade
på Skatteverkets nummerserier för offentliga organisationer (2021, 2120, 2321).
Resultatet ligger i `backend/app/seed/authorities_data.json` med `harvested_at`,
`verification_source` och `verified_at` per rad.

**384 rader** (kontrollerat 2026-11-06): 124 statliga myndigheter, 31 lärosäten,
20 regioner, 209 kommuner. Inget organisationsnummer är gissat – varje nummer kommer
ur en annons som finns som snapshot.

Vad registret *inte* har, och det är den största luckan i hela systemet:

| Fält | Täckning | Konsekvens |
|---|---|---|
| `registrar_email` | 1 av 384 (IVO) | En begäran om allmän handling kan inte godkännas utan mottagare, så tillsättningsspårningen stannar vid utkast för alla utom IVO. |
| `careers_url` | 1 av 384 | Ingen karriärsidesbevakning är igång. |
| `vacancies_url` | 0 av 384 | – |
| `recruitment_platform` | 10 igenkända på URL-mönster (9 Varbi, 1 bara Platsbanken), 374 `UNKNOWN` | Parsningsstrategin kan inte väljas automatiskt. |

Allt det här syns i `GET /api/v1/authorities/coverage`, och det är meningen. Ett
register där 384 rader står som `MANUAL_ONLY` ska inte se ut som fullständig
bevakning.

### Rättelse 2026-11-06

Seedningen skrev tidigare organisationens startsida in i `careers_url`, vilket gav
225 rader som såg ut att ha en verifierad karriärsida. De hade en startsida.
`https://www.forsvarsmakten.se/` är inte en karriärsida, och ett fält som heter
`careers_url` är ett påstående om vad sidan är. Fältet sätts nu bara efter
verifiering med `python -m app.cli verify-authority`; adressen ur annonsen ligger
kvar på `organisations.website`.

### Rättelse 2026-11-06, insamlingsvägen

Insamlingen gick bara via 19 fritextfraser och 2 yrkesbegrepp. Det räcker inte,
och felet är inte att listan är för kort – det är att en sökordslista aldrig kan
bli tillräckligt lång. Statens titlar ser ut så här:

- *Chef till enheten för IT-arkitektur och IT-säkerhet* (Statens fastighetsverk)
- *Verksamhetsområdeschef Digitalisering och IT* (IVO)
- *Chef för enheten för digital infrastruktur*

Den första missades i oktober 2026, trots att `chef IT-arkitektur` finns i listan:
annonsen var avpublicerad, och den historiska källan hade aldrig körts och saknade
tidsfönster. Två vägar in finns nu, och de kompletterar varandra:

| Väg | Vad den hittar | Svaghet |
|---|---|---|
| Sökord och yrkesbegrepp | Annonser från alla arbetsgivare, även privata förmedlare | Beror på att någon gissat rätt titel i förväg |
| Svep per myndighet (`collect --authorities`) | Allt en myndighet annonserat, oavsett titel – klassificeringen avgör sedan | Bara de 384 organisationsnummer som finns i registret |

Svepet frågar `employer=<organisationsnummer>` per myndighet. Numret måste skickas
utan bindestreck: `202100-4474` ger **0 träffar utan felkod**, vilket är värsta
sortens svar – det ser ut som att myndigheten inte annonserar något. Adaptern
normaliserar numret innan den frågar, och sju tester i
`tests/test_sources_jobtech.py` provar vad adaptern faktiskt frågar efter.

Den historiska källan har nu också ett fönster, `HISTORICAL_DAYS = 180`. Utan det
gav `q="IT-chef"` 4 656 träffar sedan 2016, pagineringstaket hämtade 1 000 av dem,
och API:ets ordning avgjorde vilka – inte datumet.

## Rekryteringsplattformar

Varbi, ReachMee, Teamtailor, Visma Recruit och Jobylon är system som myndigheterna
köper, inte källor i sig. Adaptern `sources/authority_pages.py` känner igen dem på
URL-mönster och väljer parsningsstrategi därefter. Den testade ReachMee-URL:en gav
404, vilket är väntat utan en kundspecifik instans.

De flesta myndigheter speglar dessutom sina annonser till Platsbanken, vilket gör
JobTech till den enklaste och mest tillförlitliga vägen in. Karriärsidesbevakning
behövs för de som inte gör det, och för att få kravprofilen i original.

## Vad som inte går att hämta alls

**Anställningsbeslut.** Det finns inget register över svenska myndigheters
anställningsbeslut. De är allmänna handlingar och lämnas ut på begäran, men
publiceras inte systematiskt. Vissa myndigheter anslår dem på en fysisk anslagstavla.

IVO gör det, på Torsplan i Stockholm. För den myndigheten finns därför ingen digital
väg till svaret, och systemet ska inte låtsas om något annat. Det är därför
`information_requests` finns, och därför den vägen kräver en människas godkännande.
