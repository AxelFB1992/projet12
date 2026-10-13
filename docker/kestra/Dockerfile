# Image Kestra + uv : Kestra lance directement nos commandes Python (task runner "Process"), sans démarrer d'autres conteneurs.
FROM kestra/kestra:v1.3

USER root

# uv, le même gestionnaire Python que sur ta machine
# Cependant, il utilise son propre environnement uv
ARG UV_VERSION=0.11.32
RUN curl -LsSf https://astral.sh/uv/${UV_VERSION}/install.sh \
    | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

# Environnement Python du projet DANS le conteneur (dans un volume), pour ne jamais toucher au .venv de ta machine. L
# Le code est monté en lecture seule.
ENV UV_PROJECT_ENVIRONMENT=/opt/uv/venv \
    UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_CACHE_DIR=/opt/uv/cache \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

# Pas de statistiques d'usage envoyées par Soda (données RH)
RUN mkdir -p /root/.soda \
    && printf 'send_anonymous_usage_stats: false\n' > /root/.soda/config.yml
