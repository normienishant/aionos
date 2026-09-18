# Deployment Guide — Free Hosting (Render + Vercel)

Both services have free tiers, no credit card needed. Total time: ~15 minutes.

Architecture when deployed:

```
Vercel (Next.js frontend)  →HTTP→  Render (FastAPI backend)  →  SQLite on Render disk
```

---

## Step 1 — Push the repo to GitHub

```bash
git init
git add .
git commit -m "Sales Lead Qualification & Outreach Agent"
```

Then create an empty repo on github.com (no README/license — we already have them) and:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

---

## Step 2 — Deploy the backend on Render

1. Go to https://dashboard.render.com → sign in with GitHub.
2. **New → Blueprint** → select this repo. Render reads `render.yaml` and pre-fills everything.
3. Before creating, set these env vars when prompted:
   - `GEMINI_API_KEY` — paste your real key ([get one free](https://aistudio.google.com/apikey))
   - `ALLOWED_ORIGINS` — leave empty for now (you'll add the Vercel URL in Step 4)
4. Click **Apply**. First deploy takes ~3-4 minutes.
5. When live, Render gives you a URL like `https://lead-agent-backend.onrender.com`.
6. **Test it**: open `https://<your-backend-url>/docs` — you should see the Swagger UI. Then hit `GET /leads` — it should return 7 seeded leads (AUTO_SEED=1 does this on first boot).

> ⚠️ **Render free tier caveat**: the service sleeps after 15 min idle. The first request after a nap takes ~30-60s to wake. For your live demo, hit the backend URL once in the browser a minute before you start.

---

## Step 3 — Deploy the frontend on Vercel

1. Go to https://vercel.com → sign in with GitHub.
2. **Add New → Project** → import this repo.
3. Vercel auto-detects Next.js. Before deploying, add one **Environment Variable**:
   - `BACKEND_URL` = `https://lead-agent-backend.onrender.com` (your URL from Step 2, no trailing slash)
4. Click **Deploy**. Takes ~1-2 minutes.
5. Vercel gives you a URL like `https://<repo-name>.vercel.app`.

> Why `BACKEND_URL` matters: the Next.js server proxies `/api/*` → `BACKEND_URL/*` (see `frontend/next.config.js`). Without it the deployed frontend would call its own localhost.

---

## Step 4 — Connect them (CORS)

1. Copy your Vercel URL (e.g. `https://sales-lead-agent.vercel.app`).
2. In Render → your service → **Environment** → edit `ALLOWED_ORIGINS` → set it to that URL (no trailing slash).
3. Save — Render redeploys automatically (~1 min).

Done. Open your Vercel URL: the dashboard should show the 7 seeded leads, and submitting a lead runs the live agent loop end-to-end.

---

## Step 5 — Smoke-test the deployment

```bash
# Backend direct
curl https://<your-backend>.onrender.com/leads

# Full loop through the deployed frontend proxy
curl -X POST https://<your-frontend>.vercel.app/api/leads \
  -H "Content-Type: application/json" \
  -d '{"name":"Demo Lead","email":"demo@acme.com","company":"Acme Corp","title":"CTO","message":"Need a demo and pricing"}'
```

Expect a JSON response with `score`, `decision`, and a 5-step `reasoning_trace`.

---

## Local development (unchanged)

Everything still runs the same locally: `BACKEND_URL` defaults to `http://localhost:8000`, CORS allows `localhost:3000`, SQLite needs no setup. See the main README.
