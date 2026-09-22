# Nexora local database schema

Nexora uses a local SQLite database by default: `user-website/backend/nexora.db`. The control plane creates missing tables automatically at startup. Set `DATABASE_URL` only when a different database location is required.

## Core relationships

```text
users 1---* auth_sessions
users 1---1 wallets 1---* token_transactions
users 1---* jobs *---1 providers
jobs  1---1 job_billing
jobs  1---* job_artifacts
jobs  1---* checkpoints
users 1---* billing_transactions
users/providers/jobs 1---* audit_events
```

## Tables

| Table | Purpose | Key relations |
| --- | --- | --- |
| `users` | Account email, PBKDF2 password hash, wallet balance | Owns sessions, jobs, artifacts, billing, audit events |
| `wallets` | One persistent token wallet per user | `user_id → users.id`, unique; source of truth for token balance |
| `token_transactions` | Immutable token purchase, reservation, usage and refund ledger | Wallet, user, and optional job references |
| `job_billing` | Estimated, reserved, and actual token cost for a job | `job_id → jobs.id` |
| `auth_sessions` | Local signed-in session records and expiry/revocation state | `user_id → users.id` |
| `providers` | Device identity, hardware capacity, telemetry, heartbeat and availability | Receives jobs; appears in audit events |
| `jobs` | Workload request, scheduler state, progress, result and costs | `user_id → users.id`, `provider_id → providers.id` |
| `job_artifacts` | Submitted Python source and file metadata | `job_id → jobs.id`, `user_id → users.id` |
| `checkpoints` | Provider progress snapshots at 25% intervals | `job_id → jobs.id`, provider identifier |
| `billing_transactions` | Demonstration credits and future usage charges | `user_id → users.id`, optional `job_id → jobs.id` |
| `audit_events` | Durable history of authentication, billing, provider and job actions | Optional user, provider and job references |

## Data handling

- Passwords are stored only as PBKDF2 hashes.
- Card input for the demo top-up screen is not saved; only a non-sensitive last-four reference is recorded.
- Uploaded Python source is stored in `job_artifacts` so the provider can receive a reproducible job payload.
- JWTs contain a local `auth_sessions` identifier. A deleted or revoked session is rejected even before its token expires.
- Token packages and cost estimation are determined only by the backend. The frontend cannot submit a token amount or job cost.
- Results and checkpoints are persisted and reused by the dashboard, recovery workflow, analytics and provider inspector.
