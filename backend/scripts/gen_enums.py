"""Generera frontendens enum-typer ur backendens enums.

Bakgrunden: typerna var forst skrivna for hand, och fem av dem hade fel varden
-- OpportunityStatus hade NEW och REVIEWED, SourceStatus hade PAUSED,
AppointmentPublicationMode hade WEB. Inget av det syntes i tsc, eftersom en
felstavad strangunion ar en fullt giltig strangunion. Det syns i granssnittet
forst som ett filter som aldrig traffar.

Nu genereras unionerna harifran. Etiketterna pa svenska ligger kvar i
frontend/lib/format.ts som Record<Union, string>, vilket gor att tsc klagar sa
snart ett varde laggs till eller tas bort i backend.

Kor: python -m scripts.gen_enums
"""

from __future__ import annotations

import enum
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app.models import enums as e  # noqa: E402

# De enums som nar frontend genom app/schemas.py. Resten ar interna.
EXPORTERADE = [
    "AccessMode",
    "AppointmentPublicationMode",
    "AppointmentStatus",
    "Assessor",
    "CollectionMethod",
    "DocumentType",
    "EmploymentType",
    "ExclusionVerdict",
    "LegalBasis",
    "NoticeType",
    "OpportunityKind",
    "OpportunityStatus",
    "OrgType",
    "ProviderRole",
    "RecruitmentPlatform",
    "RequestStatus",
    "RoleFamily",
    "RunStatus",
    "SourceStatus",
    "UserRole",
]

HUVUD = """// GENERERAD FIL -- andra inte har.
//
// Skapad av backend/scripts/gen_enums.py ur app/models/enums.py.
// Kor om efter en andring i backendens enums:
//
//     cd backend && python -m scripts.gen_enums
//
// Etiketterna pa svenska ligger i lib/format.ts. De ar skrivna som
// Record<Union, string>, sa tsc sager till om ett varde har lagts till eller
// tagits bort.

"""


def typescript() -> str:
    delar = [HUVUD]
    for namn in EXPORTERADE:
        klass = getattr(e, namn, None)
        if klass is None or not (isinstance(klass, type) and issubclass(klass, enum.Enum)):
            raise SystemExit(f"{namn} finns inte i app.models.enums")
        varden = [m.value for m in klass]
        if len(varden) <= 3:
            rad = " | ".join(f'"{v}"' for v in varden)
            delar.append(f"export type {namn} = {rad};\n")
        else:
            rader = "\n".join(f'  | "{v}"' for v in varden)
            delar.append(f"export type {namn} =\n{rader};\n")
    return "\n".join(delar)


def main() -> int:
    mal = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "lib" / "enums.ts"
    mal.write_text(typescript(), encoding="utf-8")
    print(f"skrev {mal} ({len(EXPORTERADE)} enums)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
