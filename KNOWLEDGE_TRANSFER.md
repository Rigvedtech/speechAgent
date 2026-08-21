# Knowledge Transfer — Prabhat (speechAgent)

**Product:** Prabhat — AI voice interview + coding assessment platform  
**Repo:** `speechAgent`  
**Owner (outgoing):** *fill in name / last working day*  
**Handover owner (incoming):** *fill in name*  
**Last updated:** 20 August 2026  
**Audience:** backend, frontend, DevOps, and hiring-ops who will run this after handover

This document is the exit handover for the application. Read **sections 1–6** first. Use the rest as a runbook when something breaks or when you change interview / scoring / deploy behaviour.

**Do not put API keys, passwords, or JWT secrets in this file.** Point to `backend/.env` on the VM, GitHub Actions secrets, and `.env.example` checklists.

---

## 1. What this product is

Prabhat is Rigved Technologies’ recruiter workspace for **AI voice interviews** and **proctored coding rounds**.

- The AI interviewer (**Prabhat**) joins the candidate’s existing meeting (Microsoft Teams, Zoom, Google Meet, Webex) as a voice participant via **Recall.ai**.
- It speaks questions (TTS), listens to answers (STT), scores them with Groq, and produces a report + transcript.
- Recruiters schedule interviews, attach JD + CV, optionally add a coding round, watch live status, and read scored reports.
- Candidates can complete a coding round on a public token URL (`/c/:token`) under browser proctoring.
- Platform operators approve company access requests and manage tenant organisations.

**Personas**


| Persona                 | How they use it                                                                          |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| Recruiter (tenant user) | Dashboard, schedule, live session, reports, bulk CV upload, ATS import, coding dashboard |
| Candidate               | Joins the meeting they already have; optional public coding link; optional feedback form |
| Platform admin          | `/admin` — access requests, organisations, operators                                     |
| Ops / engineer          | Azure VM, systemd API, nginx frontend, Recall / Groq / Sarvam keys                       |


---

## 2. High-level architecture

```
Browser (Vite + React)
   │  recruiter UI  /  candidate coding  /  marketing landing
   ▼
nginx  →  static frontend  (/var/www/speechagent on Azure VM)
   │
   │  /api/*  (same origin in prod, Vite proxy in local)
   ▼
FastAPI  python api_server.py   (port 8000)     ← production process
   │
   ├── PostgreSQL  (tenants, interviews, reports, coding)
   ├── Recall.ai   (bot joins meeting; audio/video webhooks)
   ├── Groq        (live interviewer LLM + scoring + extraction + questions)
   ├── Sarvam AI   (primary STT Saaras v3 + TTS Bulbul v3)
   ├── Faster-Whisper + Edge-TTS  (fallbacks)
   ├── Microsoft Graph mail  (access-request + set-password emails)
   └── optional n8n webhooks  (legacy CV/JD file extract)
```

**Live interview audio path**

1. Recruiter calls `POST /api/join` → Recall bot created for the meeting URL.
2. Recruiter waits until bot is in the call, then `POST /api/start/{bot_id}` → greeting TTS.
3. Recall streams meeting audio to our WebSocket receiver (`WEBSOCKET_PORT`, public URL `PUBLIC_WEBSOCKET_URL`).
4. SessionManager: VAD → Sarvam STT (Whisper fallback) → `InterviewOrchestrator` + `LLMBrain` → Sarvam/Edge TTS.
5. TTS audio is sent back into the meeting (Recall output-media / webpage PCM stream).
6. Answers are scored in the background; report is persisted when the interview ends; bot auto-leaves after wrap-up.

**Production vs legacy entry points**


| Process                      | Use it?              | Notes                                            |
| ---------------------------- | -------------------- | ------------------------------------------------ |
| `python api_server.py`       | **Yes — production** | Recruiter API + Recall bot + interview loop      |
| `python main.py`             | Local demo only      | Standalone mic/speaker loop, no meeting          |
| `python ai_bridge_server.py` | Legacy               | FastAPI bridge for an old .NET Teams meeting-bot |
| `python stt_server.py`       | Legacy               | Port 8020 STT for that old Windows Step-A loop   |


If you are debugging a live customer interview, you are almost always on `api_server.py` **+ Recall**.

---

## 3. Repository map


| Path                                             | What it is                                                                      |
| ------------------------------------------------ | ------------------------------------------------------------------------------- |
| `backend/api_server.py`                          | FastAPI app: join/start/leave, reports, health, WS audio, router mount          |
| `backend/session_manager.py`                     | One `MeetingSession` per bot: STT/LLM/TTS threads, presence, camera, auto-leave |
| `backend/interview_engine.py`                    | Phases, question plan, scoring, stage-1 gate, abuse, wrap-up                    |
| `backend/llm_brain.py`                           | Spoken interviewer brain (Groq streaming)                                       |
| `backend/groq_runtime.py`                        | Safe Groq kwargs after Llama shutdown (GPT-OSS reasoning tokens)                |
| `backend/config.py`                              | All tunables; loaded from `backend/.env`                                        |
| `backend/recall_bot_service.py`                  | Recall bot create/status/delete, URL normalize, Teams deeplink fix              |
| `backend/audio_receiver.py`                      | Incoming Recall audio/transcript/video WS                                       |
| `backend/integrated_audio_sender.py`             | TTS → meeting (webpage PCM stream)                                              |
| `backend/stt_engine.py` / `sarvam_stt_engine.py` | Whisper + Sarvam STT                                                            |
| `backend/sarvam_tts_engine.py` / `tts_voice.py`  | Sarvam TTS + Edge-TTS fallback                                                  |
| `backend/language_profiles.py`                   | English vs Hinglish STT/TTS + spoken UI strings                                 |
| `backend/question_localizer.py`                  | Hinglish question rewrite before start                                          |
| `backend/n8n_extraction.py`                      | Optional n8n CV/JD webhooks; **question gen is local Groq**                     |
| `backend/services/structured_extractor.py`       | Parse CV/JD (regex + skills + Groq)                                             |
| `backend/services/jd_cv_matcher.py`              | JD↔CV fit score 0–100                                                           |
| `backend/services/coding_*.py`                   | Bank, assigner, runner, proctor, languages                                      |
| `backend/routers/`                               | REST routers (auth is under `backend/auth/`)                                    |
| `backend/ats/`                                   | ATS providers (`demo`, `custom`)                                                |
| `backend/camera_*.py` / `face_analysis.py`       | Optional live camera integrity (off by default)                                 |
| `frontend/src/`                                  | Recruiter + candidate React app                                                 |
| `frontend/src/routes/router.app.tsx`             | All UI routes                                                                   |
| `database/NNN_*.sql`                             | Ordered PostgreSQL migrations                                                   |
| `database/migrate.py`                            | Apply pending files; dump; status                                               |
| `scripts/deploy-vm.sh`                           | Production deploy on Azure VM                                                   |
| `.github/workflows/deploy-vm.yml`                | Push to `main` → SSH → deploy script                                            |
| `website/`                                       | Marketing copy + screenshots (not the running app)                              |


**Frontend pages (full app,** `VITE_LANDING_ONLY` **unset)**


| Route                       | Page                   | Who                          |
| --------------------------- | ---------------------- | ---------------------------- |
| `/`                         | Landing                | Public                       |
| `/login`                    | Login                  | Public                       |
| `/request-access`           | Access request         | Public                       |
| `/set-password`             | Invite password        | Public                       |
| `/register`                 | Org signup             | **Closed** (API returns 403) |
| `/feedback/:botId`          | Candidate feedback     | Public                       |
| `/c/:token`                 | Candidate coding round | Public, token                |
| `/dashboard`                | KPIs                   | Recruiter                    |
| `/interviews/new`           | Schedule interview     | Recruiter                    |
| `/interviews/scheduled`     | Scheduled list         | Recruiter                    |
| `/interviews/:botId`        | Live session           | Recruiter                    |
| `/interviews/:botId/report` | Report                 | Recruiter                    |
| `/reports`                  | Report history         | Recruiter                    |
| `/coding`                   | Coding dashboard       | Recruiter                    |
| `/jobs/bulk-upload`         | Bulk JD/CV             | Recruiter                    |
| `/jobs/:jobId/resumes`      | Job resumes + match    | Recruiter                    |
| `/ats/jobs`                 | Browse ATS             | Recruiter                    |
| `/settings/ats`             | ATS connection         | Recruiter                    |
| `/settings/team`            | Team users             | Tenant admin                 |
| `/admin/*`                  | Platform admin         | `platform_admin`             |


---

## 4. Tech stack


| Layer                | Stack                                                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------------------------ |
| Frontend             | React 19, Vite, TypeScript, Tailwind 4, TanStack Query, React Router 7, Zod, Monaco editor                   |
| Backend              | Python 3.11, FastAPI, Uvicorn, SQLAlchemy                                                                    |
| DB                   | PostgreSQL 14+ (`pgcrypto`, `pg_trgm`)                                                                       |
| Auth                 | JWT (HS256), bcrypt passwords, invite tokens                                                                 |
| Meeting bot          | Recall.ai                                                                                                    |
| LLM                  | Groq (`openai/gpt-oss-120b` live, `openai/gpt-oss-20b` evaluator). Ollama fallback optional, **off in prod** |
| STT                  | Sarvam Saaras v3 primary, Faster-Whisper fallback                                                            |
| TTS                  | Sarvam Bulbul v3 (`shubh`) primary, Edge-TTS `en-IN-PrabhatNeural` fallback                                  |
| Mail                 | Microsoft Graph app-only `Mail.Send`                                                                         |
| Deploy               | GitHub Actions → Azure VM → systemd `speechagent-api` + nginx                                                |
| Marketing (optional) | Vercel landing-only (`VITE_LANDING_ONLY=true`)                                                               |


---

## 5. End-to-end business flows

### 5.1 Company access (invite-only)

Public self-serve `/register` is **closed**. New companies:

1. User submits `/request-access` (`POST /api/access-requests`).
2. Honeypot field `website` — bots that fill it get a fake success.
3. Microsoft Graph emails ops (`ACCESS_NOTIFY_TO` / `GRAPH_SENDER`).
4. Platform admin reviews `/admin/requests`.
5. On grant: org + admin user created; set-password email with token (`PASSWORD_SETUP_HOURS`, default 48h).
6. User opens `/set-password` and can log in.

**Files:** `backend/routers/access_requests.py`, `backend/auth/password_setup.py`, `backend/services/graph_mail.py`, `frontend/src/pages/RequestAccessPage.tsx`.

### 5.2 Recruiter login and tenancy

- `POST /api/auth/login` → JWT with `user_id`, `organization_id`, `role`.
- Roles: tenant `admin` / `recruiter` / `viewer`; platform `platform_admin`.
- `require_writer` = admin or recruiter (create/update jobs, interviews).
- `viewer` is read-only.
- Extra platform-admin allow-list: `PLATFORM_ADMIN_EMAILS` in `.env` (legacy; prefer DB role).
- JWT expiry: 8 hours in `APP_ENV=production`, 7 days in development (overridable via `JWT_EXPIRE_MINUTES`).
- `CORS_ORIGINS` has **no code defaults**. If empty, the browser is blocked.

### 5.3 Schedule a voice interview

Typical recruiter path (`/interviews/new`):

1. Pick or create **job posting** + **candidate** (manual, upload, or ATS).
2. Extract JD and CV text (file OCR / n8n / structured parse).
3. Generate **15 spoken questions** locally via Groq (`POST /api/generate-questions`). Q1–10 JD-heavy, Q11–15 CV-heavy. Difficulty Low → Intermediate → Hard blocks.
4. Paste meeting join URL; choose English or Hinglish; optional coding round config.
5. `POST /api/interviews` stores a **scheduled** row (`interview_sessions.bot_id` is NULL until lobby).
6. Recruiter later **Send to lobby** → `POST /api/join` with `interview_id`.
7. When Recall status is in-meeting, recruiter clicks Start → `POST /api/start/{bot_id}`.

One bot per meeting URL. Duplicate join → **409**. Teams launcher/deeplink URLs are rewritten to a Recall-accepted meet link in `resolve_meeting_url_for_recall`.

### 5.4 Live voice interview (what actually happens)

Phases in `InterviewOrchestrator` (`backend/interview_engine.py`):

```
GREETING → AWAIT_INTRO → CORE (questions) → CLOSING → ENDED
```

- Greeting uses `STARTUP_GREETING` / language profile template. Interview does **not** speak until `/api/start`.
- Intro: candidate must speak enough (`INTRO_MIN_CHARS`, `INTRO_MIN_SPEECH_SEC`) before Q1. Short “hello” does not advance.
- Core questions follow the generated bank. Spoken difficulty mix in the engine is Low / Hard / Intermediate repeating (bank itself is generated with a different 1–5 / 6–10 / 11–15 split — see §7).
- **Stage-1 gate** (env-driven; see `.env.example`):
  - Score questions 1..`STAGE1_QUESTION_COUNT` (example: 7).
  - Always ask the bridge question `STAGE1_BRIDGE_QUESTION` (example: 8).
  - If average ≥ `CONTINUE_AVG_THRESHOLD` (example: 6.5) → continue remaining questions.
  - Else wrap up early. Report `qualified` uses **stage-1 average**, not the full set.
- Mid-answer: **topic poll every ~30s of speech** only. Old depth-clarifier / slot-interrupt stack is disabled (timeouts set to 9999).
- Presence: if the candidate does not start answering after the question, a silence ladder (“can you hear me?”) runs **only before speech starts**, never mid-answer.
- Repeat / rephrase requests are classified (`TURN_INTENT_CLASSIFIER`) and are **not scored**. Caps: `MAX_QUESTION_REPEATS`, `MAX_QUESTION_REPHRASES`.
- Scoring runs **in parallel** while the next question is spoken (`PARALLEL_SCORE_ENABLED`).
- Abuse language → warning then close (`ABUSE_MAX_WARNINGS`).
- After wrap-up TTS, bot auto-leaves (`INTERVIEW_AUTO_LEAVE_AFTER_WRAPUP_SEC`).
- If coding is configured, wrap-up TTS can include the public coding URL (`FRONTEND_BASE_URL` + `/c/{token}`).

**Turn-taking (easy to break — change with care)**

- Soft silence (~2s) ends an utterance capture.
- Merge window (~0.5s) keeps listening; if speech resumes it is the **same answer**.
- Hard end → score + next question.
- Answer time budget: 60s initial listen, +30s extensions, hard cap `MAX_ANSWER_SEC` (420s).

### 5.5 Reports and feedback

- Recruiter: `/interviews/:botId/report` and `/reports`.
- API: `GET /api/interview/{bot_id}/report` and HTML `.../report.html`.
- Persistence: `interview_answers`, `transcript_turns`, `interview_reports`.
- Candidate feedback: public `GET/POST /api/feedback/{bot_id}`.

### 5.6 Bulk JD/CV screening

1. Create/select a job posting.
2. `POST /api/jobs/{job_id}/upload-cvs` — up to `UPLOAD_MAX_FILES_PER_BATCH` (50), including zip.
3. Extract text (`/api/documents/{id}/extract` or batch extract) — Tesseract/Paddle OCR for scans.
4. Structured parse + `jd_cv_matcher` writes `job_candidate_matches` (0–100 with breakdown).
5. Recruiter reviews `/jobs/:jobId/resumes` and can schedule interviews from matches.

### 5.7 ATS import

- Org-wide connection in Settings → ATS.
- Providers: `demo` (fake data) and `custom` (HTTP API with encrypted key).
- Key stored in `organization.ats_api_key_encrypted` using `ATS_SECRET_ENCRYPTION_KEY`.
- Imported jobs/candidates live in the **same tables** with `source = 'ats'` and `external_ats_id`.
- Custom provider defaults assume Rigved-style paths (`/api/external/v1/requirements`, etc.) — see `backend/ats/factory.py`.

### 5.8 Coding round

- Recruiter enables coding on the interview (language track, time, task count).
- Org has a **shared problem bank** (seed + generated). Assigner picks tasks per interview.
- Candidate URL: `/c/:token` (no recruiter login).
- Browser proctor (`frontend/src/lib/proctoring/engine.ts`):
  - Gate: camera, face, fullscreen, single display.
  - Shared **3 warnings** for tab-switch / multi-face.
  - Second-display track is separate; can force-submit.
  - Paste disabled; tab-away ~10s can auto-submit.
- Code execution: `backend/services/coding_runner.py` — **local subprocess, not a sandbox**. Timeout-bounded. Comment in code: use Piston/Judge0 later for isolation.
- Recruiter views submissions + proctor summary on coding pages.

### 5.9 Optional camera integrity (voice interview)

`CAMERA_INTEGRITY_ENABLED=false` in production by default.

When true: Recall `video_separate_png` → `FaceAnalyzer` → TTS warns (multi-face, looking away/down, no face). Tunables are all in `config.py` / `.env`. Local QA: `python camera_detection_test.py`.

---

## 6. How to run locally

**Prerequisites:** Python 3.11, Node 20+, PostgreSQL 14+, ffmpeg on PATH (TTS WAV for meetings), Tesseract if you test scanned PDFs.

1. Create DB (example name `prabhat_DB`).
2. Copy `backend/.env.example` → `backend/.env`. Set at least:
  - `DATABASE_URL=postgresql://postgres:1234@localhost:5432/prabhat_DB` (**dev** — host `localhost`, not `127.0.0.1`)
  - `JWT_SECRET` (≥32 chars)
  - `CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173`
  - `GROQ_API_KEY`, `SARVAM_API_KEY`, `RECALL_API_KEY` for a real interview
  - `PUBLIC_WEBSOCKET_URL` reachable by Recall (ngrok or public IP + open port)
3. Apply schema: from repo root with backend venv and `DATABASE_URL` loaded:
  ```bash
   python database/migrate.py apply
   python database/migrate.py status
  ```
4. Backend:
  ```bash
   cd backend
   python api_server.py
  ```
   API: `http://localhost:8000` — OpenAPI at `/docs`. Health: `GET /health`.
5. Frontend:
  ```bash
   cd frontend
   npm install
   npm run dev
  ```
   App: `http://localhost:5173`. Vite proxies `/api` and `/health` to port 8000 (5-minute timeout for extract/generate).

Do **not** set `VITE_LANDING_ONLY` in local `.env.development` or you will only get the marketing page.

GPU is optional (Whisper). Groq is required for a realistic interview. If `GROQ_API_KEY` is empty, LLM falls back to local Ollama.

---

## 7. Interview engine details (tribal knowledge)

This is the highest-risk area. Small `.env` changes alter candidate experience.

**Source of truth for live knobs:** `backend/.env` (see `backend/.env.example`). `config.py` has code defaults if a key is missing. They can differ — **production follows** `.env`.


| Knob                               | Example in `.env.example` | Meaning                                      |
| ---------------------------------- | ------------------------- | -------------------------------------------- |
| `MAX_QUESTIONS`                    | 15                        | Total generated/asked questions              |
| `MAX_INTERVIEW_MINUTES`            | 30                        | Hard interview length                        |
| `STAGE1_QUESTION_COUNT`            | 7                         | Questions that feed the gate average         |
| `STAGE1_BRIDGE_QUESTION`           | 8                         | Always asked; decide continue/stop after     |
| `CONTINUE_AVG_THRESHOLD`           | 6.5                       | Continue if Q1–N avg ≥ this (scores are /10) |
| `CORE_ANSWER_SOFT_SILENCE_SEC`     | 2.0                       | Soft end of utterance                        |
| `CORE_ANSWER_MERGE_WINDOW_SEC`     | 0.5                       | Extra listen after soft end                  |
| `ANSWER_TOPIC_POLL_INTERVAL_SEC`   | 30                        | Topic check while answering                  |
| `MAX_TOPIC_REDIRECTS_PER_QUESTION` | 2                         | Then stop redirecting                        |
| `POST_QUESTION_SILENCE_STEP1_SEC`  | 22                        | First presence check                         |
| `PARALLEL_SCORE_ENABLED`           | true                      | Next question while previous scores          |
| `STREAM_STT_ENABLED`               | true                      | Live Sarvam while speaking (lower latency)   |
| `USER_BARGE_IN_ENABLED`            | false                     | Candidate cannot cut bot TTS                 |


**Question generation vs playback**

- Generator (`n8n_extraction.py`) uses `MAX_QUESTIONS` plus `QUESTION_COUNT_BEGINNER` / `INTERMEDIATE` / `HARD`. Beginner+intermediate = JD; hard = resume. If the three counts do not sum to `MAX_QUESTIONS`, they are auto-scaled (`question_plan.py`).
- Asking order is Low → Hard → Intermediate cycling (`QUESTION_PLAN.difficulty_pattern`), not a hardcoded 15-slot list.

**Languages**

- `language_mode`: `english` | `hinglish` on join.
- Hinglish: Sarvam STT `codemix` / `hi-IN`, TTS Hindi; questions localized before start. Start can **409** if localization still pending — retry.
- `HINGLISH_WHISPER_FALLBACK` allows Whisper on final answers if Sarvam fails.

**Groq model migration (16 Aug 2026)**

Groq retired `llama-3.1-8b-instant` and `llama-3.3-70b-versatile`. Replacements:

- Live interviewer: `GROQ_MODEL=openai/gpt-oss-120b`
- Scoring / extract / questions: `GROQ_EVALUATOR_MODEL=openai/gpt-oss-20b`

GPT-OSS spends tokens on hidden reasoning. `groq_runtime.py` sets `include_reasoning=false`, `reasoning_effort=low`, and bumps `max_tokens` so JSON scoring does not return empty `failed_generation` and TTS does not leak chain-of-thought.

**Python double-import trap**

`config.main_event_loop` is set on FastAPI startup. Do **not** store the loop on `api_server` module globals. If `api_server.py` is run as `__main__`, a later `from api_server import ...` loads a **second copy** of the module; TTS worker threads would never see the loop.

---

## 8. HTTP API surface (cheat sheet)

OpenAPI: `http://<host>:8000/docs`.

**Auth / access**


| Method    | Path                                    |
| --------- | --------------------------------------- |
| POST      | `/api/auth/login`                       |
| GET       | `/api/auth/me`                          |
| POST      | `/api/auth/register-org` (always 403)   |
| POST      | `/api/auth/password-setup/*`            |
| GET/POST  | `/api/users` (tenant team)              |
| POST      | `/api/access-requests` (public)         |
| GET/PATCH | `/api/access-requests` (platform admin) |
| *         | `/api/admin/...` (orgs, operators)      |


**Core interview**


| Method   | Path                                     | Notes                                     |
| -------- | ---------------------------------------- | ----------------------------------------- |
| POST     | `/api/join`                              | Create Recall bot; persist/link interview |
| POST     | `/api/start/{bot_id}`                    | Speak greeting; begin interview           |
| DELETE   | `/api/leave/{bot_id}`                    | Leave meeting                             |
| POST     | `/api/rejoin/{bot_id}`                   | Rejoin                                    |
| POST     | `/api/interviews/{bot_id}/cancel`        | Cancel                                    |
| GET      | `/api/status/{bot_id}`                   | Bot phase                                 |
| GET      | `/api/sessions` / `/api/active_meetings` | Ops                                       |
| GET      | `/api/interview/{bot_id}/report`         | JSON report                               |
| GET/POST | `/api/feedback/{bot_id}`                 | Public feedback                           |
| POST     | `/api/extract-cv` `/api/extract-jd`      | File extract adapters                     |
| POST     | `/api/generate-questions`                | Local Groq                                |
| GET      | `/health`                                | Deploy health check                       |


**CRUD routers:** `/api/candidates`, `/api/job-postings`, `/api/interviews`, `/api/documents`, `/api/extractions`, `/api/jobs` (matches + bulk upload), `/api/ats`, `/api/coding`.

WebSocket (browser webpage TTS): `/ws/audio-stream/{page_session_id}`. Recall audio uses the separate receiver on `WEBSOCKET_PORT` (example **5213**).

---

## 9. Database

PostgreSQL. Apply **numbered** files via `database/migrate.py`. Tracked in `schema_migrations`.

**Rules**

- Add a new `NNN_my_change.sql` with `IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS`.
- Do **not** edit already-applied historical files as the primary approach.
- Never `DROP SCHEMA` / re-run `init.sql` on production (local rebuild only).
- Deploy dumps **only when there are pending migrations** (`backups/db/`, keep last 3).

**Core entities**

```
organization
  └── users
        ├── job_postings ── documents, upload_batches, job_candidate_matches
        ├── candidates
        └── interview_sessions
              ├── interview_configs (frozen JD/CV)
              ├── interview_questions → interview_answers
              ├── transcript_turns
              ├── interview_reports
              ├── candidate_feedback
              └── coding config / submissions / proctor events
```


| Need                    | Table / view                                                       |
| ----------------------- | ------------------------------------------------------------------ |
| Session / bot / meeting | `interview_sessions` (`bot_id` NULL = scheduled)                   |
| JD/CV used that run     | `interview_configs`                                                |
| Generated Q list        | `document_extractions.questions_json` + `interview_questions`      |
| Scores                  | `interview_answers`                                                |
| Pass/fail               | `interview_reports.qualified` (**stage1_average**)                 |
| Dialogue                | `transcript_turns`                                                 |
| Org ATS                 | `organization.ats_provider`, `ats_config`, `ats_api_key_encrypted` |
| Dashboard lists         | `v_interview_overview`, `v_job_posting_stats`                      |


`qdrant_document_points` exists in schema; there is **no live Qdrant pipeline** in the app today (placeholder for later RAG).

Commands (venv + `backend/.env`):

```bash
python database/migrate.py status
python database/migrate.py pending-count
python database/migrate.py apply
python database/migrate.py dump --dir backups/db --keep 3
```

---

## 10. Environment and secrets checklist

Canonical list with **use cases:** `KNOWLEDGE_TRANSFER_ENV.md`. Template: `backend/.env.example`. Frontend: `frontend/.env.example`.

**Must work in production**


| Variable                          | Purpose                                                 |
| --------------------------------- | ------------------------------------------------------- |
| `DATABASE_URL`                    | Postgres                                                |
| `APP_ENV=production`              | Shorter JWT, stricter defaults                          |
| `JWT_SECRET`                      | Auth signing — never reuse the code default             |
| `CORS_ORIGINS`                    | Exact browser origins (VM IP / domain), comma-separated |
| `FRONTEND_BASE_URL`               | Coding links in wrap-up TTS/emails                      |
| `GROQ_API_KEY` + models           | Interview + scoring                                     |
| `SARVAM_API_KEY`                  | STT/TTS                                                 |
| `RECALL_API_KEY`, `RECALL_REGION` | Meeting bots                                            |
| `PUBLIC_WEBSOCKET_URL`            | Recall must reach this WS                               |
| `PUBLIC_WEBHOOK_URL`              | Recall webhooks (ngrok/public HTTPS)                    |
| `ATS_SECRET_ENCRYPTION_KEY`       | Fernet (or long passphrase)                             |
| `GRAPH_*` + `ACCESS_NOTIFY_TO`    | Access emails                                           |
| `DOCUMENT_UPLOAD_DIR`             | CV/JD files on disk                                     |


**GitHub Actions secrets (deploy):** `VM_HOST`, `VM_USER`, `VM_SSH_KEY`.

**Fill in for handover (do not write values here)**


| Item                                       | Where it lives    | Owner after exit |
| ------------------------------------------ | ----------------- | ---------------- |
| Azure VM SSH                               | §15 — `azureuser@20.244.7.67` + `Aibot_key.pem` | _                |
| Postgres password                          | Same DB user `postgres` / `1234` / `prabhat_DB`. **Prod host `127.0.0.1`**, **dev host `localhost`** — see §15.2 | _                |
| Recall / Groq / Sarvam billing             | vendor dashboards | _                |
| Graph app registration                     | Azure AD          | _                |
| nginx TLS / DNS (`prabhat.rigvedtech.com`) | _                 | _                |
| GitHub repo + Actions                      | _                 | _                |


---

## 11. Production deploy

**Trigger:** push or merge to `main` **only**. Other branches do not deploy. Manual: Actions → “Deploy to Azure VM” with confirm = `deploy`.

**VM layout (from deploy docs)**


| Piece    | Location                                   |
| -------- | ------------------------------------------ |
| Repo     | `/home/azureuser/speechAgent`              |
| API unit | systemd `speechagent-api`                  |
| Frontend | nginx root `/var/www/speechagent`          |
| Env      | `backend/.env`, `frontend/.env.production` |
| DB dumps | `backups/db/`                              |


`scripts/deploy-vm.sh` **flow**

1. Stop `speechagent-api`
2. `git fetch` + hard reset to `origin/main`
3. `pip install -r backend/requirements.txt`
4. If pending SQL > 0: `pg_dump` (keep 3) then `migrate.py apply`
5. Start API; fail deploy if unit is not active (trap restarts API if deploy died before healthy)
6. `npm ci && npm run build` in `frontend`
7. Copy `dist/` to nginx root
8. `curl http://127.0.0.1:8000/health` and frontend HTTP check

**Why the YAML is tiny:** `appleboy/ssh-action` wraps the script in `bash -c`; complex inline YAML broke. All real logic is in `deploy-vm.sh`.

**Ops commands on the VM**

```bash
sudo systemctl status speechagent-api
sudo systemctl restart speechagent-api
sudo journalctl -u speechagent-api -f
# app file logs:
ls backend/logs/api_server_*.log
```

Transcripts: `backend/transcripts/`. Uploads: `backend/uploads/` (or `DOCUMENT_UPLOAD_DIR`).

**Schema change in prod:** add `NNN_*.sql` → merge to `main` → deploy applies it. Never wipe.

**Rollback:** previous git SHA + restore last dump **only if a migration was the problem**. Code-only rollback = checkout previous commit and restart (no dump needed).

---

## 12. Frontend notes

- API client: `frontend/src/lib/api-client.ts` + `frontend/src/lib/api/index.ts`.
- Auth token: `frontend/src/lib/auth-store.ts`.
- `VITE_LANDING_ONLY=true` (Vercel / `.env.production` for public marketing) **strips dashboard routes** from the bundle. Full app on the VM must have `VITE_LANDING_ONLY=false` (or unset) and `CORS_ORIGINS` including that origin.
- Landing “Get started” can point at VM `/request-access` via `VITE_GET_STARTED_URL`.
- Extraction/question calls can take minutes; Vite proxy timeout is 300s.

---

## 13. Operations runbook


| Symptom                                      | Likely cause                                          | Where to look                                                      |
| -------------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------ |
| Frontend loads, API 401/empty                | JWT secret rotated; user inactive                     | login, `users.is_active`                                           |
| CORS errors                                  | `CORS_ORIGINS` missing that origin                    | `backend/.env`, nginx host vs IP vs HTTPS                          |
| Bot never joins                              | Recall key/region; bad meeting URL; lobby timeout     | Recall dashboard, `recall_bot_service.py`, `LOBBY_TIMEOUT_MINUTES` |
| Bot in call but silent                       | TTS fail, ffmpeg missing, output-media / WS URL wrong | logs, `PUBLIC_WEBSOCKET_URL`, Sarvam/Edge                          |
| Candidate not heard                          | STT/VAD, Recall audio WS down, muted mic              | `audio_receiver`, Sarvam, presence ladder                          |
| Hinglish start 409                           | Localization still running                            | retry `/api/start`; `question_localizer.py`                        |
| Empty/truncated scores or TTS leaks thinking | Groq GPT-OSS kwargs                                   | `groq_runtime.py`, model names, TPM limits                         |
| Interview stops after Q8                     | Stage-1 gate failed                                   | `CONTINUE_AVG_THRESHOLD`, report `stage1_average`                  |
| Duplicate bot 409                            | Same meeting URL already mapped                       | `SessionManager.meeting_to_bot`                                    |
| Deploy skipped                               | Push was not `main`                                   | Actions log                                                        |
| Migration panic                              | Pending SQL                                           | `migrate.py status`; dumps in `backups/db`                         |
| OCR empty CV                                 | Scanned PDF, Tesseract missing                        | `DOCUMENT_OCR_ENGINE`, `TESSERACT_CMD`                             |
| Access email not sent                        | Graph perms / sender                                  | `graph_mail.py`, Azure app `Mail.Send`                             |
| Coding auto-submit                           | Proctor 3/3 or second display                         | `proctoring/engine.ts`                                             |
| Coding run fails                             | Language binary not on VM PATH                        | `coding_runner.py` (python/node/etc.)                              |


**Useful log prefixes:** `[LLM]`, `[STT]`, `[TTS]`, `[STAGE1 GATE]`, `[BG SCORE]`, `[CORS]`.

---

## 14. Related in-repo docs

Read these when you need depth; this KT does not replace them.


| Doc                                    | Topic                                     |
| -------------------------------------- | ----------------------------------------- |
| `backend/README.md`                    | Old STT→LLM→TTS diagram; runtime modes    |
| `KNOWLEDGE_TRANSFER_ENV.md`        | **Every `backend/.env` variable and its use case** |
| `backend/.env.example`                 | Template (fill secrets in `.env`, not in git)     |
| `database/README.md`                   | Migrations, table map, query cheat sheet  |
| `frontend/README.md`                   | Vite vs Vercel landing-only               |
| `backend/API_REFERENCE.md`             | Older API notes — verify against `/docs`  |
| `backend/RECALL_INTEGRATION_README.md` | Recall                                    |
| `backend/SARVAM_INTEGRATION.md`        | Sarvam                                    |
| `backend/WEBRTC_*.md`                  | Historical WebRTC; webpage PCM is current |


---

## 15. Azure VM access, Postgres, ngrok, and IPs

This is the production box GitHub Actions deploys to. **Do not paste Groq / Sarvam / Recall / Graph / JWT values here** — they live only in `backend/.env` on the VM (and local laptop `.env` for dev).

### 15.1 SSH into the VM (from a Windows laptop)

| Item | Value |
| --- | --- |
| Public IP | `20.244.7.67` |
| SSH user | `azureuser` |
| Key file (current owner laptop) | `C:\Users\Pranay.Sherkar\Downloads\Aibot_key.pem` |
| Repo on VM | `/home/azureuser/speechAgent` |
| API process | systemd `speechagent-api` |
| Frontend | nginx `/var/www/speechagent` |
| App env file | `/home/azureuser/speechAgent/backend/.env` |

```powershell
ssh -i "C:\Users\Pranay.Sherkar\Downloads\Aibot_key.pem" azureuser@20.244.7.67
```

First-time Windows: if SSH refuses the key, run:

```powershell
icacls "C:\Users\Pranay.Sherkar\Downloads\Aibot_key.pem" /inheritance:r
icacls "C:\Users\Pranay.Sherkar\Downloads\Aibot_key.pem" /grant:r "$($env:USERNAME):(R)"
```

After login:

```bash
cd /home/azureuser/speechAgent
sudo systemctl status speechagent-api
sudo journalctl -u speechagent-api -f
curl -sS http://127.0.0.1:8000/health
```

GitHub Actions uses the same host via secrets `VM_HOST` / `VM_USER` / `VM_SSH_KEY` (should match `20.244.7.67` + `azureuser` + this PEM). Push to `main` runs `scripts/deploy-vm.sh`. Manual deploy on the box:

```bash
cd /home/azureuser/speechAgent
bash scripts/deploy-vm.sh
```

### 15.2 Postgres (two different machines — do not mix)

| Environment | `DATABASE_URL` | Notes |
| --- | --- | --- |
| **Development (laptop only)** | `postgresql://postgres:1234@localhost:5432/prabhat_DB` | Host **`localhost`**. Local `backend/.env`. |
| **Production (Azure VM)** | `postgresql://postgres:1234@127.0.0.1:5432/prabhat_DB` | Host **`127.0.0.1`**. File: `/home/azureuser/speechAgent/backend/.env`. Postgres is on the VM; the API uses loopback, not public IP `20.244.7.67`. |

User `postgres`, password `1234`, database `prabhat_DB` on both. Only the host string changes (`localhost` vs `127.0.0.1`).

On the VM, confirm:

```bash
grep '^DATABASE_URL=' /home/azureuser/speechAgent/backend/.env
sudo -u postgres psql -d prabhat_DB -c '\conninfo'
```

If deploy needs a dump/restore, dumps are under `/home/azureuser/speechAgent/backups/db/` (last 3, only when migrations are pending).

### 15.3 What ngrok is for (and what it is not)

Recall.ai **cannot call `localhost`**. ngrok (or a real HTTPS domain) gives Recall a **public HTTPS URL** that forwards to our FastAPI process (**port 8000**).

| Env var | What Recall uses it for | Typical value |
| --- | --- | --- |
| `PUBLIC_NGROK_URL` | HTTPS base Recall’s bot loads for **output-media** (TTS webpage). Must be `https://`. | ngrok URL **or** `https://prabhat.rigvedtech.com` on the VM |
| `PUBLIC_WEBHOOK_URL` | HTTPS base for **webhooks** (transcript / bot events). Often the **same** ngrok/HTTPS origin. | Same as ngrok / public API host |
| `PUBLIC_WEBSOCKET_URL` | **Not ngrok.** Recall streams **meeting audio in** to our receiver on **port 5213**. | `ws://<public-ip>:5213` |

**Local laptop current pattern** (from the developer `.env`; ngrok hostname **changes every time the free tunnel restarts**):

| Piece | Value / command |
| --- | --- |
| Start API | `python api_server.py` (port **8000** + WS **5213**) |
| Start ngrok | `ngrok http 8000` |
| Copy the `https://….ngrok-free.dev` URL into | `PUBLIC_NGROK_URL` and `PUBLIC_WEBHOOK_URL` |
| Example tunnel (will go stale) | `https://hyperfastidiously-subarboreal-jamika.ngrok-free.dev` |
| Audio WS (Recall → us) | `PUBLIC_WEBSOCKET_URL=ws://27.107.214.154:5213` |
| What `27.107.214.154` is | Public IP of the **machine running `api_server.py`** (office/ISP), **not** the Azure VM `20.244.7.67` |

**Azure VM production pattern**

| Piece | Value |
| --- | --- |
| SSH / nginx / app | `20.244.7.67` (and DNS `prabhat.rigvedtech.com` if pointed here) |
| Recruiter UI / API | nginx → static files + `/api` to `127.0.0.1:8000` |
| Audio WS | `PUBLIC_WEBSOCKET_URL` in **VM** `backend/.env` — should be `ws://20.244.7.67:5213` **or** `wss://<domain>` if TLS is terminated for 5213. Azure NSG must allow **5213** from the internet for Recall. |
| ngrok on the VM | **Not required** if the VM already has a public HTTPS origin. Use ngrok only for **laptop** demos. |

If the bot joins but is **silent**: check `PUBLIC_NGROK_URL` / output-media HTTPS. If the **candidate is not heard**: check `PUBLIC_WEBSOCKET_URL` and that port **5213** is reachable.

### 15.4 IP / port cheat sheet

| Address | Used for |
| --- | --- |
| `20.244.7.67` | Azure VM public IP — SSH, nginx site, GitHub deploy target |
| `azureuser@20.244.7.67` | SSH login |
| `27.107.214.154:5213` | Local-dev Recall **audio ingest** (laptop/office public IP). Do not SSH here. |
| `127.0.0.1:8000` | API on the same machine (laptop or VM loopback) |
| `0.0.0.0:5213` | Audio WebSocket bind (`WEBSOCKET_HOST` / `WEBSOCKET_PORT`) |
| `localhost:5432` | **Dev only** Postgres (`DATABASE_URL` host `localhost`) |
| `127.0.0.1:5432` | **Production** Postgres on the VM (`DATABASE_URL` host `127.0.0.1`) |
| ngrok `https://…` | Recall **HTTPS** callbacks + TTS webpage (laptop). Not the WS audio IP. |

### 15.5 After SSH — useful commands

```bash
cd /home/azureuser/speechAgent

# App
sudo systemctl restart speechagent-api
sudo journalctl -u speechagent-api -n 200 --no-pager

# Confirm what Recall will hit (no secrets except what you already know is on the box)
grep -E '^(PUBLIC_WEBSOCKET_URL|PUBLIC_WEBHOOK_URL|PUBLIC_NGROK_URL|WEBSOCKET_PORT|RECALL_REGION)=' backend/.env

# Frontend
ls /var/www/speechagent
```

Keep `Aibot_key.pem` off git, Teams, and this markdown file’s git history beyond the **path**. Rotate the key if it was ever emailed.

---

