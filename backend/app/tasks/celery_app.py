"""Celery: schemalaggning, ko och retry.

Scheman enligt bestallningen. Jobben sjalva ligger i jobs.py som vanliga
funktioner; har lindas de bara, sa att de gar att kora utan broker fran CLI och
tester.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from ..config import settings
from ..db import session_scope
from . import jobs

celery_app = Celery("interim_radar", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Europe/Stockholm",
    enable_utc=True,
    task_acks_late=True,
    # En insamling som tar over en timme har fastnat. Hellre att den dor och
    # kors om an att den haller en worker upptagen hela natten.
    task_time_limit=3600,
    task_soft_time_limit=3300,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
)

# Grundinstallningar for retry. Adaptrarna har egen retry pa HTTP-niva; detta
# ar for nar hela jobbet far problem, till exempel en databas som startar om.
RETRY = {
    "autoretry_for": (Exception,),
    "retry_backoff": 30,
    "retry_backoff_max": 900,
    "retry_jitter": True,
    "max_retries": 4,
}


@celery_app.task(name="collect_source", **RETRY)
def collect_source_task(source_key: str, **kwargs) -> dict:
    with session_scope() as s:
        return jobs.collect_source(s, source_key, **kwargs)


@celery_app.task(name="sweep_authorities", **RETRY)
def sweep_authorities_task(source_key: str = "jobtech_hist", limit: int | None = None) -> dict:
    with session_scope() as s:
        return jobs.sweep_authorities(s, source_key=source_key, limit=limit)


@celery_app.task(name="collect_authority_pages", **RETRY)
def collect_authority_pages_task(limit: int = 20) -> dict:
    with session_scope() as s:
        return jobs.collect_authority_pages(s, limit=limit)


@celery_app.task(name="follow_up_appointments", **RETRY)
def follow_up_appointments_task() -> dict:
    with session_scope() as s:
        return jobs.follow_up_appointments(s)


@celery_app.task(name="check_deadlines", **RETRY)
def check_deadlines_task() -> dict:
    with session_scope() as s:
        return jobs.check_deadlines(s)


@celery_app.task(name="check_framework_agreements", **RETRY)
def check_framework_agreements_task() -> dict:
    with session_scope() as s:
        return jobs.check_framework_agreements(s)


@celery_app.task(name="check_source_health", **RETRY)
def check_source_health_task() -> dict:
    with session_scope() as s:
        return jobs.check_source_health(s)


@celery_app.task(name="enforce_retention", **RETRY)
def enforce_retention_task() -> dict:
    with session_scope() as s:
        return jobs.enforce_retention(s)


@celery_app.task(name="send_notifications", **RETRY)
def send_notifications_task() -> dict:
    with session_scope() as s:
        return jobs.send_notifications(s)


# Frekvenserna kommer fran bestallningen. Tiderna ar forskjutna sa att inte
# alla jobb startar samtidigt och konkurrerar om samma worker.
celery_app.conf.beat_schedule = {
    # Varannan timme: konsultformedlare och levande annonser.
    "jobtech-live": {
        "task": "collect_source",
        "schedule": crontab(minute=5, hour="*/2"),
        "args": ("jobtech_live",),
    },
    # Var sjatte timme: offentliga upphandlingsdatabaser.
    "ted": {
        "task": "collect_source",
        "schedule": crontab(minute=20, hour="*/6"),
        "args": ("ted",),
    },
    # En gang per dygn: historiska annonser, for att upptacka avpubliceringar.
    "jobtech-historical": {
        "task": "collect_source",
        "schedule": crontab(minute=0, hour=3),
        "args": ("jobtech_hist",),
    },
    # Nattligt svep over myndighetsregistret, per organisationsnummer.
    #
    # Tva korningar med olika kalla, eftersom de svarar pa olika fragor: den
    # levande visar vad som gar att soka nu, den historiska vilka rekryteringar
    # som avslutats och darmed ska foljas mot en tillsattning. Svepet ar det som
    # gor att en tjanst med en oforutsagbar titel anda kommer in.
    "sweep-authorities-live": {
        "task": "sweep_authorities",
        "schedule": crontab(minute=0, hour=1),
        "kwargs": {"source_key": "jobtech_live"},
    },
    "sweep-authorities-historical": {
        "task": "sweep_authorities",
        "schedule": crontab(minute=30, hour=3),
        "kwargs": {"source_key": "jobtech_hist"},
    },
    # En gang per dygn: myndigheternas karriarsidor.
    "authority-pages": {
        "task": "collect_authority_pages",
        "schedule": crontab(minute=30, hour=4),
    },
    # En gang per dygn: uppfoljning av avslutade rekryteringar.
    "follow-up-appointments": {
        "task": "follow_up_appointments",
        "schedule": crontab(minute=0, hour=5),
    },
    # En gang per dygn: ramavtalsbevakning.
    "framework-agreements": {
        "task": "check_framework_agreements",
        "schedule": crontab(minute=30, hour=5),
    },
    "deadlines": {"task": "check_deadlines", "schedule": crontab(minute=0, hour=6)},
    "source-health": {"task": "check_source_health", "schedule": crontab(minute=15, hour=6)},
    # Personuppgifter som gatt ut raderas nattligen.
    "retention": {"task": "enforce_retention", "schedule": crontab(minute=45, hour=2)},
    "notifications": {"task": "send_notifications", "schedule": crontab(minute="*/15")},
}
