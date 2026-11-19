# OpenCVM

Brazilian company fundamentals from CVM open data (DFP, ITR, IPE, CAD): download, normalize, compute indicators, and serve them over an API.

| Path | What |
|---|---|
| `packages/cvm` | Python backend: ingest, compute, scheduler, FastAPI on :8347 |
| `packages/cvm-ui` | SolidJS + Vite frontend, Caddy on :5174 |
| `packages/cvm-site` | Astro + Starlight docs site for opencvm.org, Caddy on :5175 |

Run `just` to list the recipes. `just cvm-install`, `just cvm-initdb`, then `just cvm-sync 2024` gives a local database for one year.
