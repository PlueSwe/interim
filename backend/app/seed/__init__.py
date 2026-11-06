"""Seedning av grunddata."""

from __future__ import annotations

from sqlalchemy.orm import Session

from .authorities import coverage, seed_authorities
from .ivo_case import describe as describe_ivo_case
from .ivo_case import seed_ivo_case
from .profile import seed_profile
from .sources import seed_sources


def seed_all(session: Session, *, limit_authorities: int | None = None) -> dict:
    """Kor all seedning i rätt ordning.

    IVO-arendet sist, eftersom det bygger pa att profilen finns (for matchning)
    och pa att organisationen kan skapas.
    """
    resultat: dict = {}
    resultat["sources"] = seed_sources(session)
    profil = seed_profile(session)
    resultat["profile"] = profil.name
    resultat["authorities"] = seed_authorities(session, limit=limit_authorities)
    try:
        resultat["ivo_case"] = seed_ivo_case(session)
    except FileNotFoundError as e:
        # Snapshotet kan saknas i en frisk utcheckning. Det ska synas, inte
        # sabba hela seedningen.
        resultat["ivo_case"] = {"error": str(e)}
    return resultat


__all__ = [
    "coverage",
    "describe_ivo_case",
    "seed_all",
    "seed_authorities",
    "seed_ivo_case",
    "seed_profile",
    "seed_sources",
]
