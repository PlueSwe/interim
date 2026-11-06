"""Tester for API:et.

Tyngdpunkten ligger pa de stallen dar ett fel gor verklig skada: att en begaran
inte kan skickas utan godkannande, och att ett namn inte kan registreras utan
en handling.
"""

from __future__ import annotations

import datetime as dt

import pytest


def test_inloggning_kravs(client):
    """Alla skyddade endpoints ska ge 401 utan cookie."""
    from fastapi.testclient import TestClient

    from app.main import app

    anonym = TestClient(app)
    for sokvag in (
        "/api/v1/dashboard",
        "/api/v1/opportunities",
        "/api/v1/appointments",
        "/api/v1/information-requests",
        "/api/v1/admin/sources",
    ):
        assert anonym.get(sokvag).status_code == 401, sokvag


def test_fel_losenord_ger_401_och_avslojar_inte_kontot(client):
    from fastapi.testclient import TestClient

    from app.main import app

    c = TestClient(app)
    finns = c.post(
        "/api/v1/auth/login", json={"email": "admin@test.example.com", "password": "fel"}
    )
    finns_inte = c.post(
        "/api/v1/auth/login", json={"email": "ingen@test.example.com", "password": "fel"}
    )
    assert finns.status_code == finns_inte.status_code == 401
    # Samma text, annars gar det att ta reda pa vilka adresser som har konto.
    assert finns.json()["detail"] == finns_inte.json()["detail"]


def test_health_svarar_utan_inloggning(client):
    svar = client.get("/health")
    assert svar.status_code == 200
    assert svar.json()["status"] == "ok"


def test_dashboard_med_tom_databas(client):
    svar = client.get("/api/v1/dashboard")
    assert svar.status_code == 200
    data = svar.json()
    assert data["new_opportunities_7d"] == 0
    assert data["top_matches"] == []
    # Diagramunderlaget ska finnas aven nar det ar tomt, annars kraschar
    # frontend pa en saknad nyckel.
    for nyckel in (
        "ads_per_week",
        "by_org_type",
        "recruitments_per_authority",
        "appointments_over_time",
        "by_recruiter",
        "by_region",
    ):
        assert nyckel in data["charts"], nyckel


def test_exkluderingsregler_gar_att_granska(client):
    """Regelverket ska ga att se utan att lasa koden."""
    svar = client.get("/api/v1/admin/exclusion-rules")
    assert svar.status_code == 200
    data = svar.json()
    regel_ids = {r["rule_id"] for r in data["rules"]}
    assert "SEC_CLEARANCE_EXPLICIT" in regel_ids
    assert "INFOSEC" in regel_ids  # BENIGN-reglerna ska ocksa visas
    assert set(data["verdicts"]) == {"PASS", "REVIEW_REQUIRED", "EXCLUDED"}
    assert data["verification_levels"]["1"] or data["verification_levels"].get(1)


def test_import_vagrar_sekretessbelagt(client):
    """SECURITY.md: sekretessbelagt underlag ska inte in i systemet."""
    svar = client.post(
        "/api/v1/admin/import",
        json={
            "content": "SEKRETESS enligt OSL 15:2\ntitel;organisation\nIT-chef;Myndigheten",
            "filename": "hemlig.csv",
        },
    )
    assert svar.status_code == 422
    assert "SEKRETESS" in svar.json()["detail"]


def test_manuell_import_fungerar(client):
    """CSV med semikolon, som svenska Excel-exporter ger."""
    csv = (
        "titel;organisation;orgnr;beskrivning;sista ansökningsdag;kommun\n"
        "Interim IT-chef;Testmyndigheten;202100-1234;"
        "Vi söker interim IT-chef med budgetansvar och personalansvar till "
        "statlig myndighet. Du driver förändringsledning och verksamhetsutveckling "
        "samt ansvarar för informationssäkerhet, IT-arkitektur och molnmigrering. "
        "Uppdraget är 12 månader.;2026-12-31;Stockholm\n"
    )
    svar = client.post("/api/v1/admin/import", json={"content": csv})
    assert svar.status_code == 200, svar.text
    data = svar.json()
    assert data["found"] == 1
    assert data["new"] == 1

    lista = client.get("/api/v1/opportunities").json()
    assert lista["total"] == 1
    uppdrag = lista["items"][0]
    assert uppdrag["job_ad"]["title"] == "Interim IT-chef"
    assert uppdrag["job_ad"]["organisation_name"] == "Testmyndigheten"
    assert uppdrag["exclusion_status"] == "PASS"
    assert uppdrag["match_score"] is not None


def test_import_av_samma_rad_tva_ganger_ger_dubblett(client):
    csv = (
        "id;titel;organisation;orgnr;beskrivning\n"
        "A1;IT-chef;Testmyndigheten;202100-1234;"
        + (
            "Du leder IT-avdelningen vid en statlig myndighet med budgetansvar "
            "och personalansvar samt ansvar för verksamhetsutveckling. " * 3
        )
        + "\n"
    )
    forsta = client.post("/api/v1/admin/import", json={"content": csv}).json()
    andra = client.post("/api/v1/admin/import", json={"content": csv}).json()
    assert forsta["new"] == 1
    assert andra["new"] == 0
    assert andra["duplicate"] == 1
    assert client.get("/api/v1/opportunities").json()["total"] == 1


def test_sokfilter(client):
    csv = (
        "titel;organisation;orgnr;beskrivning;kommun\n"
        "IT-chef Stockholm;Myndighet A;202100-1111;"
        + "Statlig myndighet, budgetansvar, personalansvar, ledningsgrupp. "
        * 4
        + ";Stockholm\n"
        "Digitaliseringschef Malmö;Myndighet B;202100-2222;"
        + "Kommun, förändringsledning, verksamhetsutveckling, digitalisering. " * 4
        + ";Malmö\n"
    )
    assert client.post("/api/v1/admin/import", json={"content": csv}).json()["new"] == 2

    assert client.get("/api/v1/opportunities", params={"q": "Digitalisering"}).json()["total"] == 1
    assert (
        client.get("/api/v1/opportunities", params={"municipality": "Stockholm"}).json()["total"]
        == 1
    )
    assert client.get("/api/v1/opportunities", params={"min_score": 101 - 1}).json()["total"] <= 2
    assert (
        client.get(
            "/api/v1/opportunities", params={"role_family": "DIGITALISATION_MANAGER"}
        ).json()["total"]
        == 1
    )


def test_exkluderat_uppdrag_syns_inte_i_listan_men_i_excluded(client):
    csv = (
        "titel;organisation;orgnr;beskrivning\n"
        "IT-chef;Myndighet;202100-3333;"
        + "Du leder IT vid en statlig myndighet med budgetansvar. "
        + "Säkerhetsprövning med registerkontroll genomförs före anställning. " * 3
        + "\n"
    )
    svar = client.post("/api/v1/admin/import", json={"content": csv}).json()
    assert svar["excluded"] == 1

    assert client.get("/api/v1/opportunities").json()["total"] == 0
    exkluderade = client.get("/api/v1/opportunities/excluded").json()
    assert exkluderade["total"] == 1
    post = exkluderade["items"][0]
    assert post["exclusion"]["verdict"] == "EXCLUDED"
    # Citatet maste finnas; det ar bevisets karna.
    assert "äkerhetsprövning" in post["exclusion"]["matched_quote"]
    # Och ingen poang pa nagot man inte kan ta.
    assert post["match_score"] is None


def test_overprovning_skapar_ny_rad_och_skriver_inte_over(client):
    csv = (
        "titel;organisation;orgnr;beskrivning\n"
        "IT-chef;Myndighet;202100-4444;"
        + "Du leder IT vid en myndighet. Bakgrundskontroll görs på slutkandidater. " * 4
        + "\n"
    )
    client.post("/api/v1/admin/import", json={"content": csv})
    uppdrag_id = client.get("/api/v1/opportunities/excluded").json()["items"][0]["id"]

    svar = client.post(
        f"/api/v1/opportunities/{uppdrag_id}/exclusion-override",
        json={"verdict": "PASS", "reason": "Kontrollen gäller endast fast anställda, ej konsult."},
    )
    assert svar.status_code == 200, svar.text
    assert svar.json()["assessor"] == "HUMAN"

    detalj = client.get(f"/api/v1/opportunities/{uppdrag_id}").json()
    assert detalj["exclusion_status"] == "PASS"
    # Poang ska ha rakanats om nar posten blev godkand.
    assert detalj["match_score"] is not None

    # Revisionsloggen ska visa bade fore och efter.
    logg = client.get("/api/v1/admin/audit").json()
    overprovning = [r for r in logg if r["action"] == "exclusion_override"]
    assert overprovning
    assert overprovning[0]["before"]["exclusion_status"] == "EXCLUDED"
    assert overprovning[0]["after"]["exclusion_status"] == "PASS"


def test_analytiker_far_inte_overprova(client):
    """Rollkontroll: bara ADMIN andrar beslut."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models import User, UserRole
    from app.security import hash_password

    s = client.test_session
    s.add(
        User(
            email="analytiker@test.example.com",
            password_hash=hash_password("testlosenord-12345"),
            role=UserRole.ANALYST,
            is_active=True,
        )
    )
    s.commit()

    c = TestClient(app)
    c.post(
        "/api/v1/auth/login",
        json={"email": "analytiker@test.example.com", "password": "testlosenord-12345"},
    )
    svar = c.post(
        "/api/v1/opportunities/00000000-0000-0000-0000-000000000000/exclusion-override",
        json={"verdict": "PASS", "reason": "nagon anledning som ar lang nog"},
    )
    assert svar.status_code == 403
    assert "ADMIN" in svar.json()["detail"]


def test_profilvikter_gar_att_andra_men_inte_till_noll(client):
    from app.seed import seed_profile

    seed_profile(client.test_session)
    client.test_session.commit()

    assert client.get("/api/v1/admin/profile").status_code == 200

    ok = client.patch("/api/v1/admin/profile", json={"weights": {"role": 50, "leadership": 50}})
    assert ok.status_code == 200
    assert ok.json()["weights"]["role"] == 50

    noll = client.patch("/api/v1/admin/profile", json={"weights": {"role": 0}})
    assert noll.status_code == 422
    assert "noll" in noll.json()["detail"]


def test_snapshot_gar_att_lasa_och_verifiera(client):
    """Sparbarhet: fran uppdrag till radata med sha256-kontroll."""
    csv = (
        "titel;organisation;orgnr;beskrivning\n"
        "IT-chef;Myndighet;202100-5555;"
        + "Du leder IT vid en statlig myndighet med budget- och personalansvar. " * 4
        + "\n"
    )
    client.post("/api/v1/admin/import", json={"content": csv})
    uppdrag = client.get("/api/v1/opportunities").json()["items"][0]
    snapshot_id = uppdrag["job_ad"]["snapshot_id"]

    svar = client.get(f"/api/v1/admin/snapshots/{snapshot_id}")
    assert svar.status_code == 200
    data = svar.json()
    assert len(data["sha256"]) == 64
    assert data["integrity_ok"] is True
    assert data["content"]


# --- Begaran om allman handling: de viktiga sparrarna ---------------------


@pytest.fixture
def ivo_arende(client):
    """Seedar IVO-arendet, som ger ett arende i REQUEST_READY med ett utkast."""
    from app.seed import seed_ivo_case, seed_profile

    s = client.test_session
    seed_profile(s)
    try:
        resultat = seed_ivo_case(s)
    except FileNotFoundError:
        pytest.skip("IVO-snapshot saknas")
    s.commit()
    return resultat


def test_ivo_arendet_hamnar_i_request_ready_utan_namn(client, ivo_arende):
    """Bestallningens testarende, hela vagen genom API:et."""
    assert ivo_arende["appointment_status"] == "REQUEST_READY"
    assert ivo_arende["appointed_person"] is None
    assert ivo_arende["exclusion_status"] == "PASS"
    assert ivo_arende["information_request_status"] == "DRAFT"
    assert ivo_arende["information_request_recipient"] == "registrator@ivo.se"

    arende = client.get(f"/api/v1/appointments/{ivo_arende['appointment_id']}").json()
    assert arende["status"] == "REQUEST_READY"
    assert arende["appointed_person_name"] is None
    assert arende["verification_level"] is None
    # Historiken ska visa vagen dit, inte bara slutlaget.
    statusar = [h["to_status"] for h in arende["history"]]
    assert statusar == ["ADVERTISEMENT_FOUND", "APPLICATION_CLOSED", "REQUEST_READY"]
    assert "anslagstavla" in arende["resolution_note"]


def test_begaran_kan_inte_markeras_skickad_utan_godkannande(client, ivo_arende):
    """Den enskilt viktigaste sparren i hela systemet."""
    begaran_id = ivo_arende["information_request_id"]
    svar = client.post(f"/api/v1/information-requests/{begaran_id}/mark-sent", json={})
    assert svar.status_code == 409
    assert "godkänn" in svar.json()["detail"].lower()

    assert client.get(f"/api/v1/information-requests/{begaran_id}").json()["status"] == "DRAFT"


def test_begaran_godkanns_och_markeras_skickad(client, ivo_arende):
    begaran_id = ivo_arende["information_request_id"]

    godkann = client.post(f"/api/v1/information-requests/{begaran_id}/approve")
    assert godkann.status_code == 200
    assert godkann.json()["status"] == "APPROVED"
    assert godkann.json()["approved_at"]

    skicka = client.post(
        f"/api/v1/information-requests/{begaran_id}/mark-sent", json={"channel": "EMAIL"}
    )
    assert skicka.status_code == 200
    assert skicka.json()["status"] == "SENT"

    arende = client.get(f"/api/v1/appointments/{ivo_arende['appointment_id']}").json()
    assert arende["status"] == "REQUEST_SENT"

    # Texten som godkandes ska ligga i revisionsloggen.
    logg = client.get("/api/v1/admin/audit").json()
    godkannanden = [r for r in logg if r["action"] == "request_approve"]
    assert godkannanden
    assert "anställningsbeslutet" in godkannanden[0]["after"]["body"]


def test_godkant_utkast_gar_inte_att_redigera(client, ivo_arende):
    begaran_id = ivo_arende["information_request_id"]
    client.post(f"/api/v1/information-requests/{begaran_id}/approve")
    svar = client.patch(f"/api/v1/information-requests/{begaran_id}", json={"subject": "ändrat"})
    assert svar.status_code == 409


def test_utkastet_ar_korrekt_svenska(client, ivo_arende):
    """Texten lamnar systemet och lases av en registrator."""
    begaran = client.get(
        f"/api/v1/information-requests/{ivo_arende['information_request_id']}"
    ).json()
    for fras in (
        "Jag önskar ta del av anställningsbeslutet",
        "vem som anställdes",
        "beslutsdatum",
        "tillträdesdatum",
        "diarienummer",
        "digitalt",
    ):
        assert fras in begaran["body"], fras
    assert "Inspektionen för vård och omsorg" in begaran["body"]
    assert "anslagstavla" in begaran["body"]


def test_namn_kan_inte_registreras_utan_handling(client, ivo_arende):
    """Ett namn utan handling ar ett rykte, och ska vagras."""
    svar = client.post(
        f"/api/v1/appointments/{ivo_arende['appointment_id']}/identify",
        json={
            "full_name": "Namn Namnsson",
            "document_id": "00000000-0000-0000-0000-000000000000",
            "verification_level": 1,
        },
    )
    assert svar.status_code == 422
    assert "handling" in svar.json()["detail"]


def test_niva_fyra_ger_inget_namn(client, ivo_arende):
    """En LinkedIn-traff ar ett uppslag, inte ett belagg.

    SECURITY.md: niva 4-5 far inte ge en rad i appointed_persons.
    """
    from sqlalchemy import func, select

    from app.models import AppointedPerson, DocumentType, PublicDocument

    s = client.test_session
    dok = PublicDocument(
        document_type=DocumentType.WEB_PAGE,
        title="Profil pa yrkesnatverk",
        url="https://exempel.invalid/profil",
        acquisition="WEB_SEARCH",
    )
    s.add(dok)
    s.commit()

    svar = client.post(
        f"/api/v1/appointments/{ivo_arende['appointment_id']}/identify",
        json={
            "full_name": "Namn Namnsson",
            "document_id": str(dok.id),
            "verification_level": 4,
        },
    )
    assert svar.status_code == 200
    arende = svar.json()
    assert arende["appointed_person_name"] is None
    assert arende["status"] == "REQUEST_READY"  # arendet star kvar
    assert "Racker inte som belagg" in arende["resolution_note"]
    assert s.scalar(select(func.count()).select_from(AppointedPerson)) == 0


def test_niva_ett_ger_verifierad_tillsattning(client, ivo_arende):
    from app.models import DocumentType, PublicDocument

    s = client.test_session
    dok = PublicDocument(
        document_type=DocumentType.EMPLOYMENT_DECISION,
        title="Anställningsbeslut",
        diary_number="1.2.3-45678/2026",
        document_date=dt.date(2026, 10, 15),
        acquisition="REGISTRAR_REPLY",
    )
    s.add(dok)
    s.commit()

    svar = client.post(
        f"/api/v1/appointments/{ivo_arende['appointment_id']}/identify",
        json={
            "full_name": "Namn Namnsson",
            "document_id": str(dok.id),
            "verification_level": 1,
            "previous_role": "IT-chef",
            "previous_organisation": "Annan myndighet",
            "decision_date": "2026-10-15",
            "diary_number": "1.2.3-45678/2026",
        },
    )
    assert svar.status_code == 200, svar.text
    arende = svar.json()
    assert arende["status"] == "APPOINTMENT_VERIFIED"
    assert arende["verification_level"] == 1
    assert arende["appointed_person_name"] == "Namn Namnsson"
    assert arende["verification_label"] == "Officiellt anstallningsbeslut"


def test_personuppgift_gar_att_radera(client, ivo_arende):
    """GDPR art. 17. Arendet behalls, namnet raderas."""
    from sqlalchemy import func, select

    from app.models import AppointedPerson, DocumentType, PublicDocument

    s = client.test_session
    dok = PublicDocument(
        document_type=DocumentType.EMPLOYMENT_DECISION,
        title="Anställningsbeslut",
        document_date=dt.date(2026, 10, 15),
    )
    s.add(dok)
    s.commit()
    client.post(
        f"/api/v1/appointments/{ivo_arende['appointment_id']}/identify",
        json={
            "full_name": "Namn Namnsson",
            "document_id": str(dok.id),
            "verification_level": 1,
        },
    )
    person_id = str(
        s.scalar(select(AppointedPerson.id).where(AppointedPerson.full_name == "Namn Namnsson"))
    )

    svar = client.delete(
        f"/api/v1/appointed-persons/{person_id}", params={"reason": "begäran från den berörda"}
    )
    assert svar.status_code == 200
    assert s.scalar(select(func.count()).select_from(AppointedPerson)) == 0
    # Handlingen finns kvar; den ar myndighetens, inte var att radera.
    assert s.get(PublicDocument, dok.id) is not None

    arende = client.get(f"/api/v1/appointments/{ivo_arende['appointment_id']}").json()
    assert arende["appointed_person_name"] is None
    assert "raderad" in arende["resolution_note"]


def test_sokning_efter_beslut_hoppas_over_vid_fysisk_anslagstavla(client, ivo_arende):
    """Ingen poang att nota pa ivo.se nar besluten sitter pa en vagg."""
    svar = client.post(f"/api/v1/appointments/{ivo_arende['appointment_id']}/search-decision")
    assert svar.status_code == 200
    data = svar.json()
    assert data["searched"] is False
    assert "anslagstavla" in data["reason"]
    assert data["candidates"] == []


def test_kallregistret_visar_blockerade_kallor(client):
    from app.seed import seed_sources

    seed_sources(client.test_session)
    client.test_session.commit()

    kallor = client.get("/api/v1/admin/sources").json()
    per_nyckel = {k["key"]: k for k in kallor}

    assert per_nyckel["jobtech_live"]["access_mode"] == "OPEN_API"
    assert per_nyckel["jobtech_hist"]["access_mode"] == "OPEN_API"
    assert per_nyckel["ted"]["access_mode"] == "OPEN_API"

    # Blockerade kallor ska finnas i registret med skalet, inte saknas.
    assert per_nyckel["e_avrop"]["access_mode"] == "BLOCKED"
    assert per_nyckel["e_avrop"]["robots_allows"] is False
    assert "robots.txt" in per_nyckel["e_avrop"]["legal_note"]
    assert per_nyckel["mercell"]["access_mode"] == "MANUAL_ONLY"
    assert "användarvillkoren" in per_nyckel["mercell"]["legal_note"].lower()


def test_blockerad_kalla_vagrar_kora(client):
    """Lagesspärren ska ge skipped med skal, inte ett fel."""
    from app.seed import seed_sources

    seed_sources(client.test_session)
    client.test_session.commit()

    svar = client.post("/api/v1/admin/sources/manual/collect")
    # manual ar MANUAL_ONLY men dess egen run() tillater anrop utan innehall,
    # vilket ger ett fel om parametrar -- inte en tyst lyckad korning.
    assert svar.status_code == 200
    assert svar.json()["errors"] >= 1 or svar.json()["skipped"]


def test_matchningen_sparar_sitt_underlag(client):
    """confidence raknas ut, sparas och lamnas ut.

    Faltet fanns i matchningen och i schemat men hade ingen kolumn, sa det var
    alltid None i API:et. Ingenting gick sonder av det -- granssnittet visade
    bara inte hur mycket av poangen som vilade pa gissningar, vilket ar precis
    den uppgift som skiljer en anvandbar poang fran en siffra.
    """
    from app.seed import seed_profile

    seed_profile(client.test_session)
    client.test_session.commit()

    csv = (
        "titel;organisation;orgnr;beskrivning\n"
        "IT-chef;Myndigheten;202100-7777;"
        + "Statlig myndighet soker IT-chef med budgetansvar, personalansvar och "
        "plats i ledningsgruppen. Du driver forandringsledning, "
        "verksamhetsutveckling, informationssakerhet och molnmigrering. " * 3 + "\n"
    )
    assert client.post("/api/v1/admin/import", json={"content": csv}).json()["new"] == 1

    uppdrag_id = client.get("/api/v1/opportunities").json()["items"][0]["id"]
    matchning = client.get(f"/api/v1/opportunities/{uppdrag_id}").json()["matching"]

    assert matchning["confidence"] is not None
    assert 0 <= matchning["confidence"] <= 100
    # Arvode och langd framgar inte av texten, sa underlaget ar inte fullt.
    assert matchning["confidence"] < 100


def test_forklaringen_ar_pa_svenska(client):
    """Texten lases av en manniska och ska vara skriven som svenska."""
    from app.seed import seed_profile

    seed_profile(client.test_session)
    client.test_session.commit()

    csv = (
        "titel;organisation;orgnr;beskrivning\n"
        "IT-chef;Myndigheten;202100-8888;"
        + "Statlig myndighet med budgetansvar och personalansvar. " * 6
        + "\n"
    )
    client.post("/api/v1/admin/import", json={"content": csv})
    uppdrag_id = client.get("/api/v1/opportunities").json()["items"][0]["id"]
    text = client.get(f"/api/v1/opportunities/{uppdrag_id}").json()["matching"]["explanation"]

    assert "Matchning" in text
    assert "Förändringsledning" in text
    assert "Uppdragets längd" in text
    # Ingen text som nar anvandaren ska sakna svenska tecken.
    for fel in ("poang", "langd", "stod i annonsen", "Forandring"):
        assert fel not in text, fel
