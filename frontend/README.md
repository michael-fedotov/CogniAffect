# CogniAffect Frontend

React + Vite frontend for the BWS Empathy Annotation tool.

## Local Development

```bash
cd frontend
npm install
npm run dev
```

Vite proxies `/api` and `/admin` to Flask at `http://localhost:5000`. To target a different Flask port:

```bash
FLASK_PROXY_TARGET=http://localhost:5001 npm run dev
```

`scenarios.json` is served automatically from the project root via a Vite dev middleware — no manual copying required.

## Production Build (local / Flask-served)

```bash
cd frontend
npm run build
```

Output goes to `dist/` at the **project root** (`../dist` relative to `frontend/`). Running `python server.py` from the project root will then serve this build.

## Deployment on Render

### Static Site (frontend)

| Setting | Value |
|---|---|
| Build command | `cd frontend && npm ci && npm run build` |
| Publish directory | `dist` |
| Env var `VITE_API_BASE` | `https://<your-backend>.onrender.com` (no trailing slash) |

`VITE_API_BASE` is baked into the bundle at build time. It tells the frontend where to find the Flask API and `scenarios.json` when the frontend is not served by Flask itself.

### Web Service (backend)

| Setting | Value |
|---|---|
| Env var `CORS_ORIGINS` | `https://<your-static-site>.onrender.com` |

To allow multiple origins (e.g. the Render static URL **and** GitHub Pages), provide a comma-separated list:

```
CORS_ORIGINS=https://<your-static-site>.onrender.com,https://michael-fedotov.github.io/CogniAffect/
```

If `CORS_ORIGINS` is not set, the backend defaults to allowing `https://michael-fedotov.github.io/CogniAffect/` only.

### GitHub Pages (existing deploy — no changes needed)

The frontend detects the `michael-fedotov.github.io` hostname at runtime and automatically uses `https://cogniaffect.onrender.com` as the API base. No `VITE_API_BASE` env var is required for this deploy path.
