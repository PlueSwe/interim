#!/usr/bin/env bash
# Sakerhetskopia av databasen. Korst pa varden, inte i containern.
#
# Formatet ar pg_dumps egna (-Fc). Det ar komprimerat, gar att aterstalla
# selektivt med pg_restore och behover ingen psql-session for att lasas.
#
# Lagg i crontab pa VPS:en, till exempel kl 02:
#   0 2 * * * /srv/interim-radar/scripts/backup.sh >> /var/log/radar-backup.log 2>&1
#
# En sakerhetskopia ingen har aterstallt ar inte en sakerhetskopia. Kor
# scripts/restore_test.sh regelbundet -- den provar den senaste filen pa riktigt.

set -euo pipefail

ROT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROT"

# shellcheck disable=SC1091
set -a; [ -f .env ] && . ./.env; set +a

DB_USER="${POSTGRES_USER:-radar}"
DB_NAME="${POSTGRES_DB:-interim_radar}"
BEHALL_DAGAR="${BACKUP_KEEP_DAYS:-30}"
# Samma sokvag som volymen ./backups:/backups i docker-compose.yml.
UT_I_CONTAINER="/backups"
UT_PA_VARD="$ROT/backups"

# pg_dump skriver filen inifran db-containern, dar processen kor som postgres
# (uid 999 i den officiella avbilden). Katalogen maste darfor vara skrivbar for
# den anvandaren, inte bara for den som kor skriptet. Pa en VPS:
#   sudo chown 999:999 backups
mkdir -p "$UT_PA_VARD"
if ! docker compose exec -T db test -w /backups; then
  echo "FEL: /backups ar inte skrivbar for db-containern." >&2
  echo "Kor: sudo chown 999:999 \"$UT_PA_VARD\"" >&2
  exit 1
fi

STAMPEL="$(date -u +%Y%m%dT%H%M%SZ)"
FIL="interim-radar-${STAMPEL}.dump"

echo "[$(date -u +%FT%TZ)] dumpar $DB_NAME -> backups/$FIL"

docker compose exec -T db \
  pg_dump --username="$DB_USER" --dbname="$DB_NAME" --format=custom --compress=9 \
          --file="$UT_I_CONTAINER/$FIL"

# Storleken ar den enda billiga rimlighetskontrollen. En dump pa nagra kilobyte
# ar antingen en tom databas eller en misslyckad dump, och bada ska syna nu och
# inte den dag nagon behover filen.
BYTE="$(stat -c %s "$UT_PA_VARD/$FIL" 2>/dev/null || stat -f %z "$UT_PA_VARD/$FIL")"
if [ "$BYTE" -lt 10240 ]; then
  echo "FEL: dumpen ar bara $BYTE byte. Kontrollera databasen." >&2
  exit 1
fi

# Lista innehallet. Gar det inte att lasa innehallsforteckningen ar filen trasig.
docker compose exec -T db pg_restore --list "$UT_I_CONTAINER/$FIL" > /dev/null
echo "[$(date -u +%FT%TZ)] klar: $FIL ($((BYTE / 1024)) kB), innehallsforteckning lasbar"

# Gallring. -mtime raknar hela dygn, sa +30 betyder aldre an 31 dygn.
RENSADE="$(find "$UT_PA_VARD" -name 'interim-radar-*.dump' -type f -mtime "+$BEHALL_DAGAR" -print -delete | wc -l)"
echo "[$(date -u +%FT%TZ)] gallrade $RENSADE fil(er) aldre an $BEHALL_DAGAR dagar"
