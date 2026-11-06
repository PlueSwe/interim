"""Kallregistret.

En kalla finns i systemet aven nar den inte far hamtas. Det ar hela poangen:
BLOCKED och MANUAL_ONLY ar forstklassiga lagen, inte luckor. En kalla som inte
ar med alls blir en kalla ingen minns att den saknas.

DECLARED_SOURCES ar den sanning som seedas till source_registry. Lagena ar
kontrollerade 2026-11-06 med scripts/probe_sources.py; se DATA_SOURCES.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models.enums import AccessMode, SourceStatus
from .authority_pages import AuthorityPagesAdapter, detect_platform, verify_authority
from .base import (
    RawItem,
    SourceAdapter,
    SourceBlockedError,
    SourceRunResult,
    robots_allows,
)
from .jobtech import JobTechHistoricalAdapter, JobTechLiveAdapter
from .manual import ManualImportAdapter
from .ted import TedAdapter

ADAPTERS: dict[str, type[SourceAdapter]] = {
    JobTechLiveAdapter.key: JobTechLiveAdapter,
    JobTechHistoricalAdapter.key: JobTechHistoricalAdapter,
    TedAdapter.key: TedAdapter,
    AuthorityPagesAdapter.key: AuthorityPagesAdapter,
    ManualImportAdapter.key: ManualImportAdapter,
}


def get_adapter(key: str) -> SourceAdapter:
    if key not in ADAPTERS:
        raise KeyError(f"okand kalla {key!r}. Kanda: {', '.join(sorted(ADAPTERS))}")
    return ADAPTERS[key]()


def automatic_keys() -> list[str]:
    """Kallor som far hamtas automatiskt."""
    return [
        key
        for key, klass in ADAPTERS.items()
        if klass.access in (AccessMode.OPEN_API, AccessMode.PUBLIC_HTML)
    ]


@dataclass(frozen=True)
class DeclaredSource:
    """En kalla i registret, med eller utan adapter.

    Kallor utan adapter finns med for att dokumentera varfor de inte hamtas.
    Utan dem ser registret ut som att ingen har tankt pa Mercell.
    """

    key: str
    name: str
    access: AccessMode
    status: SourceStatus
    base_url: str | None
    legal_note: str
    schedule_cron: str | None = None


DECLARED_SOURCES: tuple[DeclaredSource, ...] = (
    # --- Verifierat fungerande ---
    DeclaredSource(
        "jobtech_live",
        "Arbetsförmedlingen Platsbanken (öppna data)",
        AccessMode.OPEN_API,
        SourceStatus.ACTIVE,
        "https://jobsearch.api.jobtechdev.se",
        "Öppna data, ingen nyckel, ingen robots.txt. Svarade 200 vid kontroll 2026-11-06.",
        "0 */2 * * *",
    ),
    DeclaredSource(
        "jobtech_hist",
        "Arbetsförmedlingen historiska annonser (öppna data)",
        AccessMode.OPEN_API,
        SourceStatus.ACTIVE,
        "https://historical.api.jobtechdev.se",
        "Öppna data. Avpublicerade annonser sedan 2016 – enda källan där en annons finns "
        "kvar efter att den tagits ner. Svarade 200 vid kontroll 2026-11-06.",
        "0 3 * * *",
    ),
    DeclaredSource(
        "ted",
        "TED - Tenders Electronic Daily",
        AccessMode.OPEN_API,
        SourceStatus.ACTIVE,
        "https://api.ted.europa.eu/v3",
        "EU:s officiella upphandlingsdatabas, öppet API. Ursprunglig publicering över "
        "tröskelvärdena. 711 svenska träffar på 90 dagar vid kontroll 2026-11-06.",
        "0 */6 * * *",
    ),
    DeclaredSource(
        "authority_pages",
        "Myndigheternas egna karriärsidor",
        AccessMode.PUBLIC_HTML,
        SourceStatus.ACTIVE,
        None,
        "Offentliga sidor, robots.txt kontrolleras per URL. Varje myndighet måste "
        "verifieras med app.cli verify-authority innan den sätts till ACTIVE.",
        "0 4 * * *",
    ),
    DeclaredSource(
        "manual",
        "Manuell import (CSV eller JSON)",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        None,
        "Export från eget abonnemang eller uppgifter från källor som inte får hämtas.",
    ),
    # --- Spärrade av robots.txt, kontrollerat 2026-11-06 ---
    DeclaredSource(
        "e_avrop",
        "e-Avrop",
        AccessMode.BLOCKED,
        SourceStatus.BLOCKED,
        "https://www.e-avrop.com",
        "robots.txt ger Disallow för vår User-Agent (kontrollerat 2026-11-06). "
        "Hämtas inte. Manuell import om uppdrag därifrån ska in.",
    ),
    DeclaredSource(
        "a_society",
        "A Society",
        AccessMode.BLOCKED,
        SourceStatus.BLOCKED,
        "https://www.asociety.se",
        "robots.txt ger Disallow (kontrollerat 2026-11-06). Hämtas inte.",
    ),
    # --- Kommersiella annonsdatabaser: medvetet inte skrapade ---
    DeclaredSource(
        "mercell",
        "Mercell",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.mercell.com",
        "robots.txt tillåter startsidan, men användarvillkoren förbjuder systematisk "
        "maskinell insamling av annonsdatabasen – det är produkten de säljer. Samma "
        "annonser finns i TED och på myndigheternas egna sidor. Har man eget "
        "abonnemang är rätt väg deras API mot egen nyckel, inte skrapning.",
    ),
    DeclaredSource(
        "tendsign",
        "TendSign (Visma Commerce)",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://tendsign.com",
        "Samma skäl som Mercell. Användarvillkoren, inte robots.txt, är det som gäller.",
    ),
    DeclaredSource(
        "kommers",
        "Kommers Annons",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.kommersannons.se",
        "Samma skäl som Mercell.",
    ),
    DeclaredSource(
        "opic",
        "Opic",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.opic.com",
        "Samma skäl som Mercell.",
    ),
    # --- Konsultmaklare ---
    DeclaredSource(
        "brainville",
        "Brainville",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.brainville.com",
        "robots.txt tillåter och sajten svarade 200 vid kontroll 2026-11-06, men ingen "
        "listningssida är verifierad än. Sätts till ACTIVE först när parsningen är "
        "testad mot verklig HTML.",
    ),
    DeclaredSource(
        "ework",
        "Ework Group",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.eworkgroup.com",
        "Som Brainville: tillåten men inte verifierad.",
    ),
    DeclaredSource(
        "poolia",
        "Poolia",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.poolia.se",
        "Som Brainville. Relevant för IVO-ärendet: Poolia hanterade den rekryteringen.",
    ),
    DeclaredSource(
        "bemannia",
        "Bemannia",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.bemannia.se",
        "Som Brainville: tillåten men inte verifierad.",
    ),
    DeclaredSource(
        "cinode_market",
        "Cinode Market",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://market.cinode.com",
        "Kräver konto för att visa uppdrag. Systemet loggar inte in å någons vägnar.",
    ),
    DeclaredSource(
        "keyman",
        "KeyMan",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://www.keyman.se",
        "Kräver konto.",
    ),
    DeclaredSource(
        "verama",
        "Verama",
        AccessMode.MANUAL_ONLY,
        SourceStatus.MANUAL_ONLY,
        "https://app.verama.com",
        "Kräver konto.",
    ),
    # --- Ramavtal ---
    DeclaredSource(
        "avropa",
        "Avropa.se (Statens inköpscentral)",
        AccessMode.PUBLIC_HTML,
        SourceStatus.MANUAL_ONLY,
        "https://www.avropa.se",
        "Statliga ramavtal med giltighetstider och leverantörer. robots.txt tillåter "
        "(kontrollerat 2026-11-06). Adapter inte byggd än; modellen finns.",
    ),
)

__all__ = [
    "ADAPTERS",
    "DECLARED_SOURCES",
    "AuthorityPagesAdapter",
    "DeclaredSource",
    "JobTechHistoricalAdapter",
    "JobTechLiveAdapter",
    "ManualImportAdapter",
    "RawItem",
    "SourceAdapter",
    "SourceBlockedError",
    "SourceRunResult",
    "TedAdapter",
    "automatic_keys",
    "detect_platform",
    "get_adapter",
    "robots_allows",
    "verify_authority",
]
