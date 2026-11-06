"""Kontraktet for hur ett modellsvar far anvandas.

Bestallningen ar entydig: AI far inte hitta pa kvalifikationer eller anta att
krav ar uppfyllda, och ingen osaker annons far automatiskt bli PASS. Det ar
inte nagot man loser med en val formulerad prompt -- en prompt ar en onskan,
inte en garanti. Darfor halls modellen i schack efterat i stallet:

1. Varje pastaende maste ha ett ordagrant citat ur annonsen.
2. Citatet verifieras mot kalltexten. Hittas det inte kastas pastaendet.
3. Ett citat som ar kortare an MIN_QUOTE_CHARS raknas inte. Utan den gransen
   kan en modell "citera" ordet "chef" och fa ratt varje gang.
4. En AI-bedomning kan bara skarpa regelmotorns utfall, aldrig mildra det.

Resultatet ar att en halucination blir synlig i stallet for trovardig. Det som
kastas sparas i dropped sa att det gar att se vad modellen forsokte pasta.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..models import ExclusionVerdict
from .provider import AIProvider, get_provider

# Kortare citat an det har ar inte ett citat utan ett ord.
MIN_QUOTE_CHARS = 16

# Falt vi over huvud taget tar emot. Ett okant falt kastas; det gor kontraktet
# till en vitlista i stallet for en svartlista.
TILLATNA_FALT = (
    "roll_och_ansvar",
    "ledarerfarenhet",
    "offentlig_sektor",
    "it_kompetens",
    "forandringsledning",
    "geografi",
    "uppdragets_langd",
    "arvode",
    "personkontroll",
)

SYSTEM_KRAV = """Du laser en svensk jobbannons och plockar ut vad den faktiskt kraver.

Regler du maste folja:
- Svara enbart med JSON.
- Varje pastaende ska ha ett ordagrant citat ur annonsen, kopierat tecken for tecken.
- Citatet ska vara minst en hel mening eller satsdel, inte ett enstaka ord.
- Star nagot inte i texten ska du utesluta det. Gissa aldrig och fyll aldrig ut.
- Ar du osaker ska du lamna faltet utanfor svaret.

Format:
{"claims": [{"field": "<falt>", "value": "<kort sammanfattning>", "quote": "<ordagrant citat>"}]}

Tillatna varden for field: roll_och_ansvar, ledarerfarenhet, offentlig_sektor,
it_kompetens, forandringsledning, geografi, uppdragets_langd, arvode, personkontroll.
"""

SYSTEM_EXKLUDERING = """Du avgor om en svensk jobbannons kraver personkontroll av den sokande.

Med personkontroll menas bakgrundskontroll, bakgrundsundersokning, registerkontroll,
sakerhetsprovning, sakerhetsintervju, sakerhetsklassning med personkontroll,
Sapo-kontroll eller likvardig kontroll av personen.

Detta ar INTE personkontroll: krav pa GDPR-efterlevnad, sekretessforbindelse,
tystnadsplikt, allmant informationssakerhetsarbete, eller att den som anstalls
ska arbeta med sakerhetsfragor.

Regler:
- Svara enbart med JSON.
- Citatet ska vara ordagrant ur annonsen.
- Finns inget stod i texten ska verdict vara "PASS" och quote utelamnas.
- Ar du osaker ska verdict vara "REVIEW_REQUIRED". Valj aldrig PASS for att vara hjalpsam.

Format:
{"verdict": "PASS" | "REVIEW_REQUIRED" | "EXCLUDED",
 "quote": "<ordagrant citat>",
 "reason": "<kort skal pa svenska>"}
"""


@dataclass(frozen=True)
class Claim:
    """Ett pastaende med sitt stod i kalltexten."""

    field: str
    value: str
    quote: str
    offset: int


@dataclass
class AIResult:
    """Utfallet, med allt som behovs for att dokumentera det."""

    available: bool
    provider: str
    model: str | None
    claims: list[Claim] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    verdict: ExclusionVerdict | None = None
    reason: str | None = None
    error: str | None = None

    @property
    def usable(self) -> bool:
        return self.available and self.error is None

    def note(self) -> str:
        """En rad att spara i en logg eller visa for en manniska."""
        if not self.available:
            return f"AI ej tillgänglig ({self.provider}): {self.error or 'ingen leverantör'}"
        if self.error:
            return f"AI-fel ({self.provider}/{self.model}): {self.error}"
        kastade = f", {len(self.dropped)} påstående(n) utan stöd förkastade" if self.dropped else ""
        return f"AI {self.provider}/{self.model}: {len(self.claims)} belagda påstående(n){kastade}"


def _normalisera(text: str) -> str:
    """Gor text jamforbar utan att tappa ordfoljden."""
    return re.sub(r"\s+", " ", text).casefold().strip()


def verify_claims(text: str | None, raw_claims: Any) -> tuple[list[Claim], list[dict[str, Any]]]:
    """Behall de pastaenden som gar att hitta i texten. Returnera (behallna, kastade).

    Verifieringen ar avsiktligt enkel: citatet ska finnas i kalltexten nar bada
    normaliserats pa blanksteg och skiftlage. En modell som skriver om ett citat
    aldrig sa lite blir underkand, och det ar ratt -- ett omskrivet citat ar
    inte langre ett citat.
    """
    behallna: list[Claim] = []
    kastade: list[dict[str, Any]] = []

    if not isinstance(raw_claims, list):
        return behallna, kastade

    kalla = _normalisera(text or "")

    for post in raw_claims:
        if not isinstance(post, dict):
            kastade.append({"claim": post, "reason": "inte ett objekt"})
            continue

        falt = str(post.get("field") or "").strip()
        varde = str(post.get("value") or "").strip()
        citat = str(post.get("quote") or "").strip()

        if falt not in TILLATNA_FALT:
            kastade.append({"claim": post, "reason": f"okänt fält {falt!r}"})
            continue
        if not varde:
            kastade.append({"claim": post, "reason": "tomt värde"})
            continue
        if len(citat) < MIN_QUOTE_CHARS:
            kastade.append(
                {"claim": post, "reason": f"citatet är kortare än {MIN_QUOTE_CHARS} tecken"}
            )
            continue

        plats = kalla.find(_normalisera(citat))
        if plats < 0:
            kastade.append({"claim": post, "reason": "citatet finns inte i annonstexten"})
            continue

        behallna.append(Claim(field=falt, value=varde, quote=citat, offset=plats))

    return behallna, kastade


def extract_requirements(
    text: str | None,
    *,
    title: str = "",
    provider: AIProvider | None = None,
) -> AIResult:
    """Fraga modellen vad annonsen kraver. Returnerar bara belagda pastaenden."""
    lev = provider or get_provider()

    if not text or len(text.strip()) < 40:
        # For kort text ar inte vart ett anrop, och ett svar pa den skulle anda
        # bli gissningar.
        return AIResult(
            available=lev.available,
            provider=lev.name,
            model=lev.model,
            error="Annonstexten är för kort för en bedömning." if lev.available else None,
        )

    svar = lev.complete_json(SYSTEM_KRAV, f"Rubrik: {title}\n\nAnnonstext:\n{text}")
    if not svar.ok:
        return AIResult(
            available=svar.available,
            provider=svar.provider,
            model=svar.model,
            error=svar.error,
        )

    behallna, kastade = verify_claims(text, (svar.data or {}).get("claims"))
    return AIResult(
        available=True,
        provider=svar.provider,
        model=svar.model,
        claims=behallna,
        dropped=kastade,
    )


def assess_exclusion(
    text: str | None,
    *,
    rule_verdict: ExclusionVerdict,
    provider: AIProvider | None = None,
) -> AIResult:
    """Andra bedomning av personkontrollfragan.

    Anvands nar regelmotorn satt needs_ai. Utfallet kombineras med regelns, och
    kombinationen kan bara ga mot det strangare -- se combine_verdicts.
    """
    lev = provider or get_provider()

    if not text or not text.strip():
        return AIResult(
            available=lev.available,
            provider=lev.name,
            model=lev.model,
            verdict=None,
            error="Ingen text att bedöma." if lev.available else None,
        )

    svar = lev.complete_json(SYSTEM_EXKLUDERING, f"Annonstext:\n{text}")
    if not svar.ok:
        return AIResult(
            available=svar.available,
            provider=svar.provider,
            model=svar.model,
            error=svar.error,
        )

    data = svar.data or {}
    ratt = str(data.get("verdict") or "").strip().upper()
    try:
        ai_utfall = ExclusionVerdict(ratt)
    except ValueError:
        # Ett obegripligt utfall far inte tolkas som PASS. Da ar granskning
        # ratt svar, for da vet vi inte.
        return AIResult(
            available=True,
            provider=svar.provider,
            model=svar.model,
            verdict=ExclusionVerdict.REVIEW_REQUIRED,
            reason="AI svarade med ett okänt utfall, ärendet går till granskning.",
            error=None,
        )

    citat = str(data.get("quote") or "").strip()
    skal = str(data.get("reason") or "").strip() or None

    # Ett utfall som skarper laget maste vara belagt. Annars ar det en gissning
    # som later myndig.
    if ai_utfall is ExclusionVerdict.EXCLUDED:
        belagda, kastade = verify_claims(
            text, [{"field": "personkontroll", "value": skal or "personkontroll", "quote": citat}]
        )
        if not belagda:
            return AIResult(
                available=True,
                provider=svar.provider,
                model=svar.model,
                dropped=kastade,
                verdict=ExclusionVerdict.REVIEW_REQUIRED,
                reason=(
                    "AI föreslog exkludering men citatet gick inte att hitta i "
                    "annonsen, så ärendet går till granskning i stället."
                ),
            )
        return AIResult(
            available=True,
            provider=svar.provider,
            model=svar.model,
            claims=belagda,
            verdict=combine_verdicts(rule_verdict, ai_utfall),
            reason=skal,
        )

    return AIResult(
        available=True,
        provider=svar.provider,
        model=svar.model,
        verdict=combine_verdicts(rule_verdict, ai_utfall),
        reason=skal,
    )


# Ordningen ar strangare ju hogre tal.
_STRANGHET = {
    ExclusionVerdict.PASS: 0,
    ExclusionVerdict.REVIEW_REQUIRED: 1,
    ExclusionVerdict.EXCLUDED: 2,
}


def combine_verdicts(rule: ExclusionVerdict, ai: ExclusionVerdict | None) -> ExclusionVerdict:
    """Det strangare av tva utfall.

    AI kan alltsa flytta PASS till REVIEW_REQUIRED, men aldrig REVIEW_REQUIRED
    till PASS. En modell som svarar "det ar nog lugnt" ska inte kunna slacka en
    flagga som en regel satt pa ett citat ur annonsen.
    """
    if ai is None:
        return rule
    return rule if _STRANGHET[rule] >= _STRANGHET[ai] else ai
