"""Kallregister, snapshots och insamlingskorningar.

Detta ar systemets bevislager. Allt annat i databasen pekar hit.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Date, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import JSONType, Record, enum_col
from .enums import AccessMode, RunStatus, SourceStatus


class SourceRegistry(Record):
    """En rad per kalla, med vad vi faktiskt far gora med den."""

    __tablename__ = "source_registry"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    access_mode: Mapped[AccessMode] = mapped_column(enum_col(AccessMode), nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    # Varfor kallan far lasas, eller varfor inte. Fritext med flit: skalet ar
    # sallan ett av tre fardiga alternativ.
    legal_note: Mapped[str | None] = mapped_column(Text)
    robots_allows: Mapped[bool | None] = mapped_column()
    robots_checked_at: Mapped[dt.date | None] = mapped_column(Date)

    status: Mapped[SourceStatus] = mapped_column(
        enum_col(SourceStatus), default=SourceStatus.MANUAL_ONLY, nullable=False
    )
    schedule_cron: Mapped[str | None] = mapped_column(String(64))
    last_success_at: Mapped[dt.datetime | None] = mapped_column()
    last_attempt_at: Mapped[dt.datetime | None] = mapped_column()
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONType)

    def __repr__(self) -> str:
        return f"<Source {self.key} {self.access_mode} {self.status}>"


class SourceSnapshot(Record):
    """Radata precis som kallan lamnade den.

    raw sparas som text nar svaret ar textbaserat, annars som sokvag till fil.
    sha256 avgor om nagot andrats; oforandrad data sparas inte igen.
    """

    __tablename__ = "source_snapshots"

    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(128))
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer)
    raw: Mapped[str | None] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # Samma innehall fran samma kalla sparas en gang. Det ar den har
        # begransningen som gor att en nattlig korning inte fyller disken med
        # identiska kopior.
        UniqueConstraint(
            "source_key", "external_id", "sha256", name="uq_source_snapshots_identity"
        ),
        Index("ix_source_snapshots_lookup", "source_key", "external_id", "fetched_at"),
    )

    def __repr__(self) -> str:
        return f"<Snapshot {self.source_key}/{self.external_id} {self.sha256[:12]}>"


class CollectionRun(Record):
    """En rad per insamlingskorning. Detta ar vad dashboardens kallhalsa laser.

    errors raknas separat fran items_found sa att en korning som hittade 40
    annonser och misslyckades med 12 inte ser ut som en lyckad korning.
    """

    __tablename__ = "collection_runs"

    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    status: Mapped[RunStatus] = mapped_column(
        enum_col(RunStatus), default=RunStatus.RUNNING, nullable=False
    )
    items_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str | None] = mapped_column(String(32))

    __table_args__ = (Index("ix_collection_runs_source_started", "source_key", "started_at"),)

    def __repr__(self) -> str:
        return f"<Run {self.source_key} {self.status} found={self.items_found} err={self.errors}>"
