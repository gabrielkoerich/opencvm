---
title: API overview
description: Endpoints, auth, rate limits.
---

All endpoints live under `/api/v1/cvm`. The hosted instance is at
`https://api.opencvm.org`; self-hosted instances expose the same surface
on whatever host you point at the container.

## Endpoints

| Method | Path                          | Returns                          |
| ------ | ----------------------------- | -------------------------------- |
| GET    | `/companies`                  | List of CVM-registered companies |
| GET    | `/companies/{ticker}`         | Single company snapshot          |
| GET    | `/companies/{ticker}/filings` | Filings index (ITR, DFP, FRE)    |
| GET    | `/prices/{ticker}`            | End-of-day prices                |

## Auth

Public reads are unauthenticated and rate-limited per IP. Higher quotas and
write endpoints require an API key — issued via the consumer dashboard.
