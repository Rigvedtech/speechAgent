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
\ir 019_recruitment_core_columns.sql
\ir 020_domain_taxonomy.sql
\ir 021_job_candidate_links.sql
\ir 022_job_candidate_matches.sql
\ir 023_upload_batches.sql
\ir 024_qdrant_document_points.sql
\ir 025_coding_round.sql
\ir 028_coding_entry_function.sql
\ir 026_coding_tasks_seed.sql
\ir 027_coding_candidate_access.sql
\ir 029_coding_domains.sql
\ir 030_coding_languages_expand.sql
\ir 031_coding_multi_task_times.sql
\ir 032_coding_proctoring.sql
\ir 033_coding_shared_bank.sql

\echo 'Schema applied successfully.'
