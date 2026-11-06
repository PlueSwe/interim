#!/usr/bin/env bash
#
# Interim Radar -- installation pa egen server.
#
# Sa har anvands den:
#   1. Oppna filen, fyll i rutan nedan, spara.
#   2. Lagg filen pa servern och kor den dar, inte pa din dator:
#        scp scripts/installera.sh anvandare@din.server:/tmp/
#        ssh anvandare@din.server
#        sudo bash /tmp/installera.sh --kontroll    # svarar bara: duger servern?
#        sudo bash /tmp/installera.sh               # installerar pa riktigt
#
#   Saknas bara Docker skriver --kontroll ut kommandona for distributionen, och
#   `sudo bash /tmp/installera.sh --installera-docker` kor dem.
#
# Losenord och nycklar fylls INTE i har. Skriptet slumpar dem, skriver dem i
# .env med rattigheter 600 och visar admin-losenordet en gang pa skarmen. Ett
# losenord i en fil som ligger kvar i /tmp ar inget losenord, och den har filen
# ska du kunna skicka och spara utan att tanka pa det.
#
# Vad som INTE ingar: TLS-certifikat och domannamn. Stacken lyssnar pa
# 127.0.0.1 och ar tankt bakom en omvand proxy (Caddy eller nginx) som
# terminerar https. Utan proxy kommer du at granssnittet genom en ssh-tunnel,
# och skriptet skriver ut kommandot for det nar det ar klart.


# ======================================================================
#  F Y L L   I   H A R
# ======================================================================

# Adressen du kommer att oppna i webblasaren. Maste stamma exakt, protokoll och
# allt, annars avvisar CSRF-kontrollen inloggningen med "otillaten origin".
# Har du ingen doman an: lamna tomt, da satts http://127.0.0.1:3000 och du
# kommer at granssnittet genom ssh-tunneln.
ADRESS=""

# Din e-post. Blir inloggningsnamnet for admin-kontot, och gar med som
# kontaktuppgift i User-Agent mot myndigheternas webbplatser -- den som undrar
# vem som laser deras sidor ska kunna hora av sig.
ADMIN_EPOST=""

# Var pa servern installationen ska ligga.
KATALOG="/srv/interim-radar"

# Arkivet koden hamtas fran.
GIT_URL="https://github.com/PlueSwe/interim.git"
GIT_GREN="main"

# 127.0.0.1 = bara en proxy pa samma maskin kommer at webben (ratt svar om du
# satter upp Caddy eller nginx, och ratt svar om du anvander ssh-tunneln).
# 0.0.0.0  = oppet mot internet utan TLS. Gor det bara for ett kort prov.
LYSSNA_PA="127.0.0.1"

# Lamna tomt sa slumpas ett losenord och visas en gang. Fyller du i ett eget:
# minst 12 tecken.
ADMIN_LOSENORD=""

# ======================================================================
#  Harefter behover du inte andra nagot.
# ======================================================================

set -euo pipefail

BARA_KONTROLL=0
FIXA_DOCKER=0
case "${1:-}" in
  --kontroll) BARA_KONTROLL=1 ;;
  --installera-docker) FIXA_DOCKER=1 ;;
  "") ;;
  *) printf 'Okand flagga: %s
Anvand --kontroll, --installera-docker eller inget alls.
' "$1" >&2; exit 2 ;;
esac

gron() { printf '\033[32m%s\033[0m\n' "$*"; }
rod() { printf '\033[31m%s\033[0m\n' "$*"; }
rubrik() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
fel() { rod "FEL: $*"; exit 1; }


# ------------------------------------------------------------------ docker
# Docker installeras inte av sig sjalv, och kommandona skiljer sig mellan
# Ubuntu/Debian och Oracle Linux/RHEL. Vi skriver ut dem for ratt distribution
# i stallet for att gissa, och kan kora dem pa begaran.

distro() {
  # shellcheck source=/dev/null
  [ -r /etc/os-release ] && . /etc/os-release
  case "${ID:-}${ID_LIKE:-}" in
    *ubuntu*) echo ubuntu ;;
    *debian*) echo debian ;;
    *rhel* | *fedora* | *ol*) echo rhel ;;
    *) echo okand ;;
  esac
}

docker_kommandon() {
  case "$(distro)" in
    ubuntu | debian)
      D=$(distro)
      cat << KOM
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl
  sudo install -m 0755 -d /etc/apt/keyrings
  sudo curl -fsSL https://download.docker.com/linux/$D/gpg -o /etc/apt/keyrings/docker.asc
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$D \$(. /etc/os-release && echo \$VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable --now docker
KOM
      ;;
    rhel)
      cat << 'KOM'
  sudo dnf -y install dnf-plugins-core
  sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
  sudo systemctl enable --now docker
KOM
      # Oracle Linux har podman forinstallerat. Det ar inte samma sak:
      # docker-compose-plugin finns inte for podman, och stacken anvander det.
      if command -v podman > /dev/null 2>&1; then
        echo
        echo "  (podman ar forinstallerat men duger inte -- stacken behover docker compose v2)"
      fi
      ;;
    *)
      echo "  Okand distribution. Folj https://docs.docker.com/engine/install/"
      echo "  och installera docker-ce och docker-compose-plugin."
      ;;
  esac
}

installera_docker() {
  rubrik "Installerar Docker"
  [ "$(id -u)" -eq 0 ] || fel "kor med sudo: sudo bash $0 --installera-docker"
  case "$(distro)" in
    ubuntu | debian)
      D=$(distro)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update
      apt-get install -y ca-certificates curl
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/$D/gpg" -o /etc/apt/keyrings/docker.asc
      chmod a+r /etc/apt/keyrings/docker.asc
      ARKITEKTUR=$(dpkg --print-architecture)
      KODNAMN=$(. /etc/os-release && echo "$VERSION_CODENAME")
      REPO="https://download.docker.com/linux/$D"
      echo "deb [arch=$ARKITEKTUR signed-by=/etc/apt/keyrings/docker.asc] $REPO $KODNAMN stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update
      apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
      ;;
    rhel)
      dnf -y install dnf-plugins-core
      dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
      dnf -y install docker-ce docker-ce-cli containerd.io docker-compose-plugin
      ;;
    *)
      fel "kanner inte igen distributionen. Kommandona star i --kontroll."
      ;;
  esac
  systemctl enable --now docker
  docker compose version > /dev/null 2>&1 || fel "docker compose v2 kom inte med. Installera docker-compose-plugin."
  gron "Docker installerat."
  echo
  echo "Kor nu installationen:"
  echo "  sudo bash $0"
  exit 0
}

[ "$FIXA_DOCKER" -eq 1 ] && installera_docker


# ---------------------------------------------------------------- kontroll
rubrik "Kontrollerar servern"

BRIST=0
DEMONEN_DOD=0
SAKNAS=""
kraver() {
  if command -v "$1" > /dev/null 2>&1; then
    gron "  ok      $1"
  else
    rod "  saknas  $1 -- $2"
    BRIST=1
    SAKNAS="$SAKNAS $1"
  fi
}

kraver git "apt install git"
kraver docker "https://docs.docker.com/engine/install/"
kraver openssl "apt install openssl"
kraver python3 "apt install python3"

if command -v docker > /dev/null 2>&1; then
  if docker compose version > /dev/null 2>&1; then
    gron "  ok      docker compose"
  else
    rod "  saknas  docker compose (v2) -- paketet heter docker-compose-plugin"
    BRIST=1
    SAKNAS="$SAKNAS docker"
  fi
  if docker info > /dev/null 2>&1; then
    gron "  ok      docker-demonen svarar"
  else
    rod "  fel     docker finns men demonen svarar inte"
    BRIST=1
    DEMONEN_DOD=1
  fi
fi

MINNE_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2> /dev/null || echo 0)
DISK_GB=$(df -BG --output=avail / 2> /dev/null | tail -1 | tr -dc '0-9' || echo 0)
echo "  minne   ${MINNE_MB} MB (sex containrar vill ha minst 2048)"
echo "  disk    ${DISK_GB} GB ledigt pa / (minst 10 rekommenderas)"
if [ "${MINNE_MB:-0}" -lt 1500 ]; then
  rod "  varning: lite minne, Postgres och Next blir trangbodda"
fi

for PORT in 3000 5432 6379; do
  if ss -ltn 2> /dev/null | grep -q ":$PORT "; then
    rod "  varning: nagot lyssnar redan pa port $PORT"
  fi
done

# Ar Docker det enda som fattas ar det inte ett odugligt serverkonto, bara en
# maskin dar inget installerats an. Skilj pa de tva: beskeden ar olika.
SAKNAR_BARA_DOCKER=0
# `case` delar inte upp ord, sa blanktecknen maste bort forst -- det gor
# ordsplittingen i ett ociterat `echo`.
SAKNAS_TRIMMAT=$(echo $SAKNAS)
case "$SAKNAS_TRIMMAT" in
  docker) SAKNAR_BARA_DOCKER=1 ;;
esac

if [ "$BRIST" -ne 0 ] && [ "$DEMONEN_DOD" -eq 1 ]; then
  cat << 'DEMON'

Docker finns pa servern men demonen svarar inte. Antingen kors skriptet utan
root, eller ligger tjansten nere:

  sudo systemctl enable --now docker
  sudo bash /tmp/installera.sh --kontroll

DEMON
  exit 1
fi

if [ "$BRIST" -ne 0 ]; then
  if [ "$SAKNAR_BARA_DOCKER" -eq 1 ]; then
    cat << HJALP

Servern duger i ovrigt -- det ar bara Docker som inte ar installerat an.

Kor ett av de har, beroende pa vad maskinen ar:

$(docker_kommandon)

Eller lat det har skriptet gora det:

  sudo bash $0 --installera-docker

HJALP
    exit 1
  fi
  cat << 'HJALP'

Servern kan inte kora det har som den ar nu. Nagot av det som behovs gar inte
att installera, och da ar det nastan alltid ett webbhotell: ett konto med FTP
och cPanel kor inte Docker, har ingen PostgreSQL och far inte ha processer som
ligger kvar och arbetar -- den har applikationen behover alla tre. FTP racker
alltsa inte, oavsett hur uppgifterna ser ut.

Det som behovs ar en VPS eller en dedikerad server dar du har SSH och root.

HJALP
  exit 1
fi

gron "Servern duger."
if [ "$BARA_KONTROLL" -eq 1 ]; then
  exit 0
fi


# ---------------------------------------------------------------- ifyllt?
rubrik "Kontrollerar det du fyllde i"

if [ -z "$ADMIN_EPOST" ]; then
  fel "ADMIN_EPOST ar tom. Oppna skriptet och fyll i den."
fi
case "$ADMIN_EPOST" in
  *@*.*) ;;
  *) fel "ADMIN_EPOST ser inte ut som en e-postadress: $ADMIN_EPOST" ;;
esac

if [ -z "$ADRESS" ]; then
  ADRESS="http://127.0.0.1:3000"
  echo "  ADRESS tom -> $ADRESS (ssh-tunnel)"
fi
case "$ADRESS" in
  http://* | https://*) ;;
  *) fel "ADRESS maste borja med http:// eller https:// -- nu: $ADRESS" ;;
esac

# Cookien skickas bara over https nar den ar Secure. Over en ssh-tunnel eller
# ren http maste den vara av, annars gar det inte att logga in alls.
case "$ADRESS" in
  https://*) SAKER_COOKIE=true ;;
  *) SAKER_COOKIE=false ;;
esac

if [ -n "$ADMIN_LOSENORD" ] && [ "${#ADMIN_LOSENORD}" -lt 12 ]; then
  fel "ADMIN_LOSENORD ar kortare an 12 tecken."
fi
if [ -z "$ADMIN_LOSENORD" ]; then
  ADMIN_LOSENORD="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
fi

gron "  ok"


# ---------------------------------------------------------------- hamta kod
rubrik "Hamtar koden"

if [ -d "$KATALOG/.git" ]; then
  git -C "$KATALOG" fetch --quiet origin "$GIT_GREN"
  git -C "$KATALOG" checkout --quiet "$GIT_GREN"
  git -C "$KATALOG" reset --hard --quiet "origin/$GIT_GREN"
  echo "  uppdaterade $KATALOG till $(git -C "$KATALOG" rev-parse --short HEAD)"
else
  mkdir -p "$(dirname "$KATALOG")"
  git clone --quiet --branch "$GIT_GREN" "$GIT_URL" "$KATALOG"
  echo "  klonade till $KATALOG ($(git -C "$KATALOG" rev-parse --short HEAD))"
fi
cd "$KATALOG"


# ---------------------------------------------------------------- .env
rubrik "Skriver .env"

satt() {
  # Ersatter "NYCKEL=..." eller en kommenterad rad med nyckeln. Python gor det
  # for att varden kan innehalla / och & som sed tolkar.
  python3 - "$1" "$2" << 'PY'
import pathlib
import re
import sys

nyckel, varde = sys.argv[1], sys.argv[2]
p = pathlib.Path(".env")
ut, gjort = [], False
for rad in p.read_text(encoding="utf-8").splitlines(keepends=True):
    if not gjort and re.match(rf"^#? ?{re.escape(nyckel)}=", rad):
        ut.append(f"{nyckel}={varde}\n")
        gjort = True
    else:
        ut.append(rad)
if not gjort:
    ut.append(f"{nyckel}={varde}\n")
p.write_text("".join(ut), encoding="utf-8")
PY
}

if [ -f .env ]; then
  gron "  .env finns redan och lamnas orord."
  echo "  Nycklarna dar inne far inte bytas av misstag: byts"
  echo "  FIELD_ENCRYPTION_KEY gar redan krypterade falt inte att lasa."
else
  if [ ! -f .env.example ]; then
    fel "saknar .env.example -- ar $KATALOG ratt katalog?"
  fi
  umask 077
  cp .env.example .env

  satt POSTGRES_PASSWORD "$(openssl rand -base64 24)"
  satt SECRET_KEY "$(openssl rand -hex 32)"
  satt FIELD_ENCRYPTION_KEY "$(openssl rand -base64 32)"
  satt CORS_ORIGINS "[\"$ADRESS\"]"
  satt WEB_BIND "$LYSSNA_PA"
  satt COOKIE_SECURE "$SAKER_COOKIE"
  satt ENVIRONMENT prod
  satt USER_AGENT "InterimRadar/0.1 (privat bevakning av offentliga chefsrekryteringar; kontakt: $ADMIN_EPOST)"
  satt NOTIFY_TO "$ADMIN_EPOST"
  chmod 600 .env

  gron "  skrev .env med slumpade nycklar (rattigheter 600)"
  echo "  OBS: ta en kopia av FIELD_ENCRYPTION_KEY pa ett annat stalle an"
  echo "       servern. Tappas den gar krypterade personuppgifter inte att"
  echo "       lasa igen."
fi


# ---------------------------------------------------------------- bygg/starta
rubrik "Bygger och startar (forsta gangen tar det nagra minuter)"

docker compose build
docker compose up -d --wait --wait-timeout 300
docker compose ps


# ---------------------------------------------------------------- seed
rubrik "Fyller databasen"

# api-containern kor "alembic upgrade head" sjalv innan uvicorn, sa schemat
# finns redan nar det har kors.
docker compose exec -T api python -m app.cli seed
docker compose exec -T api python -m app.cli coverage

echo
echo "IVO-arendet (bestallningens obligatoriska testfall):"
docker compose exec -T api python -m app.cli ivo-case --show


# ---------------------------------------------------------------- konto
rubrik "Skapar ditt konto"

if docker compose exec -T api python -m app.cli create-user \
  --email "$ADMIN_EPOST" --role ADMIN --password "$ADMIN_LOSENORD" 2> /dev/null; then
  SKAPADE=1
else
  SKAPADE=0
  echo "  kontot $ADMIN_EPOST fanns redan -- losenordet ar oforandrat"
fi


# ---------------------------------------------------------------- klart
rubrik "Klart"

echo "Installation:  $KATALOG"
echo "Adress:        $ADRESS"
echo "Lyssnar pa:    $LYSSNA_PA:3000"
echo

if [ "$SKAPADE" -eq 1 ]; then
  echo "Logga in med:"
  echo "  e-post:   $ADMIN_EPOST"
  echo "  losenord: $ADMIN_LOSENORD"
  echo
  echo "Losenordet visas bara har. Spara det i din losenordshanterare nu."
  echo
fi

if [ "$LYSSNA_PA" = "127.0.0.1" ] && [ "$ADRESS" = "http://127.0.0.1:3000" ]; then
  IP="$(hostname -I 2> /dev/null | awk '{print $1}')"
  cat << TUNNEL
Granssnittet ar inte oppet mot internet. Kor det har pa din egen dator:

  ssh -L 3000:127.0.0.1:3000 ${SUDO_USER:-$(whoami)}@${IP:-din.server}

och oppna sedan http://127.0.0.1:3000 i webblasaren.

Nar du vill na den utan tunnel: satt upp Caddy eller nginx med https mot
127.0.0.1:3000, andra CORS_ORIGINS och COOKIE_SECURE=true i .env och kor
"docker compose up -d". .env lamnas orord av det har skriptet, sa de tva
raderna andrar du for hand.

TUNNEL
fi

cat << 'NASTA'
Nyttiga kommandon (kors i installationskatalogen):

  docker compose ps                         vad som kor
  docker compose logs -f api                loggen
  docker compose exec -T api python -m app.cli collect jobtech_live
                                            hamta annonser nu
  docker compose exec -T api python -m app.cli sources
                                            vilka kallor som fungerar
  ./scripts/backup.sh                       sakerhetskopia
  ./scripts/restore_test.sh                 prova att kopian gar att aterstalla
  docker compose down                       stoppa
  git pull && docker compose up -d --build  uppdatera

Insamlingen gar automatiskt via beat-containern. Ingen begaran skickas till
nagon myndighet utan att du godkanner den i granssnittet forst.
NASTA
