# SpeechAgent / Prabhat Frontend

Vite + React + TypeScript recruiter portal and marketing landing page.

## Development (full app)

1. Start the backend API on port 8000 (`python api_server.py` in `backend/`).
2. Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — API calls are proxied to `http://localhost:8000`.

Do **not** set `VITE_LANDING_ONLY` in `.env.development` — you get the full app (dashboard, interviews, reports).

## Vercel — landing page only (Option B)

Public marketing deploy ships **only** `/` (landing). Dashboard and interview routes are excluded from the production bundle.

### Vercel project settings

| Setting | Value |
|---------|--------|
| Root Directory | `frontend` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

### Environment variables (Vercel dashboard)

```env
VITE_LANDING_ONLY=true
```

Leave `VITE_API_BASE_URL` unset — landing does not call the API.

`frontend/.env.production` already sets `VITE_LANDING_ONLY=true` for production builds.

### Deploy

```bash
cd frontend
npm run build
npx vercel --prod
```

Or connect the Git repo in Vercel with root directory `frontend`.

`frontend/vercel.json` rewrites all paths to `index.html` for client-side routing on `/` only.

## Full app production (later)

Set on your app host (not the public landing):

```env
VITE_LANDING_ONLY=false
VITE_API_BASE_URL=https://your-backend.example.com
```

Add the frontend origin to backend `CORS_ORIGINS`.

### JD/CV extraction (n8n)

Configure `N8N_CV_URI`, `N8N_JD_URI`, and `N8N_QUESTIONS_URI` in **backend** `.env`. The UI calls `POST /api/extract-cv`, `POST /api/extract-jd`, and `POST /api/generate-questions`; the backend forwards to n8n.

## Routes (full app — `VITE_LANDING_ONLY` unset/false)

| Path | Purpose |
|------|---------|
| `/` | Landing page |
| `/dashboard` | KPI dashboard |
| `/interviews/new` | Schedule interview |
| `/interviews/:botId` | Live session |
| `/interviews/:botId/report` | Interview report |
| `/reports` | Report history |
| `/feedback/:botId` | Candidate feedback form |
