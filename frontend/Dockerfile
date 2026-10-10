# syntax=docker/dockerfile:1.7
FROM node:22.22-alpine AS deps
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
COPY . .
RUN npm run build

FROM nginx:1.29-alpine AS prod
ENV PORT=80 API_UPSTREAM=http://backend:8000
COPY docker/nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
