"""TED: EU:s upphandlingsdatabas.

Den ursprungliga publiceringen for upphandlingar over troskelvardena. Oppet
API, ingen nyckel. Anvands i stallet for att skrapa Mercell eller TendSign: det
ar samma annonser, hamtade dar de forst publicerades, och det ar lagligt.

Tva saker satte kapp i vagen vid uppbyggnaden och ar vart att veta:

**Fragesyntaxen.** TED v3 tar inte fritext med AND/OR. Det ar ett eget
expert-sprak, och fel syntax ger QUERY_SYNTAX_ERROR med radkolumn. Adaptern
loggar felet rakt ut i stallet for att svalja det, eftersom ett tyst
syntaxfel ser ut som att det inte finns nagra upphandlingar.

**Flersprakiga falt.** notice-title och buyer-name kommer som ordbok fran
sprakkod till varde. Svenska ligger under "swe". Lasningen gar via _text(),
som tar svenska nar det finns och engelska annars, i stallet for att rakna pa
att nyckeln finns.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..core.timeutil import to_utc
from ..models.enums import AccessMode
from .base import RawItem, SourceAdapter

SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

# CPV-koder som fangar det systemet letar efter. 72 ar IT-tjanster, 79 ar
# foretagstjanster inklusive rekrytering och personaluthyrning -- det ar dar
# interimuppdragen ligger nar de kops som tjanst.
CPV_CODES: tuple[str, ...] = (
    "72000000",  # IT-tjanster
    "72220000",  # systemradgivning och teknisk radgivning
    "72224000",  # projektledningsradgivning
    "79400000",  # foretagsradgivning och ledningsradgivning
    "79600000",  # rekryteringstjanster
    "79620000",  # personaluthyrning
)

FIELDS: tuple[str, ...] = (
    "publication-number",
    "notice-title",
    "buyer-name",
    "publication-date",
    "notice-type",
    "classification-cpv",
    "deadline-receipt-request",
    "description-lot",
)

PAGE_SIZE = 100
MAX_PAGES = 10
DEFAULT_LOOKBACK_DAYS = 120


def _text(value: Any) -> str | None:
    """Las ett flersprakigt TED-falt. Svenska forst, engelska annars."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return _text(value[0]) if value else None
    if isinstance(value, dict):
        for sprak in ("swe", "eng", "mul"):
            if sprak in value:
                return _text(value[sprak])
        for v in value.values():
            return _text(v)
    return str(value)


def _parse_date(value: Any) -> dt.datetime | None:
    s = _text(value)
    if not s:
        return None
    try:
        stamp = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        try:
            stamp = dt.datetime.strptime(s[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return to_utc(stamp)


class TedAdapter(SourceAdapter):
    key = "ted"
    name = "TED - Tenders Electronic Daily"
    access = AccessMode.OPEN_API
    base_url = SEARCH_URL
    legal_note = (
        "EU:s officiella upphandlingsdatabas, oppet API utan nyckel. "
        "Ursprunglig publicering for upphandlingar over troskelvardena. "
        "Kontrollerad 2026-11-06."
    )
    default_cron = "0 */6 * * *"

    def build_query(self, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> str:
        """Expert-query for svenska upphandlingar inom relevanta CPV-koder.

        Datumfiltret ar inte bara en optimering. Utan det returnerar TED aldsta
        forst, och de forsta hundra traffarna blir annonser fran 2016.
        """
        fran = (dt.date.today() - dt.timedelta(days=lookback_days)).strftime("%Y%m%d")
        cpv = " ".join(CPV_CODES)
        return (
            f"place-of-performance IN (SWE) "
            f"AND classification-cpv IN ({cpv}) "
            f"AND publication-date >= {fran}"
        )

    def fetch(self, **kwargs: Any) -> list[RawItem]:
        query = kwargs.get("query") or self.build_query(
            lookback_days=kwargs.get("lookback_days", DEFAULT_LOOKBACK_DAYS)
        )
        poster: dict[str, RawItem] = {}

        for sida in range(1, MAX_PAGES + 1):
            svar = self.post_json(
                SEARCH_URL,
                {
                    "query": query,
                    "fields": list(FIELDS),
                    "limit": PAGE_SIZE,
                    "page": sida,
                    "scope": "ALL",
                },
            )
            annonser = svar.get("notices") or []
            for annons in annonser:
                post = self._to_raw_item(annons)
                if post:
                    poster[post.external_id] = post
            if len(annonser) < PAGE_SIZE:
                break

        return list(poster.values())

    def _to_raw_item(self, annons: dict[str, Any]) -> RawItem | None:
        nummer = _text(annons.get("publication-number"))
        if not nummer:
            return None
        titel = _text(annons.get("notice-title")) or f"TED {nummer}"
        return RawItem(
            external_id=nummer,
            title=titel,
            payload=annons,
            url=f"https://ted.europa.eu/sv/notice/{nummer}",
            description=_text(annons.get("description-lot")),
            organisation_name=_text(annons.get("buyer-name")),
            published_at=_parse_date(annons.get("publication-date")),
            application_deadline=_parse_date(annons.get("deadline-receipt-request")),
            extra={
                "notice_type": _text(annons.get("notice-type")),
                "cpv_codes": annons.get("classification-cpv") or [],
            },
        )
