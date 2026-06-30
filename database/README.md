# speechAgent Database Schema

PostgreSQL schema for the AI voice interview platform. One SQL file per table, applied in numeric order.

## Requirements

- PostgreSQL 14+
- Extension: `pgcrypto` (for `gen_random_uuid()`)

## Apply schema

```bash
createdb speechagent
psql -U postgres -d speechagent -f database/init.sql
```

Or run files individually in order (`000` → `014`).

## Table map

| File | Table | Purpose |
|------|--------|---------|
| `001_organization.sql` | `organization` | Tenant / hiring company |
| `002_users.sql` | `users` | Recruiters & admins |
| `003_candidates.sql` | `candidates` | People interviewed |
| `004_documents.sql` | `documents` | JD / CV uploads |
| `005_document_extractions.sql` | `document_extractions` | n8n extraction runs |
| `006_question_banks.sql` | `question_banks` | Reusable question catalogs |
| `007_question_bank_items.sql` | `question_bank_items` | Questions in a bank |
| `008_interview_sessions.sql` | `interview_sessions` | One Recall bot interview |
| `009_interview_configs.sql` | `interview_configs` | Frozen JD/CV + settings |
| `010_interview_questions.sql` | `interview_questions` | 10 planned Qs + status |
| `011_interview_answers.sql` | `interview_answers` | Scored Q&A pairs |
| `012_transcript_turns.sql` | `transcript_turns` | Full raw transcription |
| `013_interview_reports.sql` | `interview_reports` | Final report card |
| `014_session_events.sql` | `session_events` | Audit / lifecycle events |

## Data flow

```
organization → users, candidates, question_banks
                    ↓
            interview_sessions (+ bot_id from Recall)
                    ├── interview_configs (JD/CV snapshot)
                    ├── interview_questions (completed / remaining)
                    ├── transcript_turns (raw full conversation)
                    ├── interview_answers (scored only)
                    ├── interview_reports (summary)
                    └── session_events (audit)
```

## Notes

- **`bot_id`** on `interview_sessions` matches the existing API (`POST /api/join` response).
- **`interview_questions.status`**: `pending` → `in_progress` → `completed`; slots never reached become `remaining`.
- **`transcript_turns`** stores the full conversation; **`interview_answers`** stores evaluated main Q&A only.
- **`report_json`** on `interview_reports` supports migration from current `backend/reports/*.json` files.
