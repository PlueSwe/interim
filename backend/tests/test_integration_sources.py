"""Integrationstester mot verkliga kallor.

Hoppas over som standard (pyproject sätter `-m "not integration"`). Kor dem med:

    pytest -q -m integration

Varfor de finns: enhetstesterna provar att adaptern tolkar en payload ratt, men
inte att kallan fortfarande ser ut som adaptern tror. Ett API som byter namn pa
ett falt gar igenom varje enhetstest och ger noll traffar i drift. Det ar den
sortens fel som bara ett riktigt anrop hittar.

Varfor de inte kors som standard: de kraver nat, de belastar nagon annans
server, och ett rott test for att JobTech har driftstorning sager ingenting om
koden.

Testerna ar medvetet tolerant skrivna. De provar att kallan svarar och att
svaret gar att normalisera -- inte att en viss annons finns, eftersom annonser
forsvinner och ett test som kraver en namngiven annons bryts av sig sjalvt.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.sources import get_adapter
from app.sources.base import RawItem

pytestmark = pytest.mark.integration


def _rimlig(post: RawItem) -> None:
    """Gemensamma krav pa en normaliserad post, oavsett kalla."""
    assert post.external_id, "en post utan id gar inte att dubblettkontrollera"
    assert post.title and post.title.strip(), "tom titel"
    assert post.payload, "radatan maste foljas med, den ar beviset"
    for stampel in (post.published_at, post.application_deadline, post.depublished_at):
        if stampel is not None:
            assert stampel.tzinfo is not None, f"naiv tidsstampel: {stampel!r}"
            assert stampel.year >= 2015, f"orimligt datum: {stampel!r}"


def test_jobtech_live_svarar_och_gar_att_normalisera():
    resultat = get_adapter("jobtech_live").run()

    assert resultat.errors == 0, resultat.error_detail
    assert not resultat.skipped, resultat.skip_reason
    # Noll traffar ar inte ett fel i sig, men det ar vart att veta.
    if not resultat.items:
        pytest.skip("JobTech gav noll traffar for fragan just nu")

    for post in resultat.items[:25]:
        _rimlig(post)

    # Minst en post ska ha en organisation, annars faller dubblettsteg 2 och 3
    # for hela insamlingen.
    assert any(p.organisation_name for p in resultat.items)


def test_jobtech_historiska_ger_avpublicerade_annonser():
    """Enda kallan dar en annons finns kvar efter att den tagits ner."""
    resultat = get_adapter("jobtech_hist").run()

    assert resultat.errors == 0, resultat.error_detail
    if not resultat.items:
        pytest.skip("inga historiska traffar for fragan just nu")

    for post in resultat.items[:25]:
        _rimlig(post)

    # I det historiska API:et betyder last_publication_date att annonsen ar
    # nere. Satter adaptern inte depublished_at dar har tolkningen glidit.
    assert any(p.depublished_at is not None for p in resultat.items)


def test_ted_svarar_pa_expertfragan():
    resultat = get_adapter("ted").run()

    assert resultat.errors == 0, resultat.error_detail
    if resultat.skipped:
        pytest.skip(resultat.skip_reason or "TED hoppades over")
    if not resultat.items:
        pytest.skip("TED gav noll traffar for fragan just nu")

    for post in resultat.items[:25]:
        _rimlig(post)


def test_jobtech_hamtar_en_namngiven_annons():
    """fetch_one ar vagen in for en annons man har id:t till."""
    adapter = get_adapter("jobtech_hist")
    resultat = adapter.run()
    if not resultat.items:
        pytest.skip("inget id att prova med")

    id_ = resultat.items[0].external_id
    post = adapter.fetch_one(id_)

    assert post is not None, f"id {id_} gick inte att hamta en andra gang"
    assert post.external_id == id_
    _rimlig(post)


def test_robots_txt_respekteras_for_en_kalla_vi_inte_far_hamta():
    """Spärren ska vara pa, inte bara dokumenterad."""
    from app.sources.base import robots_allows

    # Google tillater inte /search. Ett lamplig prov eftersom svaret ar stabilt
    # och vi inte hamtar nagonting darifran i skarpt lage.
    assert robots_allows("https://www.google.com/search?q=test") is False


def test_tidsstamplar_ar_inte_i_framtiden():
    """En publicering i framtiden betyder nastan alltid fel tidszon."""
    resultat = get_adapter("jobtech_live").run()
    if not resultat.items:
        pytest.skip("inga traffar")

    nu = dt.datetime.now(dt.UTC)
    marginal = dt.timedelta(days=1)
    for post in resultat.items:
        if post.published_at:
            assert post.published_at <= nu + marginal, post.published_at
