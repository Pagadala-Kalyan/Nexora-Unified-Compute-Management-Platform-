# Nexora — Unified Compute Management Platform

Nexora is a functional distributed-compute prototype: the web control plane schedules a controlled workload to a separately running provider agent, receives live progress, checkpoints, and returns its result.

## What works in this foundation

- User registration and JWT login
- Provider authentication, registration, health heartbeat, and resource telemetry
- Capacity-aware, cost/reliability-aware provider selection
- A real HTTP polling path from a provider server on another machine
- Safe, allow-listed matrix computation with progress and a checkpoint at 50%
- Result reporting, provider release, dashboard polling, job history, and basic analytics

## Quick local demonstration

1. Create and activate a Python virtual environment in `user-website/backend`, then install `requirements.txt`.
2. Start the control plane: `uvicorn app.main:app --reload --port 8000`.
3. In a second terminal, install `provider-server/requirements.txt` and run `python main.py` from `provider-server`.
4. In `user-website/frontend`, install dependencies and run `npm run dev`.
5. Register an account with `POST /auth/register` (the login screen includes this temporary setup note), sign in, and submit a workload.

For a LAN demonstration, run the backend with host `0.0.0.0`, allow port 8000 in the firewall, and set `UCMP_BACKEND_URL=http://<computer-a-lan-ip>:8000` on Laptop B before launching its provider agent.

See [architecture.md](docs/architecture.md) and [api.md](docs/api.md) for the execution flow and API contract.
