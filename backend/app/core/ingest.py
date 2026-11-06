"""Insamlingskedjan: fran RawItem till uppdrag i databasen.

Ordningen ar inte godtycklig:

  snapshot -> dubblett -> klassificering -> exkludering -> matchning -> arende

Snapshot forst, sa att radatan finns aven om nagot senare steg kraschar.
Exkludering fore matchning, eftersom en exkluderad post inte ska ha en
matchningspoang som lockar nagon att titta pa den. Arende sist, eftersom bara
fasta och tidsbegransade tjanster hos myndigheter foljs mot en tillsattning.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.classify import assess_exclusion as ai_assess_exclusion
from ..models import (
    Appointment,
    Authority,
    CollectionRun,
    ConsultantProfile,
    EmploymentType,
    ExclusionRecord,
    ExclusionVerdict,
    JobAd,
    JobAdVersion,
    MatchingResult,
    Notification,
    NotificationKind,
    Opportunity,
    OpportunityKind,
    OpportunityStatus,
    Organisation,
    OrgType,
    Provider,
    RoleFamily,
    RunStatus,
    SourceRegistry,
    SourceStatus,
)
from ..models.enums import Assessor
from ..sources.base import RawItem, SourceRunResult
from . import appointments as appt
from .classify import classify
from .dedup import changed_fields, find_duplicate
from .exclusion import ENGINE_VERSION as EXCL_VERSION
from .exclusion import assess
from .matching import ENGINE_VERSION as MATCH_VERSION
from .matching import score_opportunity
from .snapshots import store_snapshot
from .text import normalise_orgnr, normalise_title


@dataclass
class IngestStats:
    found: int = 0
    new: int = 0
    changed: int = 0
    duplicate: int = 0
    irrelevant: int = 0
    excluded: int = 0
    review: int = 0
    errors: int = 0
    notes: list[str] = field(default_factory=list)


def _get_or_create_organisation(
    session: Session, name: str | None, org_number: str | None
) -> Organisation | None:
    """Hitta eller skapa organisationen.

    Organisationsnummer vager tyngst. Utan nummer matchas pa exakt namn och
    inte pa likhet: "Region Stockholm" och "Regionen Stockholm" kan vara samma,
    men en felaktig sammanslagning av tva myndigheter ar varre an en dubblett.
    """
    orgnr = normalise_orgnr(org_number)
    if orgnr:
        org = session.scalar(select(Organisation).where(Organisation.org_number == orgnr))
        if org:
            if name and not org.name:
                org.name = name
            return org
    if not name:
        return None
    org = session.scalar(select(Organisation).where(Organisation.name == name))
    if org:
        if orgnr and not org.org_number:
            org.org_number = orgnr
        return org

    org = Organisation(name=name, org_number=orgnr, org_type=_guess_org_type(name, orgnr))
    session.add(org)
    session.flush()
    return org


def _guess_org_type(name: str, orgnr: str | None) -> OrgType:
    """Gissa organisationstyp.

    Organisationsnummer som borjar pa 2021 ar statliga myndigheter, 2120 ar
    kommuner och 2321 ar regioner. Det ar Skatteverkets serier och det ar
    tillrackligt tillforlitligt att anvanda. Namnmonstren ar sekundara.
    """
    if orgnr:
        if orgnr.startswith("2021"):
            return OrgType.STATE_AGENCY
        if orgnr.startswith("2120"):
            return OrgType.MUNICIPALITY
        if orgnr.startswith("2321"):
            return OrgType.REGION
    lag = (name or "").lower()
    if any(o in lag for o in ("universitet", "högskola", "hogskola")):
        return OrgType.UNIVERSITY
    if lag.startswith("region ") or " region" in lag:
        return OrgType.REGION
    if "kommun" in lag:
        return OrgType.MUNICIPALITY
    if any(o in lag for o in ("myndighet", "verket", "inspektionen", "styrelsen", "kansli")):
        return OrgType.STATE_AGENCY
    return OrgType.PRIVATE


def _get_or_create_provider(session: Session, name: str | None) -> Provider | None:
    if not name:
        return None
    p = session.scalar(select(Provider).where(Provider.name == name))
    if p:
        return p
    p = Provider(name=name)
    session.add(p)
    session.flush()
    return p


def _opportunity_kind(employment_type: EmploymentType) -> OpportunityKind:
    if employment_type is EmploymentType.INTERIM_CONSULTANT:
        return OpportunityKind.INTERIM_ASSIGNMENT
    if employment_type in (EmploymentType.PERMANENT, EmploymentType.FIXED_TERM):
        return OpportunityKind.PERMANENT_POSITION
    if employment_type is EmploymentType.SUBSTITUTE:
        return OpportunityKind.INTERIM_ASSIGNMENT
    return OpportunityKind.CONSULTING_ASSIGNMENT


def _active_profile(session: Session) -> ConsultantProfile | None:
    return session.scalar(select(ConsultantProfile).where(ConsultantProfile.is_active.is_(True)))


def ingest_item(
    session: Session,
    item: RawItem,
    source_key: str,
    *,
    stats: IngestStats,
    profile: ConsultantProfile | None = None,
    now: dt.datetime | None = None,
) -> JobAd | None:
    """Bearbeta en post. Returnerar annonsen, eller None nar den hoppades over."""
    nu = now or dt.datetime.now(dt.UTC)
    stats.found += 1

    snapshot, snapshot_ny = store_snapshot(
        session,
        source_key=source_key,
        external_id=item.external_id,
        payload=item.payload,
        url=item.url,
    )

    org = _get_or_create_organisation(session, item.organisation_name, item.organisation_number)
    dubblett = find_duplicate(
        session,
        source_key=source_key,
        external_id=item.external_id,
        title=item.title,
        organisation_id=org.id if org else None,
        published_at=item.published_at,
    )

    klass = classify(item.title, item.description)

    nya_varden = {
        "title": item.title,
        "description": item.description,
        "application_deadline": item.application_deadline,
        "employment_type": klass.employment_type,
        "role_family": klass.role_family,
        "depublished_at": item.depublished_at,
        "url": item.url,
    }

    if dubblett.found:
        stats.duplicate += 1
        befintlig = session.get(JobAd, dubblett.job_ad_id)
        if befintlig is None:
            return None
        if not snapshot_ny:
            # Samma kalla, samma innehall. Ingenting har hant.
            return befintlig
        diff = changed_fields(befintlig, nya_varden)
        if diff:
            session.add(
                JobAdVersion(
                    job_ad_id=befintlig.id,
                    snapshot_id=snapshot.id,
                    valid_from=befintlig.updated_at or nu,
                    valid_to=nu,
                    changed_fields=diff,
                )
            )
            for falt, varde in nya_varden.items():
                if falt in diff:
                    setattr(befintlig, falt, varde)
            befintlig.snapshot_id = snapshot.id
            stats.changed += 1
            stats.notes.append(f"{befintlig.title!r}: {', '.join(diff)} ändrat")
            session.flush()
        return befintlig

    # Irrelevanta roller sparas inte som annonser. Snapshotet finns kvar, sa
    # att det gar att se att posten passerade och varfor den sorterades bort.
    if klass.role_family is RoleFamily.NOT_RELEVANT:
        stats.irrelevant += 1
        return None

    annons = JobAd(
        source_key=source_key,
        external_id=item.external_id,
        snapshot_id=snapshot.id,
        organisation_id=org.id if org else None,
        recruiter_id=(
            p.id if (p := _get_or_create_provider(session, item.recruiter_name)) else None
        ),
        title=item.title,
        title_normalised=normalise_title(item.title),
        description=item.description,
        employment_type=klass.employment_type,
        role_family=klass.role_family,
        occupation_concept_id=item.occupation_concept_id,
        occupation_label=item.occupation_label,
        published_at=item.published_at,
        application_deadline=item.application_deadline,
        depublished_at=item.depublished_at,
        workplace_municipality=item.municipality,
        workplace_region=item.region,
        workplace_address=item.address,
        url=item.url,
    )
    session.add(annons)
    session.flush()
    stats.new += 1

    uppdrag = Opportunity(
        kind=_opportunity_kind(klass.employment_type),
        job_ad_id=annons.id,
        status=(
            OpportunityStatus.CLOSED
            if (
                item.depublished_at
                or (item.application_deadline and item.application_deadline < nu)
            )
            else OpportunityStatus.OPEN
        ),
        duration_months=klass.duration_months,
        fee_sek_per_hour=klass.fee_sek_per_hour,
    )
    session.add(uppdrag)
    session.flush()

    # --- Exkludering ---
    bedomning = assess(item.description, title=item.title)
    session.add(
        ExclusionRecord(
            opportunity_id=uppdrag.id,
            verdict=bedomning.verdict,
            rule_id=bedomning.rule_id,
            matched_quote=bedomning.matched_quote,
            quote_offset=bedomning.quote_offset,
            document_url=item.url,
            assessed_at=nu,
            assessor=Assessor.RULE,
            ai_reasoning=f"{EXCL_VERSION}: {bedomning.reason}",
        )
    )

    slutligt = bedomning.verdict

    # En andra bedomning av en sprakmodell, men bara nar regelmotorn sjalv sager
    # att texten ar tvetydig, och bara i skarpande riktning. Finns ingen modell
    # konfigurerad hander ingenting -- regelutfallet star kvar och arendet
    # ligger kvar for granskning, vilket ar det ratta svaret nar vi inte vet.
    if bedomning.needs_ai:
        ai = ai_assess_exclusion(item.description, rule_verdict=bedomning.verdict)
        if ai.usable and ai.verdict is not None and ai.verdict is not bedomning.verdict:
            slutligt = ai.verdict
            citat = ai.claims[0].quote if ai.claims else None
            session.add(
                ExclusionRecord(
                    opportunity_id=uppdrag.id,
                    verdict=slutligt,
                    rule_id=bedomning.rule_id,
                    matched_quote=citat or bedomning.matched_quote,
                    quote_offset=(ai.claims[0].offset if ai.claims else bedomning.quote_offset),
                    document_url=item.url,
                    assessed_at=nu,
                    assessor=Assessor.AI,
                    ai_model=f"{ai.provider}/{ai.model}",
                    ai_reasoning=ai.reason or ai.note(),
                )
            )

    uppdrag.exclusion_status = slutligt
    if slutligt is ExclusionVerdict.EXCLUDED:
        stats.excluded += 1
    elif slutligt is ExclusionVerdict.REVIEW_REQUIRED:
        stats.review += 1

    # --- Matchning ---
    # Exkluderade poster matchas inte. En poang pa en post man inte kan ta ar
    # bara en distraktion.
    if bedomning.verdict is not ExclusionVerdict.EXCLUDED:
        profil = profile or _active_profile(session)
        resultat = score_opportunity(
            title=item.title,
            description=item.description,
            role_family=klass.role_family,
            employment_type=klass.employment_type,
            occupation_label=item.occupation_label,
            municipality=item.municipality,
            region=item.region,
            duration_months=klass.duration_months,
            fee_sek_per_hour=klass.fee_sek_per_hour,
            profile_weights=(profil.weights if profil else None),
            profile_preferences=(profil.preferences if profil else None),
        )
        uppdrag.match_score = resultat.score
        if profil is not None:
            session.add(
                MatchingResult(
                    opportunity_id=uppdrag.id,
                    profile_id=profil.id,
                    score=resultat.score,
                    confidence=resultat.confidence,
                    subscores=resultat.subscores,
                    explanation=resultat.explanation,
                    computed_at=nu,
                    engine_version=MATCH_VERSION,
                )
            )
        _maybe_notify(session, annons, uppdrag, resultat.score, nu)

    # --- Tillsattningsarende ---
    # Bara fasta och tidsbegransade tjanster hos offentliga organisationer
    # foljs. Ett konsultuppdrag har inget anstallningsbeslut att begara.
    if klass.employment_type in (EmploymentType.PERMANENT, EmploymentType.FIXED_TERM) and org:
        myndighet = session.scalar(select(Authority).where(Authority.organisation_id == org.id))
        if myndighet or org.org_type in (
            OrgType.STATE_AGENCY,
            OrgType.REGION,
            OrgType.MUNICIPALITY,
            OrgType.UNIVERSITY,
        ):
            befintligt = session.scalar(
                select(Appointment).where(Appointment.job_ad_id == annons.id)
            )
            if befintligt is None:
                arende = appt.open_case(session, annons, myndighet, now=nu)
                appt.evaluate(session, arende, annons, myndighet, now=nu)

    session.flush()
    return annons


def _maybe_notify(
    session: Session, annons: JobAd, uppdrag: Opportunity, score: int, nu: dt.datetime
) -> None:
    from ..config import settings

    if score < settings.notify_match_threshold:
        return
    kind = (
        NotificationKind.NEW_PERMANENT_POSITION
        if uppdrag.kind is OpportunityKind.PERMANENT_POSITION
        else NotificationKind.HIGH_MATCH_OPPORTUNITY
    )
    nyckel = f"{annons.source_key}:{annons.external_id}"
    # dedupe_key har ett unikt index. Finns den redan ar handelsen aviserad, och
    # da ska inte varannan-timme-korningen skicka om den.
    if session.scalar(
        select(Notification).where(Notification.kind == kind, Notification.dedupe_key == nyckel)
    ):
        return
    session.add(
        Notification(
            kind=kind,
            dedupe_key=nyckel,
            subject=f"{score} p: {annons.title}",
            payload={
                "job_ad_id": str(annons.id),
                "score": score,
                "url": annons.url,
                "deadline": annons.application_deadline.isoformat()
                if annons.application_deadline
                else None,
            },
            queued_at=nu,
        )
    )


def ingest_run(
    session: Session,
    result: SourceRunResult,
    *,
    triggered_by: str = "manual",
    now: dt.datetime | None = None,
) -> tuple[CollectionRun, IngestStats]:
    """Bearbeta en hel korning och skriv en rad i collection_runs.

    Korningen loggas aven nar adaptern misslyckades eller hoppades over. En
    kalla som tystnar ska syntas, inte forsvinna.
    """
    nu = now or dt.datetime.now(dt.UTC)
    stats = IngestStats(errors=result.errors)
    korning = CollectionRun(
        source_key=result.source_key,
        started_at=nu,
        status=RunStatus.RUNNING,
        triggered_by=triggered_by,
    )
    session.add(korning)
    session.flush()

    profil = _active_profile(session)

    if result.skipped:
        korning.status = RunStatus.SKIPPED
        korning.error_detail = result.skip_reason
        korning.finished_at = dt.datetime.now(dt.UTC)
        _update_source_status(session, result, nu, skipped=True)
        session.flush()
        return korning, stats

    for post in result.items:
        try:
            ingest_item(session, post, result.source_key, stats=stats, profile=profil, now=nu)
        except Exception as e:
            stats.errors += 1
            stats.notes.append(f"{post.external_id}: {type(e).__name__}: {e}")
            session.rollback()

    korning.items_found = stats.found
    korning.items_new = stats.new
    korning.items_changed = stats.changed
    korning.items_duplicate = stats.duplicate
    korning.errors = stats.errors
    korning.error_detail = result.error_detail or ("; ".join(stats.notes[:10]) or None)
    korning.finished_at = dt.datetime.now(dt.UTC)
    korning.status = (
        RunStatus.FAILED
        if stats.errors and not stats.found
        else RunStatus.PARTIAL
        if stats.errors
        else RunStatus.SUCCESS
    )
    _update_source_status(session, result, nu, skipped=False)
    session.flush()
    return korning, stats


def _update_source_status(
    session: Session, result: SourceRunResult, nu: dt.datetime, *, skipped: bool
) -> None:
    kalla = session.scalar(select(SourceRegistry).where(SourceRegistry.key == result.source_key))
    if kalla is None:
        return
    kalla.last_attempt_at = nu
    if skipped:
        return
    if result.errors:
        kalla.consecutive_failures += 1
        kalla.last_error = result.error_detail
        # Tre misslyckanden i rad ar inte ett hickande nat, det ar en trasig
        # kalla. Da ska den synas pa dashboarden.
        if kalla.consecutive_failures >= 3 and kalla.status is SourceStatus.ACTIVE:
            kalla.status = SourceStatus.FAILING
    else:
        kalla.consecutive_failures = 0
        kalla.last_error = None
        kalla.last_success_at = nu
        if kalla.status is SourceStatus.FAILING:
            kalla.status = SourceStatus.ACTIVE
