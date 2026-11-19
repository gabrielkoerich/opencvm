cvm_data_dir := env('CVM_DATA_DIR', justfile_directory() + '/packages/cvm/data')

_default:
    just --list

# ────────────────────────────────────────────────────────────────
# cvm — Brazilian SEC open-data fundamentals (DFP/ITR/IPE/CAD)
# All commands share CVM_DATA_DIR; override with
# `CVM_DATA_DIR=/some/other/path just cvm-...`.
# ────────────────────────────────────────────────────────────────

# Install the Python dependencies (FastAPI + SQLAlchemy + Dramatiq + boto3 + APScheduler)
[group('cvm')]
cvm-install:
    cd packages/cvm && uv sync

# Create the SQLite schema (idempotent — run once after install)
[group('cvm')]
cvm-initdb:
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm initdb

# Inline sync for one fiscal year: download → ingest → tickers → indicators
# Usage: just cvm-sync 2024
[group('cvm')]
cvm-sync year=`date +%Y`:
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm sync --inline --year {{ year }}

# Inline full backfill (DFP from 2010, ITR from 2011, IPE from 2003). Slow + big.
[group('cvm')]
[confirm]
cvm-sync-full:
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm sync --inline --full

# Refresh just the cd_cvm <-> ticker map from B3 (run on its own when tickers
# drift but nothing else needs re-syncing).
[group('cvm')]
cvm-tickers:
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm tickers

# Run the read-only FastAPI server in the foreground
# Usage: just cvm-serve              (port 8347)
#        just cvm-serve 8765         (custom port)
[group('cvm')]
cvm-serve port="8347":
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm serve --port {{ port }}

# Snapshot the SQLite DB (and upload to S3 if CVM_S3_BUCKET is set)
[group('cvm')]
cvm-backup:
    cd packages/cvm && CVM_DATA_DIR={{ cvm_data_dir }} uv run python -m cvm backup

# Bring up the production stack (api + worker + scheduler + redis + litestream) via Docker.
# Sources .envrc first so LITESTREAM_* secrets from `pass` are exported into compose.
[group('cvm')]
cvm-up:
    cd packages/cvm && [ -f .envrc ] && . ./.envrc; docker compose up -d

[group('cvm')]
cvm-down:
    cd packages/cvm && docker compose down

# ────────────────────────────────────────────────────────────────
# cvm-ui — SolidJS + Vite frontend (deployed separately)
# ────────────────────────────────────────────────────────────────

# Install JS deps for the OpenCVM frontend.
[group('cvm-ui')]
cvm-ui-install:
    cd packages/cvm-ui && bun install

# Run the frontend dev server (Vite on :5174, proxies /api to FastAPI on :8347).
[group('cvm-ui')]
cvm-ui-dev:
    cd packages/cvm-ui && bun run dev

# Build static assets into packages/cvm-ui/dist.
[group('cvm-ui')]
cvm-ui-build:
    cd packages/cvm-ui && bun run build

# Bring up the frontend container (Caddy on :5174).
[group('cvm-ui')]
cvm-ui-up:
    cd packages/cvm-ui && docker compose up -d --build

[group('cvm-ui')]
cvm-ui-down:
    cd packages/cvm-ui && docker compose down

# ────────────────────────────────────────────────────────────────
# cvm-site — Astro + Starlight, opencvm.org (EN + pt-BR)
# ────────────────────────────────────────────────────────────────

# Install JS deps for the marketing/docs site.
[group('cvm-site')]
cvm-site-install:
    cd packages/cvm-site && bun install

# Run the site dev server (Astro on :4321).
[group('cvm-site')]
cvm-site-dev:
    cd packages/cvm-site && bun run dev

# Build static site into packages/cvm-site/dist.
[group('cvm-site')]
cvm-site-build:
    cd packages/cvm-site && bun run build

# Bring up the site container (Caddy on :5175).
[group('cvm-site')]
cvm-site-up:
    cd packages/cvm-site && docker compose up -d --build

[group('cvm-site')]
cvm-site-down:
    cd packages/cvm-site && docker compose down

[group('cvm')]
cvm-test:
    cd packages/cvm && uv run pytest tests
