"""Bakgrundskontrollfiltret.

Absolut krav i bestallningen: uppdrag som kraver bakgrundskontroll,
registerkontroll eller sakerhetsprovning ska exkluderas.

Den svara delen ar inte att hitta orden. Den svara delen ar att inte exkludera
allt som rakar innehalla "sakerhet". Nastan varje IT-chefsannons i offentlig
sektor namner informationssakerhet, sekretess och GDPR, och ingen av dem
innebar en personkontroll. Ett filter som fastnar pa dem tar bort alla traffar
och blir avstangt inom en vecka, vilket ar samma sak som inget filter.

Darfor tre utfall och tre regelgrupper:

  EXCLUDE    uttryckligt krav pa kontroll av personen
  AMBIGUOUS  formulering som kan betyda personkontroll -> manniska far avgora
  BENIGN     sakerhetsord som i sig inte innebar personkontroll

Ett BENIGN-trafferat ord exkluderar aldrig. En AMBIGUOUS-traff blir alltid
REVIEW_REQUIRED. Och en annons utan brukbar text blir REVIEW_REQUIRED, inte
PASS: bestallningen sager uttryckligen att ingen osaker annons far markeras som
PASS automatiskt, och "vi hittade ingen text att lasa" ar osakert.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from ..models.enums import ExclusionVerdict
from .text import excerpt


class RuleKind(str, Enum):
    EXCLUDE = "EXCLUDE"
    AMBIGUOUS = "AMBIGUOUS"
    BENIGN = "BENIGN"


@dataclass(frozen=True)
class Rule:
    rule_id: str
    kind: RuleKind
    pattern: re.Pattern[str]
    description: str
    # Nar satt kraver regeln att ett av dessa uttryck ocksa finns inom
    # near_window tecken. "sakerhetsklass" plus "personkontroll" ar en
    # personkontroll; "sakerhetsklassad information" ar det inte.
    requires_near: tuple[str, ...] = ()
    near_window: int = 160


def _p(s: str) -> re.Pattern[str]:
    return re.compile(s, re.IGNORECASE | re.UNICODE)


# --- Uttryckliga krav pa kontroll av personen ---------------------------------

EXCLUDE_RULES: tuple[Rule, ...] = (
    Rule(
        "SEC_CLEARANCE_EXPLICIT",
        RuleKind.EXCLUDE,
        _p(r"s[äa]kerhetspr[öo]vning(ar|en)?|s[äa]kerhetspr[öo]va[sd]?e?\b"),
        "Uttryckligt krav på säkerhetsprövning",
    ),
    Rule(
        "REGISTER_CHECK",
        RuleKind.EXCLUDE,
        _p(r"registerkontroll(er|en)?"),
        "Registerkontroll enligt säkerhetsskyddslagen",
    ),
    Rule(
        "BACKGROUND_CHECK",
        RuleKind.EXCLUDE,
        _p(r"bakgrundskontroll(er|en)?|bakgrundsunders[öo]kning(ar|en)?"),
        "Bakgrundskontroll eller bakgrundsundersökning",
    ),
    Rule(
        "SECURITY_INTERVIEW",
        RuleKind.EXCLUDE,
        _p(r"s[äa]kerhetsintervju(er|n)?"),
        "Sakerhetsintervju",
    ),
    Rule(
        "SAPO",
        RuleKind.EXCLUDE,
        _p(r"\bs[äa]po\b|s[äa]kerhetspolisen"),
        "Kontroll genom Säkerhetspolisen",
    ),
    Rule(
        "CRIMINAL_RECORD",
        RuleKind.EXCLUDE,
        _p(r"belastningsregistret|utdrag ur (polisens )?register|straffregisterutdrag"),
        "Utdrag ur belastningsregistret",
    ),
    Rule(
        # Sakerhetsklass i sig sager inget. Sakerhetsklass tillsammans med en
        # personkontroll gor det.
        "SECURITY_CLASS_WITH_VETTING",
        RuleKind.EXCLUDE,
        _p(r"s[äa]kerhetsklass(ad|ning|en|er|as)?"),
        "Placering i säkerhetsklass med personkontroll",
        requires_near=(
            r"personkontroll",
            r"s[äa]kerhetspr[öo]vning",
            r"registerkontroll",
            r"placera[sd]?e? i",
        ),
    ),
    Rule(
        "PERSONAL_VETTING",
        RuleKind.EXCLUDE,
        _p(r"personkontroll(er|en)?|personutredning(ar|en)?"),
        "Personkontroll eller personutredning",
    ),
    Rule(
        # Ett sakerhetsskyddsavtal som uttryckligen kraver provning av personalen.
        "PROTECTIVE_SECURITY_AGREEMENT_WITH_VETTING",
        RuleKind.EXCLUDE,
        _p(r"s[äa]kerhetsskyddsavtal"),
        "Säkerhetsskyddsavtal med krav på säkerhetsprövning",
        requires_near=(
            r"s[äa]kerhetspr[öo]v",
            r"registerkontroll",
            r"personkontroll",
            r"placera[sd]?e? i s[äa]kerhetsklass",
        ),
        near_window=260,
    ),
)

# --- Formuleringar som kraver en manniskas bedomning --------------------------

AMBIGUOUS_RULES: tuple[Rule, ...] = (
    Rule(
        # Utan narliggande provningskrav vet vi inte om konsulten sjalv berors.
        "PROTECTIVE_SECURITY_AGREEMENT_PLAIN",
        RuleKind.AMBIGUOUS,
        _p(r"s[äa]kerhetsskyddsavtal|s[äa]kerhetsskyddslag"),
        "Säkerhetsskyddsavtal nämns utan att prövningskravet framgår",
    ),
    Rule(
        "SECURITY_CLASS_PLAIN",
        RuleKind.AMBIGUOUS,
        _p(r"s[äa]kerhetsklass(ad|ning|en|er|as)?"),
        "Säkerhetsklass nämns utan att personkontroll framgår",
    ),
    Rule(
        "SECURITY_SENSITIVE_ACTIVITY",
        RuleKind.AMBIGUOUS,
        _p(r"s[äa]kerhetsk[äa]nslig verksamhet|totalf[öo]rsvar|skyddsv[äa]rd"),
        "Säkerhetskänslig verksamhet, kan medföra prövning",
    ),
    Rule(
        "VETTING_VERB_VAGUE",
        RuleKind.AMBIGUOUS,
        _p(r"(kontroll|pr[öo]vning) av (kandidat|konsult|personal|den som)"),
        "Oklar formulering om kontroll av person",
    ),
    Rule(
        "CLASSIFIED_INFORMATION",
        RuleKind.AMBIGUOUS,
        _p(r"hemliga uppgifter|kvalificerat hemlig|f[öo]rsvarssekretess"),
        "Hantering av hemliga uppgifter",
    ),
)

# --- Sakerhetsord som inte ar personkontroll ---------------------------------
#
# Dessa exkluderar aldrig nagot. De finns har for att dokumentera varfor, och
# for att kunna visa i granskningsvyn att filtret sag dem och lat dem passera.

BENIGN_RULES: tuple[Rule, ...] = (
    Rule("INFOSEC", RuleKind.BENIGN, _p(r"informations[säa]kerhet"), "Informationssakerhet"),
    Rule("IT_SECURITY", RuleKind.BENIGN, _p(r"it-?s[äa]kerhet|cybers[äa]kerhet"), "IT-sakerhet"),
    Rule("GDPR", RuleKind.BENIGN, _p(r"\bgdpr\b|dataskyddsf[öo]rordning"), "GDPR"),
    Rule(
        "CONFIDENTIALITY",
        RuleKind.BENIGN,
        _p(r"sekretessf[öo]rbindelse|tystnadsplikt|sekretess\b"),
        "Sekretess och tystnadsplikt",
    ),
    Rule(
        "SECURITY_REQUIREMENTS_GENERAL",
        RuleKind.BENIGN,
        _p(r"h[öo]gt st[äa]llda s[äa]kerhetskrav|s[äa]kerhetskrav\b|s[äa]kerhetsarbete"),
        "Allmänna säkerhetskrav på verksamheten",
    ),
    Rule(
        "NIS2", RuleKind.BENIGN, _p(r"\bnis2?\b|iso ?27001"), "Regelverk för informationssäkerhet"
    ),
    Rule(
        "PSYCH_TESTS",
        RuleKind.BENIGN,
        _p(r"arbetspsykologiska? test|personlighetstest"),
        "Arbetspsykologiska tester i urvalet",
    ),
    Rule(
        "REFERENCES",
        RuleKind.BENIGN,
        _p(r"referenstagning|referenser tas"),
        "Referenstagning",
    ),
)

# Negationer. "Ingen sakerhetsprovning kravs" ska inte exkludera.
#
# Mellanliggande ord tillats ("omfattas inte av registerkontroll"), men hogst 25
# tecken och aldrig over en satsgrans. Det ar medvetet snalt: en falsk negation
# later ett verkligt kontrollkrav passera, och det ar det dyra felet. Hellre att
# en krystad formulering exkluderas i onodan an att en sakerhetsprovning slinker
# igenom for att nagot "inte" stod tva satser tidigare.
_NEGATION = _p(
    r"(ingen|inte|utan|ej|inga)[^.!?\n]{0,25}?"
    r"(s[äa]kerhetspr[öo]vning|registerkontroll|bakgrundskontroll|personkontroll)"
)
# Och det omvanda: "sakerhetsprovning kravs inte".
_NEGATION_EFTER = _p(
    r"(s[äa]kerhetspr[öo]vning|registerkontroll|bakgrundskontroll|personkontroll)"
    r"[^.]{0,40}?(kr[äa]vs inte|beh[öo]vs inte|f[öo]rekommer inte|ej akt?uellt)"
)

# Villkorade formuleringar.
#
# Den har texten star ordagrant i en stor del av statens annonser:
#
#   "Innan ett beslut om anstallning fattas kan en sakerhetsprovning enligt
#    sakerhetsskyddslagen (2018:585) komma att genomforas. Om anstallningen
#    avser befattning i sakerhetsklass kommer sakerhetsprovningen aven att
#    innefatta en registerkontroll."
#
# Det ar inte ett krav pa den har tjansten. Det ar myndighetens standardtext om
# att provning *kan* bli aktuell. Behandlas den som ett uttryckligt krav
# forsvinner storre delen av statens chefsrekryteringar ur radarn -- och det ar
# precis vad som hande: en vikarierande enhetschef for IT-arkitektur och
# IT-sakerhet hos Statens fastighetsverk exkluderades pa den har texten, trots
# att tjansten var sokbar och gick till intervju.
#
# Bestallningen sager tva saker som bada pekar pa REVIEW_REQUIRED har:
# exkludera uppdrag som *kraver* kontroll, och lat ingen osaker annons bli PASS
# automatiskt. En villkorad formulering ar varken det ena eller det andra, sa
# den gar till manuell bedomning med citatet sparat.
#
# Monstren ar bundna till provningsordet och inte frislappta: ett ensamt "kan"
# hundra tecken bort far inte mjuka upp ett verkligt krav. Och "i vissa fall"
# raknas bara nar det star *fore* traffen, eftersom "registerkontroll kommer
# att genomforas. I vissa fall kravs svenskt medborgarskap" ar ett krav.
_PROVNINGSORD = r"(?:s[äa]kerhetspr[öo]vning|registerkontroll|bakgrundskontroll|personkontroll)"

_VILLKOR_FORE = _p(
    r"kan\s+komma\s+att"
    rf"|kan\s+(?:en|ett)?\s*{_PROVNINGSORD}"
    r"|kan\s+(?:bli|kr[äa]vas|f[öo]rekomma|genomf[öo]ras)"
    rf"|eventuell(?:t|a)?\s+{_PROVNINGSORD}"
    r"|i\s+vissa\s+fall"
    r"|f[öo]r\s+vissa\s+(?:tj[äa]nster|befattningar|roller|anst[äa]llningar)"
    r"|om\s+(?:anst[äa]llningen|tj[äa]nsten|befattningen)\s+"
    r"(?:avser|[äa]r|blir|placeras|innefattar)"
    r"|vid\s+behov"
)
_VILLKOR_EFTER = _p(
    r"kan\s+komma\s+att"
    r"|komma\s+att\s+(?:genomf[öo]ras|kr[äa]vas|bli|ske)"
    r"|kan\s+(?:bli\s+aktuell|kr[äa]vas|f[öo]rekomma|genomf[öo]ras)"
)
_SATSGRANS = re.compile(r"[.!?;\n]")
VILLKOR_FONSTER_FORE = 160
VILLKOR_FONSTER_EFTER = 160

MIN_TEXT_LENGTH = 200
ENGINE_VERSION = "excl-2"


@dataclass
class RuleHit:
    rule_id: str
    kind: RuleKind
    description: str
    quote: str
    offset: int
    # Sant nar traffen star i en villkorad formulering ("kan komma att").
    conditional: bool = False


@dataclass
class ExclusionAssessment:
    verdict: ExclusionVerdict
    rule_id: str | None
    matched_quote: str | None
    quote_offset: int | None
    reason: str
    hits: list[RuleHit] = field(default_factory=list)
    benign_hits: list[RuleHit] = field(default_factory=list)
    needs_ai: bool = False

    @property
    def is_excluded(self) -> bool:
        return self.verdict is ExclusionVerdict.EXCLUDED


def _near(text: str, pos: int, patterns: tuple[str, ...], window: int) -> bool:
    start = max(0, pos - window)
    omgivning = text[start : pos + window]
    return any(re.search(p, omgivning, re.IGNORECASE | re.UNICODE) for p in patterns)


def _negated(text: str, pos: int) -> bool:
    """Ar traffen negerad? Tittar i ett fonster runt traffen, inte i hela texten.

    Hela texten vore fel: en annons kan namna att nagon annan roll inte kraver
    provning och samtidigt krava det for den har.
    """
    start = max(0, pos - 80)
    omgivning = text[start : pos + 120]
    return bool(_NEGATION.search(omgivning) or _NEGATION_EFTER.search(omgivning))


def _villkorad(text: str, pos: int) -> bool:
    """Star traffen i en villkorad formulering?

    Fore och efter behandlas olika med flit. "I vissa fall" mjukar upp det som
    kommer efter, inte det som stod innan: "registerkontroll kommer att
    genomforas. I vissa fall kravs svenskt medborgarskap" ar ett krav, inget
    villkor.
    """
    fore = text[max(0, pos - VILLKOR_FONSTER_FORE) : pos]
    efter = text[pos : pos + VILLKOR_FONSTER_EFTER]
    # Villkoret maste sta i samma sats som traffen. Utan den gransen smittar ett
    # "kan komma att" i foregaende mening ner nasta mening, och texten "En
    # sakerhetsprovning kan komma att genomforas. Befattningen ar placerad i
    # sakerhetsklass och registerkontroll genomfors." hade blivit manuell
    # bedomning i stallet for exkluderad.
    fore = _SATSGRANS.split(fore)[-1]
    efter = _SATSGRANS.split(efter)[0]
    return bool(_VILLKOR_FORE.search(fore) or _VILLKOR_EFTER.search(efter))


def _scan(text: str, rules: tuple[Rule, ...]) -> list[RuleHit]:
    traffar: list[RuleHit] = []
    for regel in rules:
        for m in regel.pattern.finditer(text):
            if regel.requires_near and not _near(
                text, m.start(), regel.requires_near, regel.near_window
            ):
                continue
            if regel.kind is RuleKind.EXCLUDE and _negated(text, m.start()):
                continue
            traffar.append(
                RuleHit(
                    rule_id=regel.rule_id,
                    kind=regel.kind,
                    description=regel.description,
                    quote=excerpt(text, m.start()),
                    offset=m.start(),
                    conditional=(regel.kind is RuleKind.EXCLUDE and _villkorad(text, m.start())),
                )
            )
            break  # en traff per regel racker som bevis
    return traffar


def assess(text: str | None, *, title: str = "") -> ExclusionAssessment:
    """Bedom en annons eller ett upphandlingsunderlag.

    Returnerar alltid ett utfall med skal. Kastar inte undantag pa tom text --
    tom text ar ett giltigt och vanligt fall, och svaret pa det ar
    REVIEW_REQUIRED.
    """
    full = f"{title}\n{text or ''}".strip()

    if len(full) < MIN_TEXT_LENGTH:
        return ExclusionAssessment(
            verdict=ExclusionVerdict.REVIEW_REQUIRED,
            rule_id="INSUFFICIENT_TEXT",
            matched_quote=None,
            quote_offset=None,
            reason=(
                f"Underlaget är bara {len(full)} tecken, för kort för att bedöma "
                f"om det finns krav på bakgrundskontroll. Kräver manuell granskning."
            ),
            needs_ai=False,
        )

    exclude_hits = _scan(full, EXCLUDE_RULES)
    benign_hits = _scan(full, BENIGN_RULES)

    # En ovillkorad traff avgor. Finns bara villkorade blir det manuell
    # bedomning -- aldrig PASS, aldrig automatisk exkludering.
    ovillkorade = [h for h in exclude_hits if not h.conditional]
    if ovillkorade:
        forsta = ovillkorade[0]
        return ExclusionAssessment(
            verdict=ExclusionVerdict.EXCLUDED,
            rule_id=forsta.rule_id,
            matched_quote=forsta.quote,
            quote_offset=forsta.offset,
            reason=f"{forsta.description}. Regel {forsta.rule_id}.",
            hits=exclude_hits,
            benign_hits=benign_hits,
        )

    if exclude_hits:
        forsta = exclude_hits[0]
        return ExclusionAssessment(
            verdict=ExclusionVerdict.REVIEW_REQUIRED,
            rule_id=f"{forsta.rule_id}_CONDITIONAL",
            matched_quote=forsta.quote,
            quote_offset=forsta.offset,
            reason=(
                f"{forsta.description}, men formuleringen ar villkorad "
                f'("kan komma att", "i vissa fall" eller liknande). Det ar inte '
                f"ett uttryckligt krav pa den har tjansten och far darfor inte "
                f"exkluderas automatiskt. Kraver manuell bedomning. "
                f"Regel {forsta.rule_id}."
            ),
            hits=exclude_hits,
            benign_hits=benign_hits,
            needs_ai=True,
        )

    ambiguous_hits = _scan(full, AMBIGUOUS_RULES)
    if ambiguous_hits:
        forsta = ambiguous_hits[0]
        return ExclusionAssessment(
            verdict=ExclusionVerdict.REVIEW_REQUIRED,
            rule_id=forsta.rule_id,
            matched_quote=forsta.quote,
            quote_offset=forsta.offset,
            reason=(
                f"{forsta.description}. Går inte att avgöra ur texten om konsulten "
                f"själv måste genomgå kontroll. Regel {forsta.rule_id}."
            ),
            hits=ambiguous_hits,
            benign_hits=benign_hits,
            needs_ai=True,
        )

    sakerhetsord = ", ".join(sorted({h.description for h in benign_hits}))
    return ExclusionAssessment(
        verdict=ExclusionVerdict.PASS,
        rule_id=None,
        matched_quote=None,
        quote_offset=None,
        reason=(
            "Inget uttryckligt krav på bakgrunds- eller säkerhetskontroll hittat."
            + (
                f" Underlaget nämner {sakerhetsord}, vilket inte är personkontroll."
                if sakerhetsord
                else ""
            )
        ),
        benign_hits=benign_hits,
    )


def all_rules() -> list[Rule]:
    """For administrationsvyn: visa regelverket som det faktiskt ar."""
    return [*EXCLUDE_RULES, *AMBIGUOUS_RULES, *BENIGN_RULES]
