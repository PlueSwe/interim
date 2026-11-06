"""Tester for tillstandsmaskinen och tidszonhanteringen.

Den har filen finns pa grund av tva fel som bada bara visade sig vid andra
korningen: ett arende som lastes tillbaka ur databasen hade naiva tidsstamplar
och kraschade i jamforelsen mot now(UTC).
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.core import appointments as appt
from app.core.timeutil import to_utc
from app.models import AppointmentStatus as S

# --- Tidszon ---------------------------------------------------------------


def test_to_utc_ger_jamforbar_tid():
    naiv = dt.datetime(2026, 9, 20, 12, 0)
    assert to_utc(naiv).tzinfo is dt.UTC
    # Hela poangen: den ska ga att jamfora utan att Python klagar.
    assert to_utc(naiv) < dt.datetime.now(dt.UTC)


def test_to_utc_konverterar_annan_zon():
    stockholm = dt.timezone(dt.timedelta(hours=2))
    stamp = dt.datetime(2026, 9, 20, 14, 0, tzinfo=stockholm)
    assert to_utc(stamp) == dt.datetime(2026, 9, 20, 12, 0, tzinfo=dt.UTC)


def test_to_utc_slapper_igenom_none():
    assert to_utc(None) is None


# --- Tillatna overgangar ---------------------------------------------------


def test_verifierad_nas_bara_via_identifierad():
    """Bestallningens hardaste krav: inget antagande fran en borttagen annons.

    APPLICATION_CLOSED -> APPOINTMENT_IDENTIFIED ar tillaten, eftersom ett
    beslut kan hittas publicerat direkt efter att annonsen stangde. Spaarren
    ligger i transition(), som vagrar bada de stegen utan en handling. Det som
    tillstandsmaskinen sjalv garanterar ar att VERIFIED bara nas via
    IDENTIFIED -- aldrig direkt fran en stangd eller borttagen annons.
    """
    for fran in S:
        if fran is S.APPOINTMENT_IDENTIFIED:
            continue
        assert not appt.can_transition(fran, S.APPOINTMENT_VERIFIED), fran
    assert appt.can_transition(S.APPOINTMENT_IDENTIFIED, S.APPOINTMENT_VERIFIED)


def test_begaran_maste_passera_skickad_innan_svar():
    assert appt.can_transition(S.REQUEST_READY, S.REQUEST_SENT)
    assert appt.can_transition(S.REQUEST_SENT, S.RESPONSE_RECEIVED)
    assert not appt.can_transition(S.REQUEST_READY, S.RESPONSE_RECEIVED)


def test_terminala_lagen_har_ingen_vag_ut():
    for lage in appt.TERMINAL_STATES:
        for mal in S:
            assert not appt.can_transition(lage, mal), f"{lage} -> {mal}"


def test_varje_status_ar_natbar_fran_start():
    """Ingen status ska vara en o. Ar den det ar den antingen dod kod eller
    ett glapp i flodet."""
    natt = {S.ADVERTISEMENT_FOUND}
    andrat = True
    while andrat:
        andrat = False
        for fran in list(natt):
            for till in appt.ALLOWED_TRANSITIONS.get(fran, ()):
                if till not in natt:
                    natt.add(till)
                    andrat = True
    saknas = set(S) - natt
    assert saknas == set(), f"onaabara statusar: {saknas}"


# --- evaluate() ------------------------------------------------------------


class FalskAnnons:
    def __init__(self, deadline=None, avpublicerad=None):
        self.application_deadline = deadline
        self.depublished_at = avpublicerad
        self.title = "IT-chef"


class FalskMyndighet:
    def __init__(self, lage, plats=None):
        self.appointment_publication_mode = lage
        self.notice_board_location = plats


@pytest.fixture
def arende(session):
    """Ett arende med den annons databasen kraver att det hanger pa."""
    from app.models import Appointment, JobAd, SourceSnapshot

    snapshot = SourceSnapshot(
        source_key="test",
        fetched_at=dt.datetime.now(dt.UTC),
        sha256="0" * 64,
    )
    session.add(snapshot)
    session.flush()

    annons = JobAd(
        source_key="test",
        external_id="T-1",
        snapshot_id=snapshot.id,
        title="IT-chef",
        title_normalised="it-chef",
    )
    session.add(annons)
    session.flush()

    a = Appointment(
        job_ad_id=annons.id,
        status=S.ADVERTISEMENT_FOUND,
        status_changed_at=dt.datetime.now(dt.UTC),
    )
    session.add(a)
    session.commit()
    return a


def test_evaluate_taler_naiv_deadline(session, arende):
    """Regressionstest.

    SQLite lamnar ut datetime utan zon. Tidigare kraschade evaluate() da med
    "can't compare offset-naive and offset-aware datetimes", och det slog bara
    till vid andra korningen -- alltsa i drift, inte i utvecklingen.
    """
    annons = FalskAnnons(deadline=dt.datetime(2026, 9, 20, 12, 0))  # naiv, passerad
    resultat = appt.evaluate(session, arende, annons, None)
    assert resultat is not None
    assert arende.status is S.APPLICATION_CLOSED


def test_evaluate_oppen_ansokningstid(session, arende):
    framtid = dt.datetime.now(dt.UTC) + dt.timedelta(days=10)
    appt.evaluate(session, arende, FalskAnnons(deadline=framtid), None)
    assert arende.status is S.APPLICATION_OPEN


def test_evaluate_gor_ingenting_nar_inget_hant(session, arende):
    """None ar det normala svaret och ska inte forvaxlas med ett fel."""
    framtid = dt.datetime.now(dt.UTC) + dt.timedelta(days=10)
    appt.evaluate(session, arende, FalskAnnons(deadline=framtid), None)
    assert appt.evaluate(session, arende, FalskAnnons(deadline=framtid), None) is None


def test_fysisk_anslagstavla_gar_direkt_till_begaran(session, arende):
    from app.models import AppointmentPublicationMode as M

    annons = FalskAnnons(deadline=dt.datetime(2026, 9, 20, 12, 0))
    myndighet = FalskMyndighet(M.PHYSICAL_NOTICE_BOARD, "Torsplan, Stockholm")
    appt.evaluate(session, arende, annons, myndighet)
    assert arende.status is S.APPLICATION_CLOSED
    appt.evaluate(session, arende, annons, myndighet)
    assert arende.status is S.REQUEST_READY
    assert "anslagstavla" in arende.resolution_note


def test_webbpublicerande_myndighet_soks_pa_natet(session, arende):
    from app.models import AppointmentPublicationMode as M

    annons = FalskAnnons(deadline=dt.datetime(2026, 9, 20, 12, 0))
    myndighet = FalskMyndighet(M.DIGITAL)
    appt.evaluate(session, arende, annons, myndighet)
    appt.evaluate(session, arende, annons, myndighet)
    assert arende.status is S.RECRUITMENT_ONGOING
    assert appt.needs_web_search(arende, myndighet) is True


def test_ingen_sokning_mot_en_vagg(session, arende):
    """Att nota pa myndighetens webb nar besluten sitter pa en anslagstavla ar
    bortkastade anrop mot en sida som aldrig kommer att ha svaret."""
    from app.models import AppointmentPublicationMode as M

    arende.status = S.APPOINTMENT_NOT_FOUND
    assert appt.needs_web_search(arende, FalskMyndighet(M.PHYSICAL_NOTICE_BOARD)) is False


def test_sokning_upprepas_inte_for_ofta(session, arende):
    from app.models import AppointmentPublicationMode as M

    arende.status = S.APPOINTMENT_NOT_FOUND
    myndighet = FalskMyndighet(M.DIGITAL)
    arende.last_searched_at = dt.datetime.now(dt.UTC) - dt.timedelta(days=1)
    assert appt.needs_web_search(arende, myndighet) is False
    # Naiv tidsstampel, som den kommer ur SQLite.
    arende.last_searched_at = dt.datetime.now() - dt.timedelta(days=appt.SEARCH_INTERVAL_DAYS + 1)
    assert appt.needs_web_search(arende, myndighet) is True


# --- transition() ----------------------------------------------------------


def test_namn_kraver_handling(session, arende):
    arende.status = S.RESPONSE_RECEIVED
    with pytest.raises(ValueError, match="dokument"):
        appt.transition(session, arende, S.APPOINTMENT_IDENTIFIED, reason="svar inkom")


def test_verifierad_kraver_niva_ett_till_tre(session, arende):
    from app.models import DocumentType, PublicDocument

    dok = PublicDocument(document_type=DocumentType.WEB_PAGE, title="Profilsida")
    session.add(dok)
    session.commit()

    arende.status = S.APPOINTMENT_IDENTIFIED
    with pytest.raises(ValueError):
        appt.transition(
            session,
            arende,
            S.APPOINTMENT_VERIFIED,
            reason="hittade pa yrkesnatverk",
            evidence_document_id=dok.id,
            verification_level=4,
        )


def test_otillaten_overgang_vagras(session, arende):
    with pytest.raises(ValueError, match="inte tillåten"):
        appt.transition(session, arende, S.RESPONSE_RECEIVED, reason="hoppar over steg")


def test_historiken_skrivs(session, arende):
    from app.models import AppointmentStatusHistory

    appt.transition(session, arende, S.APPLICATION_OPEN, reason="ansokan oppen")
    appt.transition(session, arende, S.APPLICATION_CLOSED, reason="ansokan stangd")
    session.commit()

    from sqlalchemy import select

    rader = session.scalars(
        select(AppointmentStatusHistory)
        .where(AppointmentStatusHistory.appointment_id == arende.id)
        .order_by(AppointmentStatusHistory.changed_at)
    ).all()
    assert [r.to_status for r in rader] == [S.APPLICATION_OPEN, S.APPLICATION_CLOSED]
    assert rader[0].from_status is S.ADVERTISEMENT_FOUND
    assert rader[1].reason == "ansokan stangd"
