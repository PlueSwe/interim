"""Anvandare, aviseringar, sparade sokningar och revisionslogg."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .base import JSONType, Record, enum_col
from .enums import NotificationKind, NotificationStatus, UserRole


class User(Record):
    """Ingen publik registrering. Konton skapas med app.cli create-user."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_col(UserRole), default=UserRole.ANALYST, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[dt.datetime | None] = mapped_column()

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"


class Notification(Record):
    """Kolagd avisering.

    dedupe_key hindrar att samma handelse aviseras varje gang en insamling
    kor. Utan den skickar systemet samma "ny tjanst hos IVO" varannan timme.
    """

    __tablename__ = "notifications"

    kind: Mapped[NotificationKind] = mapped_column(enum_col(NotificationKind), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONType)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_col(NotificationStatus), default=NotificationStatus.QUEUED, nullable=False
    )
    queued_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    sent_at: Mapped[dt.datetime | None] = mapped_column()
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("kind", "dedupe_key", name="uq_notifications_dedupe"),
        Index("ix_notifications_status_queued", "status", "queued_at"),
    )

    def __repr__(self) -> str:
        return f"<Notification {self.kind} {self.status}>"


class SavedSearch(Record):
    __tablename__ = "saved_searches"

    user_id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    filters: Mapped[dict] = mapped_column(JSONType, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_saved_searches_user_name"),)


class AuditLog(Record):
    """Skrivs for varje manuell andring som paverkar ett beslut.

    before och after sparas som JSON sa att en felaktig overprovning gar att se
    i efterhand, inte bara att den gjordes.
    """

    __tablename__ = "audit_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        SA_Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict | None] = mapped_column(JSONType)
    after: Mapped[dict | None] = mapped_column(JSONType)
    ip: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[dt.datetime] = mapped_column(nullable=False)

    __table_args__ = (
        Index("ix_audit_logs_object", "object_type", "object_id"),
        Index("ix_audit_logs_at", "at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog {self.action} {self.object_type}/{self.object_id}>"
