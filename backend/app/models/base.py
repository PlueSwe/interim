"""Bas, mixins och portabla kolumntyper.

Modellerna kors mot PostgreSQL i drift och mot SQLite i enhetstesterna. Det ar
vart att halla eftersom det later testerna kora utan databas, men det kraver att
varje typ som bara finns i Postgres har en variant for SQLite. Det sker har, en
gang, i stallet for i varje modellfil.

Enum lagras som VARCHAR med CHECK-villkor (native_enum=False) i stallet for
Postgres egna enum-typer. Postgres-enum later sig inte andras utan DDL-dans i
Alembic, och vardena i det har systemet kommer att behova andras.
"""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import JSON as SA_JSON
from sqlalchemy import DateTime, Enum, MetaData, Text, func
from sqlalchemy import Uuid as SA_Uuid
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Namngivningsmall sa att Alembic kan andra och ta bort index och villkor senare.
# Utan den far villkoren namn som databasen hittar pa, och da blir migreringarna
# omojliga att skriva.
NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


# --- Portabla typer ---

JSONType = JSONB().with_variant(SA_JSON(), "sqlite")
StrArray = PG_ARRAY(Text()).with_variant(SA_JSON(), "sqlite")

try:  # pgvector finns i drift, men testerna ska inte krava den
    from pgvector.sqlalchemy import Vector

    def vector_type(dim: int) -> Any:
        return Vector(dim).with_variant(SA_JSON(), "sqlite")

except ImportError:  # pragma: no cover

    def vector_type(dim: int) -> Any:
        return SA_JSON()


def enum_col(py_enum: type[enum.Enum], **kw: Any) -> Any:
    """Enum som VARCHAR + CHECK, med Python-namnen som varden i databasen."""
    return Enum(
        py_enum,
        native_enum=False,
        length=48,
        values_callable=lambda e: [m.value for m in e],
        **kw,
    )


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# --- Mixins ---


class PKMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        SA_Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Record(Base, PKMixin, TimestampMixin):
    """Allt i det har systemet har id och tidsstamplar."""

    __abstract__ = True
