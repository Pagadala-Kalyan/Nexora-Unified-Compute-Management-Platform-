# Nexora architecture

```text
Browser (React) ── JWT ──> FastAPI control plane <── provider token ── Provider Server
                                  │                              │
                            SQLAlchemy database              psutil telemetry
                                  │                              │
              schedule provider  │<──── jobs / updates ──────────┘
                                  │
              checkpoint metadata / completed result
```

The control plane owns users, provider inventory, scheduling, job state, and checkpoint metadata. The provider server owns local resource inspection and execution. It has no UI and never receives user code; it runs only an allow-listed controlled workload. This makes the remote execution demo safe while leaving an explicit place to add Docker isolation in a later phase.

Provider selection rejects offline or insufficient-capacity candidates, then minimizes price adjusted for reliability. The design accepts multiple provider processes with distinct provider IDs.

## Failure recovery phase

The current implementation creates a persisted checkpoint at 50%. The next implementation phase should mark jobs on heartbeat timeout as `RECOVERING`, choose a compatible provider, pass the last checkpoint payload, and continue the allow-listed workload from its saved progress.
