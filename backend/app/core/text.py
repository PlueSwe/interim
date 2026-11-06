"""Textnormalisering som delas av dubblettkontroll, matchning och filter.

Ligger samlat eftersom tva olika normaliseringar av samma titel ger tva olika
svar pa fragan om det ar samma annons.
"""

from __future__ import annotations

import re
import unicodedata

# Ord som inte sager nagot om rollen men stor jamforelsen. "IT-chef till
# Skolinspektionen" och "IT-chef, Skolinspektionen" ska bli samma strang.
_FYLLORD = {
    "till",
    "hos",
    "pa",
    "for",
    "med",
    "och",
    "en",
    "ett",
    "vi",
    "soker",
    "nu",
    "dig",
    "som",
    "ar",
    "vill",
    "du",
}

_ICKE_ORD = re.compile(r"[^\w\s-]", re.UNICODE)
_FLERA_BLANK = re.compile(r"\s+")


def strip_diacritics(s: str) -> str:
    """aao -> aao. Bara for jamforelse, aldrig for visning."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalise_title(title: str) -> str:
    """Gemener, utan skiljetecken, utan fyllord, utan dubbla blanksteg.

    Bindestreck behalls: "IT-chef" och "IT chef" ska mota varandra, sa
    bindestreck blir blanksteg, men "e-halsa" far inte bli "ehalsa".
    """
    s = strip_diacritics(title.lower())
    s = s.replace("-", " ")
    s = _ICKE_ORD.sub(" ", s)
    ord_lista = [o for o in _FLERA_BLANK.split(s) if o and o not in _FYLLORD]
    return " ".join(ord_lista).strip()


def normalise_orgnr(value: str | None) -> str | None:
    """Tio siffror utan bindestreck, eller None.

    202100-6537 och 2021006537 ar samma myndighet. Tolvsiffriga nummer med
    sekelprefix kortas till tio.
    """
    if not value:
        return None
    siffror = re.sub(r"\D", "", value)
    if len(siffror) == 12:
        siffror = siffror[2:]
    return siffror if len(siffror) == 10 else None


def token_set(text: str) -> set[str]:
    return set(normalise_title(text).split())


def jaccard(a: str, b: str) -> float:
    """Likhet mellan tva titlar, 0.0-1.0.

    Jaccard pa ordmangder och inte teckenavstand, eftersom titlar skiljer sig
    genom tillagda ord ("IT-chef" vs "IT-chef med personalansvar") snarare an
    genom stavfel.
    """
    sa, sb = token_set(a), token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def excerpt(text: str, offset: int, width: int = 250) -> str:
    """Citat runt en traff, klippt vid ordgrans.

    Anvands for exclusion_records.matched_quote. Bredden ar medvetet begransad:
    ett helt dokument i citatfaltet gor beviset olasbart, och SECURITY.md satter
    500 tecken som tak.
    """
    start = max(0, offset - width)
    end = min(len(text), offset + width)
    bit = text[start:end]
    if start > 0:
        mellanslag = bit.find(" ")
        if 0 <= mellanslag < 40:
            bit = bit[mellanslag + 1 :]
        bit = "..." + bit
    if end < len(text):
        mellanslag = bit.rfind(" ")
        if mellanslag > len(bit) - 40:
            bit = bit[:mellanslag]
        bit = bit + "..."
    return _FLERA_BLANK.sub(" ", bit).strip()
