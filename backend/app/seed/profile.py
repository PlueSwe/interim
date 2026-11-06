"""Konsultprofilen.

Utgangsvarden ur bestallningen. Profilen ar redigerbar i gransnittet, och
vikterna ligger i databasen, sa detta ar en startpunkt och inte en sanning.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.matching import DEFAULT_WEIGHTS
from ..models import ConsultantProfile

HEADLINE = "Interim CIO och IT-chef, 15+ ar inom IT-ledning"

EXPERIENCES = [
    {"role": "Interim CIO / IT-chef", "organisation": "Skolinspektionen", "sector": "STATE_AGENCY"},
    {"role": "Interim CIO", "organisation": "Svenska Filminstitutet", "sector": "STATE_AGENCY"},
    {"role": "Interim CIO", "organisation": "Friskis & Svettis", "sector": "PRIVATE"},
    {"role": "Interim CIO", "organisation": "Arla Plastic", "sector": "PRIVATE"},
    {"role": "IT-chef", "organisation": "Kockums", "sector": "PRIVATE"},
    {"role": "IT-chef", "organisation": "Region och kommun", "sector": "REGION"},
]

SKILLS = [
    "IT-ledning",
    "Interim CIO",
    "IT-chef",
    "ITIL",
    "PM3",
    "SAFe",
    "Scrum",
    "IT Service Management",
    "IT-arkitektur",
    "Digitalisering",
    "Forandringsledning",
    "Informationssakerhet",
    "Leverantorsstyrning",
    "Molnmigrering",
    "Hybrid IT",
    "Budgetansvar",
    "Personalansvar",
    "Upphandling och avtalsstyrning",
]

EDUCATION = [
    {"degree": "Magisterexamen", "field": "Datavetenskap"},
    {"degree": "Kandidatexamen", "field": "Informatik"},
]

PREFERENCES = {
    "preferred_locations": ["Stockholm", "Solna", "Uppsala", "Sundbyberg", "Stockholms lan"],
    "accepts_remote": True,
    "min_duration_months": 3,
    "max_duration_months": 24,
    # Satt till None tills anvandaren fyller i. Ett pahittat tal har skulle gora
    # arvodeskriteriet till en gissning i stallet for en okand uppgift.
    "min_fee_sek_per_hour": None,
    "include_permanent_positions": True,
    "sectors": ["STATE_AGENCY", "REGION", "MUNICIPALITY", "UNIVERSITY", "MUNICIPAL_COMPANY"],
}


def seed_profile(session: Session, *, name: str = "Standardprofil") -> ConsultantProfile:
    befintlig = session.scalar(select(ConsultantProfile).where(ConsultantProfile.name == name))
    if befintlig:
        return befintlig
    profil = ConsultantProfile(
        name=name,
        is_active=True,
        headline=HEADLINE,
        experiences=EXPERIENCES,
        skills=SKILLS,
        preferences=PREFERENCES,
        weights=dict(DEFAULT_WEIGHTS),
    )
    profil.preferences["education"] = EDUCATION
    session.add(profil)
    session.flush()
    return profil
