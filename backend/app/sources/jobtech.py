"""JobTech: Arbetsformedlingens oppna annonsdata.

Tva API:er, och skillnaden mellan dem ar hela skalet till att systemet kan
besvara fragan om vem som fick en tjanst:

**jobsearch** ger annonser som ar publicerade just nu.

**historical** ger avpublicerade annonser sedan 2016, med
`last_publication_date`. Det ar det enda stallet dar en annons finns kvar efter
att den tagits ner fran myndighetens sida. Utan det skulle en rekrytering
forsvinna ur systemet precis nar den blir intressant.

Oppen data, ingen nyckel, ingen robots.txt. Villkoren tillater maskinell
anvandning. Takthallning anda, av hyfs.

Kallan ar ocksa battre an fritextgissning pa ett satt som ar latt att missa:
varje annons har ett yrkesbegrepp ur JobTechs taxonomi. IVO:s annons har bara
titeln "Verksamhetsomradeschef", men `occupation.label` sager "Chief Digital
Officer/CDO". Det ar kallans egen klassificering och den ar battre an var.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from ..core.text import normalise_orgnr
from ..core.timeutil import to_utc
from ..models.enums import AccessMode
from .base import RawItem, SourceAdapter

LIVE_URL = "https://jobsearch.api.jobtechdev.se/search"
HIST_URL = "https://historical.api.jobtechdev.se/search"

# Sokfraser ur bestallningen. Fritext, eftersom JobTechs `q` soker i rubrik och
# beskrivning. Listan ar bred med flit: filtreringen gors av
# core/classify.py, inte av sokningen. Att soka snavt har betyder missade
# annonser som aldrig gar att fa tillbaka.
ROLE_QUERIES: tuple[str, ...] = (
    "interim IT-chef",
    "interim CIO",
    "tillförordnad IT-chef",
    "IT-chef",
    "IT-direktör",
    "CIO",
    "CTO",
    "digitaliseringschef",
    "digitaliseringsdirektör",
    "verksamhetsområdeschef digitalisering",
    "avdelningschef IT",
    "enhetschef IT",
    "chef digital utveckling",
    "chef IT-arkitektur",
    "chef IT-drift",
    "IT Operations Manager",
    "förvaltningschef IT",
    "head of IT",
    "chief digital officer",
)

# Yrkesbegrepp ur JobTechs taxonomi som ar direkt relevanta. Soker man pa
# concept_id slipper man fritextens brus helt.
OCCUPATION_CONCEPT_IDS: tuple[str, ...] = (
    "rxZf_XT6_5xt",  # Chief Digital Officer/CDO  (IVO:s annons)
    "5zDe_ZGc_x89",  # Avdelningschef, statlig
)

PAGE_SIZE = 100
# JobTech slapper inte igenom hur djup paginering som helst. Tio sidor per fraga
# racker: en bredare traffmangd an 1000 betyder att fragan ar for vid, inte att
# det finns 1000 IT-chefsannonser.
MAX_PAGES = 10


def _parse_dt(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # JobTech skickar lokal tid utan zon. Databasen lagrar UTC, sa en naiv
    # tidsstampel maste fa en zon nagonstans, och det ar battre att gora det har
    # an att upptacka det som en dags fel i en deadline.
    return to_utc(stamp)


def _to_raw_item(hit: dict[str, Any], *, historical: bool) -> RawItem:
    arbetsgivare = hit.get("employer") or {}
    plats = hit.get("workplace_address") or {}
    yrke = hit.get("occupation") or {}

    return RawItem(
        external_id=str(hit.get("id")),
        title=(hit.get("headline") or "").strip(),
        payload=hit,
        url=hit.get("webpage_url"),
        description=((hit.get("description") or {}).get("text") or None),
        organisation_name=arbetsgivare.get("name") or arbetsgivare.get("workplace"),
        organisation_number=normalise_orgnr(arbetsgivare.get("organization_number")),
        published_at=_parse_dt(hit.get("publication_date")),
        application_deadline=_parse_dt(hit.get("application_deadline")),
        # Bara i det historiska API:et betyder last_publication_date att
        # annonsen faktiskt ar nere. I det levande ar det nar den kommer att
        # tas ner, och att tolka det som avpublicerad vore fel.
        depublished_at=_parse_dt(hit.get("last_publication_date")) if historical else None,
        municipality=plats.get("municipality"),
        region=plats.get("region"),
        address=plats.get("street_address"),
        occupation_concept_id=yrke.get("concept_id"),
        occupation_label=yrke.get("label"),
        extra={
            "employer_url": arbetsgivare.get("url"),
            "employment_type_raw": (hit.get("employment_type") or {}).get("label"),
            "duration_raw": (hit.get("duration") or {}).get("label"),
            "scope_of_work": hit.get("scope_of_work"),
            "historical": historical,
        },
    )


class _JobTechBase(SourceAdapter):
    access = AccessMode.OPEN_API
    url: str
    historical: bool

    def _search(self, params: dict[str, Any]) -> list[dict]:
        """En sokning med paginering. Returnerar traffarna."""
        traffar: list[dict] = []
        for sida in range(MAX_PAGES):
            svar = self.get_json(
                self.url, params={**params, "limit": PAGE_SIZE, "offset": sida * PAGE_SIZE}
            )
            del_traffar = svar.get("hits") or []
            traffar.extend(del_traffar)
            if len(del_traffar) < PAGE_SIZE:
                break
        return traffar

    def _collect(
        self,
        queries: tuple[str, ...] = ROLE_QUERIES,
        concept_ids: tuple[str, ...] = OCCUPATION_CONCEPT_IDS,
        employer: str | None = None,
    ) -> list[RawItem]:
        rader: dict[str, RawItem] = {}

        if employer:
            for hit in self._search({"employer": employer}):
                # Sokningen kan ge narliggande arbetsgivare. Behall bara exakt
                # rätt organisationsnummer.
                orgnr = normalise_orgnr((hit.get("employer") or {}).get("organization_number"))
                if orgnr != normalise_orgnr(employer):
                    continue
                rader[str(hit.get("id"))] = _to_raw_item(hit, historical=self.historical)
            return list(rader.values())

        for fraga in queries:
            for hit in self._search({"q": fraga}):
                rader[str(hit.get("id"))] = _to_raw_item(hit, historical=self.historical)

        for concept_id in concept_ids:
            for hit in self._search({"occupation-name": concept_id}):
                rader[str(hit.get("id"))] = _to_raw_item(hit, historical=self.historical)

        return list(rader.values())


class JobTechLiveAdapter(_JobTechBase):
    key = "jobtech_live"
    name = "Arbetsformedlingen Platsbanken (oppna data)"
    url = LIVE_URL
    base_url = LIVE_URL
    historical = False
    legal_note = (
        "Oppna data fran Arbetsformedlingen (JobTech Dev). Ingen nyckel, ingen robots.txt, "
        "villkoren tillater maskinell anvandning. Kontrollerad 2026-11-06."
    )
    default_cron = "0 */2 * * *"

    def fetch(self, **kwargs: Any) -> list[RawItem]:
        return self._collect(
            queries=kwargs.get("queries", ROLE_QUERIES),
            concept_ids=kwargs.get("concept_ids", OCCUPATION_CONCEPT_IDS),
            employer=kwargs.get("employer"),
        )


class JobTechHistoricalAdapter(_JobTechBase):
    """Avpublicerade annonser.

    Anvands till tva saker: att hitta rekryteringar som avslutats och darmed ska
    foljas vidare mot en tillsattning, och att bygga historik over vilka
    myndigheter som ofta rekryterar IT-chefer.
    """

    key = "jobtech_hist"
    name = "Arbetsformedlingen historiska annonser (oppna data)"
    url = HIST_URL
    base_url = HIST_URL
    historical = True
    legal_note = (
        "Oppna data fran Arbetsformedlingen (JobTech Dev), avpublicerade annonser sedan 2016. "
        "Kontrollerad 2026-11-06."
    )
    default_cron = "0 3 * * *"

    def fetch(self, **kwargs: Any) -> list[RawItem]:
        return self._collect(
            queries=kwargs.get("queries", ROLE_QUERIES),
            concept_ids=kwargs.get("concept_ids", OCCUPATION_CONCEPT_IDS),
            employer=kwargs.get("employer"),
        )

    def fetch_one(self, ad_id: str) -> RawItem | None:
        """En enskild annons via id. Anvands av IVO-testarendet."""
        hit = self.get_json(f"https://historical.api.jobtechdev.se/ad/{ad_id}")
        if not hit:
            return None
        return _to_raw_item(hit, historical=True)
