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
| `POST /stream/sessions` | Validate balance/provider/profile and create an assigned remote stream. |
| `GET /stream/sessions/active` | Return the signed-in user's active stream and OBS publish key. |
| `POST /stream/sessions/{id}/stop` | Stop the user's stream; provider termination is confirmed asynchronously. |
| `POST /providers/{id}/streams/claim` | Authenticated provider claim; returns one `START_STREAM` command and credentials only to the assigned provider. |
| `POST /providers/streams/{id}/heartbeat` | Report validated process state and measured FFmpeg metrics; returns `STOP_STREAM` when requested. |
| `POST /providers/streams/{id}/stopped` | Confirm provider process termination and revoke per-session credentials. |
| `POST /stream/internal/mediamtx/auth` | MediaMTX HTTP-auth callback for session-scoped publish/read keys. |

User stream updates are published through the existing user-scoped `streams` WebSocket topic. Provider commands continue to use the authenticated provider HTTP polling channel; no second provider transport is introduced.

Errors use FastAPI's JSON shape: `{ "detail": "human-readable reason" }`.
