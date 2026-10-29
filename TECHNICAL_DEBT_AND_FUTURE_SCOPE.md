# Technical Debt and Future Scope

| Priority | Current evidence | Impact | Recommendation | Acceptance criteria |
| --- | --- | --- | --- | --- |
| P0 | Provider executes submitted Python directly (`provider-server/main.py:1758-1821`) | Remote code execution on provider host | Disable for untrusted users or isolate per job in constrained containers/VMs | Adversarial workload cannot read host data/network or exceed quotas |
| P0 | One shared provider token and client-supplied provider ID | Provider impersonation/control risk | Per-provider enrollment credentials or mTLS, rotation/revocation | A credential cannot act as another provider |
| P1 | Job cancellation does not stop provider execution; stop-all does not refund reservations | Billing/state drift | Add cancellable provider command/acknowledgement and idempotent settlement | Cancelled job stops once; wallet/provider state reconciles |
| P1 | Provider polling can create multiple execution threads before state changes | Duplicate execution | Atomic claim/lease with expiry and single-slot concurrency control | Concurrent polls yield exactly one execution |
| P1 | In-memory real-time/recovery and SQLite default | Not safe for replicas/high concurrency | Durable queue/locks/pubsub; PostgreSQL production baseline | Multi-replica test has no duplicate events/recovery |
| P1 | Artifact files on local disk; provider output unlimited | Data loss/resource exhaustion | Object storage, quotas, antivirus/content validation, retention | Enforced sizes/types and expired artifact cleanup |
| P2 | SQLite ad-hoc schema alterations, no migrations | Upgrade/recovery risk | Versioned migration framework and backup/rollback process | Fresh and upgrade DBs reach same schema |
| P2 | Stale docs/config naming | Operator errors | Update docs/API/OpenAPI and fix `SECRET_KEY`/legacy Vite message | CI checks docs/config against current endpoints |
| P2 | No measured observability/history | Diagnosis/scaling limits | Structured logs, metrics, telemetry time series/alerts | Provider/job/stream timelines visible and retained |

## Realistic future scope

1. Provider pools, labels, quotas, priorities, fairness, and preemption.
2. Formal RBAC and a restricted provider/operator console.
3. Object storage and signed artifact URLs with lifecycle handling.
4. Per-provider TLS enrollment, secret rotation, and audit viewer.
5. Production payments only after an explicit payment-provider design and legal/security review.
6. HA scheduler/realtime architecture with database migrations and observability.
7. Automated CI that installs Python test dependencies and runs API, provider, frontend, Compose, and browser tests.
