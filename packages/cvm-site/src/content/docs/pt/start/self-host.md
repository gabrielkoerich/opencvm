---
title: Auto-hospedagem
description: Rode o OpenCVM na sua infraestrutura com um único docker compose.
---

O OpenCVM é entregue como um stack Docker único: FastAPI + worker + scheduler + Redis,
com backup contínuo opcional via Litestream para qualquer bucket S3-compatível.

```bash
git clone https://github.com/opencvm/opencvm
cd opencvm/packages/cvm
docker compose up -d
```

Para um guia completo de deploy em produção (Oracle Always Free, Hetzner, Contabo),
veja o [guia de deploy](https://github.com/opencvm/opencvm/blob/main/docs/cvm-deploy.md).
