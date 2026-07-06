# speechAgent Database Schema

PostgreSQL schema for the AI voice interview platform. One SQL file per table, applied in numeric order.

## Requirements

- PostgreSQL 14+
- Extensions: `pgcrypto` (UUIDs), `pg_trgm` (job title search)

## Fresh apply (pgAdmin or psql)

Drop and recreate if you already ran an older schema:

```bash
psql -U postgres -d speechagent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -U postgres -d speechagent -f database/init.sql
```

Or run files individually in order (`000` → `016`).

## Table map

| File | Table / view | Purpose |
|------|----------------|---------|
| `001_organization.sql` | `organization` | Tenant / hiring company |
| `002_users.sql` | `users` | Recruiters & admins (login) |
| `003_candidates.sql` | `candidates` | People interviewed (`created_by` = recruiter) |
| `004_documents.sql` | `documents` | JD / CV uploads |
| `005_document_extractions.sql` | `document_extractions` | n8n extraction runs |
| `006_job_postings.sql` | `job_postings` | **Job title / role** (recruiter-owned) |
| `007_question_banks.sql` | `question_banks` | Reusable question catalogs |
| `008_question_bank_items.sql` | `question_bank_items` | Questions in a bank |
| `009_interview_sessions.sql` | `interview_sessions` | One Recall bot interview |
| `010_interview_configs.sql` | `interview_configs` | Frozen JD/CV + job/recruiter/candidate snapshot |
| `011_interview_questions.sql` | `interview_questions` | Planned Qs + status |
| `012_interview_answers.sql` | `interview_answers` | Scored Q&A pairs |
| `013_transcript_turns.sql` | `transcript_turns` | Full raw transcription |
| `014_interview_reports.sql` | `interview_reports` | Final report + `qualified` flag |
| `015_session_events.sql` | `session_events` | Audit / lifecycle events |
| `016_views.sql` | `v_interview_overview`, `v_job_posting_stats` | Lists, search, dashboards |
| `017_candidate_feedback.sql` | `candidate_feedback` | Post-interview candidate feedback (one per `bot_id`) |

## Core relationships

```
organization
  └── users (recruiter)
        ├── job_postings (job_title)
        ├── candidates (full_name, cv)
        └── interview_sessions
              ├── job_posting_id  → job title
              ├── candidate_id    → candidate name
              └── created_by      → recruiter name
```

## Registration fields

**Organization:** `name`, `slug` (e.g. `acme-hiring`)

**User (recruiter):** `full_name`, `email`, `password_hash`, `organization_id`, `role` (`admin` | `recruiter` | `viewer`)

## Search & reporting

- **Job title search:** `WHERE job_title ILIKE '%analyst%'` on `job_postings` or `v_interview_overview`
- **Session detail:** `SELECT * FROM v_interview_overview WHERE interview_id = :id`
- **Stats per role:** `SELECT * FROM v_job_posting_stats WHERE recruiter_id = :user_id`
- **Qualified:** `interview_reports.qualified` (= `overall_average >= continue_threshold`)

## Notes

- **`bot_id`** on `interview_sessions` matches the existing API (`POST /api/join` response).
- **Recruiter isolation:** filter `created_by = :user_id` on `candidates`, `job_postings`, `interview_sessions`.
- **Snapshots:** `interview_configs` and `interview_reports` store `job_title`, `recruiter_name`, `candidate_name` at interview time.
- **`report_json`** supports migration from current `backend/reports/*.json` files.
