# Nexora — Unified Compute Management Platform

Nexora is a functional distributed-compute prototype: the web control plane schedules a controlled workload to a separately running provider agent, receives live progress, checkpoints, and returns its result.

## What works in this foundation

- User registration and JWT login
- Provider authentication, registration, health heartbeat, and resource telemetry
- Capacity-aware, cost/reliability-aware provider selection
- A real HTTP polling path from a provider server on another machine
- Provider-side matrix, prime, Fibonacci, and submitted Python-file execution
- Live progress plus persisted recovery checkpoints at 25%, 50%, 75%, and 100%
- Result reporting, provider release, dashboard polling, job history, and basic analytics
- Local SQLite persistence for accounts, password hashes, sessions, providers, telemetry, jobs, submitted source, checkpoints, and results

## Quick local demonstration

1. Create and activate a Python virtual environment in `user-website/backend`, then install `requirements.txt`.
2. Start the local control plane: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. This creates `nexora.db` locally; it is the single persistent store for the project.
3. In a second terminal, install `provider-server/requirements.txt` and run `python main.py` from `provider-server`. The terminal prints `Connected as ...` when the provider device is live.
4. Build the dashboard once with `npm run build` in `user-website/frontend-vite-backup`, then open `http://127.0.0.1:8000`. Alternatively, run Vite locally on port 5173.
5. Create an account in the login screen, sign in, verify the provider card appears as ONLINE, and submit a preset or `.py` file. The provider runs it locally and returns its output to the job inspector.

For a LAN demonstration, run the backend with host `0.0.0.0`, allow port 8000 in the firewall, and set `UCMP_BACKEND_URL=http://<control-plane-lan-ip>:8000` on each provider device before launching its agent. Set `VITE_API_URL` to that same address before building a dashboard used from another computer.

See [architecture.md](docs/architecture.md) and [api.md](docs/api.md) for the execution flow and API contract.

## Vercel dashboard deployment

Vercel is configured to build the static dashboard from `user-website/frontend-vite-backup`. Set `VITE_API_URL` in the Vercel project environment to the public URL of a separately deployed Nexora FastAPI control plane. The provider agent must also point `UCMP_BACKEND_URL` to that same control-plane URL; it cannot connect to a static Vercel dashboard.

## Public backend deployment with Render

The repository includes `render.yaml` to create a Render web service and PostgreSQL database. In Render, choose **New → Blueprint**, select this repository, and deploy `nexora-control-plane`. Once it reports healthy, copy its `https://...onrender.com` URL into Vercel as `VITE_API_URL`, then redeploy Vercel. Set the same URL in the provider machine's `UCMP_BACKEND_URL` and copy Render's generated `PROVIDER_SHARED_TOKEN` into that machine's environment.

If the Render service is configured as Docker instead of a Blueprint, the root `Dockerfile` runs the same FastAPI control plane automatically.
