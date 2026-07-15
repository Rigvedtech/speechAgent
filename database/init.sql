-- Apply all schema files in dependency order (PostgreSQL psql).
-- Usage:
--   psql -U postgres -d speechagent -f database/init.sql
--
-- Fresh install (drops existing public schema objects first):
--   psql -U postgres -d speechagent -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
--   psql -U postgres -d speechagent -f database/init.sql

\echo 'Applying speechAgent database schema...'

\ir 000_extensions.sql
\ir 001_organization.sql
\ir 002_users.sql
\ir 003_candidates.sql
\ir 004_documents.sql
\ir 005_document_extractions.sql
\ir 006_job_postings.sql
\ir 009_interview_sessions.sql
\ir 010_interview_configs.sql
\ir 011_interview_questions.sql
\ir 012_interview_answers.sql
\ir 013_transcript_turns.sql
\ir 014_interview_reports.sql
\ir 015_session_events.sql
\ir 016_views.sql
\ir 017_candidate_feedback.sql
\ir 018_organization_ats_api_key.sql

\echo 'Schema applied successfully.'
