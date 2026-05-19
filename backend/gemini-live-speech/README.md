# Gemini Live speech-to-speech (local demo)

This folder is a **standalone** experiment using the **Gemini Live API** (bidirectional WebSocket) with the official **`google-genai`** Python SDK: **microphone → model → speaker** for native-audio models, plus a small **text smoke test**.

## Prerequisites

- Python 3.11+ (same venv as `backend/` is fine)
- A **Google AI Studio / Gemini API key** with access to **Live** models on your account
- Working default **microphone** and **speakers** (WASAPI on Windows)

## Setup

From the repository `backend/` folder (or any environment where you install deps):

```powershell
cd "c:\All Projects\speechAgent\backend"
.\venv\Scripts\python.exe -m pip install -r gemini-live-speech\requirements.txt
```

Copy `gemini-live-speech\.env.example` to `gemini-live-speech\.env` **or** reuse keys in `backend\.env`:

- `GOOGLE_API_KEY` (or `GEMINI_API_KEY`)

## Which Google models are for speech → conversation?

Names change over time; always confirm in the official lists:

- **Gemini API (API key / AI Studio):** [Live API](https://ai.google.dev/gemini-api/docs/live), [Models](https://ai.google.dev/gemini-api/docs/models)
- **Vertex AI (GCP / service account):** [Gemini 2.5 Flash + Live](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash-live-api)

Useful families:

| Goal | Typical model family (verify current IDs in docs) |
|------|-----------------------------------------------------|
| **Native audio (speech in → speech out, low latency)** | e.g. `gemini-2.5-flash-native-audio-preview-...` on AI Studio; `gemini-live-2.5-flash-native-audio` on Vertex |
| **Live preview (often used for TEXT / tooling demos)** | e.g. `gemini-live-2.5-flash-preview` (SDK examples) |

Defaults in `.env.example`:

- `GEMINI_LIVE_MODEL` — native audio for `run_live_s2s_mic.py`
- `GEMINI_LIVE_SMOKE_MODEL` — text smoke (`run_text_smoke.py`)

## Run

```powershell
cd "c:\All Projects\speechAgent\backend\gemini-live-speech"

# Optional: pick devices
..\venv\Scripts\python.exe .\run_live_s2s_mic.py --list-devices

# 1) Verify key + Live routing (TEXT)
..\venv\Scripts\python.exe .\run_text_smoke.py

# 2) Speech-to-speech (AUDIO) — requires a native-audio Live model
..\venv\Scripts\python.exe .\run_live_s2s_mic.py
```

**English-only note:** `speech_config.language_code` plus a system instruction **reduces** off-language replies but does **not** guarantee it under noisy conditions (see project discussion). For stricter control, combine with **English-locked ASR** in a staged pipeline.

## Files

| File | Role |
|------|------|
| `settings.py` | Loads `.env` / `backend/.env` |
| `audio_pcm.py` | Mic float32 → PCM16 LE for 16 kHz input |
| `run_live_s2s_mic.py` | Live session + mic capture + PCM playback (24 kHz int16 out) |
| `run_text_smoke.py` | Minimal Live TEXT session |
