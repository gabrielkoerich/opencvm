# AGENTS.md

Layout and commands are in the README. Run `just cvm-test` for the backend tests.

- The API serves on :8347. The UI dev server proxies `/api` there.
- Litestream mirrors `cvm.sqlite` to R2 (`storage/opencvm/`). Keep `retention` at 48h or under: a snapshot grows with the 6.6 GB DB and the R2 free tier is 10 GB.
- Secrets for the stack come from `packages/cvm/.envrc`, which is gitignored. `.env.example` lists the variables.
- `.github/workflows/deploy-cvm.yml` builds `ghcr.io/<owner>/opencvm` and deploys over SSH. It needs the `CVM_HOST`, `CVM_USER`, `CVM_SSH_KEY` and optional `CVM_SSH_PORT` secrets.
