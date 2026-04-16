# Production Hardening Checklist

## Runtime

- Run at least 2 service instances behind a stable HTTPS ingress.
- Use sticky routing or external state store when handling stateful call callbacks.
- Configure health probes (`/healthz`) and readiness checks before accepting callbacks.

## Reliability

- Set correlation ID on every request (`x-correlation-id`).
- Persist room and callback events to durable storage (SQL/Redis) for restart recovery.
- Alert on callback failures, token failures, and unexpected `terminated` states.

## Security

- Store `Graph:ClientSecret` in Azure Key Vault or equivalent secret manager.
- Restrict callback endpoint with network controls and threat protection.
- Rotate app secrets and validate Graph permission drift regularly.

## Operations

- Track metrics by `roomId`, `callId`, and transition state.
- Run Gate 1-5 validation in staging before each release.
- Maintain runbooks for join timeout, callback timeout, and forced leave.
