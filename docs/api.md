# API contract

All browser endpoints other than `/auth/*` require `Authorization: Bearer <JWT>`. Provider endpoints require `X-Provider-Token`.

| Endpoint | Purpose |
| --- | --- |
| `POST /auth/register` | Create a user and receive a session token. |
| `POST /auth/login` | Receive a session token. |
| `GET /dashboard` | Return dashboard counters and recent jobs. |
| `GET /providers` | List connected compute providers. |
| `POST /jobs` | Schedule an allow-listed workload. |
| `GET /jobs`, `GET /jobs/{id}` | List or inspect the signed-in user's jobs. |
| `POST /jobs/{id}/cancel` | Cancel a queued/running job. |
| `POST /providers/register` | Register/update a provider agent. |
| `POST /providers/{id}/heartbeat` | Update agent availability and telemetry. |
| `GET /providers/{id}/jobs/pending` | Poll scheduled jobs assigned to that provider. |
| `POST /providers/jobs/{id}/update` | Send job status, progress, or result. |
| `POST /providers/jobs/{id}/checkpoint` | Store checkpoint metadata. |
| `GET /checkpoints` | List checkpoint history for the signed-in user's jobs. |
| `GET /billing` | Return wallet balance, actual spend, and pending cost estimate. |

Errors use FastAPI's JSON shape: `{ "detail": "human-readable reason" }`.
