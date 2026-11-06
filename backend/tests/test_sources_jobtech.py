"""Insamlingsvagarna i JobTech-adaptrarna.

Testerna har gar inte ut pa natet. De provar vad adaptern *fragar efter*,
eftersom det var dar felen satt: en fraga utan tidsfonster och ett
organisationsnummer i fel format gav bada tomma svar utan felkod.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.sources.jobtech import (
    HISTORICAL_DAYS,
    JobTechHistoricalAdapter,
    JobTechLiveAdapter,
)


def _hit(ad_id: str, titel: str, orgnr: str = "2021004474") -> dict[str, Any]:
    return {
        "id": ad_id,
        "headline": titel,
        "employer": {"name": "Statens Fastighetsverk", "organization_number": orgnr},
        "publication_date": "2026-10-13T14:41:33",
        "employment_type": {"label": "Vanlig anställning"},
        "description": {"text": "Beskrivning."},
    }


@pytest.fixture
def spion(monkeypatch):
    """Fangar varje fraga adaptern skickar, utan att rora natet."""
    fragor: list[dict] = []

    def fejkad_get_json(self, url, params=None, **kwargs):
        fragor.append(dict(params or {}))
        return {"hits": [_hit("1", "Chef till enheten för IT-arkitektur och IT-säkerhet")]}

    monkeypatch.setattr("app.sources.base.SourceAdapter.get_json", fejkad_get_json)
    return fragor


def test_orgnummer_med_bindestreck_normaliseras(spion) -> None:
    """API:et svarar 0 traffar pa "202100-4474" -- utan felkod.

    Det ar varsta sortens tyst fel: det ser ut som att myndigheten inte
    annonserar nagot. Adaptern maste darfor normalisera innan den fragar.
    """
    poster = JobTechLiveAdapter().fetch(employer="202100-4474")

    assert spion, "ingen fraga skickades"
    assert spion[0]["employer"] == "2021004474"
    assert len(poster) == 1


def test_historiska_kallan_har_ett_tidsfonster(spion) -> None:
    """Utan fonster avgor API:ets ordning vilka 1 000 av 4 656 traffar man far."""
    JobTechHistoricalAdapter().fetch(queries=("IT-chef",), concept_ids=())

    assert spion[0]["historical-from"], spion[0]
    assert spion[0]["q"] == "IT-chef"


def test_live_kallan_har_inget_tidsfonster(spion) -> None:
    """Platsbanken visar bara det som ar publicerat nu. Fonstret vore fel dar."""
    JobTechLiveAdapter().fetch(queries=("IT-chef",), concept_ids=())

    assert "historical-from" not in spion[0]


def test_tidsfonstret_ar_det_konfigurerade(spion) -> None:
    JobTechHistoricalAdapter().fetch(queries=("IT-chef",), concept_ids=())

    import datetime as dt

    fran = dt.datetime.fromisoformat(spion[0]["historical-from"])
    dagar = (dt.datetime.now() - fran).days
    assert HISTORICAL_DAYS - 1 <= dagar <= HISTORICAL_DAYS + 1, dagar


def test_svep_over_flera_myndigheter(spion) -> None:
    """En fraga per myndighet, och samma annons raknas en gang."""
    poster = JobTechHistoricalAdapter().fetch(
        employers=("202100-4474", "2021006065", "202100-4474")
    )

    # Tre angivna, tva unika organisationsnummer -- men adaptern ska inte gissa
    # sig till unikhet, den ska fraga en gang per angivet nummer.
    assert len(spion) == 3
    assert {f["employer"] for f in spion} == {"2021004474", "2021006065"}
    # Alla svar har samma annons-id, sa resultatet ar en post.
    assert len(poster) == 1


def test_annan_arbetsgivare_i_svaret_slangs(monkeypatch) -> None:
    """Sokningen pa employer kan ge narliggande organisationer."""

    def fejkad_get_json(self, url, params=None, **kwargs):
        return {
            "hits": [
                _hit("1", "Chef IT", orgnr="2021004474"),
                _hit("2", "Chef IT hos nagon annan", orgnr="2021006065"),
            ]
        }

    monkeypatch.setattr("app.sources.base.SourceAdapter.get_json", fejkad_get_json)
    poster = JobTechLiveAdapter().fetch(employer="2021004474")

    assert [p.external_id for p in poster] == ["1"]


def test_tomt_orgnummer_ger_ingen_fraga(spion) -> None:
    """Hellre noll fragor an en fraga som matchar allt."""
    poster = JobTechLiveAdapter().fetch(employers=("", "   ", None))

    assert spion == []
    assert poster == []
