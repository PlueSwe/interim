"""Manuell import.

Behovs for allt som inte far hamtas automatiskt: kallor som robots.txt
forbjuder, konsultmaklare bakom inloggning, och export fran ett eget abonnemang
hos Mercell eller TendSign. Det ar inte en nodlosning utan den ratta vagen in
for en del av marknaden, och darfor en forstklassig adapter.

Tar emot CSV eller JSON. Ett faltnamn som inte kanns igen kastas inte bort utan
hamnar i extra, sa att ingenting tappas pa vagen in.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from typing import Any

from ..core.text import normalise_orgnr
from ..models.enums import AccessMode
from .base import RawItem, SourceAdapter

# Faltnamn vi kanner igen, svenska och engelska. Nycklarna ar normaliserade till
# gemener utan blanksteg vid uppslag.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "external_id": ("id", "externtid", "annonsid", "referens", "reference"),
    "title": ("titel", "rubrik", "title", "headline", "befattning", "roll"),
    "description": ("beskrivning", "description", "text", "uppdragsbeskrivning"),
    "organisation_name": ("organisation", "myndighet", "kund", "arbetsgivare", "buyer", "employer"),
    "organisation_number": ("orgnr", "organisationsnummer", "organizationnumber"),
    "url": ("url", "lank", "link", "webadress"),
    "published_at": ("publicerad", "publiceringsdatum", "publicationdate", "published"),
    "application_deadline": ("sistaansokningsdag", "deadline", "sistadag", "applicationdeadline"),
    "municipality": ("kommun", "ort", "municipality", "arbetsort"),
    "region": ("region", "lan", "län"),
    "recruiter_name": ("formedlare", "förmedlare", "maklare", "recruiter", "leverantor"),
}

DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d")


def _norm_key(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


def _parse_date(value: Any) -> dt.datetime | None:
    if not value:
        return None
    s = str(value).strip()
    try:
        stamp = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return stamp if stamp.tzinfo else stamp.replace(tzinfo=dt.UTC)
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return dt.datetime.strptime(s[: len(fmt) + 4], fmt).replace(tzinfo=dt.UTC)
        except ValueError:
            continue
    return None


def _map_row(row: dict[str, Any], index: int, source_key: str) -> RawItem:
    uppslag = {_norm_key(k): v for k, v in row.items() if k}
    varden: dict[str, Any] = {}
    anvanda: set[str] = set()

    for falt, alias in FIELD_ALIASES.items():
        for a in alias:
            nyckel = _norm_key(a)
            if nyckel in uppslag and uppslag[nyckel] not in (None, ""):
                varden[falt] = uppslag[nyckel]
                anvanda.add(nyckel)
                break

    # Allt som inte kandes igen foljer med. Ett falt vi inte forstar idag kan
    # vara det som behovs nar nagon undrar var en uppgift kom ifran.
    extra = {k: v for k, v in uppslag.items() if k not in anvanda and v not in (None, "")}

    titel = str(varden.get("title") or "").strip()
    if not titel:
        raise ValueError(f"rad {index + 1}: titel saknas (sokta falt: {FIELD_ALIASES['title']})")

    return RawItem(
        external_id=str(varden.get("external_id") or f"{source_key}-rad{index + 1}"),
        title=titel,
        payload={"row": row, "imported_at": dt.datetime.now(dt.UTC).isoformat()},
        url=varden.get("url"),
        description=varden.get("description"),
        organisation_name=varden.get("organisation_name"),
        organisation_number=normalise_orgnr(varden.get("organisation_number")),
        published_at=_parse_date(varden.get("published_at")),
        application_deadline=_parse_date(varden.get("application_deadline")),
        municipality=varden.get("municipality"),
        region=varden.get("region"),
        recruiter_name=varden.get("recruiter_name"),
        extra={"manual": True, "unmapped_fields": extra},
    )


class ManualImportAdapter(SourceAdapter):
    key = "manual"
    name = "Manuell import (CSV eller JSON)"
    access = AccessMode.MANUAL_ONLY
    legal_note = (
        "Data som anvandaren sjalv har ratt till: export fran eget abonnemang, "
        "eller uppgifter fran en kalla som inte far hamtas automatiskt."
    )

    def fetch(self, **kwargs: Any) -> list[RawItem]:
        """Las CSV eller JSON. `content` som text, eller `rows` som lista."""
        rader = kwargs.get("rows")
        innehall = kwargs.get("content")
        source_key = kwargs.get("source_key", "manual")

        if rader is None and innehall is None:
            raise ValueError("manual kraver content eller rows")

        if rader is None:
            rader = self.parse(innehall, filename=kwargs.get("filename"))

        poster = []
        fel = []
        for i, rad in enumerate(rader):
            try:
                poster.append(_map_row(rad, i, source_key))
            except ValueError as e:
                fel.append(str(e))
        if fel and not poster:
            raise ValueError("; ".join(fel[:5]))
        return poster

    @staticmethod
    def parse(content: str, filename: str | None = None) -> list[dict]:
        """Tolka CSV eller JSON. Avgor pa innehall, inte pa filandelse."""
        text = content.lstrip("﻿").strip()
        if text.startswith(("[", "{")):
            data = json.loads(text)
            if isinstance(data, dict):
                for nyckel in ("items", "rows", "data", "hits", "annonser"):
                    if isinstance(data.get(nyckel), list):
                        return data[nyckel]
                return [data]
            return data

        # CSV. Avskiljaren varierar: svenska Excel-exporter anvander semikolon.
        prov = text[:4096]
        try:
            dialekt = csv.Sniffer().sniff(prov, delimiters=";,\t|")
        except csv.Error:
            dialekt = csv.excel
            dialekt.delimiter = ";" if prov.count(";") > prov.count(",") else ","
        return list(csv.DictReader(io.StringIO(text), dialect=dialekt))

    def run(self, **kwargs: Any):
        """Overlagrar basen: manuell import ar avsiktlig och ska inte hoppas over.

        Basklassen hoppar over MANUAL_ONLY-kallor eftersom de inte far hamtas
        automatiskt. Just den har adaptern hamtar ingenting -- den tar emot vad
        anvandaren laddar upp -- sa spärren galler den inte.
        """
        from .base import SourceRunResult

        try:
            poster = self.fetch(**kwargs)
        except Exception as e:
            return SourceRunResult(self.key, errors=1, error_detail=f"{type(e).__name__}: {e}")
        return SourceRunResult(self.key, items=poster)
