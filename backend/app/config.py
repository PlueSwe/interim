"""Konfiguration. Allt kommer ur miljovariabler; inga hemligheter i koden.

Hemliga varden maskeras i repr sa att en dump av settings inte lacker dem till
loggen. Det ar lattare att gora det en gang har an att komma ihag det pa varje
stalle dar nagon loggar ett objekt.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Grund ---
    app_name: str = "Interim Radar"
    environment: Literal["dev", "prod", "test"] = "dev"
    debug: bool = False

    # Skickas med i varje utgaende anrop sa att en myndighet kan se vem som lasar
    # och hora av sig. En anonym skrapa ar inte ett bra satt att bygga fortroende.
    user_agent: str = (
        "InterimRadar/0.1 (privat bevakning av offentliga chefsrekryteringar; "
        "kontakt via webbplatsens agare)"
    )

    # --- Databas ---
    database_url: str = "postgresql+psycopg://radar:radar@localhost:5432/interim_radar"
    db_echo: bool = False

    # --- Redis och Celery ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Sakerhet ---
    secret_key: SecretStr = SecretStr("byt-ut-mig-i-produktion")
    field_encryption_key: SecretStr | None = None
    access_token_minutes: int = 30
    refresh_token_days: int = 14
    cookie_secure: bool = True
    # Bada skrivsatten for utvecklingsservern. localhost och 127.0.0.1 ar
    # skilda origins for webblasaren, och att bara ha det ena gav ett
    # "otillaten origin" vid inloggning som ser ut som ett fel i koden.
    # I drift satts CORS_ORIGINS explicit till appens egen adress.
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    login_attempts_per_window: int = 5
    login_window_minutes: int = 15
    api_rate_limit: str = "120/minute"

    # --- AI ---
    # Tom nyckel ar ett giltigt lage. Systemet faller tillbaka pa regler.
    ai_provider: Literal["anthropic", "local", "none"] = "none"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    local_llm_base_url: str | None = None
    local_llm_model: str = "llama3.1:8b"
    ai_max_tokens: int = 2048

    # --- Insamling ---
    http_timeout_seconds: int = 30
    http_retries: int = 3
    # Minsta tid mellan anrop mot samma vard. HTML-sidor far langre paus an API:er
    # eftersom de kostar mer for den som star for servern.
    delay_api_seconds: float = 0.5
    delay_html_seconds: float = 5.0
    snapshot_dir: str = "data/snapshots"

    # --- Avisering ---
    notify_match_threshold: int = 80
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    notify_from: str = "radar@localhost"
    notify_to: str | None = None

    # --- Personuppgifter ---
    # Beslutsdatum + 5 ar. Motiverat i SECURITY.md.
    person_retention_years: int = 5

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ai_enabled(self) -> bool:
        if self.ai_provider == "anthropic":
            return self.anthropic_api_key is not None
        if self.ai_provider == "local":
            return self.local_llm_base_url is not None
        return False

    def __repr__(self) -> str:  # pragma: no cover - bekvamlighet vid felsokning
        return f"Settings(environment={self.environment!r}, ai_provider={self.ai_provider!r})"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
