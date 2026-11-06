#!/usr/bin/env bash
# Prova att aterstalla den senaste sakerhetskopian. Pa riktigt.
#
# Skriptet skapar en tillfallig databas vid sidan av den riktiga, aterstaller
# dumpen dit, raknar rader i de tabeller som betyder nagot och slapper
# databasen igen. Den riktiga databasen rors inte.
#
# Varfor: en dump som aldrig aterstallts ar ett pastaende, inte en
# sakerhetskopia. Det vanliga felet ar att dumpen gar igenom men aterstallningen
# fallerar pa ett tillagg som saknas -- pgvector, till exempel. Det marks forst
# den dag man behover filen, och da ar det for sent.
#
# Kor manuellt efter varje schemaandring, och fran crontab en gang i veckan:
#   0 4 * * 0 /srv/interim-radar/scripts/restore_test.sh >> /var/log/radar-restore.log 2>&1

set -euo pipefail

ROT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROT"

# shellcheck disable=SC1091
set -a; [ -f .env ] && . ./.env; set +a

DB_USER="${POSTGRES_USER:-radar}"
DB_NAME="${POSTGRES_DB:-interim_radar}"
PROV_DB="${DB_NAME}_restore_test"
UT_I_CONTAINER="/backups"

# Tabeller vars innehall ar sjalva poangen med systemet. Ar nagon av dem tom
# efter en aterstallning ar kopian vardelos aven om pg_restore sa noll fel.
VIKTIGA=(job_ads opportunities exclusion_records appointments source_snapshots authorities)

FIL="${1:-}"
if [ -z "$FIL" ]; then
  FIL="$(ls -1t "$ROT"/backups/interim-radar-*.dump 2>/dev/null | head -n1 || true)"
  if [ -z "$FIL" ]; then
    echo "FEL: ingen dump i $ROT/backups. Kor scripts/backup.sh forst." >&2
    exit 1
  fi
fi
BASNAMN="$(basename "$FIL")"

psql_prov() {
  docker compose exec -T db psql --username="$DB_USER" --dbname="$PROV_DB" -tAq -c "$1"
}

stad() {
  echo "[$(date -u +%FT%TZ)] slapper $PROV_DB"
  docker compose exec -T db psql --username="$DB_USER" --dbname=postgres -q \
    -c "DROP DATABASE IF EXISTS \"$PROV_DB\" WITH (FORCE)" || true
}
trap stad EXIT

echo "[$(date -u +%FT%TZ)] provar $BASNAMN"

docker compose exec -T db psql --username="$DB_USER" --dbname=postgres -q \
  -c "DROP DATABASE IF EXISTS \"$PROV_DB\" WITH (FORCE)"
docker compose exec -T db psql --username="$DB_USER" --dbname=postgres -q \
  -c "CREATE DATABASE \"$PROV_DB\" OWNER \"$DB_USER\""

# pgvector maste finnas innan tabellerna skapas, annars faller
# "embedding vector(1024)". Dumpen innehaller CREATE EXTENSION, men bara om den
# togs med --create; den har raden gor provet oberoende av det.
docker compose exec -T db psql --username="$DB_USER" --dbname="$PROV_DB" -q \
  -c "CREATE EXTENSION IF NOT EXISTS vector"

# --exit-on-error: en aterstallning som "nastan" gick igenom ar ett fel.
# Utan flaggan skriver pg_restore varningar och returnerar 0, och da ser ett
# trasigt prov ut som ett lyckat.
if ! docker compose exec -T db pg_restore \
      --username="$DB_USER" --dbname="$PROV_DB" \
      --no-owner --no-privileges --exit-on-error \
      "$UT_I_CONTAINER/$BASNAMN"; then
  echo "FEL: pg_restore misslyckades for $BASNAMN" >&2
  exit 1
fi

echo "[$(date -u +%FT%TZ)] aterstalld utan fel, raknar rader"

TABELLER="$(psql_prov "select count(*) from information_schema.tables where table_schema='public'")"
echo "  tabeller i schemat: $TABELLER"
if [ "$TABELLER" -lt 25 ]; then
  echo "FEL: forvantade minst 25 tabeller, hittade $TABELLER" >&2
  exit 1
fi

# Alembics egen tabell ska peka pa en revision. Gor den inte det ar databasen
# aterstalld utan versionshistoria, och nasta migrering kommer att kora om allt.
REV="$(psql_prov "select version_num from alembic_version" || true)"
if [ -z "$REV" ]; then
  echo "FEL: alembic_version ar tom. Databasen vet inte vilken revision den ar pa." >&2
  exit 1
fi
echo "  alembic-revision: $REV"

TOMMA=0
for t in "${VIKTIGA[@]}"; do
  N="$(psql_prov "select count(*) from \"$t\"" || echo "FEL")"
  printf '  %-20s %s\n' "$t" "$N"
  if [ "$N" = "0" ]; then TOMMA=$((TOMMA + 1)); fi
done

if [ "$TOMMA" -gt 0 ]; then
  echo "VARNING: $TOMMA av ${#VIKTIGA[@]} viktiga tabeller ar tomma." >&2
  echo "Pa ett nytt system ar det vantat. Pa ett system i drift ar det ett fel." >&2
fi

echo "[$(date -u +%FT%TZ)] OK: $BASNAMN gar att aterstalla"
