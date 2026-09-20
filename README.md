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

## Vercel dashboard deployment

Vercel is configured to build the static dashboard from `user-website/frontend-vite-backup`. Set `VITE_API_URL` in the Vercel project environment to the public URL of a separately deployed Nexora FastAPI control plane. The provider agent must also point `UCMP_BACKEND_URL` to that same control-plane URL; it cannot connect to a static Vercel dashboard.

## Public backend deployment with Render

The repository includes `render.yaml` to create a Render web service and PostgreSQL database. In Render, choose **New → Blueprint**, select this repository, and deploy `nexora-control-plane`. Once it reports healthy, copy its `https://...onrender.com` URL into Vercel as `VITE_API_URL`, then redeploy Vercel. Set the same URL in the provider machine's `UCMP_BACKEND_URL` and copy Render's generated `PROVIDER_SHARED_TOKEN` into that machine's environment.

If the Render service is configured as Docker instead of a Blueprint, the root `Dockerfile` runs the same FastAPI control plane automatically.
