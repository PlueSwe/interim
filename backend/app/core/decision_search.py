"""Sokning efter anstallningsbeslut och pressmeddelanden.

Bestallningen vill att systemet soker pa myndighetens webbplats, efter
pressmeddelanden och efter offentliga beslutshandlingar. Det gor den har
modulen -- men den avgor aldrig sjalv att en tjanst ar tillsatt.

Vad den returnerar ar kandidater: sidor som namner befattningen och ser ut att
handla om en tillsattning, med en foreslagen verifieringsniva och ett skal.
Beslutet att koppla en person till en tjanst fattas i core/appointments.py, med
ett dokument som krav, och niva 4-5 racker aldrig.

Varfor sa forsiktigt: en myndighetssida som namner "ny chef for digitalisering"
kan vara ett pressmeddelande om en tillsattning, en nyhet om en organisations-
forandring, eller en gammal sida som rakar ligga kvar. Skillnaden gar inte att
se av en regex, och att gissa fel namnger fel person i en offentlig roll.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from ..models.enums import DocumentType
from ..sources.base import SourceAdapter, SourceBlockedError, robots_allows
from .text import excerpt, normalise_title

# Formuleringar som tyder pa en tillsattning. Sorterade efter hur starkt de
# pekar pa ett faktiskt anstallningsbeslut.
DECISION_PHRASES: tuple[tuple[str, int, str], ...] = (
    (r"anst[äa]llningsbeslut", 1, "sidan nämner anställningsbeslut"),
    (r"beslut om anst[äa]llning", 1, "sidan nämner beslut om anställning"),
    (
        r"har (utsetts|anst[äa]llts|f[öo]rordnats) (till|som)",
        2,
        "myndigheten anger att någon utsetts",
    ),
    (r"(utses|anst[äa]ller|v[äa]ljer) (till|som)? ?ny", 2, "myndigheten anger en ny chef"),
    (r"blir ny", 2, "myndigheten anger en ny chef"),
    (r"tilltr[äa]der (tj[äa]nsten|sin|som)", 2, "sidan anger ett tillträde"),
    (r"ny chef (f[öo]r|p[åa])", 3, "sidan nämner en ny chef"),
    (r"v[äa]lkomnar", 4, "sidan välkomnar någon, oklart om det gäller tjänsten"),
)

# Sidtyper vi letar pa. Myndigheter lagger pressmeddelanden pa olika stallen.
PRESS_PATH_PATTERNS = (
    r"/aktuellt/",
    r"/nyhet",
    r"/press",
    r"/om-oss/",
    r"/om-[a-z]+/organisation",
    r"/pressmeddelande",
    r"/sa-styrs",
)

DIARY_NUMBER = re.compile(
    r"\b(?:dnr|diarienummer|diarienr)[\s.:]*([0-9]{1,6}[-/][0-9]{2,6}(?:[-/][0-9]{1,6})?)",
    re.IGNORECASE,
)


@dataclass
class DecisionCandidate:
    url: str
    title: str
    document_type: DocumentType
    suggested_verification_level: int
    reason: str
    quote: str | None = None
    diary_number: str | None = None

    @property
    def can_verify(self) -> bool:
        """Racker kandidaten for en verifierad tillsattning?

        Bara niva 1-3. En niva 4-traff far synas i granskningsvyn men inte bli
        ett pastaende.
        """
        return self.suggested_verification_level <= 3


@dataclass
class SearchOutcome:
    searched_at: dt.datetime
    pages_checked: int
    candidates: list[DecisionCandidate]
    skipped_reason: str | None = None

    @property
    def found_anything(self) -> bool:
        return bool(self.candidates)


class _Fetcher(SourceAdapter):
    """Minimal adapter sa att sokningen far takthallning och robots-spärr."""

    key = "decision_search"
    name = "Sökning efter anställningsbeslut"
    from ..models.enums import AccessMode as _AM

    access = _AM.PUBLIC_HTML
    legal_note = "Offentliga myndighetssidor. robots.txt kontrolleras per URL."

    def fetch(self, **kwargs):  # pragma: no cover - anvands inte
        return []


def _role_terms(title: str) -> list[str]:
    """Ord ur befattningen som ar varda att soka pa.

    Tar bort ortsnamn och fyllord via normalise_title, och behaller ord som ar
    langre an fyra tecken. "chef" ensamt ger for mycket brus.
    """
    ord_lista = normalise_title(title).split()
    return [o for o in ord_lista if len(o) > 4][:4]


def search_for_decision(
    *,
    authority_website: str | None,
    position_title: str,
    published_at: dt.datetime | None = None,
    max_pages: int = 25,
) -> SearchOutcome:
    """Leta efter ett tillsattningsbeslut pa myndighetens webbplats.

    Gar via sitemap i forsta hand, eftersom den ger en lista utan att behova
    gissa URL:er. Returnerar alltid ett resultat, aven nar inget hittades --
    "inget hittat" ar ett svar systemet behover kunna lagra.
    """
    nu = dt.datetime.now(dt.UTC)
    if not authority_website:
        return SearchOutcome(nu, 0, [], "Myndighetens webbplats saknas i registret.")

    tillatet = robots_allows(authority_website)
    if tillatet is False:
        return SearchOutcome(nu, 0, [], f"robots.txt förbjuder {authority_website}")

    hamtare = _Fetcher()
    delar = urlsplit(authority_website)
    bas = f"{delar.scheme}://{delar.netloc}"
    termer = _role_terms(position_title)
    if not termer:
        return SearchOutcome(nu, 0, [], f"Inga sökbara ord i befattningen {position_title!r}.")

    # Kandidatsidor ur sitemap.
    sidor: list[str] = []
    try:
        xml = hamtare.get_text(f"{bas}/sitemap.xml")
        alla = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        sidor = [
            u
            for u in alla
            if any(re.search(p, u, re.IGNORECASE) for p in PRESS_PATH_PATTERNS)
            and any(t in u.lower() for t in termer)
        ]
        if not sidor:
            # Inga URL:er namner befattningen. Ta pressidorna anda, men fa.
            sidor = [
                u for u in alla if any(re.search(p, u, re.IGNORECASE) for p in PRESS_PATH_PATTERNS)
            ][:max_pages]
    except SourceBlockedError as e:
        return SearchOutcome(nu, 0, [], str(e))
    except Exception:
        sidor = []

    # Myndighetens egen sokfunktion som komplement.
    if len(sidor) < 5:
        for term in termer[:2]:
            sidor.append(f"{bas}/sok/?q={quote(term)}")

    kandidater: list[DecisionCandidate] = []
    lasta = 0
    for url in sidor[:max_pages]:
        try:
            html = hamtare.get_text(url)
        except Exception:
            continue
        lasta += 1
        text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        lag = text.lower()

        # Sidan maste namna befattningen, annars handlar den om nagot annat.
        if not any(t in lag for t in termer):
            continue

        for monster, niva, skal in DECISION_PHRASES:
            m = re.search(monster, text, re.IGNORECASE)
            if not m:
                continue
            dnr = DIARY_NUMBER.search(text)
            kandidater.append(
                DecisionCandidate(
                    url=url,
                    title=_page_title(html) or url,
                    document_type=(
                        DocumentType.EMPLOYMENT_DECISION
                        if niva == 1
                        else DocumentType.PRESS_RELEASE
                        if niva == 2
                        else DocumentType.WEB_PAGE
                    ),
                    suggested_verification_level=niva,
                    reason=skal,
                    quote=excerpt(text, m.start()),
                    diary_number=dnr.group(1) if dnr else None,
                )
            )
            break

    kandidater.sort(key=lambda k: k.suggested_verification_level)
    return SearchOutcome(nu, lasta, kandidater)


def _page_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    if not m:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()[:200]
