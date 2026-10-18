# syntax=docker/dockerfile:1.7
FROM node:26.12-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Dev: Vite dev server with HMR; proxies /api to the backend container.
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

# Prod: static bundle served by nginx, /api proxied to the backend.
FROM deps AS build
# Public demo deployments show the demo logins on the sign-in page.
ARG VITE_SHOW_DEMO_CREDENTIALS=false
ENV VITE_SHOW_DEMO_CREDENTIALS=$VITE_SHOW_DEMO_CREDENTIALS
# Error reporting is off unless a DSN is given. The release is the git SHA so Sentry can
# group errors by deploy. (A DSN is a public, write-only identifier; it is not a secret.)
ARG VITE_SENTRY_DSN=
ARG VITE_RELEASE=
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN VITE_RELEASE=$VITE_RELEASE
COPY . .
RUN npm run build

FROM nginx:1.31-alpine AS prod
# Runs as the unprivileged `nginx` user, not root: it listens on 8080 (no privileged port), keeps
# its pid file in /tmp, and may write only the config files the entrypoint generates at start.
ENV PORT=8080 API_UPSTREAM=http://backend:8000
# `apk upgrade` takes the base image's OS packages up to their fixed versions.
RUN apk upgrade --no-cache \
    && sed -i -e '/^user /d' -e 's,^pid .*,pid /tmp/nginx.pid;,' /etc/nginx/nginx.conf \
    && rm -f /etc/nginx/conf.d/default.conf \
    && touch /etc/nginx/pulse-headers.conf \
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d /etc/nginx/pulse-headers.conf
COPY docker/nginx.conf /etc/nginx/templates/default.conf.template
COPY --chmod=0755 docker/15-pulse-headers.envsh /docker-entrypoint.d/15-pulse-headers.envsh
COPY --from=build /app/dist /usr/share/nginx/html
USER nginx
EXPOSE 8080
