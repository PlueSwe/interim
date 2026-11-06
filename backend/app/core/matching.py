"""Matchningsmotor.

Ger 0-100 med delpoang per kriterium och en forklaring pa svenska.

Tva regler styr designen:

**AI far inte hitta pa kvalifikationer.** Motorn laser annonsen och profilen.
Nar annonsen inte sager nagot om arvode, langd eller ort gissar den inte -- den
markerar kriteriet som okant, ger halv poang och sager i forklaringen att
uppgiften saknas. Att tolka tystnad som uppfyllt krav ar precis det fel som gor
en matchningspoang vardelos.

**Forklaringen ar en del av svaret.** En poang pa 78 utan skal gar inte att
lita pa. Darfor returneras delpoang, vilka ord som trafade, och vilka kriterier
som vilar pa okand uppgift. confidence sager hur stor del av vikten som har
faktiskt stod i texten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..models.enums import EmploymentType, RoleFamily

ENGINE_VERSION = "match-1"

# Vikterna fran bestallningen. Summerar till 100. Ligger ocksa i
# consultant_profiles.weights sa att de kan andras utan kodandring; detta ar
# utgangsvardet.
DEFAULT_WEIGHTS: dict[str, int] = {
    "role": 25,
    "leadership": 20,
    "public_sector": 15,
    "it_competence": 15,
    "change_management": 10,
    "geography": 5,
    "duration": 5,
    "fee": 5,
}

# Nar ett kriterium saknar underlag i annonsen. Halv poang, inte full och inte
# noll: full vore en gissning till var fordel, noll vore ett straff for att
# annonsen ar kortfattad.
UNKNOWN_SCORE = 0.5


@dataclass
class CriterionResult:
    key: str
    label: str
    weight: int
    score: float  # 0.0-1.0
    evidence: list[str] = field(default_factory=list)
    unknown: bool = False

    @property
    def points(self) -> float:
        return self.score * self.weight


@dataclass
class MatchResult:
    score: int
    criteria: list[CriterionResult]
    explanation: str
    confidence: int  # andel av vikten som har stod i texten, 0-100

    @property
    def subscores(self) -> dict[str, dict]:
        return {
            c.key: {
                "label": c.label,
                "weight": c.weight,
                "score": round(c.score, 3),
                "points": round(c.points, 1),
                "unknown": c.unknown,
                "evidence": c.evidence[:6],
            }
            for c in self.criteria
        }


# --- Nyckelord per kriterium -------------------------------------------------
#
# Listorna ar korta med flit. Langa synonymlistor ger hog traffprocent pa allt
# och darmed ingen diskriminering mellan annonser.

ROLE_TERMS: dict[RoleFamily, tuple[str, ...]] = {
    RoleFamily.CIO: ("cio", "chief information officer"),
    RoleFamily.IT_DIRECTOR: ("it-direktor", "it direktor", "biträdande it-direktör"),
    RoleFamily.IT_MANAGER: ("it-chef", "it chef", "head of it", "chef it"),
    RoleFamily.DIGITALISATION_MANAGER: (
        "digitaliseringschef",
        "digitaliseringsdirektör",
        "chef digitalisering",
        "verksamhetsområdeschef digitalisering",
        "chef för digital utveckling",
        "chief digital officer",
        "cdo",
    ),
    RoleFamily.CTO: ("cto", "chief technology officer", "teknikchef"),
    RoleFamily.ARCHITECTURE_MANAGER: ("it-arkitektur", "chef arkitektur", "arkitekturchef"),
    RoleFamily.OPERATIONS_MANAGER: ("it-drift", "it operations", "driftchef"),
}

LEADERSHIP_TERMS = (
    "personalansvar",
    "budgetansvar",
    "verksamhetsansvar",
    "leda chefer",
    "underställda chefer",
    "ledningsgrupp",
    "chefsuppdrag",
    "chefserfarenhet",
    "leda och utveckla",
    "arbetsgivarrepresentant",
    "linjechef",
)

PUBLIC_SECTOR_TERMS = (
    "myndighet",
    "statlig",
    "kommun",
    "region",
    "offentlig verksamhet",
    "offentlig sektor",
    "förvaltning",
    "universitet",
    "högskola",
    "offentlighets- och sekretesslagen",
    "rättssäker",
    "lou",
)

IT_TERMS = (
    "it-arkitektur",
    "informationssäkerhet",
    "molnmigrering",
    "hybrid",
    "itil",
    "it service management",
    "dataförsörjning",
    "datadriven",
    "systemförvaltning",
    "pm3",
    "it-drift",
    "infrastruktur",
    "ai",
    "integration",
    "e-tjänster",
    "it-säkerhet",
)

CHANGE_TERMS = (
    "förändringsledning",
    "förändringsarbete",
    "verksamhetsutveckling",
    "transformation",
    "safe",
    "agil",
    "scrum",
    "förbättringsarbete",
    "omorganisation",
    "digitalisering av verksamheten",
    "nya arbetssätt",
)

# Interim eller tidsbegransat ar det profilen i forsta hand soker. En fast
# tjanst ar inte ointressant -- bestallningen vill ha bada -- men den far inte
# full poang pa langdkriteriet, eftersom "tillsvidare" inte ar ett uppdrag.
INTERIM_TERMS = ("interim", "tillförordnad", "tf ", "vikariat", "vikarierande", "konsultuppdrag")


def _find(text: str, terms: tuple[str, ...]) -> list[str]:
    """Vilka termer finns i texten. Ordgrans for korta termer.

    "ai" och "cdo" ar sa korta att de annars trafar inuti andra ord: "ai" i
    "arbetsmiljo" far inte rakna som AI-kompetens.
    """
    hittade = []
    for t in terms:
        if len(t.strip()) <= 4:
            if re.search(rf"\b{re.escape(t.strip())}\b", text, re.IGNORECASE):
                hittade.append(t.strip())
        elif t in text:
            hittade.append(t)
    return hittade


def _ratio(hits: int, full_at: int) -> float:
    """Andel, mattad vid full_at traffar.

    Mattningen finns for att den tionde traffen pa "digitalisering" inte gor
    annonsen mer relevant an den tredje.
    """
    return min(1.0, hits / full_at) if full_at else 0.0


def _score_role(
    text: str, role_family: RoleFamily, occupation_label: str | None
) -> CriterionResult:
    bevis: list[str] = []
    score = 0.0

    # Kallans egen yrkesklassificering vager tyngst nar den finns. JobTech satte
    # "Chief Digital Officer/CDO" pa IVO-annonsen trots att titeln bara sa
    # "Verksamhetsomradeschef" -- det ar battre information an var egen gissning
    # pa titelordet.
    if occupation_label:
        etikett = occupation_label.lower()
        if any(
            n in etikett
            for n in ("chief digital", "cdo", "cio", "it-chef", "it chef", "chief information")
        ):
            score = 1.0
            bevis.append(f"källans yrkesbegrepp: {occupation_label}")
        elif any(n in etikett for n in ("chef", "direktor", "manager", "head")):
            score = 0.6
            bevis.append(f"källans yrkesbegrepp: {occupation_label}")

    if role_family in ROLE_TERMS:
        traffar = _find(text, ROLE_TERMS[role_family])
        if traffar:
            score = max(score, 1.0)
            bevis.append(f"rolltitel: {', '.join(traffar[:3])}")
        else:
            score = max(score, 0.7)
            bevis.append(f"klassad som {role_family.value}")
    elif role_family is RoleFamily.OTHER_IT_LEADERSHIP:
        score = max(score, 0.5)
        bevis.append("IT-ledningsroll utan exakt titelmatchning")
    elif role_family is RoleFamily.NOT_RELEVANT and score == 0.0:
        bevis.append("ingen IT-ledningsroll identifierad")

    return CriterionResult("role", "Roll och ansvar", DEFAULT_WEIGHTS["role"], score, bevis)


def _keyword_criterion(
    key: str, label: str, text: str, terms: tuple[str, ...], full_at: int, weights: dict[str, int]
) -> CriterionResult:
    traffar = _find(text, terms)
    return CriterionResult(
        key,
        label,
        weights[key],
        _ratio(len(traffar), full_at),
        [", ".join(traffar[:6])] if traffar else [],
    )


def _score_geography(
    municipality: str | None, region: str | None, preferences: dict, weights: dict[str, int]
) -> CriterionResult:
    onskade = [s.lower() for s in preferences.get("preferred_locations", [])]
    accepterar_distans = bool(preferences.get("accepts_remote", True))

    if not municipality and not region:
        return CriterionResult(
            "geography",
            "Geografi",
            weights["geography"],
            UNKNOWN_SCORE,
            ["arbetsort saknas i annonsen"],
            unknown=True,
        )
    plats = f"{municipality or ''} {region or ''}".lower()
    if not onskade:
        return CriterionResult(
            "geography",
            "Geografi",
            weights["geography"],
            UNKNOWN_SCORE,
            [f"ingen önskad ort i profilen; annonsen gäller {municipality or region}"],
            unknown=True,
        )
    if any(o in plats for o in onskade):
        return CriterionResult(
            "geography",
            "Geografi",
            weights["geography"],
            1.0,
            [f"arbetsort {municipality or region} matchar profilens önskemål"],
        )
    return CriterionResult(
        "geography",
        "Geografi",
        weights["geography"],
        0.3 if accepterar_distans else 0.0,
        [f"arbetsort {municipality or region} utanför profilens önskemål"],
    )


def _score_duration(
    text: str,
    employment_type: EmploymentType,
    duration_months: int | None,
    preferences: dict,
    weights: dict[str, int],
) -> CriterionResult:
    min_m = preferences.get("min_duration_months", 3)
    max_m = preferences.get("max_duration_months", 24)

    if duration_months:
        inom = min_m <= duration_months <= max_m
        return CriterionResult(
            "duration",
            "Uppdragets längd",
            weights["duration"],
            1.0 if inom else 0.4,
            [
                f"{duration_months} manader"
                + ("" if inom else f", utanfor profilens {min_m}-{max_m} manader")
            ],
        )

    interim = _find(text, INTERIM_TERMS)
    if employment_type in (EmploymentType.INTERIM_CONSULTANT, EmploymentType.SUBSTITUTE) or interim:
        return CriterionResult(
            "duration",
            "Uppdragets längd",
            weights["duration"],
            0.8,
            [f"interimuppdrag ({', '.join(interim[:2])})" if interim else "interimuppdrag"],
        )
    if employment_type is EmploymentType.PERMANENT:
        # Fast tjanst ska synas i systemet, men den ar inte ett uppdrag med
        # langd. Halv poang, och skalet star i forklaringen.
        return CriterionResult(
            "duration",
            "Uppdragets längd",
            weights["duration"],
            0.5,
            ["tillsvidareanställning, inte ett tidsbegränsat uppdrag"],
        )
    return CriterionResult(
        "duration",
        "Uppdragets längd",
        weights["duration"],
        UNKNOWN_SCORE,
        ["längd framgår inte av annonsen"],
        unknown=True,
    )


def _score_fee(fee: int | None, preferences: dict, weights: dict[str, int]) -> CriterionResult:
    min_fee = preferences.get("min_fee_sek_per_hour")
    if fee is None:
        # Normalfallet. Myndighetsannonser anger nastan aldrig arvode.
        return CriterionResult(
            "fee",
            "Arvode",
            weights["fee"],
            UNKNOWN_SCORE,
            ["arvode anges inte"],
            unknown=True,
        )
    if min_fee is None:
        return CriterionResult(
            "fee",
            "Arvode",
            weights["fee"],
            UNKNOWN_SCORE,
            [f"{fee} kr/h, ingen niva angiven i profilen"],
            unknown=True,
        )
    if fee >= min_fee:
        return CriterionResult(
            "fee", "Arvode", weights["fee"], 1.0, [f"{fee} kr/h når profilens nivå"]
        )
    andel = max(0.0, fee / min_fee)
    return CriterionResult(
        "fee",
        "Arvode",
        weights["fee"],
        andel * 0.8,
        [f"{fee} kr/h under profilens {min_fee} kr/h"],
    )


def score_opportunity(
    *,
    title: str,
    description: str | None,
    role_family: RoleFamily,
    employment_type: EmploymentType,
    occupation_label: str | None = None,
    municipality: str | None = None,
    region: str | None = None,
    duration_months: int | None = None,
    fee_sek_per_hour: int | None = None,
    profile_weights: dict[str, int] | None = None,
    profile_preferences: dict | None = None,
) -> MatchResult:
    """Poangsatt ett uppdrag mot profilen.

    Tar emot falten direkt i stallet for ORM-objekt, sa att motorn gar att testa
    utan databas och kan koras pa ett utkast innan nagot sparas.
    """
    weights = {**DEFAULT_WEIGHTS, **(profile_weights or {})}
    prefs = profile_preferences or {}
    text = f"{title}\n{description or ''}".lower()

    kriterier = [
        _score_role(text, role_family, occupation_label),
        _keyword_criterion("leadership", "Ledarerfarenhet", text, LEADERSHIP_TERMS, 4, weights),
        _keyword_criterion(
            "public_sector", "Offentlig sektor", text, PUBLIC_SECTOR_TERMS, 3, weights
        ),
        _keyword_criterion("it_competence", "IT-kompetens", text, IT_TERMS, 4, weights),
        _keyword_criterion(
            "change_management", "Förändringsledning", text, CHANGE_TERMS, 3, weights
        ),
        _score_geography(municipality, region, prefs, weights),
        _score_duration(text, employment_type, duration_months, prefs, weights),
        _score_fee(fee_sek_per_hour, prefs, weights),
    ]

    total_vikt = sum(c.weight for c in kriterier) or 1
    poang = sum(c.points for c in kriterier)
    score = round(100 * poang / total_vikt)

    kand_vikt = sum(c.weight for c in kriterier if not c.unknown)
    confidence = round(100 * kand_vikt / total_vikt)

    return MatchResult(
        score=max(0, min(100, score)),
        criteria=kriterier,
        explanation=_explain(kriterier, score, confidence),
        confidence=confidence,
    )


def _explain(kriterier: list[CriterionResult], score: int, confidence: int) -> str:
    """Forklaring pa svenska, sorterad efter vad som bidrog mest."""
    rader = []
    for c in sorted(kriterier, key=lambda c: c.points, reverse=True):
        bevis = "; ".join(b for b in c.evidence if b) or "inget stöd i texten"
        markor = " (uppgift saknas)" if c.unknown else ""
        rader.append(f"- {c.label}: {c.points:.0f} av {c.weight} p{markor}. {bevis}")

    okanda = [c.label for c in kriterier if c.unknown]
    svans = ""
    if okanda:
        svans = (
            f"\n\n{confidence} % av vikten har stöd i annonsen. "
            f"Dessa kriterier vilar på okänd uppgift och har fått halv poäng: "
            f"{', '.join(okanda)}. Poängen är därför en nedre uppskattning, "
            f"inte ett påstående om att kraven är uppfyllda."
        )
    return f"Matchning {score} av 100.\n" + "\n".join(rader) + svans
