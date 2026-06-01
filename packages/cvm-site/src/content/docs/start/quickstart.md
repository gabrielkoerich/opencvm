---
title: Quickstart
description: Hit the OpenCVM API in under a minute.
---

Call a public endpoint to fetch a ticker snapshot:

```bash
curl https://api.opencvm.org/v1/cvm/companies/PETR4
```

Response:

```json
{
  "ticker": "PETR4",
  "name": "Petróleo Brasileiro S.A.",
  "cd_cvm": 9512,
  "sector": "Petróleo, Gás e Biocombustíveis"
}
```

That's it. See the [API overview](/api/overview/) for the full surface.
