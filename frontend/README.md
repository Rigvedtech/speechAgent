# SpeechAgent Recruiter Frontend

Vite + React + TypeScript recruiter portal for voice interview bots.

## Development

1. Start the backend API on port 8000 (`python api_server.py` in `backend/`).
2. Install and run the frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — API calls are proxied to `http://localhost:8000`.

## Production build

```bash
npm run build
```

Serve `dist/` via Nginx or static hosting. Set `VITE_API_BASE_URL` to your API origin at build time and configure `CORS_ORIGINS` on the backend.

### JD/CV extraction (n8n)

Configure `N8N_URI` in **backend** `.env` (not frontend). The UI calls `POST /api/extract-jd-cv`; the backend forwards files to n8n and returns extracted text + questions.

## Routes

| Path | Purpose |
|------|---------|
| `/` | Dashboard — active sessions |
| `/interviews/new` | Join meeting + configure interview |
| `/interviews/:botId` | Live session — status, planned questions, start/leave |
| `/interviews/:botId/report` | Interview report card |
| `/reports` | Completed report history |
