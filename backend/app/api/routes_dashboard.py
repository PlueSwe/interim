"""Dashboard, marknadsanalys och organisationer."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..deps import CurrentUser, SessionDep
from ..models import (
    Appointment,
    AppointmentStatus,
    Authority,
    CallOff,
    EmploymentType,
    ExclusionVerdict,
    FrameworkAgreement,
    InformationRequest,
    JobAd,
    Opportunity,
    OpportunityKind,
    OpportunityStatus,
    Organisation,
    OrgType,
    Provider,
    RequestStatus,
    SourceRegistry,
    SourceStatus,
)
from ..schemas import (
    AuthorityOut,
    DashboardOut,
    FrameworkAgreementOut,
    OrganisationOut,
    SourceOut,
)
from .routes_appointments import _out as appointment_out
from .routes_opportunities import _out as opportunity_out

router = APIRouter(tags=["dashboard"])


def _agreement_out(avtal: FrameworkAgreement) -> FrameworkAgreementOut:
    data = FrameworkAgreementOut.model_validate(avtal)
    if avtal.valid_to:
        data.days_left = (avtal.valid_to - dt.date.today()).days
    return data


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(session: SessionDep, user: CurrentUser):
    nu = dt.datetime.now(dt.UTC)
    vecka = nu - dt.timedelta(days=7)

    def rakna(fraga) -> int:
        return session.scalar(select(func.count()).select_from(fraga.subquery())) or 0

    ej_exkluderad = Opportunity.exclusion_status != ExclusionVerdict.EXCLUDED

    nya = rakna(select(Opportunity).where(Opportunity.created_at >= vecka, ej_exkluderad))
    aktiva_interim = rakna(
        select(Opportunity).where(
            Opportunity.kind.in_(
                [OpportunityKind.INTERIM_ASSIGNMENT, OpportunityKind.CONSULTING_ASSIGNMENT]
            ),
            Opportunity.status == OpportunityStatus.OPEN,
            ej_exkluderad,
        )
    )
    fasta = rakna(
        select(Opportunity).where(
            Opportunity.kind == OpportunityKind.PERMANENT_POSITION, ej_exkluderad
        )
    )
    avslutade = rakna(
        select(Appointment).where(
            Appointment.status.not_in(
                [AppointmentStatus.ADVERTISEMENT_FOUND, AppointmentStatus.APPLICATION_OPEN]
            )
        )
    )
    identifierade = rakna(
        select(Appointment).where(
            Appointment.status.in_(
                [
                    AppointmentStatus.APPOINTMENT_IDENTIFIED,
                    AppointmentStatus.APPOINTMENT_VERIFIED,
                ]
            )
        )
    )
    verifierade = rakna(
        select(Appointment).where(Appointment.status == AppointmentStatus.APPOINTMENT_VERIFIED)
    )
    olosta = rakna(
        select(Appointment).where(
            Appointment.status.in_(
                [
                    AppointmentStatus.APPOINTMENT_NOT_FOUND,
                    AppointmentStatus.REQUEST_READY,
                    AppointmentStatus.REQUEST_SENT,
                    AppointmentStatus.CLOSED_UNRESOLVED,
                ]
            )
        )
    )
    vantar_godkannande = rakna(
        select(InformationRequest).where(InformationRequest.status == RequestStatus.DRAFT)
    )
    exkluderade = rakna(
        select(Opportunity).where(Opportunity.exclusion_status == ExclusionVerdict.EXCLUDED)
    )
    granskning = rakna(
        select(Opportunity).where(Opportunity.exclusion_status == ExclusionVerdict.REVIEW_REQUIRED)
    )

    toppar = session.scalars(
        select(Opportunity)
        .where(ej_exkluderad, Opportunity.match_score.is_not(None))
        .order_by(Opportunity.match_score.desc())
        .limit(10)
    ).all()

    deadlines = session.scalars(
        select(Opportunity)
        .join(JobAd, Opportunity.job_ad_id == JobAd.id)
        .where(
            ej_exkluderad,
            JobAd.application_deadline > nu,
            JobAd.depublished_at.is_(None),
        )
        .order_by(JobAd.application_deadline.asc())
        .limit(10)
    ).all()

    avtal = session.scalars(
        select(FrameworkAgreement)
        .where(
            FrameworkAgreement.valid_to.is_not(None),
            FrameworkAgreement.valid_to >= dt.date.today(),
        )
        .order_by(FrameworkAgreement.valid_to.asc())
        .limit(10)
    ).all()

    senaste_tillsattningar = session.scalars(
        select(Appointment)
        .where(Appointment.status == AppointmentStatus.APPOINTMENT_VERIFIED)
        .order_by(Appointment.status_changed_at.desc())
        .limit(10)
    ).all()

    trasiga = session.scalars(
        select(SourceRegistry).where(SourceRegistry.status == SourceStatus.FAILING)
    ).all()

    return DashboardOut(
        new_opportunities_7d=nya,
        active_interim=aktiva_interim,
        permanent_positions=fasta,
        recruitments_closed=avslutade,
        appointments_identified=identifierade,
        appointments_verified=verifierade,
        appointments_unresolved=olosta,
        requests_awaiting_approval=vantar_godkannande,
        excluded_count=exkluderade,
        review_required_count=granskning,
        top_matches=[opportunity_out(session, o) for o in toppar],
        upcoming_deadlines=[opportunity_out(session, o) for o in deadlines],
        expiring_agreements=[_agreement_out(a) for a in avtal],
        recent_appointments=[appointment_out(session, a) for a in senaste_tillsattningar],
        failing_sources=[SourceOut.model_validate(k) for k in trasiga],
        charts=_charts(session),
    )


def _charts(session: Session) -> dict:
    """Underlag till diagrammen. Raknas i databasen, inte i frontend."""
    nu = dt.datetime.now(dt.UTC)

    # Uppdrag per vecka, 16 veckor bakat. Grupperas i Python eftersom
    # veckonumrering skiljer sig mellan Postgres och SQLite och det inte ar
    # vart ett dialektberoende for ett staplat diagram.
    per_vecka: dict[str, int] = {}
    rader = session.scalars(
        select(JobAd).where(JobAd.published_at >= nu - dt.timedelta(weeks=16))
    ).all()
    for annons in rader:
        if annons.published_at:
            ar, vecka, _ = annons.published_at.isocalendar()
            per_vecka[f"{ar}-v{vecka:02d}"] = per_vecka.get(f"{ar}-v{vecka:02d}", 0) + 1

    per_orgtyp = dict(
        session.execute(
            select(Organisation.org_type, func.count(JobAd.id))
            .join(JobAd, JobAd.organisation_id == Organisation.id)
            .group_by(Organisation.org_type)
        ).all()
    )

    per_myndighet = session.execute(
        select(Organisation.name, func.count(JobAd.id))
        .join(JobAd, JobAd.organisation_id == Organisation.id)
        .where(
            Organisation.org_type.in_(
                [OrgType.STATE_AGENCY, OrgType.REGION, OrgType.MUNICIPALITY, OrgType.UNIVERSITY]
            ),
            JobAd.employment_type.in_([EmploymentType.PERMANENT, EmploymentType.FIXED_TERM]),
        )
        .group_by(Organisation.name)
        .order_by(func.count(JobAd.id).desc())
        .limit(15)
    ).all()

    tillsattningar_over_tid: dict[str, int] = {}
    for arende in session.scalars(
        select(Appointment).where(Appointment.status == AppointmentStatus.APPOINTMENT_VERIFIED)
    ).all():
        nyckel = (arende.decision_date or arende.status_changed_at.date()).strftime("%Y-%m")
        tillsattningar_over_tid[nyckel] = tillsattningar_over_tid.get(nyckel, 0) + 1

    per_formedlare = session.execute(
        select(Provider.name, func.count(JobAd.id))
        .join(JobAd, JobAd.recruiter_id == Provider.id)
        .group_by(Provider.name)
        .order_by(func.count(JobAd.id).desc())
        .limit(10)
    ).all()

    per_geografi = session.execute(
        select(JobAd.workplace_region, func.count(JobAd.id))
        .where(JobAd.workplace_region.is_not(None))
        .group_by(JobAd.workplace_region)
        .order_by(func.count(JobAd.id).desc())
        .limit(15)
    ).all()

    per_status = dict(
        session.execute(
            select(Appointment.status, func.count(Appointment.id)).group_by(Appointment.status)
        ).all()
    )

    return {
        "ads_per_week": [{"period": k, "count": v} for k, v in sorted(per_vecka.items())],
        "by_org_type": [
            {"label": (k.value if hasattr(k, "value") else str(k)), "count": v}
            for k, v in per_orgtyp.items()
        ],
        "recruitments_per_authority": [{"label": n, "count": c} for n, c in per_myndighet],
        "appointments_over_time": [
            {"period": k, "count": v} for k, v in sorted(tillsattningar_over_tid.items())
        ],
        "by_recruiter": [{"label": n, "count": c} for n, c in per_formedlare],
        "by_region": [{"label": n, "count": c} for n, c in per_geografi],
        "appointments_by_status": [
            {"label": (k.value if hasattr(k, "value") else str(k)), "count": v}
            for k, v in per_status.items()
        ],
    }


# --- Marknadsanalys --------------------------------------------------------

market = APIRouter(prefix="/market", tags=["market"])


@market.get("/intelligence", response_model=dict)
def intelligence(session: SessionDep, user: CurrentUser, months: int = Query(24, ge=1, le=120)):
    """Marknadsanalys: vem koper, vem rekryterar, vilka avtal loper ut.

    Historik, inte prognos. Prognoser ar medvetet inte byggda: en uppskattning
    av framtida behov fran nagra manaders data vore en siffra utan tackning,
    och att markera den som uppskattning gor den inte mer anvandbar. Se
    IMPLEMENTATION_PLAN.md.
    """
    sedan = dt.datetime.now(dt.UTC) - dt.timedelta(days=30 * months)

    aterkommande_interim = session.execute(
        select(Organisation.name, Organisation.org_type, func.count(Opportunity.id))
        .join(JobAd, JobAd.organisation_id == Organisation.id)
        .join(Opportunity, Opportunity.job_ad_id == JobAd.id)
        .where(
            Opportunity.kind.in_(
                [OpportunityKind.INTERIM_ASSIGNMENT, OpportunityKind.CONSULTING_ASSIGNMENT]
            ),
            JobAd.published_at >= sedan,
        )
        .group_by(Organisation.name, Organisation.org_type)
        .having(func.count(Opportunity.id) >= 2)
        .order_by(func.count(Opportunity.id).desc())
        .limit(25)
    ).all()

    ofta_rekryterar = session.execute(
        select(Organisation.name, Organisation.org_type, func.count(JobAd.id))
        .join(JobAd, JobAd.organisation_id == Organisation.id)
        .where(
            JobAd.employment_type.in_([EmploymentType.PERMANENT, EmploymentType.FIXED_TERM]),
            JobAd.published_at >= sedan,
        )
        .group_by(Organisation.name, Organisation.org_type)
        .having(func.count(JobAd.id) >= 2)
        .order_by(func.count(JobAd.id).desc())
        .limit(25)
    ).all()

    formedlare = session.execute(
        select(Provider.name, func.count(JobAd.id))
        .join(JobAd, JobAd.recruiter_id == Provider.id)
        .group_by(Provider.name)
        .order_by(func.count(JobAd.id).desc())
        .limit(20)
    ).all()

    vinnande = session.execute(
        select(Provider.name, func.count(CallOff.id), func.sum(CallOff.value_sek))
        .join(CallOff, CallOff.winning_provider_id == Provider.id)
        .group_by(Provider.name)
        .order_by(func.count(CallOff.id).desc())
        .limit(20)
    ).all()

    utlopande = session.scalars(
        select(FrameworkAgreement)
        .where(
            FrameworkAgreement.valid_to.is_not(None),
            FrameworkAgreement.valid_to >= dt.date.today(),
            FrameworkAgreement.valid_to <= dt.date.today() + dt.timedelta(days=548),
        )
        .order_by(FrameworkAgreement.valid_to.asc())
    ).all()

    chefsbyten = session.execute(
        select(Organisation.name, func.count(Appointment.id))
        .join(Authority, Authority.organisation_id == Organisation.id)
        .join(Appointment, Appointment.authority_id == Authority.id)
        .group_by(Organisation.name)
        .having(func.count(Appointment.id) >= 2)
        .order_by(func.count(Appointment.id).desc())
        .limit(20)
    ).all()

    return {
        "window_months": months,
        "recurring_interim_buyers": [
            {
                "organisation": n,
                "org_type": t.value if hasattr(t, "value") else str(t),
                "assignments": c,
            }
            for n, t, c in aterkommande_interim
        ],
        "frequent_recruiters": [
            {
                "organisation": n,
                "org_type": t.value if hasattr(t, "value") else str(t),
                "positions": c,
            }
            for n, t, c in ofta_rekryterar
        ],
        "brokers_by_volume": [{"provider": n, "assignments": c} for n, c in formedlare],
        "suppliers_winning_call_offs": [
            {"provider": n, "call_offs": c, "total_value_sek": int(v or 0)} for n, c, v in vinnande
        ],
        "expiring_agreements": [_agreement_out(a).model_dump() for a in utlopande],
        "organisations_with_leadership_turnover": [
            {"organisation": n, "recruitments": c} for n, c in chefsbyten
        ],
        "caveat": (
            "Alla tal ar raknade pa insamlad data, inte pa hela marknaden. "
            "Tackningen framgar av /sources och /authorities/coverage. Inga "
            "prognoser lamnas; se IMPLEMENTATION_PLAN.md for varfor."
        ),
    }


@market.get("/framework-agreements", response_model=list[FrameworkAgreementOut])
def list_agreements(session: SessionDep, user: CurrentUser):
    rader = session.scalars(
        select(FrameworkAgreement).order_by(FrameworkAgreement.valid_to.asc().nulls_last())
    ).all()
    return [_agreement_out(a) for a in rader]


# --- Organisationer och myndigheter ----------------------------------------

orgs = APIRouter(prefix="/organisations", tags=["organisations"])


@orgs.get("", response_model=dict)
def list_organisations(
    session: SessionDep,
    user: CurrentUser,
    org_type: OrgType | None = None,
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    fraga = select(Organisation)
    if org_type is not None:
        fraga = fraga.where(Organisation.org_type == org_type)
    if q:
        fraga = fraga.where(Organisation.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(fraga.subquery()))
    rader = session.scalars(fraga.order_by(Organisation.name).limit(limit).offset(offset)).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [OrganisationOut.model_validate(o) for o in rader],
    }


authorities = APIRouter(prefix="/authorities", tags=["organisations"])


@authorities.get("/coverage", response_model=dict)
def authority_coverage(session: SessionDep, user: CurrentUser):
    """Vad registret faktiskt tacker, och vad det inte tacker."""
    from ..seed import coverage

    return coverage(session)


@authorities.get("", response_model=dict)
def list_authorities(
    session: SessionDep,
    user: CurrentUser,
    status_filter: SourceStatus | None = Query(None, alias="status"),
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    fraga = select(Authority, Organisation).join(
        Organisation, Authority.organisation_id == Organisation.id
    )
    if status_filter is not None:
        fraga = fraga.where(Authority.status == status_filter)
    if q:
        fraga = fraga.where(Organisation.name.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(fraga.subquery()))
    rader = session.execute(fraga.order_by(Organisation.name).limit(limit).offset(offset)).all()
    poster = []
    for myndighet, org in rader:
        data = AuthorityOut.model_validate(myndighet)
        data.organisation_name = org.name
        poster.append(data)
    return {"total": total, "limit": limit, "offset": offset, "items": poster}


@authorities.get("/{authority_id}", response_model=AuthorityOut)
def get_authority(authority_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    myndighet = session.get(Authority, authority_id)
    if myndighet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Myndigheten finns inte.")
    data = AuthorityOut.model_validate(myndighet)
    org = session.get(Organisation, myndighet.organisation_id)
    data.organisation_name = org.name if org else None
    return data
