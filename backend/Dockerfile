# Backend: FastAPI, Celery-worker och beat kor alla ur den har avbilden.
#
# Tva steg. Beroendena installeras i ett eget steg sa att en andring i app/
# inte invaliderar pip-lagret -- det ar skillnaden mellan en ombyggnad pa
# sekunder och en pa minuter.
#
# Inga byggverktyg behovs: psycopg[binary], argon2-cffi och cryptography har
# fardiga wheels for linux/amd64 och linux/arm64. Skulle en framtida beroende
# krava kompilering ar det bara det steget som behover build-essential, inte
# den avbild som gar i drift.

FROM python:3.12-slim AS deps

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY pyproject.toml ./
# En tom app/ racker for att pip ska kunna lasa paketet ur pyproject.
RUN mkdir -p app && touch app/__init__.py && pip install --prefix=/install .


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/install/bin:$PATH" \
    PYTHONPATH=/app

# curl behovs for healthchecken i docker-compose.yml.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=deps /install /install

WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY scripts ./scripts
COPY app ./app

# Bara IVO-annonsen foljer med, enligt .dockerignore. Den ar bestallningens
# obligatoriska testfall och "app.cli seed" kan inte seeda arendet utan den.
#
# Observera samspelet med volymen: compose monterar en namngiven volym pa
# /app/data/snapshots. Docker fyller en TOM namngiven volym med det som ligger
# pa monteringspunkten i avbilden, sa filen hamnar i volymen vid forsta start.
# Pa en volym som redan har innehall gor den inte det -- behover filen laggas
# in i en befintlig installation far den kopieras dit med "docker compose cp".
COPY data ./data

# Snapshots och loggar skrivs hit. Volymen monteras pa samma stalle i compose.
RUN mkdir -p /app/data/snapshots \
    && useradd --create-home --uid 10001 radar \
    && chown -R radar:radar /app/data
USER radar

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
