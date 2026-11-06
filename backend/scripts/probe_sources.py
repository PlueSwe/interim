"""Kontrollera vilka kallor som faktiskt svarar, just nu.

Bestallningen kraver att det framgar vilka kallor som fungerar och vilka som
kraver manuell atkomst, och att saknad atkomst dokumenteras i stallet for att
doljas. Registret i app/sources/__init__.py ar ett pastaende om hur det ligger
till; det har skriptet provar pastaendet.

Skriptet hamtar ingen data och lagger ingenting i databasen. Det gor en
HEAD- eller GET-forfragan per kalla, laser robots.txt och skriver ut vad det
fick. En kalla med access MANUAL_ONLY eller BLOCKED kontaktas inte alls -- det
vore att prova en dorr vi redan vet att vi inte far oppna.

Kor:
    cd backend && python -m scripts.probe_sources
    cd backend && python -m scripts.probe_sources --json > kallor.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.config import settings  # noqa: E402
from app.models import AccessMode  # noqa: E402
from app.sources import ADAPTERS, DECLARED_SOURCES  # noqa: E402
from app.sources.base import robots_allows  # noqa: E402

# Lagen vi inte provar, och varfor.
EJ_KONTAKTAS = {
    AccessMode.MANUAL_ONLY: "manuell atkomst, kontaktas inte",
    AccessMode.BLOCKED: "atkomst saknas, kontaktas inte",
}


def _prova(url: str) -> dict:
    """En forfragan. Returnerar vad som hande, aldrig en gissning."""
    huvuden = {"User-Agent": settings.user_agent}
    start = time.monotonic()
    try:
        svar = httpx.get(
            url,
            headers=huvuden,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        )
        ms = int((time.monotonic() - start) * 1000)
        return {
            "status": svar.status_code,
            "ms": ms,
            "slutlig_url": str(svar.url) if str(svar.url) != url else None,
            "innehallstyp": svar.headers.get("content-type", "").split(";")[0] or None,
            "fel": None,
        }
    except Exception as e:  # noqa: BLE001 - alla fel ska rapporteras, inte kasta
        return {
            "status": None,
            "ms": int((time.monotonic() - start) * 1000),
            "slutlig_url": None,
            "innehallstyp": None,
            "fel": f"{type(e).__name__}: {e}",
        }


def _bedom(rad: dict) -> str:
    if rad["kontaktad"] is False:
        return "EJ PROVAD"
    if rad["fel"]:
        return "FEL"
    if rad["robots"] is False:
        return "ROBOTS NEKAR"
    status = rad["status"]
    if status is None:
        return "FEL"
    if 200 <= status < 300:
        return "OK"
    if status in (401, 403):
        return "KRAVER INLOGGNING"
    # Ett API som bara svarar pa POST ger 405 eller 404 pa en GET. Det betyder
    # att varden finns och svarar -- att kalla det SAKNAS vore fel, och ett
    # falskt larm om en kalla som fungerar ar lika illa som ett uteblivet.
    if status in (404, 405) and rad["lage"] == AccessMode.OPEN_API.value:
        return "SVARAR (ej GET)"
    if status == 404:
        return "SAKNAS"
    return f"HTTP {status}"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="scripts.probe_sources", description=__doc__)
    p.add_argument("--json", action="store_true", help="skriv JSON i stallet for tabell")
    p.add_argument("--only", help="bara kallor vars nyckel innehaller detta")
    args = p.parse_args(argv)

    rader: list[dict] = []
    for kalla in DECLARED_SOURCES:
        if args.only and args.only not in kalla.key:
            continue

        rad: dict = {
            "nyckel": kalla.key,
            "namn": kalla.name,
            "lage": kalla.access.value,
            "status_i_registret": kalla.status.value,
            "adapter": kalla.key in ADAPTERS,
            "url": kalla.base_url,
            "kontaktad": False,
            "robots": None,
            "status": None,
            "ms": None,
            "slutlig_url": None,
            "innehallstyp": None,
            "fel": None,
            "anteckning": kalla.legal_note,
        }

        # Finns en adapter ar dess base_url den faktiska slutpunkten, inte
        # bara varden. Att prova den sager nagot om integrationen; att prova
        # roten sager bara att servern lever.
        adapter = ADAPTERS.get(kalla.key)
        prov_url = getattr(adapter, "base_url", None) or kalla.base_url
        rad["provad_url"] = prov_url

        skal = EJ_KONTAKTAS.get(kalla.access)
        if skal or not prov_url:
            rad["fel"] = skal or "ingen adress i registret"
            rader.append(rad)
            continue

        rad["kontaktad"] = True
        rad["robots"] = robots_allows(prov_url)
        if rad["robots"] is False:
            # robots.txt sager nej. Da gor vi ingen forfragan alls.
            rader.append(rad)
            continue

        rad.update(_prova(prov_url))
        rader.append(rad)
        # Samma hovlighet som insamlingen.
        time.sleep(settings.delay_api_seconds)

    for rad in rader:
        rad["bedomning"] = _bedom(rad)

    if args.json:
        print(
            json.dumps(
                {"kord": dt.datetime.now(dt.UTC).isoformat(), "kallor": rader},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    bredd = max(len(r["nyckel"]) for r in rader) if rader else 10
    print(f"Kontroll {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}")
    print(f"User-Agent: {settings.user_agent}\n")
    print(f"{'nyckel'.ljust(bredd)}  {'lage':<12}  {'bedomning':<18}  detalj")
    print("-" * (bredd + 60))
    for r in rader:
        detalj = r["fel"] or ""
        if not detalj and r["status"]:
            detalj = f"HTTP {r['status']} pa {r['ms']} ms"
            if r["slutlig_url"]:
                detalj += f" -> {r['slutlig_url']}"
        if r["robots"] is False:
            detalj = "robots.txt forbjuder hamtning"
        if not r["adapter"] and r["kontaktad"]:
            detalj += "  [ingen adapter]"
        print(f"{r['nyckel'].ljust(bredd)}  {r['lage']:<12}  {r['bedomning']:<18}  {detalj}")

    antal = {}
    for r in rader:
        antal[r["bedomning"]] = antal.get(r["bedomning"], 0) + 1
    print("\n" + ", ".join(f"{v} {k.lower()}" for k, v in sorted(antal.items())))
    print(
        "\nEn kalla som star som EJ PROVAD kontaktas inte med flit. Se kolumnen\n"
        "lage och anteckningen i app/sources/__init__.py for varfor."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
