---
title: Início rápido
description: Consuma a API do OpenCVM em menos de um minuto.
---

Chame um endpoint público para obter o snapshot de um ticker:

```bash
curl https://api.opencvm.org/v1/cvm/companies/PETR4
```

Resposta:

```json
{
  "ticker": "PETR4",
  "name": "Petróleo Brasileiro S.A.",
  "cd_cvm": 9512,
  "sector": "Petróleo, Gás e Biocombustíveis"
}
```

É isso. Veja a [visão geral da API](/pt/api/overview/) para a superfície completa.
