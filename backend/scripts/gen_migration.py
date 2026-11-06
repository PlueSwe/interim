"""Skriv den forsta Alembic-revisionen ur modellerna.

Varfor ett skript och inte `alembic revision --autogenerate`: autogenerate
kraver en igang databas att jamfora mot, och den forsta revisionen har inget att
jamfora med. Alternativet -- en migrering som anropar
`Base.metadata.create_all()` -- fungerar men lamnar ingen DDL att lasa i
granskningen, och da gar det inte att se vad som faktiskt kommer att koras.

Det har skriptet kompilerar modellernas DDL for PostgreSQL och skriver ut den
ordagrant i revisionen. Samma sanning (modellerna) och samtidigt en migrering
som gar att lasa rad for rad. Senare andringar gors som vanligt med
`alembic revision --autogenerate`, eftersom det da finns en databas att jamfora
mot.

Kor:  cd backend && python -m scripts.gen_migration
"""

from __future__ import annotations

import datetime as dt
import pathlib
import subprocess
import sys

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.models import Base  # noqa: E402

REVISION = "0001"
UT = pathlib.Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0001_initial.py"

HUVUD = '''"""Grundschema.

Genererad ur app/models av scripts/gen_migration.py. Andra inte for hand --
andra modellerna och kor om skriptet, annars sager koden och databasen olika
saker och det ar precis vad migreringar finns for att forhindra.

Tabeller: {antal}

Revision ID: {rev}
Revises: None
Create Date: {datum}
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "{rev}"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# pgvector behovs for embeddings-kolumnerna. IF NOT EXISTS gor att en databas
# dar nagon redan lagt in tillagget inte stoppar migreringen.
EXTENSIONS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
)

TABELLER: tuple[str, ...] = (
'''

MITTEN = """)

INDEX: tuple[str, ...] = (
"""

SLUT = """)

# Omvand ordning, sa att en tabell aldrig slapps fore den som pekar pa den.
DROPPAR: tuple[str, ...] = (
{droppar})


def upgrade() -> None:
    for sats in EXTENSIONS:
        op.execute(sats)
    for sats in TABELLER:
        op.execute(sats)
    for sats in INDEX:
        op.execute(sats)


def downgrade() -> None:
    for sats in DROPPAR:
        op.execute(sats)
"""


def _ddl(element) -> str:
    return str(element.compile(dialect=postgresql.dialect())).strip()


def main() -> int:
    # Utan pgvector faller models/base.py tillbaka pa JSON, och da skulle
    # migreringen skapa "embedding JSON" i Postgres. Det ar inte ett fel som
    # syns forran nagon forsoker gora en likhetssokning, sa skriptet vagrar
    # hellre an att skriva en migrering som ser riktig ut.
    try:
        import pgvector.sqlalchemy  # noqa: F401
    except ImportError:
        raise SystemExit(
            "pgvector saknas. Installera den forst (pip install pgvector), annars "
            "blir embedding-kolumnen JSON i stallet for vector."
        ) from None

    dialekt = postgresql.dialect()
    tabeller = list(Base.metadata.sorted_tables)

    skapa = [_ddl(CreateTable(t)) for t in tabeller]
    index = [
        _ddl(CreateIndex(ix)) for t in tabeller for ix in sorted(t.indexes, key=lambda i: i.name)
    ]
    droppar = [f'DROP TABLE IF EXISTS "{t.name}" CASCADE' for t in reversed(tabeller)]

    def block(satser: list[str]) -> str:
        rader = []
        for sats in satser:
            if "%" in sats:
                raise SystemExit(f"DDL innehaller %, maste hanteras sarskilt: {sats[:80]}")
            rader.append('    """' + sats + '""",\n')
        return "".join(rader)

    text = (
        HUVUD.format(
            antal=len(tabeller),
            rev=REVISION,
            datum=dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M:%S+00:00"),
        )
        + block(skapa)
        + MITTEN
        + block(index)
        + SLUT.format(droppar=block(droppar))
    )

    UT.parent.mkdir(parents=True, exist_ok=True)
    UT.write_text(text, encoding="utf-8")

    # Formatera resultatet. Utan det har steget skiljer sig filen pa disk fran
    # vad skriptet skriver, sa fort nagon kort "ruff format" over projektet --
    # och CI-jobbet som genererar om och jamfor blev rott pa radbrytningar som
    # inte sager nagot om schemat.
    try:
        klar = subprocess.run(["ruff", "format", "--quiet", str(UT)], check=False)
    except FileNotFoundError:
        print("  varning: ruff ar inte installerad, filen ar oformaterad")
    else:
        if klar.returncode:
            print("  varning: 'ruff format' misslyckades, filen ar oformaterad")
    print(f"skrev {UT.relative_to(UT.parents[2])}")
    print(f"  {len(tabeller)} tabeller, {len(index)} index, dialekt {dialekt.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
