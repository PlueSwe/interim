"""Tidszonhantering.

Allt lagras i UTC. Problemet ar att det inte kommer tillbaka som UTC: SQLite
har ingen tidszonstyp och lamnar ut naiva datetime-objekt, och flera kallor
skickar tidsstamplar utan zon. Jamfor man ett sadant varde med
datetime.now(UTC) kraschar Python med "can't compare offset-naive and
offset-aware datetimes".

Felet marks inte i ett nyskrivet varde, eftersom det fortfarande har sin zon i
minnet. Det marks forst nar samma rad lasts tillbaka ur databasen, vilket ar
precis vad de nattliga jobben gor. Darfor gar varje sadan jamforelse genom
to_utc.
"""

from __future__ import annotations

import datetime as dt


def to_utc(stamp: dt.datetime | None) -> dt.datetime | None:
    """Gor en tidsstampel jamforbar med datetime.now(dt.UTC).

    Ett naivt varde antas vara UTC, vilket ar sant for allt systemet sjalv har
    skrivit. Ett varde med zon konverteras.
    """
    if stamp is None:
        return None
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=dt.UTC)
    return stamp.astimezone(dt.UTC)


def now() -> dt.datetime:
    """Nu, i UTC. Finns for att inte behova importera dt pa varje stalle."""
    return dt.datetime.now(dt.UTC)
