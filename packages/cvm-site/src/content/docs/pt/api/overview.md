---
title: Visão geral da API
description: Endpoints, autenticação e limites de uso.
---

Todos os endpoints ficam em `/api/v1/cvm`. A instância hospedada está em
`https://api.opencvm.org`; instâncias auto-hospedadas expõem a mesma superfície
no host que você apontar para o container.

## Endpoints

| Método | Caminho                       | Retorna                                      |
| ------ | ----------------------------- | -------------------------------------------- |
| GET    | `/companies`                  | Lista de companhias registradas na CVM       |
| GET    | `/companies/{ticker}`         | Snapshot de uma companhia                    |
| GET    | `/companies/{ticker}/filings` | Índice de fatos (ITR, DFP, FRE)              |
| GET    | `/prices/{ticker}`            | Preços de fechamento                         |

## Autenticação

Leituras públicas são anônimas e têm limite por IP. Cotas maiores e
endpoints de escrita exigem uma API key — emitida no dashboard.
