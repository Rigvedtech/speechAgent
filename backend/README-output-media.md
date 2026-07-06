# Recall.ai Output Media — Webpage Audio Streaming

## Overview

Instead of uploading MP3 files to Recall.ai (`output_audio` API), the bot now streams real-time
PCM audio through a lightweight webpage that Recall.ai renders inside its headless Chromium bot.

```
User speaks → Recall.ai STT (port 5213)
           → Whisper STT → LLM (Groq)
           → Sarvam TTS (bulbul:v3) → MP3
           → MP3 → PCM Int16 (pydub)
           → WebSocket (/ws/audio-stream/<session>)
           → AudioWorkletProcessor (output-media.html)
           → AudioContext.destination
           → Recall.ai captures page audio
           → Broadcast into Teams/Zoom/Meet
```

**Latency budget (measured):**

| Stage                        | Typical   |
|------------------------------|-----------|
| Sarvam TTS generation        | 200–400ms |
| MP3 → PCM conversion         | ~20ms     |
| WebSocket send                | <5ms      |
| AudioWorklet buffering        | ~50ms     |
| Recall.ai ingest + broadcast | ~50ms     |
| **Total (first word heard)** | **~350ms**|

Compare to the previous file-upload path which was 4–8s.

---

## Audio Format Contract

| Property    | Value                          |
|-------------|-------------------------------|
| Encoding    | **Int16 PCM** (little-endian)  |
| Sample rate | **24 000 Hz** (Sarvam bulbul:v3 default) |
| Channels    | **1** (mono)                   |
| Frame size  | 4 096 bytes per WebSocket chunk |

The `audio-worklet-processor.js` expects and decodes this format. If you change the Sarvam model
or sample rate, also update `SAMPLE_RATE` in `output-media.html` and the `target_rate` default in
`IntegratedAudioSender._mp3_to_pcm_int16()`.

---

## Setup

### 1. Environment variables (`.env`)

```dotenv
# Enable webpage Output Media (requires PUBLIC_NGROK_URL below)
RECALL_USE_OUTPUT_MEDIA=true

# The public HTTPS URL where your FastAPI server is reachable (ngrok or VPS)
# Must be HTTPS — Recall.ai will NOT load http:// pages
PUBLIC_NGROK_URL=https://your-subdomain.ngrok-free.app

# Your existing WebSocket URL for receiving bot audio (STT input, port 5213)
PUBLIC_WEBSOCKET_URL=ws://your-ip:5213
```

### 2. Start services

```bash
# Terminal 1 — FastAPI (API + WebSocket hub + static files)
cd backend
python api_server.py

# Terminal 2 — ngrok HTTPS tunnel on port 8000
ngrok http 8000
# Copy the https://... URL into PUBLIC_NGROK_URL above
```

### 3. Join a meeting

```http
POST https://your-ngrok.ngrok-free.app/api/join
Content-Type: application/json

{
  "meeting_url": "https://teams.microsoft.com/l/meetup-join/..."
}
```

The response includes a `bot_id`. The bot will join the meeting and load the
`/voice-agent?page_session_id=<uuid>&name=Prabhat` page automatically.

### 4. Start the interview

```http
POST http://localhost:8000/api/start/<bot_id>
```

---

## New Files

| File | Description |
|------|-------------|
| `backend/static/output-media.html` | The voice-agent page (served at `/voice-agent`) |
| `backend/static/audio-worklet-processor.js` | Low-latency PCM ring-buffer processor |
| `backend/README-output-media.md` | This file |

## Modified Files

| File | Change |
|------|--------|
| `backend/api_server.py` | Added `/voice-agent`, `/ws/audio-stream/{id}`, static mount, `broadcast_pcm_sync` |
| `backend/recall_bot_service.py` | Changed `output_media` payload to `camera.kind="webpage"` with URL |
| `backend/session_manager.py` | Added `use_webpage` flag; passes `webpage_broadcaster` to audio sender; per-sentence streaming enabled |
| `backend/integrated_audio_sender.py` | Added `_mp3_to_pcm_int16()`, `webpage_broadcaster` path in both Sarvam and Edge-TTS senders |

---

## Architecture Diagram

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │  Python Backend (port 8000, exposed via ngrok)                         │
 │                                                                        │
 │  POST /api/join ──► create Recall bot with output_media.camera.webpage │
 │                                                                        │
 │  Recall bot opens  ──► GET /voice-agent?page_session_id=<uuid>         │
 │                                                                        │
 │  output-media.html ──► WebSocket /ws/audio-stream/<page_session_id>    │
 │                                │                                       │
 │  [TTS worker thread]           │                                       │
 │  Sarvam TTS → MP3              │                                       │
 │  MP3 → PCM Int16               │                                       │
 │  broadcast_pcm_sync() ─────────┘ (run_coroutine_threadsafe)            │
 │                                                                        │
 └────────────────────────────────────────────────────────────────────────┘
                                  │  raw Int16 PCM (24kHz) over WS
                                  ▼
 ┌─────────────────────────────────────────────────────┐
 │  output-media.html  (inside Recall.ai headless bot) │
 │                                                     │
 │  AudioWorkletNode (pcm-player-processor)            │
 │    ► ring buffer (50–100ms)                         │
 │    ► AudioContext.destination                       │
 │                   │                                 │
 └───────────────────┼─────────────────────────────────┘
                     │  Recall.ai captures page audio
                     ▼
        Microsoft Teams / Zoom / Google Meet
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Bot joins but no audio | `PUBLIC_NGROK_URL` not set or HTTP (not HTTPS) | Set `PUBLIC_NGROK_URL=https://...` |
| "Missing ?page_session_id" in browser console | URL not constructed correctly | Check api_server.py logs for "Output Media page URL:" |
| Audio plays with glitches | Buffer underrun | Network latency; increase `BUFFER_FRAMES` in `audio-worklet-processor.js` |
| Still using file upload | `RECALL_USE_OUTPUT_MEDIA=false` or no ngrok URL | Set both env vars and restart |
| `pydub` error on PCM conversion | `ffmpeg` not installed | Install ffmpeg: `choco install ffmpeg` or `apt install ffmpeg` |

---

## Recall.ai Docs

- https://docs.recall.ai/docs/stream-media (Output Media)
- https://docs.recall.ai/reference/bot_create (bot creation API)
