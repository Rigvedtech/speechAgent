-- Apply all schema files in dependency order (PostgreSQL psql).
-- Usage:
--   psql -U postgres -d speechagent -f database/init.sql

\echo 'Applying speechAgent database schema...'

\ir 000_extensions.sql
\ir 001_organization.sql
\ir 002_users.sql
\ir 003_candidates.sql
\ir 004_documents.sql
\ir 005_document_extractions.sql
\ir 006_question_banks.sql
\ir 007_question_bank_items.sql
\ir 008_interview_sessions.sql
\ir 009_interview_configs.sql
\ir 010_interview_questions.sql
\ir 011_interview_answers.sql
\ir 012_transcript_turns.sql
\ir 013_interview_reports.sql
\ir 014_session_events.sql

\echo 'Schema applied successfully.'
