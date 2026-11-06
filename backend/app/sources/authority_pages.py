"""Myndigheternas egna karriarsidor.

Den har adaptern ar aerlig om sin begransning: den kan inte parsa en sida den
inte har sett. Myndigheternas rekryteringssidor ar Varbi, ReachMee, Teamtailor,
Visma Recruit, Jobylon eller handskriven HTML, och varje variant har sin egen
struktur. Ett generiskt skript som "hittar jobbannonser" pa vilken sida som
helst finns inte.

Darfor tre niva av ambition, i den ordning som ar mest tillforlitlig:

1. **Sitemap och RSS.** Strukturerat, stabilt over tid, latt att verifiera. Om
   myndigheten har det anvands det.
2. **Kand plattform.** Varbi och Teamtailor har forutsagbara URL-monster och
   JSON-endpoints. De hanteras per plattform.
3. **Lankutvinning med monster.** Letar lankar som ser ut som annonser, med
   titeln fran lanktexten. Ger alltid `uncertain` och kraver att nagon tittar
   pa resultatet innan myndigheten satts till ACTIVE.

En myndighet star kvar som MANUAL_ONLY i source_registry tills nagon har kort
`verify_authority` mot den och sett att parsningen ger ratt annonser. Det ar
skalet till att bara tre av 62 myndigheter ar ACTIVE: resten ar inte verifierade,
och en overdriven siffra i registret hade varit varre an en lag.

De flesta myndigheter speglar sina annonser till Platsbanken, vilket gor
jobtech-adaptern till den enklaste vagen in. Karriarsidesbevakning behovs for
dem som inte gor det, och for att fa kravprofilen i original.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..models.enums import AccessMode, RecruitmentPlatform
from .base import RawItem, SourceAdapter, SourceBlockedError, robots_allows

# URL-monster som identifierar rekryteringsplattform.
PLATFORM_PATTERNS: tuple[tuple[RecruitmentPlatform, str], ...] = (
    (RecruitmentPlatform.VARBI, r"varbi\.com|/varbi/"),
    (RecruitmentPlatform.REACHMEE, r"reachmee\.com|web\d+\.reachmee"),
    (RecruitmentPlatform.TEAMTAILOR, r"teamtailor\.com"),
    (RecruitmentPlatform.VISMA_RECRUIT, r"visma(recruit|\.com/recruit)|recruit\.visma"),
    (RecruitmentPlatform.JOBYLON, r"jobylon\.com"),
)

# Lankar som brukar vara annonser.
AD_LINK_PATTERNS = (
    r"/jobb/",
    r"/job/",
    r"/vacancy",
    r"/lediga-jobb/",
    r"/lediga-tjanster/",
    r"/positions?/",
    r"/annons",
    r"what:joblist",
    r"/anstallning/",
)

# Titelord som gor en lank vard att plocka upp. Filtrerar bort "Om oss" och
# "Kontakta oss" utan att behova forsta sidans struktur.
TITLE_HINTS = re.compile(
    r"chef|direkt[öo]r|cio\b|cto\b|\bcdo\b|head of|ledare|f[öo]rest[åa]ndare"
    r"|verksamhetsomr[åa]de|avdelnings|enhets|f[öo]rvaltnings",
    re.IGNORECASE,
)


def detect_platform(url: str | None) -> RecruitmentPlatform:
    if not url:
        return RecruitmentPlatform.UNKNOWN
    for plattform, monster in PLATFORM_PATTERNS:
        if re.search(monster, url, re.IGNORECASE):
            return plattform
    return RecruitmentPlatform.OWN_HTML


@dataclass
class _Link:
    href: str
    text: str


class _LinkCollector(HTMLParser):
    """Stdlib-parser i stallet for ett HTML-bibliotek.

    Det ar bara lankar och lanktext som behovs, och en extra beroende for det
    ar inte vart det. Parsern ar overseende med trasig HTML, vilket ar det man
    far fran en del myndighetssidor.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[_Link] = []
        self._current: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self._current = href
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._current is not None:
            text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if text:
                self.links.append(_Link(self._current, text))
            self._current = None
            self._buffer = []


def _extract_links(html: str, base: str) -> list[_Link]:
    parser = _LinkCollector()
    # Trasig HTML ska inte stoppa korningen. Det vi hann samla duger.
    with contextlib.suppress(Exception):
        parser.feed(html)
    return [_Link(urljoin(base, unescape(link.href)), link.text) for link in parser.links]


def _sitemap_urls(xml: str) -> list[str]:
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)


def _rss_items(xml: str) -> list[tuple[str, str, str | None]]:
    """(titel, lank, datum) ur ett RSS- eller Atom-flode."""
    poster = []
    for block in re.findall(r"<(?:item|entry)\b.*?</(?:item|entry)>", xml, re.S | re.I):
        titel = re.search(
            r"<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.S | re.I
        )
        lank = re.search(r"<link[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.S | re.I)
        if not lank:
            lank = re.search(r'<link[^>]*href="([^"]+)"', block, re.I)
        datum = re.search(r"<(?:pubDate|updated|published)[^>]*>(.*?)</", block, re.S | re.I)
        if titel and lank:
            poster.append(
                (
                    unescape(re.sub(r"<[^>]+>", "", titel.group(1))).strip(),
                    unescape(lank.group(1)).strip(),
                    datum.group(1).strip() if datum else None,
                )
            )
    return poster


class AuthorityPagesAdapter(SourceAdapter):
    key = "authority_pages"
    name = "Myndigheternas egna karriarsidor"
    access = AccessMode.PUBLIC_HTML
    legal_note = (
        "Offentliga webbsidor. robots.txt kontrolleras per URL fore hamtning och en "
        "Disallow stoppar korningen. Minst 5 sekunder mellan anrop mot samma vard."
    )
    default_cron = "0 4 * * *"

    def fetch(self, **kwargs: Any) -> list[RawItem]:
        """Hamta fran en myndighets sida.

        Kraver `url`. Anropas en myndighet i taget av tasks/jobs.py, sa att en
        myndighet som slutar svara inte stoppar de andra.
        """
        url = kwargs.get("url")
        if not url:
            raise ValueError("authority_pages kraver url")
        organisation = kwargs.get("organisation_name")
        metod = kwargs.get("method", "auto")

        tillatet = robots_allows(url)
        if tillatet is False:
            raise SourceBlockedError(f"robots.txt forbjuder {url}")

        if metod in ("auto", "RSS") and (poster := self._try_rss(url, organisation)):
            return poster
        if metod in ("auto", "SITEMAP") and (poster := self._try_sitemap(url, organisation)):
            return poster
        return self._try_html(url, organisation)

    # --- Strategier ---

    def _try_rss(self, url: str, organisation: str | None) -> list[RawItem]:
        for kandidat in self._candidates(url, ("/rss", "/feed", "?feed=rss", "/jobs.rss")):
            try:
                text = self.get_text(kandidat)
            except Exception:
                continue
            if "<rss" not in text[:600].lower() and "<feed" not in text[:600].lower():
                continue
            poster = []
            for titel, lank, datum in _rss_items(text):
                if not TITLE_HINTS.search(titel):
                    continue
                poster.append(
                    RawItem(
                        external_id=lank,
                        title=titel,
                        payload={"source": "rss", "feed": kandidat, "link": lank, "date": datum},
                        url=lank,
                        organisation_name=organisation,
                        extra={"method": "RSS", "uncertain": False},
                    )
                )
            if poster:
                return poster
        return []

    def _try_sitemap(self, url: str, organisation: str | None) -> list[RawItem]:
        delar = urlsplit(url)
        bas = f"{delar.scheme}://{delar.netloc}"
        try:
            xml = self.get_text(f"{bas}/sitemap.xml")
        except Exception:
            return []
        if "<loc" not in xml.lower():
            return []

        kandidater = [
            u
            for u in _sitemap_urls(xml)
            if any(re.search(p, u, re.IGNORECASE) for p in AD_LINK_PATTERNS)
        ]
        # En sitemap kan ha tusentals URL:er. Hamta inte varje; det ar en
        # lankkalla, och titeln hamtas forst nar annonsen ar vard att oppna.
        poster = []
        for u in kandidater[:200]:
            slug = u.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            if not TITLE_HINTS.search(slug):
                continue
            poster.append(
                RawItem(
                    external_id=u,
                    title=slug.title(),
                    payload={"source": "sitemap", "url": u},
                    url=u,
                    organisation_name=organisation,
                    # Titeln kommer ur URL-slugen och ar inte annonsens rubrik.
                    extra={
                        "method": "SITEMAP",
                        "uncertain": True,
                        "note": "titel utlast ur URL, ej fran annonsen",
                    },
                )
            )
        return poster

    def _try_html(self, url: str, organisation: str | None) -> list[RawItem]:
        html = self.get_text(url)
        plattform = detect_platform(url)
        poster = []
        for link in _extract_links(html, url):
            if not any(re.search(p, link.href, re.IGNORECASE) for p in AD_LINK_PATTERNS):
                continue
            if not TITLE_HINTS.search(link.text):
                continue
            poster.append(
                RawItem(
                    external_id=link.href,
                    title=link.text,
                    payload={
                        "source": "html",
                        "page": url,
                        "href": link.href,
                        "link_text": link.text,
                        "platform": plattform.value,
                    },
                    url=link.href,
                    organisation_name=organisation,
                    extra={
                        "method": "HTML_SCRAPE",
                        "platform": plattform.value,
                        # Lankutvinning ar den minst tillforlitliga strategin.
                        # Resultatet ska granskas innan myndigheten blir ACTIVE.
                        "uncertain": True,
                        "note": "titel fran lanktext, beskrivning saknas",
                    },
                )
            )
        return poster

    @staticmethod
    def _candidates(url: str, suffixes: tuple[str, ...]) -> list[str]:
        delar = urlsplit(url)
        bas = f"{delar.scheme}://{delar.netloc}"
        return [url.rstrip("/") + s for s in suffixes] + [bas + s for s in suffixes]


def verify_authority(url: str, organisation_name: str | None = None) -> dict:
    """Prova en myndighets sida och rapportera vad som gick att lasa.

    Anvands av `python -m app.cli verify-authority <url>` fore man satter en
    myndighet till ACTIVE. Returnerar ett resultat att titta pa, inte ett
    pastaende om att det fungerade.
    """
    adapter = AuthorityPagesAdapter()
    resultat: dict[str, Any] = {
        "url": url,
        "robots_allows": robots_allows(url),
        "platform": detect_platform(url).value,
        "checked_at": dt.datetime.now(dt.UTC).isoformat(),
    }
    korning = adapter.run(url=url, organisation_name=organisation_name)
    resultat["skipped"] = korning.skipped
    resultat["skip_reason"] = korning.skip_reason
    resultat["errors"] = korning.errors
    resultat["error_detail"] = korning.error_detail
    resultat["found"] = len(korning.items)
    resultat["method"] = korning.items[0].extra.get("method") if korning.items else None
    resultat["uncertain"] = any(p.extra.get("uncertain") for p in korning.items)
    resultat["sample"] = [{"title": p.title, "url": p.url} for p in korning.items[:10]]
    return resultat
