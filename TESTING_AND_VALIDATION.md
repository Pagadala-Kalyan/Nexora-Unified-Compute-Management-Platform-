# Testing and Validation Evidence

Audit date: 25 October 2026. Commands were non-destructive. Source and configuration were not modified.

| Check | Executed | Result | Scope/limitation |
| --- | --- | --- | --- |
| Python parse check: backend and provider `py_compile` | Yes | PASS (exit 0) | Syntax only; does not start/import services. |
| Node utility suite: `browser-capture.test.mjs`, `stream-stop.test.mjs` | Yes | PASS: 12 tests, 0 failures | Mocks browser/WHIP dependencies; no native capture or media server. |
| Backend pytest suite | Attempted | NOT RUN: project venv reports `No module named pytest` | Not installed because audit rules forbid dependency changes. |
| Provider stream pytest suite | Attempted as part of pytest invocation | NOT RUN for same reason | — |
| Docker Compose | No | UNVERIFIED | Would create services/data; excluded from audit. |
| FastAPI functional APIs | No | UNVERIFIED | Would create local database records; excluded from audit. |
| Remote provider/MediaMTX/OBS/cloud destination | No | UNVERIFIED | Requires infrastructure/credentials/hardware outside supplied evidence. |

## Test inventory inspected

- `backend/tests/test_token_wallet.py`: persistent/server-owned wallet behavior.
- `backend/tests/test_video_workload.py`: invalid inputs, scheduling, artifact access/output/billing, optional real FFmpeg compression.
- `backend/tests/test_checkpoint_recovery.py`: checkpoint/resume/integrity/fencing/billing/two-provider scenarios, often using mocks/simulated provider loss.
- `backend/tests/test_remote_streaming.py`: configuration, destination SSRF validation, secrets, stream allocation/claim/auth/billing/stop flows.
- `provider-server/test_stream_runner.py`: provider FFmpeg stream runner behavior.
- Frontend Node tests above: screen capture errors, WHIP negotiation/cleanup, and combined backend/capture stop behavior.

Passing frontend tests establish only utility behavior. They do not establish end-to-end compute, persistence, billing, streaming, security, or deployment correctness.
