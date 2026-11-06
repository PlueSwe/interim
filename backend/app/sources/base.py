"""Basen for alla kalladaptrar.

En adapter hamtar fran en kalla och normaliserar till RawItem. Den avgor inte om
nagot ar relevant, matchar inte mot profilen och skriver inte till
uppdragstabellerna. Den gor en sak, och det gor den mojlig att testa.

Tre saker ar inbyggda har i stallet for i varje adapter, eftersom de annars
glommas i exakt den adapter dar de betyder mest:

**Lagesspärren.** En adapter med access=BLOCKED vagrar kora. Det ar inte en
rekommendation i en README utan ett undantag i run().

**Takthallningen.** Minsta tid mellan anrop mot samma vard, langre for HTML an
for API. Spars per vard sa att tva adaptrar mot samma sajt inte kringgar den.

**Felrapporteringen.** run() returnerar alltid ett SourceRunResult, aven nar
allt gick fel. En adapter som kastar undantag uppat gor att korningen ser ut som
att den aldrig hande; en adapter som returnerar noll traffar och ett skal syns pa
dashboarden.
"""

from __future__ import annotations

import datetime as dt
import time
import urllib.robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..config import settings
from ..models.enums import AccessMode

# Sista anropstidpunkt per vard, delat mellan adaptrar i samma process.
_last_call: dict[str, float] = {}
_robots_cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}


class SourceBlockedError(RuntimeError):
    """Kallan far inte hamtas automatiskt."""


@dataclass
class RawItem:
    """En normaliserad post fran en kalla, fore all tolkning.

    payload ar radatan som den kom, och den ar det som hamnar i snapshotet.
    Falten ovanfor ar bara det adaptern kunde lasa ut utan att gissa.
    """

    external_id: str
    title: str
    payload: Any
    url: str | None = None
    description: str | None = None
    organisation_name: str | None = None
    organisation_number: str | None = None
    published_at: dt.datetime | None = None
    application_deadline: dt.datetime | None = None
    depublished_at: dt.datetime | None = None
    municipality: str | None = None
    region: str | None = None
    address: str | None = None
    occupation_concept_id: str | None = None
    occupation_label: str | None = None
    recruiter_name: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class SourceRunResult:
    source_key: str
    items: list[RawItem] = field(default_factory=list)
    errors: int = 0
    error_detail: str | None = None
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.errors == 0 and not self.skipped


def _host(url: str) -> str:
    return urlsplit(url).netloc


def _throttle(url: str, *, is_html: bool) -> None:
    vard = _host(url)
    minsta = settings.delay_html_seconds if is_html else settings.delay_api_seconds
    forra = _last_call.get(vard)
    nu = time.monotonic()
    if forra is not None:
        vanta = minsta - (nu - forra)
        if vanta > 0:
            time.sleep(vanta)
    _last_call[vard] = time.monotonic()


def robots_allows(url: str) -> bool | None:
    """Far vi hamta denna URL? None nar robots.txt inte gick att lasa.

    None behandlas inte som ja. Anroparen far avgora, och for en ny kalla
    innebar det manuell kontroll.
    """
    delar = urlsplit(url)
    bas = f"{delar.scheme}://{delar.netloc}"
    if bas not in _robots_cache:
        parser = urllib.robotparser.RobotFileParser()
        try:
            svar = httpx.get(
                f"{bas}/robots.txt",
                headers={"User-Agent": settings.user_agent},
                timeout=15,
                follow_redirects=True,
            )
            if svar.status_code == 200:
                parser.parse(svar.text.splitlines())
                _robots_cache[bas] = parser
            else:
                # 404 pa robots.txt betyder att det inte finns nagra regler.
                _robots_cache[bas] = None
        except Exception:
            _robots_cache[bas] = None
    parser = _robots_cache[bas]
    if parser is None:
        return None
    return parser.can_fetch(settings.user_agent, url)


class SourceAdapter(ABC):
    key: str
    name: str
    access: AccessMode
    legal_note: str = ""
    base_url: str = ""
    # Vilka scheman i celery beat som ska trigga adaptern.
    default_cron: str | None = None

    @abstractmethod
    def fetch(self, **kwargs: Any) -> list[RawItem]:
        """Hamta och normalisera. Far kasta undantag; run() fangar dem."""

    # --- Gemensam HTTP ---

    def _client(self) -> httpx.Client:
        return httpx.Client(
            headers={"User-Agent": settings.user_agent, "Accept-Encoding": "gzip"},
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        )

    def get_json(self, url: str, params: dict | None = None) -> Any:
        return self._request("GET", url, params=params, is_html=False).json()

    def post_json(self, url: str, body: dict) -> Any:
        return self._request("POST", url, json=body, is_html=False).json()

    def get_text(self, url: str) -> str:
        return self._request("GET", url, is_html=True).text

    def _request(self, method: str, url: str, *, is_html: bool, **kw: Any) -> httpx.Response:
        """Anrop med takthallning och retry pa overgaende fel.

        Retry bara pa 429 och 5xx. Ett 404 ar ett svar och inte ett fel att
        forsoka igen med; att retry:a det doljer bara att en URL ar fel.
        """
        if is_html:
            tillatet = robots_allows(url)
            if tillatet is False:
                raise SourceBlockedError(f"robots.txt forbjuder {url}")

        senaste: Exception | None = None
        for forsok in range(settings.http_retries + 1):
            _throttle(url, is_html=is_html)
            try:
                with self._client() as klient:
                    svar = klient.request(method, url, **kw)
                aterforsokbar = svar.status_code in (429, 500, 502, 503, 504)
                if aterforsokbar and forsok < settings.http_retries:
                    time.sleep(2**forsok * 2)
                    continue
                svar.raise_for_status()
                return svar
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (429, 500, 502, 503, 504) and (
                    forsok < settings.http_retries
                ):
                    senaste = e
                    time.sleep(2**forsok * 2)
                    continue
                raise
            except (httpx.TransportError, httpx.TimeoutException) as e:
                senaste = e
                if forsok < settings.http_retries:
                    time.sleep(2**forsok * 2)
                    continue
                raise
        if senaste:
            raise senaste
        raise RuntimeError("otillganglig kodvag")

    # --- Korning ---

    def run(self, **kwargs: Any) -> SourceRunResult:
        """Kor adaptern och rapportera, aven nar det gick fel."""
        if self.access in (AccessMode.BLOCKED, AccessMode.MANUAL_ONLY):
            return SourceRunResult(
                self.key,
                skipped=True,
                skip_reason=(
                    f"kallan har lage {self.access.value}: "
                    f"{self.legal_note or 'ingen automatisk hamtning'}"
                ),
            )
        try:
            poster = self.fetch(**kwargs)
        except SourceBlockedError as e:
            return SourceRunResult(
                self.key, errors=1, error_detail=str(e), skipped=True, skip_reason=str(e)
            )
        except Exception as e:
            return SourceRunResult(self.key, errors=1, error_detail=f"{type(e).__name__}: {e}")
        return SourceRunResult(self.key, items=poster)
