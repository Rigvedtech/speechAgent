# Teams Voice Streaming (Application-hosted media) - Production Notes

This repository currently supports:
- Graph call control + callbacks (join/leave/playPrompt)
- Phase-2 manual turn endpoint (`/api/rooms/{roomId}/turn`)

For **real-time voice streaming** (receive participant audio + send audio back), Microsoft requires an **application-hosted media bot**.

## Key references
- Microsoft Teams requirements for application-hosted media bots: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/calls-and-meetings/requirements-considerations-application-hosted-media-bots
- Graph comms sample docs (app-hosted media calls): https://microsoftgraph.github.io/microsoft-graph-comms-samples/docs/articles/calls/appHostedMediaCalls.html
- Graph Communications Calling SDK docs: https://microsoftgraph.github.io/microsoft-graph-comms-samples/docs/calls/index.html

## Production constraints (important)
- **Stateful**: one instance owns a call end-to-end (notifications + media). You cannot load-balance a single call across instances.
- **Instance-level network**: requires public reachability to the bot instance (often ILPIP or equivalent). Web-app style hosting is typically not supported for media bots.
- **Failure semantics**: if the instance dies, **active calls drop**.
- **Ports**: media sockets require public-facing ports and correct firewall rules.

## Configuration
In `MeetingBot` configuration:
- `AutoLeaveSeconds`: **0** means the bot stays in the call until you call leave or Graph ends the call. Any **positive** value schedules automatic hang-up that many seconds after the call is established.
- `UseApplicationHostedMedia`: when **true** and **`MediaPlatform`** is fully configured, the bot joins via the **Graph Communications Calling SDK** (application-hosted media), receives mixed meeting **audio on the media socket**, streams it to **`SttWebSocketUrl`**, and runs the same turn path as `/api/rooms/{roomId}/turn`. Graph callbacks are handled only through the SDK (`/api/calls/callback` must still be the public notification URL). When false or media config is incomplete, join uses HTTP Graph **`/communications/calls`** (service-hosted) plus optional local loopback STT (`EnableSttVoiceLoop`).
- `SttWebSocketUrl`: websocket endpoint for STT streaming (default `ws://127.0.0.1:8020/stt`).

### AI bridge TTS (Prabhat / Edge)
`ai_bridge_server.py` uses the same **`TTS_VOICE`** / **`TTS_RATE`** environment variables as standalone mode (default voice `en-IN-PrabhatNeural`). Install **ffmpeg** and ensure it is on `PATH` so replies are converted to **16 kHz mono WAV** for reliable Graph `playPrompt`. Without ffmpeg, the bridge may serve **MP3** URLs instead.

### Step A (dev): hear meeting → STT → auto `playPrompt`
This is **not** Graph RTP media yet. On **Windows**, when `MeetingBot:EnableSttVoiceLoop` is **true** and `python stt_server.py` is running (`SttWebSocketUrl`, default `ws://127.0.0.1:8020/stt`), the bot **captures local PC audio** after the greeting:
- **`SttLocalAudioSource: Loopback`** — default **render** device (what you hear from the Teams **desktop** client on the **same machine** as `dotnet run`). Join the meeting with speakers/headset so meeting audio is audible locally.
- **`Mic`** — physical microphone (use if you prefer talking into the mic while testing).

The bot streams **16 kHz mono PCM** to the STT websocket; on each **final** transcript it calls the same path as **`POST /api/rooms/{roomId}/turn`** (LLM + TTS + `playPrompt`). **`SttSuppressionAfterPlaySeconds`** reduces picking up the bot’s own prompt from speakers.

**Production** in-meeting capture still requires **application-hosted Graph media** (see links above). Set **`EnableSttVoiceLoop`** to **false** in production unless you intentionally run this local capture pattern.

## App-hosted media (in-meeting STT from any Teams client)
1. Provision a TLS certificate in **LocalMachine\\My** whose subject/SAN matches **`MediaPlatform:ServiceFqdn`** (see Microsoft app-hosted media bot requirements).
2. Open **MediaPlatform:InstancePublicPort** (UDP/TCP per Microsoft docs) to the internet; set **`MediaPlatform:InstancePublicIPAddress`** to the instance’s public IPv4 and **`InstanceInternalPort`** to the local bind port.
3. Set **`MeetingBot:CallbackBaseUrl`** to your public HTTPS base (e.g. ngrok) ending with `/`; notifications use `{CallbackBaseUrl}api/calls/callback`.
4. Set **`MeetingBot:UseApplicationHostedMedia`**=**true**, **`MeetingBot:EnableSttVoiceLoop`**=**false** (loopback is not used in this mode), and run **`python stt_server.py`** on the bot host.
5. Deploy on a topology where **one process** owns signaling + media for the call (see “Production constraints” above). Plain HTTP-only tunnels do **not** replace public media ports.

### Remaining hardening (optional)
- Certificate rotation, health probes on media ports, and multi-instance routing are not implemented here; follow [HueBot / PolicyRecordingBot](https://github.com/microsoftgraph/microsoft-graph-comms-samples) for production patterns.
# Meeting Bot (.NET)

This service implements the Teams meeting orchestration plan with these stages:

- Baseline verification (`/api/baseline/verify`)
- No-AI flow (`/api/meetings/start`, `/api/calls/callback`, `/api/meetings/leave`)
- Validation gates script (`scripts/validate-gates.ps1`)
- AI bridge contract (`AiBridge` settings + callback hook)
- Production hardening basics (correlation IDs, health checks, structured room state)

## Run

1. Set `Graph` and `MeetingBot` values in `appsettings.Development.json` or environment variables.
2. Start service:
   - `dotnet run`
3. Verify baseline:
   - `GET /api/baseline/verify`

## Endpoints

- `POST /api/meetings/create` body: `{ "organizerUserIdOrUpn": "user@tenant.com", "subject": "Bot test", "startDateTimeUtc": "2026-04-16T13:00:00Z", "endDateTimeUtc": "2026-04-16T13:30:00Z" }`
- `POST /api/meetings/start` body: `{ "roomId": "...", "meetingJoinUrl": "..." }`
- `POST /api/calls/callback` receives Graph call notifications
- `POST /api/meetings/leave` body: `{ "roomId": "...", "reason": "..." }`
- `GET /api/rooms` session timeline per room

## Notes

- Real-time two-way media still requires Microsoft application-hosted media bot runtime for full in-meeting audio.
- This service is the orchestration/control plane and keeps all state transitions with timestamps.
