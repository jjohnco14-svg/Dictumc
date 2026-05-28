# dictum-web

The public web frontend + production server for Dictum.

```
dictum-web/
├── index.html        — landing page + full editor (single HTML file)
├── server.py         — FastAPI app: serves static + API
├── requirements.txt  — Python deps
├── Dockerfile        — Ubuntu 24.04 + QEMU + cross-compilers
├── fly.toml          — fly.io deployment config (free tier)
└── patch_api_base.py — patches index.html for same-origin /api/* URLs
```

---

## Local dev (fast, no Docker)

```bash
# From the Dictumc repo root:
pip install fastapi uvicorn[standard] pydantic aiofiles

mkdir -p dictum-web/static
cp dictum-web/index.html dictum-web/static/index.html

cd dictum-web
DICTUM_REPO=.. python server.py
# Open http://localhost:8080
```

The frontend auto-detects the API at `window.DICTUM_API`. In dev it falls
back to `http://localhost:8765` (the original VibeCoder port).

---

## Deploy to fly.io (free tier)

fly.io free tier gives you 3 shared VMs, 256MB RAM, 160GB outbound/month.
QEMU cross-compilation is CPU-bound and bursty — this fits the free tier
fine for a low-traffic demo or early beta.

### One-time setup

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Create the app (run from dictum-web/)
cd dictum-web
fly launch --name dictum-web --region sin --no-deploy

# Persistent volume for workspace.db (1 GB, free)
fly volumes create dictum_data --region sin --size 1

# Optional: set a server-side API key for demo mode
# (users can still supply their own BYOK key in the UI)
fly secrets set ANTHROPIC_API_KEY=sk-ant-...
```

### Deploy

```bash
cd dictum-web
fly deploy
```

That's it. fly.io reads `fly.toml` and `Dockerfile` automatically.
First deploy takes ~4 minutes (building the cross-compiler layer).
Subsequent deploys are ~90 seconds (layer cache).

### Your live URL

```
https://dictum-web.fly.dev
```

To use a custom domain:
```bash
fly certs add dictum-lang.dev
fly certs add www.dictum-lang.dev
```
Then add the CNAME records fly prints to your DNS.

---

## Tier enforcement

Right now tier enforcement is client-side (the `TIER = 'free'` constant in
`index.html`). This is intentional for the MVP — you can see what you're
building before adding a payment layer.

When you're ready to add paid tiers:

1. Add Stripe or LemonSqueezy webhook handler to `server.py`
2. Store `user_id → tier` in the SQLite DB (or Supabase)
3. Add a session cookie / JWT check in `server.py`
4. The `/api/run` endpoint already returns the right error message when a
   QEMU target is requested but unavailable — just gate it on tier there

---

## Cloudflare Workers (transpile-only, free forever)

The `/api/transpile` endpoint is pure Python, no subprocess, no gcc.
You can run it on a VPS or serverless function independently to keep
transpilation always-on even if the fly.io VM is sleeping.

Cheaper still: wire the transpiler into a Cloudflare Worker via a Python
WASM build (experimental). The Workers free tier is 100k requests/day.

---

## Environment variables

| Variable              | Default        | Description                              |
|-----------------------|----------------|------------------------------------------|
| `PORT`                | `8080`         | Server port                              |
| `DICTUM_REPO`         | `../`          | Path to Dictumc repo root                |
| `ANTHROPIC_API_KEY`   | (empty)        | Server-side API key for BYOK fallback    |

---

## Free tier limits

| Resource          | fly.io free        | Dictum usage              |
|-------------------|--------------------|---------------------------|
| VMs               | 3 shared           | 1 used                    |
| RAM               | 256 MB             | ~120 MB typical           |
| CPU               | shared             | spikes on compile only    |
| Outbound traffic  | 160 GB/month       | ~50KB per run response    |
| Volumes           | 3 GB total         | 1 GB used (workspace.db)  |
| Idle sleep        | yes (auto_stop)    | ~2s cold start            |

For a demo / beta with < 500 users/day, this is genuinely $0.
