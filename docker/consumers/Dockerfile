# Image des consommateurs temps réel (chargement, slack).
# Une seule image pour les deux : seule la commande lancée change (docker-compose.yml).
FROM python:3.12-slim

# uv, le même gestionnaire de dépendances que sur ta machine (même version que Kestra)
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# 1. Les dépendances seules : cette couche reste en cache tant que uv.lock ne change pas
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project

# 2. Le code, puis les vitesses max (lues par le filtre Slack, même fichier que dbt)
COPY README.md ./
COPY src ./src
COPY dbt/seeds/vitesses_max.csv ./dbt/seeds/vitesses_max.csv
RUN uv sync --frozen --no-default-groups

# Pas besoin d'être root pour consommer des messages
RUN useradd --create-home appli
USER appli
