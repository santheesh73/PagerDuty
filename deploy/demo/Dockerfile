# syntax=docker/dockerfile:1.7
# Pulse as ONE container, for free hosting tiers (Render, Koyeb, Fly). Django serves the API and
# the built SPA; there is no Redis and no Celery (DEMO_MODE), and POST /internal/tick/ does Beat's
# job when an external scheduler calls it. Build context: the repository root.
#
#   docker build -f deploy/demo/Dockerfile -t pulse-demo .
#
# docs/DEPLOY.md has the trade-offs. The full stack (workers, Beat, Redis, nginx) is
# docker-compose.prod.yml.

FROM node:22.22-alpine AS spa
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# A public demo prints its shared logins on the sign-in page.
ARG VITE_SHOW_DEMO_CREDENTIALS=true
ARG VITE_RELEASE=
ENV VITE_SHOW_DEMO_CREDENTIALS=$VITE_SHOW_DEMO_CREDENTIALS VITE_RELEASE=$VITE_RELEASE
RUN npm run build && npm run check:bundle

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
# Same as backend/Dockerfile: uv builds the venv, then pip (unused, and a scan finding) goes.
RUN pip install --no-cache-dir uv==0.11.32 && pip uninstall --yes pip
WORKDIR /app
RUN groupadd --system pulse && useradd --system --gid pulse --home /app pulse
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY backend/ ./
COPY --from=spa /app/dist /app/spa
RUN DJANGO_SETTINGS_MODULE=config.settings.dev python manage.py collectstatic --noinput \
    && chown -R pulse:pulse /app
USER pulse
# The demo's shape. Everything here can be overridden by the platform's environment.
#   REQUIRE_MFA_FOR_ADMINS=0  the shared demo admin must sign in without enrolling (and demo
#                             accounts cannot turn MFA on: apps/core/demo.py)
#   DEMO_RESET_HOURS=24       visitors can change anything, so it is reseeded daily
#   DEMO_SELF_TICK_SECONDS=30 timers advance while anyone is using it, with no scheduler at all
ENV DJANGO_SETTINGS_MODULE=config.settings.prod \
    DEMO_MODE=1 \
    SPA_DIR=/app/spa \
    SEED_DEMO=1 \
    DEMO_RESET_HOURS=24 \
    DEMO_SELF_TICK_SECONDS=30 \
    REQUIRE_MFA_FOR_ADMINS=0 \
    GUNICORN_WORKERS=2
EXPOSE 8000
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["api"]
