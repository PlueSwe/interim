"""AI-lagret.

Tva saker och inget mer: en adapter mot en sprakmodell (provider) och ett
kontrakt for hur dess svar far anvandas (classify).

Kontraktet ar det viktiga. Modellen far foresla, aldrig faststalla. Varje
pastaende maste komma med ett ordagrant citat ur annonsen, och ett pastaende
vars citat inte gar att hitta i texten kastas. Det ar enda satt vi kan uppfylla
bestallningens krav att AI inte far hitta pa kvalifikationer eller anta att krav
ar uppfyllda -- en modell som halucinerar ett citat avslojar sig sjalv.
"""

from __future__ import annotations

from .classify import (
    AIResult,
    Claim,
    assess_exclusion,
    combine_verdicts,
    extract_requirements,
    verify_claims,
)
from .provider import (
    AIProvider,
    AIResponse,
    AnthropicProvider,
    LocalProvider,
    NullProvider,
    get_provider,
)

__all__ = [
    "AIProvider",
    "AIResponse",
    "AIResult",
    "AnthropicProvider",
    "Claim",
    "LocalProvider",
    "NullProvider",
    "assess_exclusion",
    "combine_verdicts",
    "extract_requirements",
    "get_provider",
    "verify_claims",
]
