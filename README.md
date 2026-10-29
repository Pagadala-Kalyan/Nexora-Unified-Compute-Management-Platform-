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

The complete local relational model is documented in [database-schema.md](docs/database-schema.md).

## Quick local demonstration

1. Create and activate a Python virtual environment in `user-website/backend`, then install `requirements.txt`.
2. Start the local control plane: `uvicorn app.main:app --host 0.0.0.0 --port 8000`. This creates `nexora.db` locally; it is the single persistent store for the project.
3. In a second terminal, install `provider-server/requirements.txt` and run `python main.py` from `provider-server`. The terminal prints `Connected as ...` when the provider device is live.
4. In a third terminal, run `user-website/nexora-frontend/start.bat` (or `python -m http.server 5173 --bind 127.0.0.1` from that folder), then open `http://127.0.0.1:5173`. This repository's dashboard is static HTML/JavaScript and does not require a Vite build.
5. Create an account in the login screen, sign in, verify the provider card appears as ONLINE, and submit a preset or `.py` file. The provider runs it locally and returns its output to the job inspector.

For a LAN demonstration, run the backend with host `0.0.0.0`, allow port 8000 in the firewall, and set `UCMP_BACKEND_URL=http://<control-plane-lan-ip>:8000` on each provider device before launching its agent. Open the dashboard from another computer using the host's port 5173 and set its **Control plane URL** in Settings to `http://<control-plane-lan-ip>:8000`.

See [architecture.md](docs/architecture.md) and [api.md](docs/api.md) for the execution flow and API contract.

To let users on any device open the deployed Vercel dashboard while retaining the provider and SQLite database on your laptop, follow [remote-local-access.md](docs/remote-local-access.md).

## Vercel dashboard deployment

Vercel serves the static dashboard from `user-website/nexora-frontend` (configured in the root `vercel.json`). Set the dashboard's **Control plane URL** in Settings to the public URL of a separately deployed Nexora FastAPI control plane. The provider agent must also point `UCMP_BACKEND_URL` to that same control-plane URL; it cannot connect to a static Vercel dashboard.

## Public backend deployment with Render

The repository includes `render.yaml` to create a Render web service and PostgreSQL database. In Render, choose **New → Blueprint**, select this repository, and deploy `nexora-control-plane`. Once it reports healthy, set its `https://...onrender.com` URL in the dashboard's **Control plane URL** setting. Set the same URL in the provider machine's `UCMP_BACKEND_URL` and copy Render's generated `PROVIDER_SHARED_TOKEN` into that machine's environment.

Remote OBS-to-provider streaming also requires a reachable MediaMTX deployment with RTMP(S)/RTSP(S) ports; Render's web service does not provide those ports. For local development, copy `.env.example` to the ignored `.env` file and run `docker compose up --build`. See [remote streaming setup](docs/remote-streaming-setup.md) for local Docker, OBS connection, firewall, and internet deployment configuration.

If the Render service is configured as Docker instead of a Blueprint, the root `Dockerfile` runs the same FastAPI control plane automatically.
