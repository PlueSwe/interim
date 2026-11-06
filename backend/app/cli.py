"""Kommandoradsgranssnitt.

python -m app.cli seed
python -m app.cli create-user --email du@exempel.se --role ADMIN
python -m app.cli collect jobtech_live
python -m app.cli collect --all
python -m app.cli sources
python -m app.cli ivo-case --show
python -m app.cli follow-up
python -m app.cli verify-authority https://www.exempel.se/jobb
python -m app.cli coverage
python -m app.cli retention
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys

from sqlalchemy import func, select

from .db import create_all, session_scope
from .models import (
    Appointment,
    CollectionRun,
    JobAd,
    Opportunity,
    Organisation,
    SourceRegistry,
    User,
    UserRole,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _skriv(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


# --- Kommandon --------------------------------------------------------------


def cmd_initdb(args) -> int:
    create_all()
    print("Tabeller skapade. I drift ska du anvanda: alembic upgrade head")
    return 0


def cmd_seed(args) -> int:
    from .seed import seed_all

    with session_scope() as s:
        resultat = seed_all(s, limit_authorities=args.limit_authorities)
    _skriv(resultat)
    return 0


def cmd_create_user(args) -> int:
    from .security import hash_password

    losenord = args.password or getpass.getpass("Losenord: ")
    if len(losenord) < 12:
        print("Losenordet maste vara minst 12 tecken.", file=sys.stderr)
        return 1
    with session_scope() as s:
        if s.scalar(select(User).where(User.email == args.email)):
            print(f"{args.email} finns redan.", file=sys.stderr)
            return 1
        s.add(
            User(
                email=args.email,
                password_hash=hash_password(losenord),
                role=UserRole(args.role),
                is_active=True,
            )
        )
    print(f"Skapade {args.email} som {args.role}.")
    return 0


def _myndighetsnummer(limit: int | None = None) -> list[str]:
    """Organisationsnummer ur myndighetsregistret, for arbetsgivarsvepet."""
    from .models import Authority, Organisation

    with session_scope() as s:
        fraga = (
            s.query(Organisation.org_number)
            .join(Authority, Authority.organisation_id == Organisation.id)
            .filter(Organisation.org_number.isnot(None))
            .order_by(Organisation.name)
        )
        if limit:
            fraga = fraga.limit(limit)
        return [r[0] for r in fraga.all()]


def cmd_collect(args) -> int:
    from .core.ingest import ingest_run
    from .sources import automatic_keys, get_adapter

    nycklar = automatic_keys() if args.all else [args.source]
    if args.all:
        # authority_pages kraver en URL per myndighet och kors av tasks/jobs.py,
        # inte av "collect --all".
        nycklar = [k for k in nycklar if k != "authority_pages"]

    kod = 0
    for nyckel in nycklar:
        adapter = get_adapter(nyckel)
        print(f"\n=== {nyckel} ({adapter.access.value}) ===")
        parametrar = json.loads(args.params) if args.params else {}
        if getattr(args, "authorities", False):
            # Svep per myndighet i stallet for per sokord. Se _by_employer i
            # sources/jobtech.py for varfor det ar den tillforlitliga vagen.
            orgnr = _myndighetsnummer(args.limit)
            if not orgnr:
                print("  myndighetsregistret ar tomt -- kor 'seed' forst", file=sys.stderr)
                return 1
            print(f"  sveper {len(orgnr)} myndigheter per organisationsnummer")
            parametrar["employers"] = orgnr
        resultat = adapter.run(**parametrar)
        if resultat.skipped:
            print(f"  HOPPADES OVER: {resultat.skip_reason}")
            continue
        if resultat.errors:
            print(f"  FEL: {resultat.error_detail}")
            kod = 1
        with session_scope() as s:
            korning, stats = ingest_run(s, resultat, triggered_by="cli")
            print(
                f"  hittade {stats.found}, nya {stats.new}, andrade {stats.changed}, "
                f"dubbletter {stats.duplicate}, irrelevanta {stats.irrelevant}"
            )
            print(
                f"  exkluderade {stats.excluded}, kraver granskning {stats.review}, "
                f"fel {stats.errors} -> {korning.status.value}"
            )
            for note in stats.notes[:5]:
                print(f"    - {note}")
    return kod


def cmd_reassess(args) -> int:
    """Kor exkluderingsfiltret igen pa redan insamlade uppdrag."""
    from .core.reassess import reassess_exclusions

    with session_scope() as s:
        stats = reassess_exclusions(s, only_stale=not args.all, dry_run=args.dry_run)
        print(stats)
        for rad in stats.noteringar[: args.show]:
            print(f"  {rad}")
        if len(stats.noteringar) > args.show:
            print(f"  ... och {len(stats.noteringar) - args.show} fler")
        if args.dry_run:
            print("  (dry-run: ingenting sparades)")
    return 0


def cmd_sources(args) -> int:
    with session_scope() as s:
        rader = s.scalars(select(SourceRegistry).order_by(SourceRegistry.key)).all()
        if not rader:
            print("Kallregistret ar tomt. Kor: python -m app.cli seed")
            return 1
        print(f"{'KALLA':18} {'LAGE':12} {'STATUS':12} {'ROBOTS':7} SENAST OK")
        for k in rader:
            robots = "-" if k.robots_allows is None else ("ja" if k.robots_allows else "NEJ")
            senast = k.last_success_at.strftime("%Y-%m-%d %H:%M") if k.last_success_at else "aldrig"
            print(
                f"{k.key:18} {k.access_mode.value:12} {k.status.value:12} {robots:7} {senast}"
                + (f"  FEL: {k.last_error[:50]}" if k.last_error else "")
            )
    return 0


def cmd_ivo_case(args) -> int:
    from .seed import describe_ivo_case, seed_ivo_case

    with session_scope() as s:
        resultat = describe_ivo_case(s) if args.show else seed_ivo_case(s)
    _skriv(resultat)
    return 0


def cmd_follow_up(args) -> int:
    """Kor uppfoljningen av avslutade rekryteringar en gang."""
    from .tasks.jobs import follow_up_appointments

    with session_scope() as s:
        resultat = follow_up_appointments(s, search_web=not args.no_web)
    _skriv(resultat)
    return 0


def cmd_verify_authority(args) -> int:
    from .sources import verify_authority

    _skriv(verify_authority(args.url, args.name))
    return 0


def cmd_coverage(args) -> int:
    from .seed import coverage

    with session_scope() as s:
        tackning = coverage(s)
        tackning["job_ads"] = s.scalar(select(func.count()).select_from(JobAd))
        tackning["opportunities"] = s.scalar(select(func.count()).select_from(Opportunity))
        tackning["appointments"] = s.scalar(select(func.count()).select_from(Appointment))
        tackning["organisations"] = s.scalar(select(func.count()).select_from(Organisation))
        tackning["last_runs"] = [
            f"{r.source_key}: {r.status.value} {r.items_found} traffar "
            f"({r.started_at:%Y-%m-%d %H:%M})"
            for r in s.scalars(
                select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(8)
            ).all()
        ]
    _skriv(tackning)
    return 0


def cmd_retention(args) -> int:
    """Radera personuppgifter som passerat lagringstiden."""
    from .tasks.jobs import enforce_retention

    with session_scope() as s:
        _skriv(enforce_retention(s, dry_run=args.dry_run))
    return 0


def cmd_fetch_ad(args) -> int:
    """Hamta en enskild annons och spara den som snapshot."""
    from .core.snapshots import store_snapshot
    from .sources.jobtech import JobTechHistoricalAdapter

    adapter = JobTechHistoricalAdapter()
    post = adapter.fetch_one(args.ad_id)
    if post is None:
        print(f"Ingen annons med id {args.ad_id}", file=sys.stderr)
        return 1
    with session_scope() as s:
        snapshot, ny = store_snapshot(
            s,
            source_key="jobtech_hist",
            external_id=post.external_id,
            payload=post.payload,
            url=post.url,
        )
    print(f"{'Ny' if ny else 'Befintlig'} snapshot {snapshot.sha256[:16]} for {post.title!r}")
    return 0


# --- Argument ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="app.cli", description="Interim Radar")
    sub = p.add_subparsers(dest="kommando", required=True)

    s = sub.add_parser("initdb", help="skapa tabeller (bara utveckling)")
    s.set_defaults(func=cmd_initdb)

    s = sub.add_parser("seed", help="seeda kallor, profil, myndigheter och IVO-arendet")
    s.add_argument("--limit-authorities", type=int, default=None)
    s.set_defaults(func=cmd_seed)

    s = sub.add_parser("create-user", help="skapa anvandare")
    s.add_argument("--email", required=True)
    s.add_argument("--role", default="ANALYST", choices=[r.value for r in UserRole])
    s.add_argument("--password", default=None, help="utelamna for att skriva interaktivt")
    s.set_defaults(func=cmd_create_user)

    s = sub.add_parser("collect", help="kor insamling")
    s.add_argument("source", nargs="?", help="kallans nyckel")
    s.add_argument("--all", action="store_true", help="alla automatiska kallor")
    s.add_argument("--params", default=None, help="JSON med extra parametrar till adaptern")
    s.add_argument(
        "--authorities",
        action="store_true",
        help="svep per myndighet ur registret i stallet for per sokord",
    )
    s.add_argument("--limit", type=int, default=None, help="max antal myndigheter i svepet")
    s.set_defaults(func=cmd_collect)

    s = sub.add_parser("reassess", help="kor exkluderingsfiltret igen pa sparade uppdrag")
    s.add_argument("--all", action="store_true", help="aven de som redan bedomts med denna version")
    s.add_argument("--dry-run", action="store_true", help="visa vad som skulle andras")
    s.add_argument("--show", type=int, default=20, help="hur manga andringar som listas")
    s.set_defaults(func=cmd_reassess)

    s = sub.add_parser("sources", help="visa kallregistret")
    s.set_defaults(func=cmd_sources)

    s = sub.add_parser("ivo-case", help="IVO-testarendet")
    s.add_argument("--show", action="store_true", help="visa i stallet for att seeda")
    s.set_defaults(func=cmd_ivo_case)

    s = sub.add_parser("follow-up", help="folj upp avslutade rekryteringar")
    s.add_argument("--no-web", action="store_true", help="hoppa over websokning")
    s.set_defaults(func=cmd_follow_up)

    s = sub.add_parser("verify-authority", help="prova en myndighets karriarsida")
    s.add_argument("url")
    s.add_argument("--name", default=None)
    s.set_defaults(func=cmd_verify_authority)

    s = sub.add_parser("coverage", help="vad registret tacker")
    s.set_defaults(func=cmd_coverage)

    s = sub.add_parser("retention", help="radera personuppgifter som gatt ut")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_retention)

    s = sub.add_parser("fetch-ad", help="hamta en annons via JobTech-id")
    s.add_argument("ad_id")
    s.set_defaults(func=cmd_fetch_ad)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
