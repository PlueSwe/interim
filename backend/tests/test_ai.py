"""AI-kontraktet.

Den har filen provar inte en modell. Den provar sparrarna runt modellen, och de
ar sparrar just for att en modell inte gar att prova. En testsvit som kor mot
ett riktigt API provar vad modellen svarade den dagen, inte vad systemet gor med
ett daligt svar.

Darfor en falsk leverantor som svarar exakt det vi vill undersoka: halucinerade
citat, omskrivna citat, okanda falt, trasigt JSON och ett utfall som vill mildra
en flagga. Det ar de fallen som avgor om bestallningens krav halls.
"""

from __future__ import annotations

from app.ai import classify
from app.ai.provider import (
    AIProvider,
    AIResponse,
    NullProvider,
    extract_json,
    get_provider,
)
from app.models import ExclusionVerdict

ANNONS = (
    "Myndigheten söker en IT-chef med budgetansvar och personalansvar. "
    "Du ingår i ledningsgruppen och driver förändringsledning tillsammans med "
    "verksamheten. Uppdraget omfattar informationssäkerhet och molnmigrering. "
    "Vi tillämpar sekretessförbindelse för samtliga anställda."
)


class Falsk(AIProvider):
    """En leverantor som svarar precis det testet behover."""

    name = "falsk"

    def __init__(self, data, *, available: bool = True, error: str | None = None) -> None:
        self._data = data
        self._available = available
        self._error = error
        self.anrop = 0

    @property
    def model(self) -> str | None:
        return "falsk-modell-1"

    @property
    def available(self) -> bool:
        return self._available

    def complete_json(self, system, user, *, max_tokens=None) -> AIResponse:
        self.anrop += 1
        return AIResponse(
            data=self._data,
            provider=self.name,
            model=self.model,
            available=self._available,
            error=self._error,
        )


# --------------------------------------------------------------------------
# Leverantorer
# --------------------------------------------------------------------------


def test_utan_konfiguration_finns_ingen_modell():
    """Standardlaget ska saga att AI saknas, inte svara tomt."""
    lev = NullProvider()
    svar = lev.complete_json("x", "y")

    assert lev.available is False
    assert svar.ok is False
    assert svar.data is None
    assert "Ingen AI-leverantör" in (svar.error or "")


def test_standardleverantoren_ar_null():
    assert get_provider(fresh=True).name == "none"


def test_json_ur_kodstaket():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Visst! Här kommer svaret:\n{"a": 2}') == {"a": 2}
    assert extract_json("inget alls") is None
    assert extract_json("[1, 2]") is None


# --------------------------------------------------------------------------
# Citatkravet
# --------------------------------------------------------------------------


def test_belagt_pastaende_behalls():
    behallna, kastade = classify.verify_claims(
        ANNONS,
        [
            {
                "field": "ledarerfarenhet",
                "value": "budget- och personalansvar",
                "quote": "IT-chef med budgetansvar och personalansvar",
            }
        ],
    )

    assert kastade == []
    assert len(behallna) == 1
    assert behallna[0].field == "ledarerfarenhet"
    assert behallna[0].offset > 0


def test_halucinerat_citat_kastas():
    """Det har ar hela poangen med kontraktet."""
    behallna, kastade = classify.verify_claims(
        ANNONS,
        [
            {
                "field": "arvode",
                "value": "1100 kr per timme",
                "quote": "Arvodet är 1100 kronor per timme enligt ramavtalet",
            }
        ],
    )

    assert behallna == []
    assert kastade[0]["reason"] == "citatet finns inte i annonstexten"


def test_omskrivet_citat_raknas_inte_som_citat():
    behallna, _ = classify.verify_claims(
        ANNONS,
        [
            {
                "field": "roll_och_ansvar",
                "value": "chef",
                # Ordfoljden ar andrad. Da ar det inte langre ett citat.
                "quote": "med personalansvar och budgetansvar IT-chef",
            }
        ],
    )
    assert behallna == []


def test_blanksteg_och_skiftlage_far_skilja():
    """En kalla som bytt radbrytning mot mellanslag ska inte underkannas."""
    behallna, _ = classify.verify_claims(
        ANNONS,
        [
            {
                "field": "it_kompetens",
                "value": "molnmigrering",
                "quote": "informationssäkerhet\n  och MOLNMIGRERING",
            }
        ],
    )
    assert len(behallna) == 1


def test_for_kort_citat_kastas():
    behallna, kastade = classify.verify_claims(
        ANNONS, [{"field": "roll_och_ansvar", "value": "chef", "quote": "IT-chef"}]
    )
    assert behallna == []
    assert "kortare än" in kastade[0]["reason"]


def test_okant_falt_kastas():
    behallna, kastade = classify.verify_claims(
        ANNONS,
        [
            {
                "field": "sakerhetsklassning_ok",
                "value": "ja",
                "quote": "Vi tillämpar sekretessförbindelse för samtliga anställda",
            }
        ],
    )
    assert behallna == []
    assert "okänt fält" in kastade[0]["reason"]


def test_skrap_i_stallet_for_lista_ger_inget():
    assert classify.verify_claims(ANNONS, None) == ([], [])
    assert classify.verify_claims(ANNONS, {"claims": []}) == ([], [])


# --------------------------------------------------------------------------
# extract_requirements
# --------------------------------------------------------------------------


def test_kravuttagning_behaller_det_belagda_och_kastar_resten():
    lev = Falsk(
        {
            "claims": [
                {
                    "field": "offentlig_sektor",
                    "value": "statlig myndighet",
                    "quote": "Myndigheten söker en IT-chef med budgetansvar",
                },
                {
                    "field": "arvode",
                    "value": "1200 kr/tim",
                    "quote": "Arvode enligt överenskommelse, cirka 1200 kr per timme",
                },
            ]
        }
    )
    res = classify.extract_requirements(ANNONS, title="IT-chef", provider=lev)

    assert res.usable
    assert [c.field for c in res.claims] == ["offentlig_sektor"]
    assert len(res.dropped) == 1
    assert "förkastade" in res.note()


def test_kort_text_kostar_inget_anrop():
    lev = Falsk({"claims": []})
    res = classify.extract_requirements("IT-chef", provider=lev)

    assert lev.anrop == 0
    assert res.claims == []


def test_trasigt_svar_blir_ett_dokumenterat_fel():
    lev = Falsk(None, error="Svaret gick inte att läsa som JSON.")
    res = classify.extract_requirements(ANNONS, provider=lev)

    assert res.usable is False
    assert res.claims == []
    assert "AI-fel" in res.note()


def test_saknad_leverantor_dokumenteras():
    res = classify.extract_requirements(ANNONS, provider=NullProvider())
    assert res.available is False
    assert "ej tillgänglig" in res.note()


# --------------------------------------------------------------------------
# Exkludering: AI far skarpa, aldrig mildra
# --------------------------------------------------------------------------


def test_ai_kan_inte_mildra_en_regelflagga():
    """En modell som sager "det ar nog lugnt" ska inte slacka en flagga."""
    lev = Falsk({"verdict": "PASS", "reason": "bara sekretessförbindelse"})
    res = classify.assess_exclusion(
        ANNONS, rule_verdict=ExclusionVerdict.REVIEW_REQUIRED, provider=lev
    )

    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED


def test_ai_kan_skarpa_fran_pass_till_granskning():
    lev = Falsk({"verdict": "REVIEW_REQUIRED", "reason": "oklar formulering"})
    res = classify.assess_exclusion(ANNONS, rule_verdict=ExclusionVerdict.PASS, provider=lev)

    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED


def test_exkludering_utan_citat_blir_granskning_inte_exkludering():
    """Att kasta bort ett uppdrag kraver ett belagg, inte en asikt."""
    lev = Falsk(
        {
            "verdict": "EXCLUDED",
            "quote": "Säkerhetsprövning med registerkontroll krävs",
            "reason": "säkerhetsprövning",
        }
    )
    res = classify.assess_exclusion(ANNONS, rule_verdict=ExclusionVerdict.PASS, provider=lev)

    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED
    assert res.dropped
    assert "citatet gick inte att hitta" in (res.reason or "")


def test_exkludering_med_citat_gar_igenom():
    text = ANNONS + " Säkerhetsprövning med registerkontroll krävs för tjänsten."
    lev = Falsk(
        {
            "verdict": "EXCLUDED",
            "quote": "Säkerhetsprövning med registerkontroll krävs för tjänsten",
            "reason": "säkerhetsprövning krävs",
        }
    )
    res = classify.assess_exclusion(text, rule_verdict=ExclusionVerdict.PASS, provider=lev)

    assert res.verdict is ExclusionVerdict.EXCLUDED
    assert res.claims[0].field == "personkontroll"


def test_obegripligt_utfall_blir_granskning():
    lev = Falsk({"verdict": "KANSKE", "reason": "vet inte"})
    res = classify.assess_exclusion(ANNONS, rule_verdict=ExclusionVerdict.PASS, provider=lev)

    assert res.verdict is ExclusionVerdict.REVIEW_REQUIRED


def test_kombinationen_valjer_alltid_det_strangare():
    V = ExclusionVerdict
    assert classify.combine_verdicts(V.PASS, V.EXCLUDED) is V.EXCLUDED
    assert classify.combine_verdicts(V.EXCLUDED, V.PASS) is V.EXCLUDED
    assert classify.combine_verdicts(V.REVIEW_REQUIRED, V.PASS) is V.REVIEW_REQUIRED
    assert classify.combine_verdicts(V.PASS, None) is V.PASS
    for regel in V:
        for ai in list(V) + [None]:
            kombinerat = classify.combine_verdicts(regel, ai)
            assert classify._STRANGHET[kombinerat] >= classify._STRANGHET[regel]
