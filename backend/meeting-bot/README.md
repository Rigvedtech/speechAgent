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
