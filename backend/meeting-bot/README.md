# meeting-bot (ACS architecture)

Teams interview bot using **Azure Communication Services Call Automation**:

- **Graph** — optional `POST /api/meetings/create` (`joinWebUrl`)
- **ACS** — `POST /api/meetings/start` joins via `teamsMeetingLink`, streams mixed audio to STT WebSocket, plays TTS via `PlayToAll`

See [docs/acs-architecture.md](docs/acs-architecture.md) and [docs/teams-meeting-join-plan.md](docs/teams-meeting-join-plan.md).

## API

| Endpoint | Purpose |
|----------|---------|
| `GET /api/baseline/verify` | Config checklist |
| `POST /api/meetings/create` | Graph `joinWebUrl` |
| `POST /api/meetings/start` | ACS join + media streaming |
| `POST /api/acs/events` | ACS Call Automation callbacks |
| `WS /ws/acs-media` | ACS → bot PCM (16 kHz mono) |
| `POST /api/meetings/leave` | Hang up |
| `POST /api/rooms/{id}/turn` | Manual transcript turn |

## Run

```bash
cd backend/meeting-bot
dotnet run
```

Set `Acs__ConnectionString` and `MeetingBot__CallbackBaseUrl` (HTTPS tunnel to port 5213).

## Test flow

1. `POST /api/meetings/create` → `joinWebUrl`
2. Open meeting in Teams
3. `POST /api/meetings/start` with `{ "roomId", "meetingJoinUrl" }`
4. Watch `GET /api/rooms` for `acs-call-connected`, `stt-final-received`
