# syntax=docker/dockerfile:1.7
# One image, three roles (api / worker / beat) — the command decides which.

FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app
RUN groupadd --system pulse && useradd --system --gid pulse --home /app pulse

# Dependencies first so source edits don't bust the layer cache.
FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY . .
# Dev runs as root on purpose: the source is bind-mounted from the host, and tools like
# makemigrations / ruff / the OpenAPI generator must be able to write into it.
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]

FROM base AS prod
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py collectstatic --noinput \
    && chown -R pulse:pulse /app
USER pulse
ENV DJANGO_SETTINGS_MODULE=config.settings.prod
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]
