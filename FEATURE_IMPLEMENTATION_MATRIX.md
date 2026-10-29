# Feature Implementation Matrix

| Capability | Status | Evidence | Verification limit |
| --- | --- | --- | --- |
| User registration/login/JWT session | IMPLEMENTED | `backend/app/main.py:863-871` | Runtime API flow not executed |
| Session validity/revocation data model | IMPLEMENTED | `AuthSession`, `current_user` | Logout endpoint not found |
| Provider registration/heartbeat | IMPLEMENTED | `main.py:874-906`; provider `register`, `heartbeat` | No real provider run |
| CPU/RAM/disk/GPU telemetry | IMPLEMENTED | provider `utilization()` | Hardware measurement not audited |
| Capacity/cost/reliability selection | IMPLEMENTED | `compatible_provider()` | Reliability update policy not found |
| Job dispatch via polling | IMPLEMENTED | backend `pending`; provider `listener()` | Multi-provider test not run |
| Matrix/prime/Fibonacci | IMPLEMENTED | provider execution methods | End-to-end not run |
| Custom Python | IMPLEMENTED | provider `execute()` | Dangerous; no isolation |
| Video artifact/compression | IMPLEMENTED | artifact routes, `run_video_compress` | FFmpeg path not run |
| Checkpoint integrity/fencing/recovery | IMPLEMENTED | checkpoint routes, `recover_lost_providers` | Tests not run due missing pytest |
| Live WebSocket events | IMPLEMENTED | `/ws/realtime`, frontend `realtime.js` | Live connection not run |
| Client fallback refresh | IMPLEMENTED | frontend `state.js` | Browser flow not run |
| Token wallet/ledger | IMPLEMENTED | `Wallet`, `TokenTransaction`, billing routes | No payment provider |
| Card payment | SIMULATED | `demo_topup`; purchase modal labels | No gateway exists |
| Remote live encoding | IMPLEMENTED | stream models/routes, provider FFmpeg runner, MediaMTX config | Media server/OBS/destination unverified |
| Browser screen capture | IMPLEMENTED | `browser-capture.js`; 12 Node tests pass | Native browser capture not run |
| Resource pools | SIMULATED | `pages/resource-pool.js` | No persistent pool/scheduler model |
| Admin controls/RBAC | NOT FOUND | no roles/admin routes found | — |
| Historical telemetry/monitoring | NOT FOUND | no sample table/service found | Dashboard is current aggregates |
