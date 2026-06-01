---
title: Self-host
description: Run OpenCVM on your own infrastructure with one docker compose.
---

OpenCVM ships as a single Docker stack: FastAPI + worker + scheduler + Redis,
with optional Litestream continuous backup to any S3-compatible bucket.

```bash
git clone https://github.com/opencvm/opencvm
cd opencvm/packages/cvm
docker compose up -d
```

For a production deploy walkthrough (Oracle Always Free, Hetzner, Contabo)
see the [deploy guide](https://github.com/opencvm/opencvm/blob/main/docs/cvm-deploy.md).
