"""Regelbaserad klassificering av annonser.

Avgor tre saker: ar rollen relevant, vilken rollfamilj ar det, och ar det en
fast tjanst eller ett uppdrag.

Regler forst och AI bara for resten. Skalet ar inte misstro mot AI utan att
regler ar granskningsbara: nar en annons hamnar i fel facka gar det att se
vilket ord som orsakade det och rata till regeln. En modell som svarar fel ger
ingen sadan trad att dra i.

AI anvands dar regler verkligen inte racker: annonser dar titeln inte sager
nagot ("Verksamhetsomradeschef") och texten maste lasas. Se ai/classify.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..models.enums import EmploymentType, RoleFamily

# Rollfamiljer i prioritetsordning. Forsta traffen vinner, sa mer specifika
# monster star forst: "digitaliseringschef" ska inte fastna pa "chef".
ROLE_PATTERNS: tuple[tuple[RoleFamily, str], ...] = (
    (RoleFamily.CIO, r"\bcio\b|chief information officer"),
    (RoleFamily.CTO, r"\bcto\b|chief technology officer|teknikchef"),
    (
        RoleFamily.DIGITALISATION_MANAGER,
        r"digitaliseringschef|digitaliseringsdirekt[öo]r|chief digital officer|\bcdo\b"
        # "Som chef for verksamhetsomrade digitalisering och IT" -- IVO:s annons.
        # Titeln sager bara "Verksamhetsomradeschef", sa rollen framgar forst av
        # brodtexten. Narhetskravet (hogst 35 tecken mellan "chef for" och
        # "digitalisering") ar det som skiljer rollbeskrivningen fran en
        # meriterande-punkt langre ner i samma annons: IVO:s parallella annons
        # for verksamhetsomrade registratur och arkiv namner ocksa
        # "digitaliserings- och it-utvecklingsarbete", men da som onskad
        # erfarenhet och utan "chef for" strax innan.
        r"|chef (f[öo]r|[öo]ver) [^.]{0,35}digitalisering"
        r"|verksamhetsomr[åa]de(schef)? (f[öo]r )?digitalisering"
        r"|chef (f[öo]r )?digital utveckling|digitaliseringsavdelning",
    ),
    (RoleFamily.IT_DIRECTOR, r"it-?direkt[öo]r|bitr[äa]dande it-?direkt[öo]r"),
    (
        RoleFamily.ARCHITECTURE_MANAGER,
        r"(chef|ledare)[^.]{0,30}(it-?)?arkitektur|arkitekturchef|chef it-?arkitektur",
    ),
    (
        RoleFamily.OPERATIONS_MANAGER,
        r"chef[^.]{0,20}it-?drift|it-?driftchef|it operations manager|chef infrastruktur",
    ),
    (
        RoleFamily.IT_MANAGER,
        r"it-?chef|head of it|chef (f[öo]r )?it\b|avdelningschef[^.]{0,20}it"
        r"|enhetschef[^.]{0,20}it|f[öo]rvaltningschef[^.]{0,30}it",
    ),
)

# Roller som ar IT-ledning men inte passar en familj ovan.
OTHER_LEADERSHIP = re.compile(
    r"(chef|direkt[öo]r|manager|head of|ledare)[^.]{0,40}"
    r"(it|digital|data|teknik|system|informations[säa]kerhet)",
    re.IGNORECASE,
)

# Yrken dar ordet "chef" betyder nagot helt annat. Pa engelska ar en chef en
# kock, och sa snart titeln innehaller "sous-chef" eller "Executive Chef" racker
# en brodtext som namner kassasystem for att OTHER_LEADERSHIP ska sla till.
# Utfallet i den verkliga insamlingen var att "Forste Kock / sous-chef" lag i
# uppdragslistan som IT-ledning. Listan provas pa titeln forst av allt, och en
# traff ar definitiv: ingen brodtext kan gora en kock till IT-chef.
WRONG_KIND_OF_CHEF = re.compile(
    r"\b(kock|sous[- ]?chef|souschef|k[öo]ksm[äa]stare|k[öo]kschef|restaurangchef"
    r"|executive chef|head chef|chef de (partie|cuisine|rang)|bagare|konditor"
    r"|servitris|servit[öo]r|barchef|hovm[äa]stare)\b",
    re.IGNORECASE,
)

# Utesluter roller som innehaller IT-ord men inte ar ledningsroller. Utan dessa
# klassas varje "IT-tekniker" som IT-ledning via OTHER_LEADERSHIP.
#
# Ordgränsen sitter bara i slutet, med flit. Svenska sätter ihop ord:
# "IT-säkerhetsspecialist" och "systemtekniker" är yrkesorden med ett förled,
# och ett `\b` framför "specialist" kräver att ordet står för sig självt. Därför
# slank *Taktisk och operativ IT-säkerhetsspecialist* förbi spärren, och
# brödtextens IT-ord gjorde den till IT-ledning. Slutgränsen behålls däremot:
# "specialistenhet" och "teknikerutbildning" är inte titlar på en sökande.
NOT_LEADERSHIP = re.compile(
    r"(utvecklare|tekniker|systemadministrat[öo]r|konsultm[äa]klare"
    r"|testare|specialist|handl[äa]ggare|assistent|praktikant|student"
    r"|projektledare|produkt[äa]gare|scrum master|designer|analytiker)\b",
    re.IGNORECASE,
)

INTERIM_PATTERNS = re.compile(
    r"\binterim\b|tillf[öo]rordnad|\btf\b|\bt\.?f\.?\s|konsultuppdrag|uppdrag som konsult"
    r"|via konsultbolag|underkonsult",
    re.IGNORECASE,
)
SUBSTITUTE_PATTERNS = re.compile(r"vikariat|vikarierande|f[öo]r[äa]ldraledighet", re.IGNORECASE)
PERMANENT_PATTERNS = re.compile(
    r"tillsvidareanst[äa]llning|tillsvidare\b|fast anst[äa]llning|provanst[äa]llning",
    re.IGNORECASE,
)
FIXED_TERM_PATTERNS = re.compile(
    r"tidsbegr[äa]nsad anst[äa]llning|visstidsanst[äa]llning|f[öo]rordnande"
    r"|anst[äa]llning p[åa] \d+ [åa]r",
    re.IGNORECASE,
)

# Uppdragslangd: "6 manader", "12-18 manader", "ca 9 man".
DURATION = re.compile(
    r"(\d{1,2})\s*(?:-|till|–)\s*(\d{1,2})\s*m[åa]n|(\d{1,2})\s*m[åa]n(?:ader)?\b",
    re.IGNORECASE,
)
# Arvode: "1 150 kr/h", "1150 kr per timme", "timpris 1200".
FEE = re.compile(
    r"(\d[\d\s]{2,6})\s*(?:kr|sek)\s*(?:/|per\s*)(?:h|tim(?:me|mar)?)"
    r"|tim(?:pris|arvode|taxa)[^\d]{0,12}(\d[\d\s]{2,6})",
    re.IGNORECASE,
)


@dataclass
class Classification:
    role_family: RoleFamily
    employment_type: EmploymentType
    duration_months: int | None
    fee_sek_per_hour: int | None
    reason: str
    # Satt nar reglerna inte gav ett tryggt svar. Anroparen kan da fraga AI, och
    # om AI saknas blir posten REVIEW_REQUIRED i granskningslistan.
    uncertain: bool = False

    @property
    def is_relevant(self) -> bool:
        return self.role_family is not RoleFamily.NOT_RELEVANT


def classify_role(title: str, description: str | None = None) -> tuple[RoleFamily, str, bool]:
    """Rollfamilj ur titel och, vid behov, text.

    Titeln vager tyngst. En annons som namner "IT-chef" i brodtexten handlar
    ofta om vem man rapporterar till, inte om tjansten.
    """
    titel = title or ""
    text = f"{titel}\n{description or ''}"

    if WRONG_KIND_OF_CHEF.search(titel):
        return (
            RoleFamily.NOT_RELEVANT,
            f"titeln ar ett kokyrke, inte en ledningsroll: {titel[:60]}",
            False,
        )

    for familj, monster in ROLE_PATTERNS:
        if re.search(monster, titel, re.IGNORECASE):
            return familj, f"titeln matchar {familj.value}", False

    if NOT_LEADERSHIP.search(titel):
        return RoleFamily.NOT_RELEVANT, f"titeln ar en icke-ledningsroll: {titel[:60]}", False

    # Titeln sade inget. IVO:s "Verksamhetsomradeschef" ar typfallet: utan
    # brodtexten gar det inte att veta om det handlar om digitalisering eller
    # arkiv. Da laser vi texten, men markerar svaret som osakert.
    for familj, monster in ROLE_PATTERNS:
        if re.search(monster, text, re.IGNORECASE):
            return familj, f"brodtexten matchar {familj.value} (titeln var otydlig)", True

    if OTHER_LEADERSHIP.search(titel):
        return RoleFamily.OTHER_IT_LEADERSHIP, "titeln ar en IT-nara ledningsroll", True
    if re.search(r"\bchef|direkt[öo]r|head of\b", titel, re.IGNORECASE) and OTHER_LEADERSHIP.search(
        text
    ):
        return RoleFamily.OTHER_IT_LEADERSHIP, "chefsroll med IT-innehall i texten", True

    return RoleFamily.NOT_RELEVANT, "ingen IT-ledningsroll hittad i titel eller text", False


def classify_employment(title: str, description: str | None = None) -> tuple[EmploymentType, str]:
    text = f"{title or ''}\n{description or ''}"

    # Interim forst: en annons kan namna bade "tillsvidare" (om myndigheten) och
    # "interim" (om uppdraget), och da ar det uppdraget som galler.
    if INTERIM_PATTERNS.search(text):
        return EmploymentType.INTERIM_CONSULTANT, "texten anger interim- eller konsultuppdrag"
    if SUBSTITUTE_PATTERNS.search(text):
        return EmploymentType.SUBSTITUTE, "texten anger vikariat"
    if PERMANENT_PATTERNS.search(text):
        return EmploymentType.PERMANENT, "texten anger tillsvidareanstallning"
    if FIXED_TERM_PATTERNS.search(text):
        return EmploymentType.FIXED_TERM, "texten anger tidsbegransad anstallning"
    return EmploymentType.UNKNOWN, "anstallningsform framgar inte"


def extract_duration_months(text: str) -> int | None:
    m = DURATION.search(text or "")
    if not m:
        return None
    if m.group(1) and m.group(2):
        # Intervall: ta den undre granden, eftersom det ar det som ar utlovat.
        return int(m.group(1))
    if m.group(3):
        manader = int(m.group(3))
        # "6 man" ar en langd; "800 man" ar ett fel. Och "12 manader" i frasen
        # "de senaste 12 manaderna" ar inte en uppdragslangd, men det kravs AI
        # for att se skillnaden, sa har slapper vi igenom den.
        return manader if 1 <= manader <= 60 else None
    return None


def extract_fee(text: str) -> int | None:
    m = FEE.search(text or "")
    if not m:
        return None
    rått = m.group(1) or m.group(2)
    if not rått:
        return None
    try:
        belopp = int(re.sub(r"\s", "", rått))
    except ValueError:
        return None
    # Rimlighetsspann for ett timarvode i kronor. Utanfor det ar traffen
    # sannolikt nagot annat, till exempel ett arsbelopp.
    return belopp if 300 <= belopp <= 5000 else None


def classify(title: str, description: str | None = None) -> Classification:
    roll, roll_skal, osaker = classify_role(title, description)
    anst, anst_skal = classify_employment(title, description)
    text = f"{title or ''}\n{description or ''}"

    return Classification(
        role_family=roll,
        employment_type=anst,
        duration_months=extract_duration_months(text),
        fee_sek_per_hour=extract_fee(text),
        reason=f"{roll_skal}; {anst_skal}",
        uncertain=osaker,
    )
