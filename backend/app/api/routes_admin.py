"""Administration: kallor, profil, korningar, manuell import, regelverk."""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import func, select

from ..core.exclusion import all_rules
from ..core.ingest import ingest_run
from ..deps import AdminUser, CurrentUser, SessionDep, write_audit
from ..models import (
    VERIFICATION_LEVELS,
    AccessMode,
    Authority,
    CollectionRun,
    ConsultantProfile,
    Organisation,
    SourceRegistry,
    SourceSnapshot,
    SourceStatus,
)
from ..schemas import (
    AuthorityPatch,
    ManualImportIn,
    ProfileOut,
    ProfilePatch,
    RunOut,
    SourceOut,
)
from ..sources import ADAPTERS, get_adapter, verify_authority

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Kallor ---


@router.get("/sources", response_model=list[SourceOut])
def list_sources(session: SessionDep, user: CurrentUser):
    """Kallregistret med lage, robots-utfall och halsa."""
    return [
        SourceOut.model_validate(k)
        for k in session.scalars(select(SourceRegistry).order_by(SourceRegistry.key)).all()
    ]


@router.get("/runs", response_model=list[RunOut])
def list_runs(
    session: SessionDep,
    user: CurrentUser,
    source_key: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    fraga = select(CollectionRun)
    if source_key:
        fraga = fraga.where(CollectionRun.source_key == source_key)
    return [
        RunOut.model_validate(r)
        for r in session.scalars(fraga.order_by(CollectionRun.started_at.desc()).limit(limit)).all()
    ]


@router.post("/sources/{source_key}/collect", response_model=dict)
def collect_now(source_key: str, http_request: Request, session: SessionDep, admin: AdminUser):
    """Kor en kalla nu.

    Spärren for BLOCKED och MANUAL_ONLY ligger i adaptern, inte har. Anropet
    returnerar da ett skipped-resultat med skalet, i stallet for ett fel -- det
    ar ett giltigt svar och inte ett misslyckande.
    """
    if source_key not in ADAPTERS:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Okänd källa. Kända källor: {', '.join(sorted(ADAPTERS))}",
        )
    adapter = get_adapter(source_key)
    resultat = adapter.run()
    korning, stats = ingest_run(session, resultat, triggered_by=f"api:{admin.email}")
    write_audit(
        session,
        user=admin,
        action="collect_now",
        object_type="source",
        object_id=source_key,
        after={"status": korning.status.value, "found": stats.found},
        request=http_request,
    )
    session.commit()
    return {
        "source": source_key,
        "status": korning.status.value,
        "skipped": resultat.skipped,
        "skip_reason": resultat.skip_reason,
        "found": stats.found,
        "new": stats.new,
        "changed": stats.changed,
        "duplicate": stats.duplicate,
        "irrelevant": stats.irrelevant,
        "excluded": stats.excluded,
        "review_required": stats.review,
        "errors": stats.errors,
        "notes": stats.notes[:20],
    }


@router.post("/import", response_model=dict)
def manual_import(
    data: ManualImportIn, http_request: Request, session: SessionDep, admin: AdminUser
):
    """Manuell import av CSV eller JSON.

    Vagen in for kallor som inte far hamtas automatiskt: e-Avrop och A Society
    (robots.txt sager nej), de kommersiella annonsdatabaserna (villkoren sager
    nej), och konsultmaklare bakom inloggning.
    """
    _warn_if_classified(data.content)
    adapter = get_adapter("manual")
    resultat = adapter.run(content=data.content, filename=data.filename, source_key=data.source_key)
    if resultat.errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, resultat.error_detail)
    korning, stats = ingest_run(session, resultat, triggered_by=f"import:{admin.email}")
    write_audit(
        session,
        user=admin,
        action="manual_import",
        object_type="source",
        object_id=data.source_key,
        after={"found": stats.found, "new": stats.new, "filename": data.filename},
        request=http_request,
    )
    session.commit()
    return {
        "status": korning.status.value,
        "found": stats.found,
        "new": stats.new,
        "duplicate": stats.duplicate,
        "irrelevant": stats.irrelevant,
        "excluded": stats.excluded,
        "review_required": stats.review,
        "errors": stats.errors,
        "notes": stats.notes[:20],
    }


# Markorer som tyder pa att ett dokument inte borde in i systemet alls.
CLASSIFIED_MARKERS = (
    "SEKRETESS",
    "BEGRÄNSAD SPRIDNING",
    "BEGRANSAD SPRIDNING",
    "HEMLIG",
    "KVALIFICERAT HEMLIG",
    "SÄKERHETSSKYDDSKLASSIFICERAD",
)


def _warn_if_classified(content: str) -> None:
    """Vagra import av uppenbart sekretessbelagt underlag.

    SECURITY.md: ett sekretessbelagt underlag ska inte in i systemet over huvud
    taget. Kontrollen ar grov men fangar det vanliga fallet: en PDF med
    sekretessmarkering i sidhuvudet.
    """
    topp = content[:4000].upper()
    traffade = [m for m in CLASSIFIED_MARKERS if m in topp]
    if traffade:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Underlaget innehåller {', '.join(traffade)} i början av filen. "
            f"Sekretessbelagt material ska inte importeras. Ta bort markeringen "
            f"bara om du vet att den ar felaktig.",
        )


# --- Myndigheter ---


@router.post("/authorities/verify", response_model=dict)
def verify_authority_page(url: str, session: SessionDep, admin: AdminUser, name: str | None = None):
    """Prova en myndighets karriarsida och rapportera vad som gick att lasa.

    Andrar ingenting. Resultatet ar underlag for att satta vacancies_url och
    status ACTIVE, vilket gors med PATCH nedan.
    """
    return verify_authority(url, name)


@router.patch("/authorities/{authority_id}", response_model=dict)
def patch_authority(
    authority_id: uuid.UUID,
    data: AuthorityPatch,
    http_request: Request,
    session: SessionDep,
    admin: AdminUser,
):
    myndighet = session.get(Authority, authority_id)
    if myndighet is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Myndigheten finns inte.")
    fore = {
        "vacancies_url": myndighet.vacancies_url,
        "registrar_email": myndighet.registrar_email,
        "status": myndighet.status.value,
        "appointment_publication_mode": myndighet.appointment_publication_mode.value,
    }
    for falt, varde in data.model_dump(exclude_unset=True).items():
        if varde is not None:
            setattr(myndighet, falt, varde)

    # En myndighet far inte bli ACTIVE utan en verifierad listningssida. Utan
    # den lasas ingenting, och statusen skulle ljuga pa dashboarden.
    if myndighet.status is SourceStatus.ACTIVE and not myndighet.vacancies_url:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Status ACTIVE kräver vacancies_url. Verifiera sidan först med "
            "POST /admin/authorities/verify.",
        )
    myndighet.verified_at = dt.date.today()
    myndighet.verification_source = f"manuellt verifierad av {admin.email}"
    write_audit(
        session,
        user=admin,
        action="authority_patch",
        object_type="authority",
        object_id=str(myndighet.id),
        before=fore,
        after=data.model_dump(exclude_unset=True, mode="json"),
        request=http_request,
    )
    session.commit()
    return {"ok": True, "id": str(myndighet.id)}


# --- Profil ---


@router.get("/profile", response_model=ProfileOut)
def get_profile(session: SessionDep, user: CurrentUser):
    profil = session.scalar(select(ConsultantProfile).where(ConsultantProfile.is_active.is_(True)))
    if profil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingen aktiv profil. Kör app.cli seed.")
    return profil


@router.patch("/profile", response_model=ProfileOut)
def patch_profile(data: ProfilePatch, http_request: Request, session: SessionDep, admin: AdminUser):
    """Redigera profil och vikter.

    Vikterna behover inte summera till 100; poangen normaliseras mot summan.
    Men en summa pa noll ger ingen matchning, sa den vagras.
    """
    profil = session.scalar(select(ConsultantProfile).where(ConsultantProfile.is_active.is_(True)))
    if profil is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingen aktiv profil.")

    andringar = data.model_dump(exclude_unset=True)
    if "weights" in andringar and andringar["weights"] is not None:
        vikter = andringar["weights"]
        if not all(isinstance(v, int | float) and v >= 0 for v in vikter.values()):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Vikter måste vara tal större än eller lika med noll.",
            )
        if sum(vikter.values()) <= 0:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Vikterna summerar till noll, då blir varje matchning noll.",
            )

    fore = {"weights": profil.weights, "preferences": profil.preferences}
    for falt, varde in andringar.items():
        if varde is not None:
            setattr(profil, falt, varde)
    write_audit(
        session,
        user=admin,
        action="profile_patch",
        object_type="consultant_profile",
        object_id=str(profil.id),
        before=fore,
        after=andringar,
        request=http_request,
    )
    session.commit()
    return profil


# --- Regelverk och bevis ---


@router.get("/exclusion-rules", response_model=dict)
def exclusion_rules(user: CurrentUser):
    """Visa exkluderingsregelverket som det faktiskt ar.

    Finns for att regelverket ska ga att granska utan att lasa koden. Ett
    filter som pastar att det foljer ett krav ska kunna visa sina regler.
    """
    return {
        "rules": [
            {
                "rule_id": r.rule_id,
                "kind": r.kind.value,
                "description": r.description,
                "pattern": r.pattern.pattern,
                "requires_near": list(r.requires_near),
            }
            for r in all_rules()
        ],
        "verdicts": {
            "PASS": "inget uttryckligt kontrollkrav hittat",
            "REVIEW_REQUIRED": "oklar formulering, kraver mansklig granskning",
            "EXCLUDED": "uttryckligt krav pa bakgrunds- eller sakerhetskontroll",
        },
        "verification_levels": VERIFICATION_LEVELS,
        "note": (
            "BENIGN-regler exkluderar aldrig. De finns for att kunna visa att "
            "filtret sag ett sakerhetsord och lat det passera, i stallet for att "
            "det missade ordet."
        ),
    }


@router.get("/snapshots/{snapshot_id}", response_model=dict)
def get_snapshot(snapshot_id: uuid.UUID, session: SessionDep, user: CurrentUser):
    """Las radatan bakom en uppgift, och kontrollera sha256.

    Detta ar vad "varje uppgift gar att spara" betyder i praktiken: fran en
    annons i granssnittet till det raa svaret kallan gav, med en kontroll av att
    innehallet inte andrats sedan dess.
    """
    from ..core.snapshots import read_snapshot, verify_snapshot

    snapshot = session.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ögonblicksbilden finns inte.")
    innehall = read_snapshot(snapshot)
    return {
        "id": str(snapshot.id),
        "source_key": snapshot.source_key,
        "external_id": snapshot.external_id,
        "url": snapshot.url,
        "fetched_at": snapshot.fetched_at.isoformat(),
        "http_status": snapshot.http_status,
        "content_type": snapshot.content_type,
        "sha256": snapshot.sha256,
        "byte_size": snapshot.byte_size,
        "integrity_ok": verify_snapshot(snapshot),
        "content": (innehall[:200_000] if innehall else None),
        "truncated": bool(innehall and len(innehall) > 200_000),
    }


@router.get("/audit", response_model=list[dict])
def audit_log(session: SessionDep, admin: AdminUser, limit: int = Query(100, ge=1, le=500)):
    from ..models import AuditLog, User

    rader = session.execute(
        select(AuditLog, User)
        .join(User, AuditLog.user_id == User.id, isouter=True)
        .order_by(AuditLog.at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "at": logg.at.isoformat(),
            "user": anvandare.email if anvandare else None,
            "action": logg.action,
            "object_type": logg.object_type,
            "object_id": logg.object_id,
            "before": logg.before,
            "after": logg.after,
            "ip": logg.ip,
        }
        for logg, anvandare in rader
    ]


@router.get("/coverage", response_model=dict)
def coverage_report(session: SessionDep, user: CurrentUser):
    """Vad systemet tacker och inte tacker, pa ett stalle.

    Lases av dashboardens fot. Att visa luckorna ar en funktion: ett system som
    ser komplett ut men bevakar tre av 384 myndigheters karriarsidor ar
    vilseledande.
    """
    from ..seed import coverage

    kallor = session.scalars(select(SourceRegistry)).all()
    return {
        "authorities": coverage(session),
        "sources": {
            "total": len(kallor),
            "automatic": sum(
                1 for k in kallor if k.access_mode in (AccessMode.OPEN_API, AccessMode.PUBLIC_HTML)
            ),
            "manual_only": sum(1 for k in kallor if k.access_mode is AccessMode.MANUAL_ONLY),
            "blocked": sum(1 for k in kallor if k.access_mode is AccessMode.BLOCKED),
            "active": sum(1 for k in kallor if k.status is SourceStatus.ACTIVE),
            "failing": [k.key for k in kallor if k.status is SourceStatus.FAILING],
        },
        "organisations_total": session.scalar(select(func.count()).select_from(Organisation)),
    }
