# Use the deployed website with your local provider

Nexora can keep its provider agent and SQLite database on your laptop while users open the Vercel dashboard from any device. The laptop must be running the control plane and an HTTPS tunnel.

## 1. Start Nexora locally

```powershell
cd "C:\Users\KALYAN PAGADALA\Desktop\Nexora-Unified-Compute-Management-Platform-\user-website\backend"
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8000
```

In another terminal, start the provider agent:

```powershell
cd "C:\Users\KALYAN PAGADALA\Desktop\Nexora-Unified-Compute-Management-Platform-\provider-server"
python .\main.py
```

## 2. Create an HTTPS tunnel

Install Cloudflare's `cloudflared` on the laptop, then run:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Copy the generated `https://...trycloudflare.com` address. Keep that terminal open while people use the project. The quick address is temporary; create a named Cloudflare Tunnel for a stable project URL.

## 3. Share the Vercel dashboard link

Append the encoded tunnel URL as `controlPlane`:

```text
https://YOUR-VERCEL-DOMAIN/?controlPlane=https%3A%2F%2FYOUR-TUNNEL.trycloudflare.com
```

Example:

```text
https://nexora-unified-compute-management-platform-3zwy7stnm.vercel.app/?controlPlane=https%3A%2F%2Fblue-sun.trycloudflare.com
```

Anyone opening this link uses your laptop's control plane, so they see the same local accounts, providers, submitted jobs, checkpoints, and results. Their browser never needs direct access to your local network address.
