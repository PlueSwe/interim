"""Inlasning: dubblettkontroll, versionering, kallnormalisering och begaran.

De harm testade delarna ar de som avgor om systemet gar att lita pa over tid.
En trasig dubblettkontroll syns inte som ett fel utan som en dashboard dar samma
uppdrag star fem ganger. En felaktig tidszon syns inte heller -- den syns som en
deadline som gick ut i gar nar den gar ut i dag.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from app.core import foi
from app.core.dedup import DuplicateKind, changed_fields, find_duplicate
from app.core.ingest import IngestStats, ingest_item
from app.models import (
    AppointmentPublicationMode,
    Authority,
    JobAd,
    JobAdVersion,
    Organisation,
    RequestStatus,
)
from app.sources.base import RawItem
from app.sources.jobtech import _to_raw_item

NU = dt.datetime(2026, 9, 1, 8, 0, tzinfo=dt.UTC)


def _post(
    *,
    external_id: str = "1",
    titel: str = "IT-chef",
    org: str = "Skolinspektionen",
    orgnr: str | None = "202100-6065",
    publicerad: dt.datetime | None = NU,
    deadline: dt.datetime | None = None,
    beskrivning: str | None = None,
) -> RawItem:
    return RawItem(
        external_id=external_id,
        title=titel,
        # Radatan ar det snapshotet hashas pa, sa en andrad deadline maste
        # synas aven dar -- precis som hos en riktig kalla.
        payload={
            "id": external_id,
            "headline": titel,
            "application_deadline": deadline.isoformat() if deadline else None,
        },
        url=f"https://exempel.test/{external_id}",
        description=beskrivning
        or (
            "Statlig myndighet soker IT-chef med budgetansvar, personalansvar "
            "och plats i ledningsgruppen. Du driver forandringsledning, "
            "informationssakerhet och molnmigrering."
        ),
        organisation_name=org,
        organisation_number=orgnr,
        published_at=publicerad,
        application_deadline=deadline,
    )


# --------------------------------------------------------------------------
# Dubblettkontroll
# --------------------------------------------------------------------------


def test_samma_kalla_och_id_ar_samma_annons(session):
    stats = IngestStats()
    forsta = ingest_item(session, _post(), "jobtech_live", stats=stats, now=NU)
    andra = ingest_item(session, _post(), "jobtech_live", stats=stats, now=NU)

    assert forsta is not None
    assert andra is not None
    assert andra.id == forsta.id
    assert stats.duplicate == 1
    assert session.query(JobAd).count() == 1


def test_samma_tjanst_fran_tva_kallor_samma_dag(session):
    """Platsbanken och myndighetens egen sida ska inte bli tva uppdrag."""
    stats = IngestStats()
    ingest_item(session, _post(external_id="a"), "jobtech_live", stats=stats, now=NU)
    ingest_item(session, _post(external_id="b"), "myndighet_egen", stats=stats, now=NU)

    assert stats.duplicate == 1
    assert session.query(JobAd).count() == 1


def test_olika_myndigheter_slas_inte_samman(session):
    """Tva myndigheters "IT-chef" ar tva tjanster, aldrig en."""
    stats = IngestStats()
    ingest_item(session, _post(external_id="a"), "jobtech_live", stats=stats, now=NU)
    ingest_item(
        session,
        _post(external_id="b", org="Statens fastighetsverk", orgnr="202100-4474"),
        "jobtech_live",
        stats=stats,
        now=NU,
    )

    assert stats.duplicate == 0
    assert session.query(JobAd).count() == 2


def test_okand_organisation_ger_hellre_dubblett_an_sammanslagning(session):
    """Utan organisation hoppas steg 2 och 3 over, och det ska sagas rakt ut."""
    traff = find_duplicate(
        session,
        source_key="manual",
        external_id="x",
        title="IT-chef",
        organisation_id=None,
        published_at=NU,
    )
    assert traff.kind is DuplicateKind.NONE
    assert "steg 2-3" in traff.reason


def test_liknande_titel_inom_fonstret_ar_dubblett(session):
    stats = IngestStats()
    ingest_item(
        session, _post(external_id="a", titel="IT-chef till myndigheten"), "k1", stats=stats, now=NU
    )
    ingest_item(
        session,
        _post(
            external_id="b",
            titel="IT-chef till myndigheten",
            publicerad=NU + dt.timedelta(days=14),
        ),
        "k2",
        stats=stats,
        now=NU,
    )

    assert stats.duplicate == 1


def test_samma_titel_ett_halvar_senare_ar_ny_rekrytering(session):
    stats = IngestStats()
    ingest_item(session, _post(external_id="a"), "k1", stats=stats, now=NU)
    ingest_item(
        session,
        _post(external_id="b", publicerad=NU + dt.timedelta(days=200)),
        "k2",
        stats=stats,
        now=NU,
    )

    assert stats.duplicate == 0
    assert session.query(JobAd).count() == 2


# --------------------------------------------------------------------------
# Versionering
# --------------------------------------------------------------------------


def test_andrad_deadline_ger_en_ny_version(session):
    stats = IngestStats()
    ingest_item(
        session,
        _post(deadline=dt.datetime(2026, 9, 20, tzinfo=dt.UTC)),
        "jobtech_live",
        stats=stats,
        now=NU,
    )
    ingest_item(
        session,
        _post(deadline=dt.datetime(2026, 10, 4, tzinfo=dt.UTC)),
        "jobtech_live",
        stats=stats,
        now=NU,
    )

    assert stats.changed == 1
    versioner = session.query(JobAdVersion).all()
    assert len(versioner) == 1
    assert "application_deadline" in versioner[0].changed_fields


def test_omskrivet_blanksteg_ar_ingen_andring():
    """En kalla som byter radbrytning mot mellanslag ska inte ge en version."""
    annons = JobAd(title="IT-chef", description="en rad\noch en till")
    diff = changed_fields(annons, {"description": "en rad och en till"})
    assert diff == {}


def test_andrad_titel_syns_i_diffen():
    annons = JobAd(title="IT-chef", description="x")
    diff = changed_fields(annons, {"title": "IT-direktor"})
    assert diff["title"]["from"] == "IT-chef"
    assert diff["title"]["to"] == "IT-direktor"


# --------------------------------------------------------------------------
# JobTech-normalisering
# --------------------------------------------------------------------------


def _hit(**extra) -> dict:
    grund = {
        "id": "28471234",
        "headline": "Verksamhetsomradeschef Digitalisering och IT",
        "description": {"text": "Vi soker en chef."},
        "employer": {
            "name": "Inspektionen for vard och omsorg",
            "organization_number": "2021007752",
        },
        "workplace_address": {"municipality": "Stockholm", "region": "Stockholms lan"},
        "occupation": {"concept_id": "rxZf_XT6_5xt", "label": "Chief Digital Officer/CDO"},
        "publication_date": "2026-08-20T09:00:00",
        "application_deadline": "2026-09-20T23:59:59",
        "last_publication_date": "2026-09-20T23:59:59",
        "webpage_url": "https://arbetsformedlingen.se/platsbanken/annonser/28471234",
    }
    grund.update(extra)
    return grund


def test_naiv_tid_fran_jobtech_far_en_zon():
    """Utan zon blir en jamforelse mot now(UTC) ett undantag i drift."""
    post = _to_raw_item(_hit(), historical=False)
    assert post.published_at is not None
    assert post.published_at.tzinfo is not None
    assert post.application_deadline is not None
    assert post.application_deadline.tzinfo is not None


def test_levande_annons_markeras_inte_som_avpublicerad():
    """I det levande API:et ar last_publication_date ett framtida datum."""
    assert _to_raw_item(_hit(), historical=False).depublished_at is None
    assert _to_raw_item(_hit(), historical=True).depublished_at is not None


def test_orgnr_normaliseras():
    # normalise_orgnr lamnar tio siffror utan bindestreck, sa att 202100-7752
    # och 2021007752 blir samma myndighet.
    assert _to_raw_item(_hit(), historical=False).organisation_number == "2021007752"
    assert (
        _to_raw_item(
            _hit(employer={"name": "IVO", "organization_number": "202100-7752"}), historical=False
        ).organisation_number
        == "2021007752"
    )


def test_saknade_falt_ger_none_inte_krasch():
    post = _to_raw_item({"id": "1", "headline": "IT-chef"}, historical=False)
    assert post.description is None
    assert post.organisation_name is None
    assert post.published_at is None
    assert post.application_deadline is None


# --------------------------------------------------------------------------
# Begaran om allman handling
# --------------------------------------------------------------------------


def _ivo_annons() -> JobAd:
    return JobAd(
        title="Verksamhetsomradeschef Digitalisering och IT",
        published_at=dt.datetime(2026, 8, 20, tzinfo=dt.UTC),
        application_deadline=dt.datetime(2026, 9, 20, tzinfo=dt.UTC),
        url="https://exempel.test/ivo",
    )


def test_utkastet_anvander_bestallningens_standardtext():
    utkast = foi.build_draft(
        job_ad=_ivo_annons(),
        authority=Authority(registrar_email="registrator@ivo.se"),
        organisation=Organisation(name="Inspektionen för vård och omsorg"),
    )

    assert utkast.body.startswith("Jag önskar ta del av anställningsbeslutet avseende")
    assert "Verksamhetsomradeschef Digitalisering och IT" in utkast.body
    assert "Inspektionen för vård och omsorg" in utkast.body
    # Deluppgift ska begaras aven om nagot inte kan lamnas ut.
    assert "beslut med uppgift om skälen" in utkast.body
    assert utkast.missing == []
    assert utkast.is_sendable


def test_anslagstavlan_namns_i_utkastet():
    """Myndigheten ska se att vi vet att beslutet inte finns digitalt."""
    utkast = foi.build_draft(
        job_ad=_ivo_annons(),
        authority=Authority(
            registrar_email="registrator@ivo.se",
            appointment_publication_mode=AppointmentPublicationMode.PHYSICAL_NOTICE_BOARD,
            notice_board_location="Torsplan, Stockholm",
        ),
        organisation=Organisation(name="Inspektionen för vård och omsorg"),
    )

    assert "anslagstavla vid Torsplan, Stockholm" in utkast.body
    assert "tryckfrihetsförordningen" in utkast.body


def test_utkast_utan_registrator_sager_vad_som_saknas():
    utkast = foi.build_draft(
        job_ad=_ivo_annons(),
        authority=Authority(registrar_email=None),
        organisation=Organisation(name="Inspektionen för vård och omsorg"),
    )

    assert "registratorsadress" in utkast.missing
    assert not utkast.is_sendable


def test_utkast_utan_deadline_gissar_inte_fram_ett_datum():
    annons = _ivo_annons()
    annons.application_deadline = None
    utkast = foi.build_draft(
        job_ad=annons,
        authority=Authority(registrar_email="registrator@ivo.se"),
        organisation=Organisation(name="Inspektionen för vård och omsorg"),
    )

    assert "okänt datum" in utkast.body
    assert "sista ansokningsdag" in utkast.missing


def test_godkannande_kraver_en_mottagare():
    """Utan registratorsadress finns ingen att skicka till, och da ska det sta still."""
    begaran = foi.InformationRequest(
        id=uuid.uuid4(),
        subject="Begäran",
        body="text",
        recipient_email=None,
        status=RequestStatus.DRAFT,
    )
    with pytest.raises(ValueError, match="[Mm]ottagare saknas"):
        foi.approve(None, begaran, user_id=uuid.uuid4())


def test_bara_utkast_kan_godkannas():
    begaran = foi.InformationRequest(
        id=uuid.uuid4(),
        subject="Begäran",
        body="text",
        recipient_email="registrator@ivo.se",
        status=RequestStatus.APPROVED,
    )
    with pytest.raises(ValueError, match="bara utkast"):
        foi.approve(None, begaran, user_id=uuid.uuid4())


# --------------------------------------------------------------------------
# AI som andra bedomning i inlasningen
# --------------------------------------------------------------------------

# Over MIN_TEXT_LENGTH, annars faller bedomningen pa INSUFFICIENT_TEXT i
# stallet for pa den tvetydiga regeln.
TVETYDIG = (
    "Myndigheten soker en interim IT-chef med budgetansvar och personalansvar. "
    "Uppdraget omfattar informationssakerhet, leverantorsstyrning och "
    "molnmigrering, och du ingar i myndighetens ledningsgrupp under hela "
    "perioden. Du driver forandringsledning tillsammans med verksamheten och "
    "ansvarar for forvaltningen av myndighetens it-stod. "
    "Säkerhetsskyddsavtal tillämpas i uppdraget."
)


def test_utan_ai_star_regelutfallet_kvar(session):
    """Standardlaget: ingen modell, och da ska arendet ligga for granskning."""
    from app.models import ExclusionRecord, ExclusionVerdict, Opportunity

    stats = IngestStats()
    ingest_item(
        session,
        _post(beskrivning=TVETYDIG),
        "jobtech_live",
        stats=stats,
        now=NU,
    )

    uppdrag = session.query(Opportunity).one()
    assert uppdrag.exclusion_status is ExclusionVerdict.REVIEW_REQUIRED
    assert session.query(ExclusionRecord).count() == 1
    assert stats.review == 1


def test_ai_kan_skarpa_ett_tvetydigt_arende(session, monkeypatch):
    """Nar modellen hittar ett belagg i texten ska uppdraget exkluderas.

    Observera vad som provas: att det blir TVA bedomningsrader, inte en
    overskriven. Regelns rad ar beviset for vad regelmotorn sa, och den far
    aldrig forsvinna bara for att en modell sa nagot annat senare.
    """
    from app.ai import classify
    from app.ai.provider import AIProvider, AIResponse
    from app.models import Assessor, ExclusionRecord, ExclusionVerdict, Opportunity

    citat = "Säkerhetsskyddsavtal tillämpas i uppdraget"

    class Falsk(AIProvider):
        name = "falsk"

        @property
        def model(self):
            return "falsk-1"

        @property
        def available(self):
            return True

        def complete_json(self, system, user, *, max_tokens=None):
            return AIResponse(
                data={
                    "verdict": "EXCLUDED",
                    "quote": citat,
                    "reason": "sakerhetsskyddsavtal med provningskrav",
                },
                provider=self.name,
                model=self.model,
                available=True,
            )

    monkeypatch.setattr(classify, "get_provider", lambda **kw: Falsk())

    stats = IngestStats()
    ingest_item(session, _post(beskrivning=TVETYDIG), "jobtech_live", stats=stats, now=NU)

    uppdrag = session.query(Opportunity).one()
    assert uppdrag.exclusion_status is ExclusionVerdict.EXCLUDED
    assert stats.excluded == 1
    assert stats.review == 0

    rader = session.query(ExclusionRecord).all()
    assert {r.assessor for r in rader} == {Assessor.RULE, Assessor.AI}
    ai_rad = next(r for r in rader if r.assessor is Assessor.AI)
    assert ai_rad.matched_quote == citat
    assert ai_rad.ai_model == "falsk/falsk-1"


def test_ai_som_vill_godkanna_far_inte_gora_det(session, monkeypatch):
    """Ett PASS fran modellen ska inte slacka regelmotorns flagga."""
    from app.ai import classify
    from app.ai.provider import AIProvider, AIResponse
    from app.models import ExclusionRecord, ExclusionVerdict, Opportunity

    class Slapp(AIProvider):
        name = "slapp"

        @property
        def model(self):
            return "slapp-1"

        @property
        def available(self):
            return True

        def complete_json(self, system, user, *, max_tokens=None):
            return AIResponse(
                data={"verdict": "PASS", "reason": "det ar nog lugnt"},
                provider=self.name,
                model=self.model,
                available=True,
            )

    monkeypatch.setattr(classify, "get_provider", lambda **kw: Slapp())

    stats = IngestStats()
    ingest_item(session, _post(beskrivning=TVETYDIG), "jobtech_live", stats=stats, now=NU)

    assert session.query(Opportunity).one().exclusion_status is ExclusionVerdict.REVIEW_REQUIRED
    # Ingen AI-rad skrivs, eftersom utfallet inte andrades.
    assert session.query(ExclusionRecord).count() == 1
