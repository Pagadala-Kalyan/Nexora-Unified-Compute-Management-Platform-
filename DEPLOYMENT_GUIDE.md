# Nexora Deployment Guide

This guide reports commands/configuration present in the repository. It does **not** certify that a deployment has succeeded.

## Direct local demonstration (unverified)

1. In `user-website/backend`, create/activate a Python environment and install `requirements.txt`; run `uvicorn app.main:app --host 0.0.0.0 --port 8000` or `start.bat`.
2. In `provider-server`, install `requirements.txt`, configure `UCMP_BACKEND_URL` and the matching `PROVIDER_SHARED_TOKEN`, then run `python main.py` (or `start.bat`).
3. In `user-website/nexora-frontend`, run `python -m http.server 5173 --bind 127.0.0.1` (or `start.bat`).
4. Open `http://127.0.0.1:5173`, choose the correct control-plane URL in Settings, register, and wait for provider status.

Do not rely on `SECRET_KEY` in `backend/start.bat`: current code reads `JWT_SECRET`.

## Docker Compose (unverified)

At repository root, copy `.env.example` to ignored `.env`, set non-development secrets and MediaMTX locations, then run:

```powershell
docker compose up --build
```

Compose defines FastAPI backend, PostgreSQL 16, and MediaMTX. It maps RTMP TCP 1935, RTSP TCP 8554, WebRTC/WHIP TCP 8889, and WebRTC UDP 8189. It creates a persistent Docker volume for Postgres. It does not start a provider agent.

## Hosted topology (unverified)

- `vercel.json` publishes the static frontend directory with SPA rewrites.
- `render.yaml` defines `nexora-control-plane` and a PostgreSQL database; it generates `JWT_SECRET` and `PROVIDER_SHARED_TOKEN`.
- A public MediaMTX-capable host is still required for remote RTMP/RTSP/WebRTC. Render web services alone do not provide the necessary media TCP/UDP listeners.

## Configuration reference

| Variable | Used by | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | backend | SQLite default or PostgreSQL SQLAlchemy URL |
| `JWT_SECRET` | backend | JWT signature and stream-key encryption derivation |
| `PROVIDER_SHARED_TOKEN` | backend/provider | provider HTTP authentication |
| `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` | backend | HTTP/WebSocket browser origin policy |
| `MEDIAMTX_INGEST_URL`, `MEDIAMTX_PROVIDER_READ_URL`, `MEDIAMTX_WEBRTC_URL` | backend | browser/OBS ingest, provider read, WHIP endpoint addresses |
| `MEDIA_SERVER_ALLOW_LOOPBACK` | backend | explicitly permits local-media addresses |
| `STREAM_INPUT_TIMEOUT_SECONDS` | provider stream flow | source-input timeout |
| `UCMP_BACKEND_URL` | provider | explicit control-plane base URL |
| `PROVIDER_ID`, `PROVIDER_NAME`, `HEARTBEAT_INTERVAL`, `COST_PER_HOUR` | provider | provider identity/advertising |
| `NEXORA_FFMPEG_PATH`, `FFMPEG_PATH` | provider | FFmpeg discovery override |

Never commit actual credential values. For production, configure TLS, narrow CORS, use non-default secrets, and replace shared provider authentication.
