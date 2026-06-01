# Build the static site with Bun, serve with Caddy.
FROM oven/bun:1-alpine AS build
WORKDIR /app
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile || bun install
COPY astro.config.mjs tsconfig.json ./
COPY src ./src
RUN bun run build

FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80
