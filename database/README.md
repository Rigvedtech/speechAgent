# speechAgent Database Schema

PostgreSQL schema for the AI voice interview platform. Apply files via `init.sql` in numeric order.

## Requirements

- PostgreSQL 14+
- Extensions: `pgcrypto` (UUIDs), `pg_trgm` (job title search)

## Fresh apply

```bash
psql -U postgres -d speechagent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -U postgres -d speechagent -f database/init.sql
```

## Table map

| File | Object | Purpose |
|------|--------|---------|
| `001_organization.sql` | `organization` | Tenant / hiring company |
| `002_users.sql` | `users` | Recruiters & admins |
| `003_candidates.sql` | `candidates` | People interviewed |
| `004_documents.sql` | `documents` | Uploaded JD/CV files |
| `005_document_extractions.sql` | `document_extractions` | One generate/extract run (JD+CV → questions) |
| `006_job_postings.sql` | `job_postings` | Job title / role |
| `009_interview_sessions.sql` | `interview_sessions` | One bot interview |
| `010_interview_configs.sql` | `interview_configs` | Frozen JD/CV + thresholds for that run |
| `011_interview_questions.sql` | `interview_questions` | This interview’s question plan + status |
| `012_interview_answers.sql` | `interview_answers` | Scored answers |
| `013_transcript_turns.sql` | `transcript_turns` | Full spoken log |
| `014_interview_reports.sql` | `interview_reports` | Final report + stage-1 / qualified |
| `015_session_events.sql` | `session_events` | Ops timeline |
| `016_views.sql` | views | Dashboard read models |
| `017_candidate_feedback.sql` | `candidate_feedback` | Post-interview feedback |

## Relationships

```
organization
  └── users (recruiter)
        ├── job_postings
        ├── candidates
        └── interview_sessions
              ├── interview_configs
              ├── interview_questions → interview_answers
              ├── transcript_turns
              ├── interview_reports
              └── candidate_feedback
```

## What to query (source of truth)

| Need | Use |
|------|-----|
| Session / bot / meeting | `interview_sessions` (`interview_id` stays stable on rejoin; update `bot_id`) |
| JD/CV used in the interview | `interview_configs` |
| Latest candidate CV text | `candidates.cv_text` |
| Uploaded files | `documents` |
| Generated Q list before join | `document_extractions.questions_json` |
| Asked / remaining questions | `interview_questions` |
| Scores | `interview_answers` |
| Pass/fail & why stopped | `interview_reports` (`qualified` uses **stage1_average**) |
| Exact dialogue | `transcript_turns` |

## Notes

- Questions are generated **per interview** from JD + CV (no reusable question-bank tables).
- Filter by recruiter with `created_by = :user_id` on candidates, jobs, and sessions.
- `v_interview_overview` / `v_job_posting_stats` are for lists and role stats.
