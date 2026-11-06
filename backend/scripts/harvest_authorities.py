"""Bygger myndighetsregistret underifran, ur verklig annonsdata.

Varfor inte en handskriven lista: ett myndighetsregister med organisationsnummer
som nagon skrivit ur minnet ar varre an inget register. Ett fel nummer pekar pa
nagon annans organisation, och det syns inte forran nagon undrar varfor
registratorsadressen inte fungerar.

SCB:s myndighetsregister gick inte att na vid kontrollen (certifikatfel, se
DATA_SOURCES.md). JobTech ger daremot arbetsgivarens organisationsnummer i varje
annons, direkt fran Arbetsformedlingen. Genom att samla arbetsgivare ur annonser
far vi namn och nummer som bada kommer fran kallan.

Skatteverkets nummerserier avgor typen:
  2021 statliga myndigheter   2120 kommuner   2321 regioner

Kor:  python scripts/harvest_authorities.py [--limit-queries N]
Ut:   app/seed/authorities_data.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

LIVE = "https://jobsearch.api.jobtechdev.se/search"
HIST = "https://historical.api.jobtechdev.se/search"
UA = "InterimRadar/0.1 (uppbyggnad av myndighetsregister ur oppna data)"

# Breda sokningar. Syftet ar inte att hitta chefsannonser utan att hitta
# arbetsgivare som ar myndigheter, sa vanliga yrken ger bast tackning.
QUERIES = [
    "handläggare",
    "utredare",
    "jurist",
    "chef",
    "IT",
    "digitalisering",
    "controller",
    "kommunikatör",
    "arkivarie",
    "inspektör",
    "analytiker",
    "verksamhetsutvecklare",
    "registrator",
    "upphandlare",
    "projektledare",
    "systemförvaltare",
    "informationssäkerhet",
    "arkitekt",
    "ekonom",
    "statistiker",
]

OUT = Path(__file__).resolve().parents[1] / "app" / "seed" / "authorities_data.json"

# Namnmonster som avslojar universitet och hogskolor, vilka ocksa ar statliga
# myndigheter men har egen typ i modellen.
UNI = re.compile(r"universitet|högskola|handelshögskolan|karolinska institutet", re.I)


def normalise_orgnr(value: str | None) -> str | None:
    if not value:
        return None
    siffror = re.sub(r"\D", "", value)
    if len(siffror) == 12:
        siffror = siffror[2:]
    return siffror if len(siffror) == 10 else None


def hamta(bas: str, params: dict) -> list[dict]:
    url = bas + "?" + urllib.parse.urlencode(params)
    for forsok in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"accept": "application/json", "User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=40) as r:
                return (json.load(r) or {}).get("hits", [])
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and forsok < 3:
                time.sleep(3 * (forsok + 1))
                continue
            raise
        except Exception:
            if forsok < 3:
                time.sleep(3 * (forsok + 1))
                continue
            raise
    return []


def _case_penalty(namn: str) -> int:
    """Hur onaturligt versaliserat ar namnet? Lagre ar battre.

    Ett svenskt myndighetsnamn har versal forst och sma bokstaver i
    funktionsord: "Inspektionen för vård och omsorg". Varje ord efter det
    forsta som borjar med versal ger straff, och ett helt versalt namn ger
    extra.
    """
    ord_lista = namn.split()
    if not ord_lista:
        return 99
    straff = sum(1 for o in ord_lista[1:] if o[:1].isupper())
    if namn.isupper():
        straff += len(ord_lista)
    return straff


def org_type(orgnr: str, namn: str) -> str | None:
    """Typ ur nummerserien. Namnet far bara finjustera, aldrig avgora.

    Ordningen spelar roll. Avgjorde namnet skulle Chalmers Tekniska Hogskola
    Aktiebolag (556-serien) och ett par folkhogskolor (stiftelser, 8xx) hamna i
    myndighetsregistret, och de ar inte myndigheter. Nummerserien ar det enda
    som faktiskt sager vad organisationen ar.
    """
    if orgnr.startswith("2120"):
        return "MUNICIPALITY"
    if orgnr.startswith("2321"):
        return "REGION"
    if orgnr.startswith("2021"):
        # Statliga larosaten ar myndigheter, men far egen typ enligt modellen.
        return "UNIVERSITY" if UNI.search(namn) else "STATE_AGENCY"
    return None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--limit-queries", type=int, default=len(QUERIES))
    args = p.parse_args()

    # orgnr -> {namn-varianter, webbplatser, antal annonser, senaste annons}
    funna: dict[str, dict] = {}

    for i, fraga in enumerate(QUERIES[: args.limit_queries]):
        for bas, etikett in ((LIVE, "live"), (HIST, "hist")):
            for offset in (0, 100):
                try:
                    traffar = hamta(bas, {"q": fraga, "limit": 100, "offset": offset})
                except Exception as e:
                    print(f"  fel {etikett} {fraga!r}: {str(e)[:70]}")
                    break
                for h in traffar:
                    arb = h.get("employer") or {}
                    orgnr = normalise_orgnr(arb.get("organization_number"))
                    namn = (arb.get("name") or "").strip()
                    if not orgnr or not namn:
                        continue
                    typ = org_type(orgnr, namn)
                    if typ is None:
                        continue  # privat arbetsgivare, inte vart uppdrag
                    post = funna.setdefault(
                        orgnr,
                        {
                            "org_number": orgnr,
                            "names": {},
                            "websites": {},
                            "ads": 0,
                            "org_type": typ,
                            "latest_ad": None,
                        },
                    )
                    post["names"][namn] = post["names"].get(namn, 0) + 1
                    if url := (arb.get("url") or "").strip():
                        post["websites"][url] = post["websites"].get(url, 0) + 1
                    post["ads"] += 1
                    pd = (h.get("publication_date") or "")[:10]
                    if pd and (post["latest_ad"] is None or pd > post["latest_ad"]):
                        post["latest_ad"] = pd
                if len(traffar) < 100:
                    break
        print(f"{i + 1}/{args.limit_queries} {fraga!r}: {len(funna)} organisationer")
        time.sleep(0.3)

    # Valj namnvariant. JobTech har bade "Inspektionen För Vård och Omsorg" och
    # "Inspektionen för vård och omsorg" for samma myndighet, och ibland
    # "GÖTEBORGS KOMMUN" i versaler.
    #
    # Att ta den vanligaste duger inte: versalvarianten ar ofta vanligare,
    # eftersom den kommer fran ett register snarare an fran myndigheten sjalv.
    # Namnet hamnar i brev till registrator, sa det ska vara stavat som
    # myndigheten stavar det. Darfor rankas varianter forst pa naturlig svensk
    # versalisering -- fa stora bokstaver mitt i namnet -- och forst darefter pa
    # hur vanliga de ar.
    rader = []
    for post in funna.values():
        namn = max(post["names"].items(), key=lambda kv: (-_case_penalty(kv[0]), kv[1]))[0]
        webb = max(post["websites"].items(), key=lambda kv: kv[1])[0] if post["websites"] else None
        rader.append(
            {
                "name": namn,
                "org_number": post["org_number"],
                "org_type": post["org_type"],
                "website": webb,
                "ad_count": post["ads"],
                "latest_ad": post["latest_ad"],
                "name_variants": sorted(post["names"]),
                # Bada falten kommer fran kallan, inte fran en gissning.
                "verified_at": dt.date.today().isoformat(),
                "verification_source": "JobTech employer.organization_number",
            }
        )

    rader.sort(key=lambda r: (-r["ad_count"], r["name"]))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "harvested_at": dt.datetime.now(dt.UTC).isoformat(),
                "source": "JobTech Dev (jobsearch + historical), oppna data",
                "method": (
                    "Arbetsgivare ur annonser, filtrerade pa Skatteverkets "
                    "nummerserier 2021/2120/2321. Inga nummer ar gissade."
                ),
                "count": len(rader),
                "authorities": rader,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )

    per_typ: dict[str, int] = {}
    for r in rader:
        per_typ[r["org_type"]] = per_typ.get(r["org_type"], 0) + 1
    print(f"\nKLART. {len(rader)} organisationer -> {OUT}")
    for typ, antal in sorted(per_typ.items()):
        print(f"  {typ:16} {antal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
