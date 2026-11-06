"""Ombedomning av exkluderingsfiltret.

Varfor det behovs som egen funktion: filtret ar regelstyrt, och en rattad regel
ar varde noll sa lange den bara galler nya annonser. Det var precis vad som
hande nar villkorsregeln kom pa plats -- en vikarierande enhetschef hos Statens
fastighetsverk lag kvar som EXCLUDED i databasen, eftersom insamlingen hoppar
over en annons vars snapshot ar oforandrad.

Tre regler for hur ombedomningen beter sig:

1. **Historiken skrivs aldrig over.** En ny bedomning blir en ny rad. Att kunna
   se att ett uppdrag var EXCLUDED i november och REVIEW_REQUIRED i december,
   och vilken regel som gallde da, ar hela skalet till att tabellen finns.
2. **En manuell bedomning vinner.** Har en manniska satt utfallet rors det inte.
   Maskinen far inte overpruta den som tog ansvar for beslutet.
3. **Bara det som faktiskt andras skrivs.** Oforandrade utfall ger ingen ny rad.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from ..models import Assessor, ExclusionRecord, JobAd, Opportunity
from .exclusion import ENGINE_VERSION, assess


@dataclass
class ReassessStats:
    granskade: int = 0
    andrade: int = 0
    manuella: int = 0
    utan_text: int = 0
    noteringar: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"granskade {self.granskade}, andrade {self.andrade}, "
            f"manuellt satta (ororda) {self.manuella}, utan text {self.utan_text}"
        )


def _senaste(uppdrag: Opportunity) -> ExclusionRecord | None:
    rader = sorted(uppdrag.exclusion_records, key=lambda r: r.assessed_at)
    return rader[-1] if rader else None


def reassess_exclusions(
    session: Session,
    *,
    only_stale: bool = True,
    dry_run: bool = False,
    now: dt.datetime | None = None,
) -> ReassessStats:
    """Kor exkluderingsfiltret igen pa redan insamlade uppdrag.

    `only_stale` begransar till de som bedomdes med en aldre version av filtret.
    """
    nu = now or dt.datetime.now(dt.UTC)
    stats = ReassessStats()

    uppdrag = session.query(Opportunity).join(JobAd, Opportunity.job_ad_id == JobAd.id).all()

    for u in uppdrag:
        senaste = _senaste(u)
        if senaste is not None and senaste.assessor is Assessor.HUMAN:
            stats.manuella += 1
            continue
        if senaste is not None and senaste.overridden_by_user_id is not None:
            stats.manuella += 1
            continue
        if only_stale and senaste is not None:
            tidigare = (senaste.ai_reasoning or "").split(":", 1)[0]
            if tidigare == ENGINE_VERSION:
                continue

        annons = u.job_ad
        if annons is None:
            continue
        stats.granskade += 1

        bedomning = assess(annons.description or "", title=annons.title or "")
        if bedomning.rule_id == "INSUFFICIENT_TEXT":
            stats.utan_text += 1

        if senaste is not None and bedomning.verdict is senaste.verdict:
            continue

        stats.andrade += 1
        fore = senaste.verdict.value if senaste else "-"
        stats.noteringar.append(
            f"{annons.title!r}: {fore} -> {bedomning.verdict.value} "
            f"({bedomning.rule_id or 'ingen regel'})"
        )
        if dry_run:
            continue

        u.exclusion_status = bedomning.verdict
        session.add(
            ExclusionRecord(
                opportunity_id=u.id,
                verdict=bedomning.verdict,
                rule_id=bedomning.rule_id,
                matched_quote=bedomning.matched_quote,
                quote_offset=bedomning.quote_offset,
                document_url=annons.url,
                assessed_at=nu,
                assessor=Assessor.RULE,
                ai_reasoning=f"{ENGINE_VERSION}: ombedomning. {bedomning.reason}",
            )
        )

    return stats
