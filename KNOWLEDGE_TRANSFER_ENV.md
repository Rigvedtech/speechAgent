# Knowledge Transfer — backend environment variables

**File:** `backend/.env` (real values) · template: `backend/.env.example`  
**Last updated:** 20 August 2026  
**Rule:** this page lists **variable names and use cases only**. Do not paste API keys, Graph secrets, JWT secrets, or ATS Fernet keys here.

Restart `python api_server.py` / `sudo systemctl restart speechagent-api` after any `.env` change.

| Environment | Where | Notes |
| --- | --- | --- |
| Development | laptop `backend/.env` | Postgres host **`localhost`**. Vite CORS. ngrok for Recall HTTPS. |
| Production | VM `/home/azureuser/speechAgent/backend/.env` | Postgres host **`127.0.0.1`**. Public IP / domain CORS. No ngrok if HTTPS already public. |

---

## Auth, database, browser

| Variable | Use case |
| --- | --- |
| `DATABASE_URL` | Postgres connection. **Dev:** `postgresql://postgres:1234@localhost:5432/prabhat_DB`. **Prod:** `postgresql://postgres:1234@127.0.0.1:5432/prabhat_DB`. |
| `APP_ENV` | `development` vs `production`. Production shortens JWT life and tightens defaults. |
| `JWT_SECRET` | Signs recruiter/admin JWTs. Must be a long random string in production. |
| `JWT_ALGORITHM` | JWT algorithm (`HS256`). |
| `JWT_EXPIRE_MINUTES` | Token lifetime. Overridden to 8 hours when `APP_ENV=production` unless you set this. |
| `JWT_ISSUER` | JWT `iss` claim (`speechagent`). |
| `JWT_AUDIENCE` | JWT `aud` claim (`speechagent-api`). |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API. **No code default** — empty = browser blocked. Dev: `http://localhost:5173,http://127.0.0.1:5173`. Prod: VM IP and/or `https://prabhat.rigvedtech.com`. |
| `FRONTEND_BASE_URL` | Public app origin. Used in coding links spoken at wrap-up and set-password emails. Dev: `http://localhost:5173`. Prod: `https://prabhat.rigvedtech.com`. |
| `PASSWORD_SETUP_HOURS` | How long a grant invite link stays valid (1–168). |
| `PLATFORM_ADMIN_EMAILS` | Optional extra emails treated as platform admin. Prefer DB role `platform_admin`. |

---

## Microsoft Graph mail (access requests)

| Variable | Use case |
| --- | --- |
| `GRAPH_TENANT_ID` | Azure AD tenant for app-only `Mail.Send`. |
| `GRAPH_CLIENT_ID` | App registration client ID (`CLIENT_ID` alias also works). |
| `GRAPH_CLIENT_SECRET` | App client secret (`CLIENT_SECRET` alias also works). |
| `GRAPH_SENDER` | Mailbox UPN that sends (`recops@…`). Needs Mail.Send + admin consent. |
| `ACCESS_NOTIFY_TO` | Inbox that receives **new access-request** alerts. Grant invite mail goes to the **applicant**, not this inbox. |

---

## Files, ATS, documents

| Variable | Use case |
| --- | --- |
| `DOCUMENT_UPLOAD_DIR` | Folder for uploaded CV/JD binaries (relative to `backend/` unless absolute). |
| `DOCUMENT_MAX_BYTES` | Max upload size (example 15 MB). |
| `ATS_SECRET_ENCRYPTION_KEY` | Fernet (or passphrase) used to encrypt each org’s ATS API key in the DB. Keep stable or orgs must re-enter keys. |
| `ATS_API_KEY` | Legacy single-key fallback if `ats_config` points at an env name. Prefer per-org encrypted key. |
| `DOCUMENT_OCR_ENGINE` | `auto` / Tesseract / Paddle for scanned PDFs. |
| `DOCUMENT_OCR_LANGUAGES` | Tesseract langs (`eng`, or `eng+hin`). |
| `DOCUMENT_OCR_PDF_DPI` | Raster DPI for PDF OCR. |
| `TESSERACT_CMD` | Full path to `tesseract.exe` if it is not on PATH. |

---

## Groq LLM

| Variable | Use case |
| --- | --- |
| `GROQ_API_KEY` | Groq Cloud key. Live interview speech, scoring, question gen, CV/JD parse, coding problem gen. |
| `GROQ_MODEL` | Spoken interviewer model. After 16 Aug 2026: `openai/gpt-oss-120b` (Llama 70B retired). |
| `GROQ_EVALUATOR_MODEL` | Fast/cheap model for scores, questions, extract, matching. After 16 Aug 2026: `openai/gpt-oss-20b`. Groq on-demand TPM is 8000 — keep completion size under that with the prompt. |
| `GROQ_EVALUATOR_MAX_TOKENS` | Max completion tokens for scoring/JSON calls (helper may still cap for TPM). |
| `GROQ_TEMPERATURE` | Spoken-reply randomness. |
| `GROQ_MAX_TOKENS` | Max spoken reply tokens (GPT-OSS needs extra room for hidden reasoning; `groq_runtime.py` bumps this). |
| `GROQ_REQUEST_TIMEOUT_SEC` | HTTP timeout for Groq. |
| `OLLAMA_MODEL` | Local fallback model if Groq is missing or 429s on the **spoken** stream. |
| `OLLAMA_EVALUATOR_FALLBACK` | If true, scoring falls back to Ollama. **Off in production** (can hang 60s+). |

---

## n8n (legacy extract)

| Variable | Use case |
| --- | --- |
| `N8N_CV_URI` | Optional webhook to extract CV text from a file. App can extract locally instead. |
| `N8N_JD_URI` | Optional webhook to extract JD text from a file. |
| `N8N_QUESTIONS_URI` | **Unused for generation.** Questions are local Groq (`POST /api/generate-questions`). Leftover if n8n still has an old flow. |
| `N8N_EXTRACTION_TIMEOUT_SEC` | Timeout for those webhooks. |

---

## Sarvam STT / TTS

| Variable | Use case |
| --- | --- |
| `SARVAM_API_KEY` | Sarvam key. Primary speech-to-text and text-to-speech in the meeting. |
| `SARVAM_STT_ENABLED` | Use Saaras as primary STT. |
| `SARVAM_TTS_ENABLED` | Use Bulbul as primary TTS. |
| `SARVAM_STT_MODEL` | STT model id (`saaras:v3`). |
| `SARVAM_STT_LANGUAGE` | Default STT language (`en-IN`). Hinglish join overrides via language profile. |
| `SARVAM_STT_MODE` | `transcribe` (English) or `codemix` (Hinglish). |
| `SARVAM_STT_HIGH_VAD` | Sarvam high-VAD flag. |
| `SARVAM_TTS_MODEL` | TTS model (`bulbul:v3`). |
| `SARVAM_TTS_SPEAKER` | Voice (`shubh`). |
| `SARVAM_TTS_LANGUAGE` | TTS language (`en-IN` / Hindi for Hinglish). |
| `SARVAM_TTS_SAMPLE_RATE` | PCM rate sent into the meeting (24000). Must match output-media page. |
| `SARVAM_TTS_PACE` | Speaking speed (higher = faster). |
| `SARVAM_TTS_TEMPERATURE` | Voice variation (lower = cleaner). |
| `TTS_STREAMING_ENABLED` | Stream TTS chunks vs one batch per utterance. |
| `SARVAM_MAX_RETRIES` | Retries on Sarvam HTTP failures. |
| `SARVAM_RETRY_BASE_SECONDS` | Backoff base between retries. |
| `STT_FALLBACK_ENABLED` | If Sarvam STT fails, use Faster-Whisper. |
| `TTS_FALLBACK_ENABLED` | If Sarvam TTS fails, use Edge-TTS. |
| `HINGLISH_WHISPER_FALLBACK` | Allow Whisper on Hinglish **final** answers if Sarvam fails. |
| `SARVAM_LOCAL_SILENCE_SEC` | Local VAD silence for Sarvam path. |
| `SARVAM_STT_COLLECT_DEADLINE_SEC` | How long to wait for a Sarvam transcript after an utterance. |
| `SARVAM_STT_COLLECT_DEADLINE_MAX_SEC` | Cap on that wait. |
| `SARVAM_STT_TRANSCRIBE_TIMEOUT_SEC` | Blocking transcribe timeout. |
| `SARVAM_STT_TRANSCRIBE_TIMEOUT_MAX_SEC` | Cap on transcribe timeout. |
| `SARVAM_STT_TRAILING_SILENCE_SEC` | Trailing silence before flush. |
| `SARVAM_STT_WAIT_AFTER_END_SEC` | Extra wait after VAD end. |
| `SARVAM_QUALITY_MIN_UTTERANCE_SEC` | Reject ultra-short Sarvam finals on long audio. |
| `SARVAM_QUALITY_MIN_CHARS` | Reject tiny Sarvam text; may fallback. |
| `STREAM_STT_ENABLED` | Live STT while the candidate is still speaking (lower latency). |
| `STREAM_STT_FINALIZE_SEC` | Short collect after silence on the streaming path. |
| `STREAM_STT_MIN_CHARS` | Minimum live text before trusting stream vs batch. |

---

## Whisper / Edge-TTS / raw audio

| Variable | Use case |
| --- | --- |
| `MODEL_SIZE` | Faster-Whisper size (`tiny.en` faster, `small.en` more accurate). |
| `WHISPER_LOCAL_SILENCE_SEC` | VAD silence when using Whisper. |
| `WHISPER_PRELOAD_ENABLED` | Load Whisper at startup (saves first-fallback delay). |
| `TTS_VOICE` | Edge-TTS voice (`en-IN-PrabhatNeural`). |
| `TTS_RATE` | Edge-TTS rate (e.g. `+10%`). |
| `TTS_REDUCE_PAUSES` | Shorten pauses at full stops in Edge-TTS. |
| `SAMPLE_RATE` | Mic/STT sample rate (16000). |
| `CHANNELS` | Audio channels (1 = mono). |
| `BOT_NAME` | Display name Recall uses in the meeting (`Prabhat`). |

---

## Recall.ai and public URLs

| Variable | Use case |
| --- | --- |
| `RECALL_API_KEY` | Create/join/leave meeting bots. |
| `RECALL_REGION` | Recall region (`ap-northeast-1` → that region’s API host). |
| `RECALL_USE_OUTPUT_MEDIA` | `true` = bot speaks via HTTPS webpage + PCM (needs `PUBLIC_NGROK_URL`). `false` = older file-upload TTS. |
| `RECALL_INCLUDE_BOT_AUDIO_IN_RECORDING` | Include Prabhat’s voice in the Recall recording (same $0.50/hr). |
| `WEBSOCKET_HOST` | Bind address for incoming meeting audio (`0.0.0.0`). |
| `WEBSOCKET_PORT` | Port Recall streams **candidate audio** to (**5213**). Open this in Azure NSG on the VM. |
| `PUBLIC_WEBSOCKET_URL` | URL Recall is told to send audio to. **Not ngrok.** Dev example: `ws://27.107.214.154:5213`. Prod: `ws://20.244.7.67:5213` (or `wss://` if TLS). |
| `PUBLIC_WEBHOOK_URL` | Public **HTTPS** origin for Recall webhooks (transcript/events). Dev = ngrok. Prod = public API HTTPS. |
| `PUBLIC_NGROK_URL` | Public **HTTPS** origin Recall loads for the TTS webpage. Dev = `ngrok http 8000`. Prod = site HTTPS if output-media is on. Must be `https://`. |
| `LOBBY_TIMEOUT_MINUTES` | Drop lobby bots that never enter the meeting. |

ngrok is only for machines Recall cannot reach (laptop). Command: `ngrok http 8000`, then paste the `https://…` URL into `PUBLIC_NGROK_URL` and `PUBLIC_WEBHOOK_URL`.

---

## Legacy Teams bot (not the current Recall path)

| Variable | Use case |
| --- | --- |
| `Microsoft_App_Id` | Old .NET / Bot Framework Teams app. Not used by `api_server.py` + Recall. |
| `Microsoft_App_Secret` | Secret for that legacy bot. |
| `AssemblyAI_API_KEY` | Legacy STT for that path. Live interviews use Sarvam. |

---

## Interview length, stage-1 gate, abuse

| Variable | Use case |
| --- | --- |
| `MAX_QUESTIONS` | Cap on core questions (15). |
| `MAX_INTERVIEW_MINUTES` | Hard interview clock (30). |
| `MAX_STRIKES` | Off-track / policy strikes before close. |
| `MAX_OFF_TOPIC_REDIRECTS` | How often the bot may pull the candidate back. |
| `ABUSE_MAX_WARNINGS` | Abuse language warnings before the bot ends. |
| `CONTINUE_AVG_THRESHOLD` | Stage-1 continue if Q1–N average ≥ this (/10). |
| `STAGE1_QUESTION_COUNT` | How many early questions feed that average (7). |
| `STAGE1_BRIDGE_QUESTION` | Always asked; decide continue vs wrap after this (8). |
| `ROLLING_WINDOW` | Rolling score window (usually same as stage-1 count). |
| `STAGE1_GATE_WAIT_SEC` | Wait for background scores before the gate decision. |
| `MAX_QUESTION_REPEATS` | Candidate “please repeat” cap (not scored). |
| `MAX_QUESTION_REPHRASES` | Candidate “say that simpler” cap (not scored). |
| `NAME_NORMALIZE_ENABLED` | Normalize candidate name in speech. |

---

## Turn-taking (when an answer ends)

| Variable | Use case |
| --- | --- |
| `MIN_ANSWER_WORDS` | Too-short answers may be treated as incomplete. |
| `MIN_SHORT_COMPLETE_WORDS` | Floor for a short-but-complete reply. |
| `MAX_ANSWER_CONTINUATIONS` | How many times we wait for them to continue. |
| `INCOMPLETE_ANSWER_CHECK_ENABLED` | Enable incomplete-answer guard. |
| `MAX_ANSWER_SEC` | Hard cap on one answer (420s). |
| `CORE_ANSWER_SOFT_SILENCE_SEC` | Silence that **soft-ends** an utterance (~2s). |
| `CORE_LONG_ANSWER_SILENCE_SEC` | Silence used on the long-answer STT path. |
| `CORE_LONG_ANSWER_SPEECH_SEC` | Speech length before “long answer” rules apply. |
| `CORE_ANSWER_MERGE_WINDOW_SEC` | After soft end, keep listening; new speech = **same** answer. |
| `CORE_ANSWER_MAX_HOLD_SEC` | Max hold before we force-end. |
| `TURN_MERGE_ENABLED` | Merge split VAD chunks into one scored turn. |
| `TURN_MERGE_WINDOW_SEC` | Time window for that merge. |
| `TURN_MERGE_MIN_AUDIO_SEC` | Ignore tiny audio blips. |
| `TURN_MERGE_MIN_CHARS` | Ignore tiny transcripts. |
| `TURN_MERGE_MIN_HOLD_SEC` | Minimum hold before merge commit. |
| `TURN_MERGE_MAX_SHORT_HOLD_SEC` | Cap hold for short fragments. |
| `TURN_FLUSH_GUARD_MIN_CHARS` | Do not flush tiny tails during a long answer. |
| `TURN_FLUSH_DEFER_SEC` | Defer flush that long. |
| `ANSWER_ACK_BEFORE_EVAL` | If true, speak an ack before scoring (usually false). |
| `PARALLEL_SCORE_ENABLED` | Speak the next question while the previous answer scores. |
| `CLARIFIER_REPLY_SILENCE_SEC` | Silence after a clarifier reply. |
| `ANSWER_INITIAL_LISTEN_SEC` | First listen budget (60s). |
| `ANSWER_EXTEND_STEP_SEC` | Extra listen if they are still talking (30s). |
| `ANSWER_MAX_TOTAL_SEC` | Total listen budget (420s). |
| `SHORT_UTTERANCE_MAX_SEC` | “Repeat that?” style short turns use faster endpointing. |
| `SHORT_UTTERANCE_SILENCE_SEC` | Silence for those short turns. |
| `INCOMPLETE_MERGE_WINDOW_SEC` | Extra listen if the last turn looked incomplete. |
| `USER_BARGE_IN_ENABLED` | If true, candidate can cut bot TTS. Production is **false**. |

---

## Mid-answer topic poll (depth interrupts are off)

| Variable | Use case |
| --- | --- |
| `BOT_INTERRUPT_ENABLED` | Master switch for mid-answer bot speech. Topic poll uses this. |
| `BOT_INTERRUPT_MIN_PARTIAL_SEC` | Ignore tiny partials. |
| `BOT_INTERRUPT_GATE_MIN_CONFIDENCE` | Confidence needed to act. |
| `BOT_INTERRUPT_CLARIFIER_ON_TRACK` | Old depth clarifiers. **Keep false.** |
| `BOT_INTERRUPT_MAX_DEPTH_CLARIFIERS_PER_Q` | **0** — disabled. |
| `BOT_INTERRUPT_MAX_CLARIFIERS_PER_Q` | **0** — disabled. |
| `BOT_INTERRUPT_DRAG_REPHRASE_MAX` | **0** — disabled. |
| `BOT_INTERRUPT_MAX_DRAG_DEPTH_PER_Q` | **0** — disabled. |
| `CLARIFIER_ON_TRACK_MIN_SPEECH_SEC` | **999** — unreachable (legacy off). |
| `CLARIFIER_MIN_INTERVAL_SEC` | **999** — unreachable. |
| `CLARIFIER_REPLY_SCORE_MIN_CHARS` | Min chars before a clarifier reply is scored. |
| `MAIN_QUESTION_INTERRUPT_COOLDOWN_SEC` | Cooldown after the main question is spoken. |
| `MID_ANSWER_BOT_COOLDOWN_SEC` | Cooldown between bot mid-answer lines. |
| `DRAG_SKIP_SCORE` | Score used when we skip a dragging answer. |
| `DRAG_CONTEXT_MIN_OVERLAP` | Topic-word overlap to count as still on-topic. |
| `PROGRESS_GATE_LONG_ANSWER_SEC` | Long-answer progress check. |
| `PROGRESS_GATE_MIN_TOPIC_OVERLAP` | Words that must overlap the question. |
| `PROGRESS_GATE_RULE_DRAG_MIN_SEC` | How long off-topic before rule-DRAG. |
| `PROGRESS_GATE_RULE_DRAG_MIN_WORDS` | Min words before rule-DRAG. |
| `PROGRESS_GATE_UNCLEAR_ESCALATION_CHECKS` | Unclear checks before escalate. |
| `ANSWER_TOPIC_POLL_INTERVAL_SEC` | Topic poll every N seconds of **speech**. |
| `ANSWER_TOPIC_POLL_WINDOW_SEC` | Window of speech inspected. |
| `MAX_TOPIC_REDIRECTS_PER_QUESTION` | Then stop redirecting. |
| `ANSWER_FIRST_CHECK_SEC` | Legacy slot. **9999** = off. |
| `ANSWER_INTERRUPT_2_AFTER_SEC` | Legacy slot. **9999** = off. |
| `ANSWER_SECOND_CHECK_SEC` | Legacy slot. **9999** = off. |
| `ANSWER_MAX_INTERRUPTS` | **0** — no slot interrupts. |
| `ANSWER_INTERRUPT_SLOT_TOLERANCE_SEC` | Timing slack if slots were on. |
| `ANSWER_DEPTH_CHECK_WINDOW_SEC` | Window for old depth checks. |
| `ANSWER_DRAG_GRACE_SEC` | Grace before drag handling. |

---

## Presence (only before they start answering)

| Variable | Use case |
| --- | --- |
| `POST_TTS_SILENCE_CHECK_ENABLED` | After the question, if nobody speaks, run the “can you hear me?” ladder. |
| `POST_TTS_SILENCE_MIN_AFTER_QUESTION_SEC` | Min wait after the question. |
| `POST_QUESTION_SILENCE_STEP1_SEC` | First presence prompt. |
| `POST_QUESTION_SILENCE_STEP2_SEC` | Second prompt. |
| `POST_QUESTION_FINAL_WRAP_SEC` | Then wrap / leave path. |
| `MAX_PRESENCE_CHECKS_PER_QUESTION` | Cap (1). Never mid-answer. |
| `PRESENCE_ONLY_AFTER_QUESTION` | Presence only after a question, not randomly. |
| `PRESENCE_SKIP_DURING_ANSWER` | Do not run presence once they are answering. |

---

## Intro and intent

| Variable | Use case |
| --- | --- |
| `INTRO_MIN_CHARS` | Intro must be this long before Q1 (short “hello” does not count). |
| `INTRO_MIN_SPEECH_SEC` | Intro must last this many seconds of speech. |
| `INTRO_MERGE_WINDOW_SEC` | Merge intro fragments. |
| `STALE_ANSWER_GUARD_SEC` | Ignore leftover audio from the previous question. |
| `STALE_ANSWER_MAX_CHARS` | Max chars treated as stale tail. |
| `TURN_INTENT_CLASSIFIER_ENABLED` | Groq classifies repeat / rephrase vs real answer. |
| `TURN_INTENT_MAX_CHARS` | Only classify short turns as meta-requests. |
| `TURN_INTENT_MIN_CONFIDENCE` | Below this, fall back to regex. |

---

## Logging

| Variable | Use case |
| --- | --- |
| `FILE_LOGGING_ENABLED` | Write `backend/logs/api_server_*.log`. Transcripts stay under `backend/transcripts/`. |

---

## Camera integrity (voice interview)

`CAMERA_INTEGRITY_ENABLED=false` in `.env.example` (prod default). Local `.env` may have `true` for QA.

| Variable | Use case |
| --- | --- |
| `CAMERA_INTEGRITY_ENABLED` | If true, Recall sends PNG video; FaceAnalyzer can TTS-warn (multi-face, looking away). |
| `CAMERA_GAZE_MODE` | `production` / `interview` / `strict`. Interview = head/face-first. |
| `CAMERA_GAZE_DEBUG` | Extra gaze logs. |
| `CAMERA_WARN_TTS_ENABLED` | Speak camera warnings in the meeting. |
| `CAMERA_WARN_AFTER_SEC` | Dwell before a generic warn. |
| `CAMERA_WARN_AFTER_MULTI_FACE_SEC` | Dwell before 2+ faces warn. |
| `CAMERA_WARN_AFTER_DOWN_SEC` | Looking down. |
| `CAMERA_WARN_AFTER_SIDE_SEC` | Looking left/right (second screen). |
| `CAMERA_WARN_AFTER_AWAY_SEC` | Hard look-away. |
| `CAMERA_WARN_COOLDOWN_SEC` | Silence between warns. |
| `CAMERA_WARN_COOLDOWN_MULTI_FACE_SEC` | Cooldown for multi-face. |
| `CAMERA_WARN_HOLD_FRAMES` | Frames required (local webcam path). |
| `CAMERA_WARN_HOLD_FRAMES_LIVE` | Frames required on live Recall (~2 fps). |
| `CAMERA_WARN_RISK_GRACE_SEC` | Keep risk timer through short blips. |
| `CAMERA_WARN_INCLUDE_SIDE_LOOK` | Enable side-look as second-monitor risk. |
| `CAMERA_WARN_SIDE_MIN_YAW_DEG` | Head yaw required before left/right counts. |
| `CAMERA_WARN_DOWN_MIN_PITCH_DEG` | Chin pitch required before look-down counts. |
| `CAMERA_WARN_ON_LOOKING_DOWN` | Toggle look-down warns. |
| `CAMERA_WARN_ON_NO_FACE` | Toggle no-face warns. |
| `CAMERA_WARN_ON_MULTI_FACE` | Toggle multi-face warns. |
| `CAMERA_WARN_ON_LOOKING_AWAY` | Toggle look-away warns. |
| `CAMERA_WARN_IGNORE_AWAY_WHILE_SPEAKING` | Do not warn away/down/side while lips move. |
| `CAMERA_WARN_ONLY_ON_CANDIDATE_TURN` | Warn only while the candidate should be answering. |
| `CAMERA_WARN_MULTI_FACE_MIN_AREA_RATIO` | Ignore tiny second faces. |
| `CAMERA_WARN_ON_MUTED_MIC` | Extra unmute warn from lips (usually false; silence ladder handles mute). |
| `CAMERA_WARN_MUTED_MIC_AFTER_SEC` | If muted-mic warn is on, delay. |
| `CAMERA_WARN_MUTED_MIC_SILENCE_SEC` | Silence treated as muted. |

---

## Must-set for a real interview

| Need | Variables |
| --- | --- |
| Login / DB | `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` |
| Bot joins meeting | `RECALL_API_KEY`, `RECALL_REGION`, `PUBLIC_WEBSOCKET_URL` |
| Bot hears candidate | `WEBSOCKET_PORT` open, `SARVAM_API_KEY` (or Whisper fallback) |
| Bot speaks | `SARVAM_API_KEY` or Edge fallback; if output-media: `PUBLIC_NGROK_URL` HTTPS |
| Questions / scores | `GROQ_API_KEY` + GPT-OSS model names |
| Access emails | `GRAPH_*`, `GRAPH_SENDER`, `ACCESS_NOTIFY_TO` |
| Coding link in wrap-up | `FRONTEND_BASE_URL` |

See also `KNOWLEDGE_TRANSFER.md` §15 for SSH, ngrok vs `20.244.7.67`, and Postgres host rules.
