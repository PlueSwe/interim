"""Adapter mot en sprakmodell.

Tre leverantorer: Anthropics API, en lokal OpenAI-kompatibel server (Ollama,
vLLM, llama.cpp) och NullProvider.

NullProvider ar standard och ar inte en platshallare. Systemet ska fungera helt
utan AI -- regelmotorn i core/exclusion.py och poangsattningen i core/matching.py
ar deterministiska och behover ingen modell. AI:n ar ett tillagg som kan foresla
saker at en manniska, och nar den inte ar konfigurerad ska det stå att den inte
ar det, inte ge ett tomt eller gissat svar.

Importen av anthropic ar lat. Paketet ar inte en hard beroende, och pa en
maskin utan nyckel ska en saknad modul inte stoppa uppstarten.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..config import settings

log = logging.getLogger("interim_radar.ai")

# Hur lang en annonstext far vara innan den kortas. En annons pa mer an det har
# ar nastan alltid en sida med navigering och cookietext inbakad, och att skicka
# den kostar pengar utan att tillfora nagot.
MAX_TEXT_CHARS = 24_000


@dataclass(frozen=True)
class AIResponse:
    """Svaret fran en leverantor, alltid med proveniens.

    available skiljer "modellen svarade nej" fran "det fanns ingen modell".
    Utan den skillnaden gar det inte att dokumentera varfor ett falt ar tomt,
    och bestallningen kraver att saknad atkomst dokumenteras.
    """

    data: dict[str, Any] | None
    provider: str
    model: str | None
    available: bool
    raw: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.available and self.data is not None and self.error is None


def extract_json(text: str | None) -> dict[str, Any] | None:
    """Plocka ut JSON ur ett modellsvar.

    Modeller lagger garna sitt JSON i en kodstaket eller skriver en rad fore.
    Att vagra sadana svar ger inget battre resultat, bara fler tomma falt, sa
    det forsta objektet i texten accepteras.
    """
    if not text:
        return None
    text = text.strip()
    staket = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if staket:
        text = staket.group(1).strip()
    try:
        varde = json.loads(text)
    except json.JSONDecodeError:
        # Sista forsok: fran forsta { till sista }.
        start, slut = text.find("{"), text.rfind("}")
        if start < 0 or slut <= start:
            return None
        try:
            varde = json.loads(text[start : slut + 1])
        except json.JSONDecodeError:
            return None
    return varde if isinstance(varde, dict) else None


class AIProvider(ABC):
    """En leverantor som kan svara med JSON pa en instruktion."""

    name: str = "abstract"

    @property
    @abstractmethod
    def model(self) -> str | None: ...

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> AIResponse:
        """Stall en fraga och forvanta ett JSON-objekt tillbaka."""

    # Gemensamt for alla leverantorer.
    def _kapad(self, text: str) -> str:
        if len(text) <= MAX_TEXT_CHARS:
            return text
        return text[:MAX_TEXT_CHARS] + "\n\n[texten kortad]"


class NullProvider(AIProvider):
    """Ingen modell. Svarar att det inte finns nagon, aldrig med ett gissat varde."""

    name = "none"

    @property
    def model(self) -> str | None:
        return None

    @property
    def available(self) -> bool:
        return False

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> AIResponse:
        return AIResponse(
            data=None,
            provider=self.name,
            model=None,
            available=False,
            error=(
                "Ingen AI-leverantör är konfigurerad. Sätt AI_PROVIDER och "
                "tillhörande nyckel eller adress för att aktivera förslagen."
            ),
        )


class AnthropicProvider(AIProvider):
    """Anthropics Messages-API."""

    name = "anthropic"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._nyckel = api_key or (
            settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        )
        self._modell = model or settings.anthropic_model
        self._klient: Any | None = None

    @property
    def model(self) -> str | None:
        return self._modell

    @property
    def available(self) -> bool:
        return bool(self._nyckel)

    def _client(self) -> Any:
        if self._klient is None:
            # Lat import: paketet ar valfritt.
            import anthropic

            self._klient = anthropic.Anthropic(api_key=self._nyckel)
        return self._klient

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> AIResponse:
        if not self.available:
            return AIResponse(
                data=None,
                provider=self.name,
                model=self._modell,
                available=False,
                error="ANTHROPIC_API_KEY saknas.",
            )
        try:
            svar = self._client().messages.create(
                model=self._modell,
                max_tokens=max_tokens or settings.ai_max_tokens,
                temperature=0,
                system=system,
                messages=[{"role": "user", "content": self._kapad(user)}],
            )
            text = "".join(
                del_.text for del_ in svar.content if getattr(del_, "type", None) == "text"
            )
        except ModuleNotFoundError:
            return AIResponse(
                data=None,
                provider=self.name,
                model=self._modell,
                available=False,
                error="Paketet anthropic är inte installerat.",
            )
        except Exception as e:  # noqa: BLE001 - leverantorsfel ska dokumenteras, inte krascha
            log.warning("anthropic-anrop misslyckades: %s", e)
            return AIResponse(
                data=None,
                provider=self.name,
                model=self._modell,
                available=True,
                error=f"{type(e).__name__}: {e}",
            )

        return AIResponse(
            data=extract_json(text),
            provider=self.name,
            model=self._modell,
            available=True,
            raw=text,
            error=None if extract_json(text) else "Svaret gick inte att läsa som JSON.",
        )


class LocalProvider(AIProvider):
    """En lokal server med OpenAI-kompatibelt chat-API.

    Finns med for att en myndighetsnara analys ibland inte far lamna huset. Da
    ar en lokal modell skillnaden mellan att ha funktionen och att inte ha den.
    """

    name = "local"

    def __init__(self, base_url: str | None = None, model: str | None = None) -> None:
        self._bas = (base_url or settings.local_llm_base_url or "").rstrip("/")
        self._modell = model or settings.local_llm_model

    @property
    def model(self) -> str | None:
        return self._modell

    @property
    def available(self) -> bool:
        return bool(self._bas)

    def complete_json(self, system: str, user: str, *, max_tokens: int | None = None) -> AIResponse:
        if not self.available:
            return AIResponse(
                data=None,
                provider=self.name,
                model=self._modell,
                available=False,
                error="LOCAL_LLM_BASE_URL saknas.",
            )
        import httpx

        try:
            svar = httpx.post(
                f"{self._bas}/v1/chat/completions",
                json={
                    "model": self._modell,
                    "temperature": 0,
                    "max_tokens": max_tokens or settings.ai_max_tokens,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": self._kapad(user)},
                    ],
                },
                timeout=settings.http_timeout_seconds * 4,
            )
            svar.raise_for_status()
            text = svar.json()["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            log.warning("lokal modell svarade inte: %s", e)
            return AIResponse(
                data=None,
                provider=self.name,
                model=self._modell,
                available=True,
                error=f"{type(e).__name__}: {e}",
            )

        data = extract_json(text)
        return AIResponse(
            data=data,
            provider=self.name,
            model=self._modell,
            available=True,
            raw=text,
            error=None if data else "Svaret gick inte att läsa som JSON.",
        )


_cache: AIProvider | None = None


def get_provider(*, force: str | None = None, fresh: bool = False) -> AIProvider:
    """Leverantoren enligt installningarna. NullProvider nar inget ar satt."""
    global _cache
    val = force or settings.ai_provider
    if not fresh and force is None and _cache is not None:
        return _cache

    if val == "anthropic":
        leverantor: AIProvider = AnthropicProvider()
    elif val == "local":
        leverantor = LocalProvider()
    else:
        leverantor = NullProvider()

    if force is None:
        _cache = leverantor
    return leverantor
