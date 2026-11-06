"""Uppdrag, sokning och exkluderingsgranskning."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..deps import AdminUser, CurrentUser, SessionDep, write_audit
from ..models import (
    Assessor,
    ConsultantProfile,
    EmploymentType,
    ExclusionRecord,
    ExclusionVerdict,
    JobAd,
    MatchingResult,
    Opportunity,
    OpportunityKind,
    OpportunityStatus,
    Organisation,
    OrgType,
    Provider,
    RoleFamily,
    SavedSearch,
)
from ..models.appointment import Appointment
from ..schemas import (
    ExclusionOut,
    ExclusionOverrideIn,
    JobAdOut,
    MatchOut,
    OpportunityDetail,
    OpportunityOut,
)

router = APIRouter(prefix="/opportunities", tags=["opportunities"])


def _job_ad_out(session: Session, annons: JobAd | None) -> JobAdOut | None:
    if annons is None:
        return None
    org = session.get(Organisation, annons.organisation_id) if annons.organisation_id else None
    data = JobAdOut.model_validate(annons)
    data.organisation_name = org.name if org else None
    return data


def _out(session: Session, uppdrag: Opportunity) -> OpportunityOut:
    data = OpportunityOut.model_validate(uppdrag)
    data.job_ad = _job_ad_out(session, uppdrag.job_ad)
    return data


@router.get("", response_model=dict)
def list_opportunities(
    session: SessionDep,
    user: CurrentUser,
    q: str | None = None,
    kind: OpportunityKind | None = None,
    status_filter: OpportunityStatus | None = Query(None, alias="status"),
    exclusion: ExclusionVerdict | None = None,
    employment_type: EmploymentType | None = None,
    role_family: RoleFamily | None = None,
    org_type: OrgType | None = None,
    organisation_id: uuid.UUID | None = None,
    municipality: str | None = None,
    region: str | None = None,
    recruiter_id: uuid.UUID | None = None,
    min_score: int | None = Query(None, ge=0, le=100),
    max_score: int | None = Query(None, ge=0, le=100),
    min_duration: int | None = None,
    max_duration: int | None = None,
    min_fee: int | None = None,
    deadline_before: dt.date | None = None,
    deadline_after: dt.date | None = None,
    published_after: dt.date | None = None,
    include_excluded: bool = False,
    sort: str = Query("score", pattern="^(score|published|deadline|created)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Avancerad sokning over hela uppdragsdatabasen.

    Exkluderade poster ar borta som standard. De gar att se med
    include_excluded=true eller via /excluded, men de ska inte ligga i samma
    lista som det man kan soka -- det var hela poangen med filtret.
    """
    fraga = select(Opportunity).join(JobAd, Opportunity.job_ad_id == JobAd.id, isouter=True)

    if not include_excluded and exclusion is None:
        fraga = fraga.where(Opportunity.exclusion_status != ExclusionVerdict.EXCLUDED)
    if exclusion is not None:
        fraga = fraga.where(Opportunity.exclusion_status == exclusion)
    if kind is not None:
        fraga = fraga.where(Opportunity.kind == kind)
    if status_filter is not None:
        fraga = fraga.where(Opportunity.status == status_filter)
    if employment_type is not None:
        fraga = fraga.where(JobAd.employment_type == employment_type)
    if role_family is not None:
        fraga = fraga.where(JobAd.role_family == role_family)
    if organisation_id is not None:
        fraga = fraga.where(JobAd.organisation_id == organisation_id)
    if recruiter_id is not None:
        fraga = fraga.where(JobAd.recruiter_id == recruiter_id)
    if municipality:
        fraga = fraga.where(JobAd.workplace_municipality.ilike(f"%{municipality}%"))
    if region:
        fraga = fraga.where(JobAd.workplace_region.ilike(f"%{region}%"))
    if org_type is not None:
        fraga = fraga.join(Organisation, JobAd.organisation_id == Organisation.id).where(
            Organisation.org_type == org_type
        )
    if min_score is not None:
        fraga = fraga.where(Opportunity.match_score >= min_score)
    if max_score is not None:
        fraga = fraga.where(Opportunity.match_score <= max_score)
    if min_duration is not None:
        fraga = fraga.where(Opportunity.duration_months >= min_duration)
    if max_duration is not None:
        fraga = fraga.where(Opportunity.duration_months <= max_duration)
    if min_fee is not None:
        fraga = fraga.where(Opportunity.fee_sek_per_hour >= min_fee)
    if deadline_before is not None:
        fraga = fraga.where(
            JobAd.application_deadline
            <= dt.datetime.combine(deadline_before, dt.time.max, tzinfo=dt.UTC)
        )
    if deadline_after is not None:
        fraga = fraga.where(
            JobAd.application_deadline
            >= dt.datetime.combine(deadline_after, dt.time.min, tzinfo=dt.UTC)
        )
    if published_after is not None:
        fraga = fraga.where(
            JobAd.published_at >= dt.datetime.combine(published_after, dt.time.min, tzinfo=dt.UTC)
        )
    if q:
        # Parametriserat via ilike, aldrig stranginterpolerat SQL. I drift mot
        # Postgres finns dessutom ett GIN-index for to_tsvector('swedish', ...),
        # men ilike fungerar pa bada databaserna och racker for en privat
        # databas av den har storleken.
        monster = f"%{q}%"
        fraga = fraga.where(or_(JobAd.title.ilike(monster), JobAd.description.ilike(monster)))

    total = session.scalar(select(func.count()).select_from(fraga.subquery()))

    ordning = {
        "score": Opportunity.match_score.desc().nulls_last(),
        "published": JobAd.published_at.desc().nulls_last(),
        "deadline": JobAd.application_deadline.asc().nulls_last(),
        "created": Opportunity.created_at.desc(),
    }[sort]

    rader = session.scalars(fraga.order_by(ordning).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_out(session, u) for u in rader],
    }


@router.get("/excluded", response_model=dict)
def list_excluded(
    session: SessionDep,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Exkluderade uppdrag, med citatet som orsakade beslutet.

    Egen vy sa att filtret gar att granska. Ett filter man inte kan se in i ar
    ett filter man slutar lita pa.
    """
    fraga = select(Opportunity).where(Opportunity.exclusion_status == ExclusionVerdict.EXCLUDED)
    total = session.scalar(select(func.count()).select_from(fraga.subquery()))
    rader = session.scalars(
        fraga.order_by(Opportunity.created_at.desc()).limit(limit).offset(offset)
    ).all()
    poster = []
    for uppdrag in rader:
        post = _out(session, uppdrag).model_dump()
        senaste = session.scalar(
            select(ExclusionRecord)
            .where(ExclusionRecord.opportunity_id == uppdrag.id)
            .order_by(ExclusionRecord.assessed_at.desc())
        )
        post["exclusion"] = ExclusionOut.model_validate(senaste).model_dump() if senaste else None
        poster.append(post)
    return {"total": total, "limit": limit, "offset": offset, "items": poster}


@router.get("/review", response_model=dict)
def list_review_required(
    session: SessionDep, user: CurrentUser, limit: int = Query(50, ge=1, le=200)
):
    """Uppdrag som kraver mansklig granskning av exkluderingsfragan."""
    rader = session.scalars(
        select(Opportunity)
        .where(Opportunity.exclusion_status == ExclusionVerdict.REVIEW_REQUIRED)
        .order_by(Opportunity.match_score.desc().nulls_last())
        .limit(limit)
    ).all()
    poster = []
    for uppdrag in rader:
        post = _out(session, uppdrag).model_dump()
        senaste = session.scalar(
            select(ExclusionRecord)
            .where(ExclusionRecord.opportunity_id == uppdrag.id)
            .order_by(ExclusionRecord.assessed_at.desc())
        )
        post["exclusion"] = ExclusionOut.model_validate(senaste).model_dump() if senaste else None
        poster.append(post)
    return {"total": len(poster), "items": poster}


@router.get("/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(opportunity_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    uppdrag = session.get(Opportunity, opportunity_id)
    if uppdrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uppdraget finns inte.")

    data = OpportunityDetail.model_validate(uppdrag)
    data.job_ad = _job_ad_out(session, uppdrag.job_ad)

    senaste = session.scalar(
        select(ExclusionRecord)
        .where(ExclusionRecord.opportunity_id == uppdrag.id)
        .order_by(ExclusionRecord.assessed_at.desc())
    )
    data.exclusion = ExclusionOut.model_validate(senaste) if senaste else None

    match = session.scalar(
        select(MatchingResult)
        .where(MatchingResult.opportunity_id == uppdrag.id)
        .order_by(MatchingResult.computed_at.desc())
    )
    if match:
        data.matching = MatchOut(
            score=match.score,
            confidence=match.confidence,
            explanation=match.explanation,
            subscores=match.subscores,
        )

    if uppdrag.job_ad_id:
        arende = session.scalar(
            select(Appointment).where(Appointment.job_ad_id == uppdrag.job_ad_id)
        )
        data.appointment_id = arende.id if arende else None
    return data


@router.post("/{opportunity_id}/exclusion-override", response_model=ExclusionOut)
def override_exclusion(
    opportunity_id: uuid.UUID,
    data: ExclusionOverrideIn,
    request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    """Overprova ett exkluderingsbeslut.

    Skapar en NY exclusion_record med assessor=HUMAN. Den gamla raden skrivs
    aldrig over -- bevisboken ska visa bade vad regeln sade och vad manniskan
    beslutade, och av vem.
    """
    uppdrag = session.get(Opportunity, opportunity_id)
    if uppdrag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Uppdraget finns inte.")

    tidigare = session.scalar(
        select(ExclusionRecord)
        .where(ExclusionRecord.opportunity_id == uppdrag.id)
        .order_by(ExclusionRecord.assessed_at.desc())
    )
    gammalt = uppdrag.exclusion_status

    ny = ExclusionRecord(
        opportunity_id=uppdrag.id,
        verdict=data.verdict,
        rule_id=(tidigare.rule_id if tidigare else None),
        # Citatet foljer med, eftersom databasen kraver ett citat for EXCLUDED
        # och eftersom en overprovning till EXCLUDED utan citat vore lika
        # obegriplig som en maskinell.
        matched_quote=(tidigare.matched_quote if tidigare else None)
        or (data.reason if data.verdict is ExclusionVerdict.EXCLUDED else None),
        quote_offset=(tidigare.quote_offset if tidigare else None),
        document_url=(tidigare.document_url if tidigare else None),
        assessed_at=dt.datetime.now(dt.UTC),
        assessor=Assessor.HUMAN,
        overridden_by_user_id=admin.id,
        override_reason=data.reason,
    )
    session.add(ny)
    uppdrag.exclusion_status = data.verdict

    # Blir posten godkand efter att ha varit exkluderad ska den fa en poang.
    if gammalt is ExclusionVerdict.EXCLUDED and data.verdict is not ExclusionVerdict.EXCLUDED:
        _rescore(session, uppdrag)
    elif data.verdict is ExclusionVerdict.EXCLUDED:
        uppdrag.match_score = None

    write_audit(
        session,
        user=admin,
        action="exclusion_override",
        object_type="opportunity",
        object_id=str(uppdrag.id),
        before={"exclusion_status": gammalt.value},
        after={"exclusion_status": data.verdict.value, "reason": data.reason},
        request=request,
    )
    session.commit()
    session.refresh(ny)
    return ExclusionOut.model_validate(ny)


def _rescore(session: Session, uppdrag: Opportunity) -> None:
    from ..core.matching import ENGINE_VERSION, score_opportunity

    annons = uppdrag.job_ad
    if annons is None:
        return
    profil = session.scalar(select(ConsultantProfile).where(ConsultantProfile.is_active.is_(True)))
    resultat = score_opportunity(
        title=annons.title,
        description=annons.description,
        role_family=annons.role_family,
        employment_type=annons.employment_type,
        occupation_label=annons.occupation_label,
        municipality=annons.workplace_municipality,
        region=annons.workplace_region,
        duration_months=uppdrag.duration_months,
        fee_sek_per_hour=uppdrag.fee_sek_per_hour,
        profile_weights=(profil.weights if profil else None),
        profile_preferences=(profil.preferences if profil else None),
    )
    uppdrag.match_score = resultat.score
    if profil:
        session.add(
            MatchingResult(
                opportunity_id=uppdrag.id,
                profile_id=profil.id,
                score=resultat.score,
                subscores=resultat.subscores,
                explanation=resultat.explanation,
                computed_at=dt.datetime.now(dt.UTC),
                engine_version=ENGINE_VERSION,
            )
        )


# --- Sparade sokningar ---

saved = APIRouter(prefix="/saved-searches", tags=["search"])


@saved.get("", response_model=list[dict])
def list_saved(session: SessionDep, user: CurrentUser):
    rader = session.scalars(select(SavedSearch).where(SavedSearch.user_id == user.id)).all()
    return [{"id": str(s.id), "name": s.name, "filters": s.filters} for s in rader]


@saved.post("", response_model=dict, status_code=201)
def create_saved(payload: dict, session: SessionDep, user: CurrentUser):
    namn = (payload.get("name") or "").strip()
    if not namn:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "name kravs")
    befintlig = session.scalar(
        select(SavedSearch).where(SavedSearch.user_id == user.id, SavedSearch.name == namn)
    )
    if befintlig:
        befintlig.filters = payload.get("filters") or {}
        session.commit()
        return {"id": str(befintlig.id), "name": namn, "updated": True}
    ny = SavedSearch(user_id=user.id, name=namn, filters=payload.get("filters") or {})
    session.add(ny)
    session.commit()
    return {"id": str(ny.id), "name": namn, "updated": False}


@saved.delete("/{search_id}", status_code=204)
def delete_saved(search_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    s = session.get(SavedSearch, search_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sökningen finns inte.")
    session.delete(s)
    session.commit()


# --- Formedlare ---

providers = APIRouter(prefix="/providers", tags=["market"])


@providers.get("", response_model=list[dict])
def list_providers(session: SessionDep, user: CurrentUser):
    rader = session.execute(
        select(Provider, func.count(JobAd.id))
        .join(JobAd, JobAd.recruiter_id == Provider.id, isouter=True)
        .group_by(Provider.id)
        .order_by(func.count(JobAd.id).desc())
    ).all()
    return [
        {
            "id": str(p.id),
            "name": p.name,
            "org_number": p.org_number,
            "website": p.website,
            "assignment_count": antal,
            "note": p.note,
        }
        for p, antal in rader
    ]
