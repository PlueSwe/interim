"""Tester for bakgrundskontrollfiltret.

Det viktigaste testet ar inte att filtret hittar "sakerhetsprovning". Det ar att
det INTE exkluderar en vanlig IT-chefsannons som namner informationssakerhet.
Ett filter som tar bort alla traffar blir avstangt, och ett avstangt filter
uppfyller inget krav.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.exclusion import ExclusionVerdict, assess

SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "snapshots"
    / "ivo-vochef-digitalisering-it-2026-08-20.json"
)


def _lang(text: str) -> str:
    """Fyller ut till over MIN_TEXT_LENGTH sa att testet provar regeln och inte
    langdkontrollen."""
    fyll = (
        " Vi soker en erfaren ledare till en myndighet i Stockholm. Rollen innebar "
        "budget- och personalansvar samt ansvar for verksamhetsutveckling och "
        "leverantorsstyrning i en organisation med manga intressenter. "
    )
    return (text + fyll * 3)[:4000]


# --- Ska exkluderas ---------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "vantad_regel"),
    [
        ("Sakerhetsprovning kommer att genomforas infor anstallning.", "SEC_CLEARANCE_EXPLICIT"),
        ("Tjansten kraver sakerhetsprovning med registerkontroll.", "SEC_CLEARANCE_EXPLICIT"),
        ("Registerkontroll genomfors enligt sakerhetsskyddslagen.", "REGISTER_CHECK"),
        ("Vi gor bakgrundskontroll pa slutkandidater.", "BACKGROUND_CHECK"),
        ("En bakgrundsundersokning ingar i processen.", "BACKGROUND_CHECK"),
        ("Sakerhetsintervju halls med den som erbjuds tjansten.", "SECURITY_INTERVIEW"),
        ("Kontroll sker av Sakerhetspolisen.", "SAPO"),
        ("Utdrag ur belastningsregistret ska uppvisas.", "CRIMINAL_RECORD"),
        ("Konsulten ska genomga personkontroll.", "PERSONAL_VETTING"),
        (
            "Befattningen ar placerad i sakerhetsklass 2 och personkontroll genomfors.",
            "SECURITY_CLASS_WITH_VETTING",
        ),
        (
            "Sakerhetsskyddsavtal tecknas och konsulten ska sakerhetsprovas.",
            "SEC_CLEARANCE_EXPLICIT",
        ),
    ],
)
def test_exkluderar_uttryckliga_krav(text: str, vantad_regel: str) -> None:
    res = assess(_lang(text))
    assert res.verdict is ExclusionVerdict.EXCLUDED, res.reason
    assert res.rule_id == vantad_regel
    # Bestallningen kraver att den exakta formuleringen sparas, och databasen har
    # ett check-villkor som vagrar EXCLUDED utan citat.
    assert res.matched_quote
    assert res.quote_offset is not None


def test_citat_innehaller_traffen() -> None:
    res = assess(_lang("Infor anstallning genomfors sakerhetsprovning med registerkontroll."))
    assert "sakerhetsprovning" in res.matched_quote.lower()


def test_citat_ar_begransat() -> None:
    """SECURITY.md satter 500 tecken som tak pa citatet."""
    res = assess("x" * 3000 + " sakerhetsprovning kravs " + "y" * 3000)
    assert res.verdict is ExclusionVerdict.EXCLUDED
    assert len(res.matched_quote) <= 510  # 2x250 plus ellipser


# --- Ska INTE exkluderas ----------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Du ansvarar for myndighetens informationssakerhet och arbetet med NIS2.",
        "Erfarenhet av IT-sakerhet och cybersakerhet ar meriterande.",
        "Du leder arbetet med GDPR och dataskyddsforordningen.",
        "Sekretessforbindelse undertecknas vid anstallning.",
        "Du omfattas av tystnadsplikt i tjansten.",
        "Verksamheten bedrivs utifran hogt stallda sakerhetskrav.",
        "I rekryteringen anvands arbetspsykologiska tester som en del av urvalet.",
        "Referenstagning sker i slutskedet av processen.",
        "Du ansvarar for systematiskt sakerhetsarbete och ISO 27001.",
    ],
)
def test_vanliga_sakerhetsord_exkluderar_inte(text: str) -> None:
    res = assess(_lang(text))
    assert res.verdict is ExclusionVerdict.PASS, f"{res.verdict}: {res.reason}"


def test_negation_exkluderar_inte() -> None:
    for text in (
        "Ingen sakerhetsprovning kravs for denna tjanst.",
        "Tjansten omfattas inte av registerkontroll.",
        "Uppdraget kan utforas utan sakerhetsprovning.",
        "Sakerhetsprovning kravs inte for rollen.",
    ):
        res = assess(_lang(text))
        assert res.verdict is not ExclusionVerdict.EXCLUDED, f"{text!r} -> {res.reason}"


# --- Ska krava granskning ---------------------------------------------------


@pytest.mark.parametrize(
    ("text", "vantad_regel"),
    [
        ("Sakerhetsskyddsavtal tecknas med leverantoren.", "PROTECTIVE_SECURITY_AGREEMENT_PLAIN"),
        ("Myndigheten bedriver sakerhetskanslig verksamhet.", "SECURITY_SENSITIVE_ACTIVITY"),
        ("Delar av systemet ar sakerhetsklassade.", "SECURITY_CLASS_PLAIN"),
        ("Kontroll av kandidater sker enligt myndighetens rutiner.", "VETTING_VERB_VAGUE"),
    ],
)
def test_oklara_formuleringar_kraver_granskning(text: str, vantad_regel: str) -> None:
    res = assess(_lang(text))
    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED, res.reason
    assert res.rule_id == vantad_regel
    assert res.needs_ai is True


def test_kort_text_blir_granskning_inte_pass() -> None:
    """Bestallningen: ingen osaker annons far automatiskt bli PASS.

    En annons utan brukbar beskrivning ar osaker. Det vanliga felet ar att lata
    tom text falla igenom som godkand.
    """
    res = assess("IT-chef sokes.")
    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED
    assert res.rule_id == "INSUFFICIENT_TEXT"

    res_tom = assess(None)
    assert res_tom.verdict is ExclusionVerdict.REVIEW_REQUIRED


def test_exkludering_slar_fore_granskning() -> None:
    """Bade ett uttryckligt och ett oklart krav i samma text -> EXCLUDED."""
    res = assess(
        _lang(
            "Myndigheten bedriver sakerhetskanslig verksamhet och sakerhetsprovning "
            "genomfors infor anstallning."
        )
    )
    assert res.verdict is ExclusionVerdict.EXCLUDED


# --- Mot den verkliga IVO-annonsen -----------------------------------------


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="snapshot saknas")
def test_ivo_annonsen_passerar() -> None:
    """IVO:s verksamhetsomradeschef Digitalisering och IT ska bli PASS.

    Annonsen sager "hogt stallda sakerhetskrav" och handlar om IT-sakerhet och
    dataforsorjning. Ett naivt filter pa ordet "sakerhet" exkluderar den, och da
    missar systemet precis den sorts tjanst det ar byggt for att hitta.

    Detta ar ett test mot verklig data, hamtad fran JobTechs historiska API.
    """
    annons = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    text = annons["description"]["text"]
    res = assess(text, title=annons["headline"])

    assert res.verdict is ExclusionVerdict.PASS, f"{res.rule_id}: {res.reason}"
    # Och filtret ska ha sett sakerhetsorden, inte bara missat dem.
    assert res.benign_hits, "filtret borde noterat sakerhetsord utan att exkludera"
    beskrivningar = {h.description for h in res.benign_hits}
    assert any("säkerhet" in d.lower() for d in beskrivningar), beskrivningar
