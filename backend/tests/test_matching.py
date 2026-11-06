"""Tester for matchningsmotorn."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.matching import DEFAULT_WEIGHTS, score_opportunity
from app.models.enums import EmploymentType, RoleFamily

SNAPSHOT = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "snapshots"
    / "ivo-vochef-digitalisering-it-2026-08-20.json"
)

PROFIL_PREFS = {
    "preferred_locations": ["Stockholm", "Solna", "Uppsala"],
    "accepts_remote": True,
    "min_duration_months": 3,
    "max_duration_months": 24,
    "min_fee_sek_per_hour": 1100,
}


def test_vikterna_summerar_till_hundra() -> None:
    """Bestallningens vikttabell. Om summan andras blir poangen inte 0-100."""
    assert sum(DEFAULT_WEIGHTS.values()) == 100


def test_irrelevant_annons_far_lag_poang() -> None:
    res = score_opportunity(
        title="Lokalvardare till Stockholms stad",
        description="Du stadar lokaler pa kvallstid. Inga forkunskaper kravs.",
        role_family=RoleFamily.NOT_RELEVANT,
        employment_type=EmploymentType.PERMANENT,
    )
    assert res.score < 35, res.explanation


def test_relevant_annons_far_hog_poang() -> None:
    res = score_opportunity(
        title="Interim IT-chef till myndighet",
        description=(
            "Vi soker en interim IT-chef med budgetansvar och personalansvar. "
            "Du ingar i ledningsgrupp, driver forandringsledning och "
            "verksamhetsutveckling. Erfarenhet av ITIL, PM3, informationssakerhet, "
            "molnmigrering och IT-arkitektur. Statlig myndighet, offentlig sektor, "
            "forvaltning. Uppdraget ar 12 manader."
        ),
        role_family=RoleFamily.IT_MANAGER,
        employment_type=EmploymentType.INTERIM_CONSULTANT,
        municipality="Stockholm",
        duration_months=12,
        fee_sek_per_hour=1200,
        profile_preferences=PROFIL_PREFS,
    )
    assert res.score >= 85, res.explanation
    assert res.confidence == 100


def test_okand_uppgift_ger_halv_poang_och_lagre_confidence() -> None:
    """Tystnad i annonsen far inte tolkas som uppfyllt krav."""
    res = score_opportunity(
        title="IT-chef",
        description="Du leder IT-avdelningen vid en myndighet. Budgetansvar ingar.",
        role_family=RoleFamily.IT_MANAGER,
        employment_type=EmploymentType.UNKNOWN,
        profile_preferences=PROFIL_PREFS,
    )
    okanda = {c.key for c in res.criteria if c.unknown}
    assert okanda == {"geography", "duration", "fee"}
    for c in res.criteria:
        if c.unknown:
            assert c.score == pytest.approx(0.5)
    assert res.confidence == 85  # 100 - 5 - 5 - 5
    assert "uppgift saknas" in res.explanation
    assert "nedre uppskattning" in res.explanation


def test_forklaringen_namner_varje_kriterium() -> None:
    res = score_opportunity(
        title="Digitaliseringschef",
        description="Du leder digitaliseringsarbetet vid en kommun med personalansvar.",
        role_family=RoleFamily.DIGITALISATION_MANAGER,
        employment_type=EmploymentType.PERMANENT,
        profile_preferences=PROFIL_PREFS,
    )
    for c in res.criteria:
        assert c.label in res.explanation
    assert res.subscores["role"]["weight"] == 25


def test_poangen_ligger_i_intervallet() -> None:
    for titel, roll in [
        ("", RoleFamily.NOT_RELEVANT),
        ("CIO" * 200, RoleFamily.CIO),
    ]:
        res = score_opportunity(
            title=titel,
            description=None,
            role_family=roll,
            employment_type=EmploymentType.UNKNOWN,
        )
        assert 0 <= res.score <= 100


def test_andrade_vikter_slar_igenom() -> None:
    """Vikterna ligger i profilen, inte i koden."""
    args = {
        "title": "IT-chef till myndighet",
        "description": "Budgetansvar, personalansvar, ledningsgrupp, chefsuppdrag.",
        "role_family": RoleFamily.IT_MANAGER,
        "employment_type": EmploymentType.PERMANENT,
    }
    bas = score_opportunity(**args)
    # Flytta all vikt till ledarerfarenhet, dar annonsen har starkt stod.
    tung = score_opportunity(
        **args,
        profile_weights={**{k: 0 for k in DEFAULT_WEIGHTS}, "leadership": 100},
    )
    assert tung.score > bas.score


def test_fast_tjanst_far_inte_full_langdpoang() -> None:
    res = score_opportunity(
        title="IT-chef",
        description="Tillsvidareanstallning vid myndighet.",
        role_family=RoleFamily.IT_MANAGER,
        employment_type=EmploymentType.PERMANENT,
    )
    langd = next(c for c in res.criteria if c.key == "duration")
    assert langd.score == pytest.approx(0.5)
    assert "tillsvidare" in langd.evidence[0]


def test_kort_term_trafar_inte_inuti_ord() -> None:
    """ "ai" far inte matcha i "arbetsmiljo" eller "detaljplan"."""
    res = score_opportunity(
        title="Handlaggare",
        description="Du arbetar med arbetsmiljo och detaljplaner.",
        role_family=RoleFamily.NOT_RELEVANT,
        employment_type=EmploymentType.PERMANENT,
    )
    it = next(c for c in res.criteria if c.key == "it_competence")
    assert it.score == 0.0, it.evidence


# --- Mot den verkliga IVO-annonsen -----------------------------------------


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="snapshot saknas")
def test_ivo_annonsen_matchar_hogt() -> None:
    """IVO:s verksamhetsomradeschef Digitalisering och IT ska ranka hogt.

    Annonsen ar en fast tjanst, vilket drar ner langdkriteriet, men i ovrigt
    traffar den profilen: IT- och digitaliseringsansvar, budget och personal,
    ledningsgrupp, statlig myndighet, Stockholm.
    """
    annons = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    res = score_opportunity(
        title=annons["headline"],
        description=annons["description"]["text"],
        role_family=RoleFamily.DIGITALISATION_MANAGER,
        employment_type=EmploymentType.PERMANENT,
        occupation_label=annons["occupation"]["label"],
        municipality=annons["workplace_address"]["municipality"],
        region=annons["workplace_address"]["region"],
        profile_preferences=PROFIL_PREFS,
    )
    assert res.score >= 75, res.explanation

    # Kallans yrkesbegrepp ska ha anvants. Titeln sager bara
    # "Verksamhetsomradeschef"; att det ar en CDO-roll vet vi fran JobTech.
    roll = next(c for c in res.criteria if c.key == "role")
    assert roll.score == 1.0
    assert any("Chief Digital Officer" in b for b in roll.evidence)

    # Arvode anges inte i myndighetsannonser. Det ska vara markerat okant,
    # inte antaget uppfyllt.
    arvode = next(c for c in res.criteria if c.key == "fee")
    assert arvode.unknown is True


# --------------------------------------------------------------------------
# Rollklassificering: ordet "chef" betyder tva olika saker
# --------------------------------------------------------------------------

KOKSTEXT = (
    "Vi soker dig som vill leda vart kok. Du ansvarar for inkop, schemalaggning "
    "och personal, och arbetar dagligen i vart kassasystem och vart digitala "
    "bokningssystem. Erfarenhet av att leda ett team ar ett krav."
)


@pytest.mark.parametrize(
    "titel",
    [
        "Forste Kock / sous-chef",
        "Junior Sous Chef",
        "Executive Chef - Facility Management",
        "Executive Head Chef",
        "Kokschef till personalrestaurang",
        "Restaurangchef",
    ],
)
def test_kokyrken_ar_inte_it_ledning(titel):
    """Pa engelska ar en chef en kock.

    Utan den har sparren rackte det med en brodtext som namnde kassasystem for
    att OTHER_LEADERSHIP skulle sla till, och i den verkliga insamlingen lag
    sex kokannonser i uppdragslistan som IT-ledning. Brodtexten nedan ar
    medvetet full av digitala ord, for det ar sa en kokannons faktiskt ser ut.
    """
    from app.core.classify import classify_role

    familj, skal, _ = classify_role(titel, KOKSTEXT)

    assert familj is RoleFamily.NOT_RELEVANT, f"{titel}: {skal}"
    assert "kokyrke" in skal


@pytest.mark.parametrize(
    ("titel", "vantad"),
    [
        ("IT-chef till myndigheten", RoleFamily.IT_MANAGER),
        ("CIO", RoleFamily.CIO),
        ("Interim IT-direktor", RoleFamily.IT_DIRECTOR),
        ("Digitaliseringschef", RoleFamily.DIGITALISATION_MANAGER),
    ],
)
def test_sparren_tar_inte_med_sig_riktiga_chefsroller(titel, vantad):
    """Kokfiltret far inte bli ett filter mot ordet chef."""
    from app.core.classify import classify_role

    familj, skal, _ = classify_role(titel, None)
    assert familj is vantad, f"{titel}: {familj} ({skal})"


# --- Sammansatta yrkestitlar --------------------------------------------------
#
# Samma sort fel som kockarna, men svarare att se: sparren NOT_LEADERSHIP hade
# en ordgrans framfor yrkesordet, och svenska satter ihop ord. "specialist" med
# \b framfor matchar inte "IT-sakerhetsspecialist", sa titeln raknades som
# otydlig, brodtextens IT-ord fick avgora, och en specialisttjanst hamnade i
# uppdragslistan som IT-ledning.

IT_BRODTEXT = (
    "Du arbetar med IT-arkitektur och IT-säkerhet i en stab som leds av "
    "IT-direktören. I rollen samarbetar du med verksamheten och IT-chefen om "
    "arkitekturstyrning, informationssäkerhet och digitalisering."
)


@pytest.mark.parametrize(
    "titel",
    [
        "Taktisk och operativ IT-säkerhetsspecialist",
        "Informationssäkerhetsspecialist",
        "Systemtekniker IT-drift",
        "Verksamhetsutvecklare digitalisering",
        "IAM-specialist",
    ],
)
def test_sammansatt_specialisttitel_ar_inte_ledning(titel: str) -> None:
    """Brödtextens IT-ord får inte göra en specialist till IT-chef."""
    from app.core.classify import classify_role

    familj, skal, _ = classify_role(titel, IT_BRODTEXT)

    assert familj is RoleFamily.NOT_RELEVANT, f"{titel} klassades som {familj.value}: {skal}"


@pytest.mark.parametrize(
    "titel,vantad",
    [
        ("Chef till enheten för IT-arkitektur och IT-säkerhet", RoleFamily.ARCHITECTURE_MANAGER),
        ("IT-chef", RoleFamily.IT_MANAGER),
        ("Verksamhetsområdeschef Digitalisering och IT", RoleFamily.DIGITALISATION_MANAGER),
        # Ordet "specialist" star har inuti ett annat ord och ar inte titeln.
        ("Chef för IT-specialistenheten", RoleFamily.IT_MANAGER),
    ],
)
def test_specialistsparren_tar_inte_med_sig_chefsroller(titel: str, vantad: RoleFamily) -> None:
    from app.core.classify import classify_role

    familj, skal, _ = classify_role(titel, IT_BRODTEXT)

    assert familj is vantad, f"{titel} blev {familj.value}: {skal}"
