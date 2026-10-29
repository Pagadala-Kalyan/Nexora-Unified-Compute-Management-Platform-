# Nexora API Reference

Source of truth: `user-website/backend/app/main.py`. Status: **IMPLEMENTED in source; runtime endpoints were not exercised in this audit.** Browser calls use JSON except multipart artifact routes. User routes require `Authorization: Bearer <JWT>`; provider routes require `X-Provider-Token`.

## Schemas

| Schema | Fields and validation |
| --- | --- |
| Register/Login | `email: str`; `password: str`, min 8 |
| JobCreate | `name` min 2/max 100; `workload` default `matrix_multiply`; `requirements` object |
| ProviderRegister | ID/name; `cpu_cores` ≥1; `ram_gb` >0; optional GPU; `cost_per_hour`; optional system info |
| Heartbeat | `status` default ONLINE; `utilization` object |
| Update | optional enum status QUEUED/SCHEDULED/RUNNING/COMPLETED/FAILED/RECOVERING/CANCELLED; progress 0–100; result; cost; attempt |
| TokenPurchase | known package ID: `starter`, `standard`, `compute` |
| DemoTopUp | amount 0–10,000 and bounded card/cardholder/expiry/CVC strings; card data is not persisted |
| StreamSessionCreate | destination platform, RTMP(S) URL/key, profile (`720p60`, `1080p60`, `720p30`), source mode (`obs` or `browser_capture`) |
| StreamHeartbeatPayload | provider ID, stream process status, metrics object, optional error |

## Public and user endpoints

| Endpoint | Purpose and response | Validation / effects / caller |
| --- | --- | --- |
| `GET /health` | `{status:'ok',service:'nexora-control-plane'}` | unauthenticated; frontend settings health check and provider discovery |
| `POST /auth/register` | access token plus `{id,email,token_balance}` | lowercase uniqueness; creates user, audit event, auth session/wallet; `auth.js` |
| `POST /auth/login` | same session response | verifies PBKDF2 password; `401` invalid; `auth.js` |
| `GET /providers` | provider list: hardware, status, reliability, utilization, heartbeat | User; dashboard/providers/resource-pool state refresh |
| `GET /jobs` / `GET /jobs/{id}` | only caller-owned job(s), requirements/result/billing fields | User; jobs views/state refresh; `404` non-owner/missing |
| `POST /jobs` | scheduled job | Selects compatible provider, reserves token ledger, stores optional custom code or video artifact link; `402/409/422`; job modal |
| `POST /jobs/{id}/cancel` | cancelled job | User owner; refunds reserved tokens then changes state. It does not signal provider process. |
| `POST /jobs/stop-all` | `{cancelled:n}` | Cancels active caller jobs; source does not refund reservations. |
| `GET /checkpoints` | checkpoint history for caller jobs | User; state refresh |
| `GET /dashboard` | active jobs/nodes/tokens/current aggregate utilization/recent jobs | User; overview/state refresh |
| `GET /analytics` | total jobs/success rate/current recovering count | User; analytics page |
| `GET /billing` | wallet balance, package catalogue, job estimates/actuals | User; billing page/state refresh |
| `GET /billing/transactions` | latest 50 caller ledger entries | User; billing refresh |
| `POST /billing/purchase` | token credit response | User; package must be configured; simulated purchase; purchase modal |
| `POST /billing/demo-topup` | demo credit and last four digits | User; fixed package price; no payment processor/storage; purchase modal |
| `POST /media/artifacts/upload` | uploaded video metadata/checksum/probe results | User multipart; allowed extension/MIME, 50 MB default, FFmpeg-valid media, 300 s default; job modal |
| `GET /media/artifacts/{id}` | caller-owned artifact metadata | User; `404` otherwise |
| `GET /jobs/{job}/artifacts/{artifact}/download` | output file response | User owner and matching job/artifact required |
| `POST /stream/sessions` | allocated session, potentially one-time ingest/WHIP credentials | User; validates balance ≥10, target URL/host, platform, profile, capacity, encoder; marks provider BUSY; streaming page |
| `GET /stream/sessions/active` | active bool/session; includes one-time keys | User; streaming page/state refresh |
| `GET /stream/sessions/{id}` | owner session without keys | User; streaming page |
| `POST /stream/sessions/{id}/stop` | session state | User owner; immediate release only before provider claim, otherwise STOPPING command on next provider heartbeat |

## Provider and MediaMTX endpoints

| Endpoint | Purpose/effects | Validation and response |
| --- | --- | --- |
| `POST /providers/register` | create/update provider, publishes provider/resource events | shared-token authentication; body `ProviderRegister` |
| `POST /providers/{id}/heartbeat` | stores state/current utilization and timestamp | `404` unknown provider; publishes telemetry/status events |
| `GET /providers/{id}/jobs/pending` | returns SCHEDULED/RECOVERING jobs for provider ID | caller token is not bound to ID; adds submitter email to response |
| `POST /providers/jobs/{id}/update` | status/progress/result and terminal token settlement | stale `attempt` gets `409`; terminal state releases assigned provider |
| `POST /providers/jobs/{id}/checkpoint` | checkpoint row and events | validates attempt fencing/state hash; assigns sequence when omitted |
| `GET /providers/jobs/{id}/checkpoint/latest` | latest checkpoint or null | current code does not verify the requesting provider owns the job |
| `GET /providers/jobs/{id}/checkpoints` | checkpoint list | same shared-token access model |
| `GET /providers/jobs/{job}/artifacts/{artifact}/download` | input file response | verifies artifact belongs to job, not provider assignment |
| `POST /providers/jobs/{job}/artifacts/upload` | stores provider output artifact | no observed output size/type validation |
| `GET /providers/{id}/streams/pending` | compatibility stub | always returns empty list |
| `POST /providers/{id}/streams/claim` | atomically moves one allocated/receiving stream to STARTING | returns scoped MediaMTX read/destination credentials only if assigned provider exists/status permits |
| `POST /providers/streams/{id}/heartbeat` | records stream status/metrics; bills elapsed streaming minutes | refuses wrong `provider_id`; may return stop command on cancellation/budget exhaustion |
| `POST /providers/streams/{id}/stopped` | finalizes stream, revokes credentials, returns provider ONLINE | wrong provider rejected; provider error is sanitized |
| `POST /stream/internal/mediamtx/auth` | verifies MediaMTX RTMP/WHIP publish or RTSP read credential | session/path/protocol/action credential validation; intended internal callback |

## Real-time WebSocket

`WS /ws/realtime` accepts an authenticated JWT in the `Sec-WebSocket-Protocol` value `nexora.jwt.<token>`, not the URL. Browser origins are checked against the CORS list/regex. Messages are JSON: `{type:'ping'}` returns pong; `{type:'subscribe',topics:[...]}` accepts `telemetry`, `providers`, `jobs`, `checkpoints`, `billing`, `resources`, `streams`. Per-user and global connection, incoming message size/rate, and pending-event caps are defined in `main.py:423-429`. REST is still the source of truth.

## Common statuses

Job: `QUEUED`, `SCHEDULED`, `RUNNING`, `COMPLETED`, `FAILED`, `RECOVERING`, `CANCELLED`. Stream: allocated/start/receiving/encoding/streaming/stopping plus terminal `STOPPED`, `COMPLETED`, `FAILED`. Error responses use FastAPI's `{detail: ...}` shape, sometimes with a structured detail object.
