--
-- PostgreSQL database dump
--

\restrict aisBTfNiF34Qb1QNr8EQ9Aotfje5ir26xYCizuFa8U1G20gsngef41iP8YqtI0Q

-- Dumped from database version 15.16
-- Dumped by pg_dump version 15.16

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: candidate_feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candidate_feedback (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    bot_id uuid NOT NULL,
    overall_rating smallint NOT NULL,
    clarity_rating smallint NOT NULL,
    tech_issues character varying(10) DEFAULT 'none'::character varying NOT NULL,
    improve_text character varying(500) NOT NULL,
    would_repeat character varying(10),
    candidate_name character varying(255),
    submitted_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT candidate_feedback_clarity_range CHECK (((clarity_rating >= 1) AND (clarity_rating <= 5))),
    CONSTRAINT candidate_feedback_improve_nonempty CHECK ((length(TRIM(BOTH FROM improve_text)) >= 1)),
    CONSTRAINT candidate_feedback_overall_range CHECK (((overall_rating >= 1) AND (overall_rating <= 5))),
    CONSTRAINT candidate_feedback_repeat_valid CHECK (((would_repeat IS NULL) OR ((would_repeat)::text = ANY ((ARRAY['yes'::character varying, 'maybe'::character varying, 'no'::character varying])::text[])))),
    CONSTRAINT candidate_feedback_tech_valid CHECK (((tech_issues)::text = ANY ((ARRAY['none'::character varying, 'minor'::character varying, 'major'::character varying])::text[])))
);


--
-- Name: TABLE candidate_feedback; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.candidate_feedback IS 'One candidate feedback form per interview; keyed by bot_id for public links.';


--
-- Name: candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.candidates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    created_by uuid NOT NULL,
    full_name character varying(255) NOT NULL,
    email character varying(320),
    phone character varying(50),
    cv_text text,
    notes text,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    external_ats_id character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    current_title character varying(255),
    location character varying(255),
    linkedin_url text,
    structured_json jsonb,
    domain_tags text[] DEFAULT '{}'::text[] NOT NULL,
    content_hash text,
    primary_cv_document_id uuid,
    CONSTRAINT candidates_email_lower CHECK (((email IS NULL) OR ((email)::text = lower((email)::text)))),
    CONSTRAINT candidates_source_valid CHECK (((source)::text = ANY ((ARRAY['manual'::character varying, 'upload'::character varying, 'ats'::character varying, 'bulk_upload'::character varying])::text[])))
);


--
-- Name: TABLE candidates; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.candidates IS 'Interview candidates scoped to recruiter (created_by) and organization.';


--
-- Name: COLUMN candidates.cv_text; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.candidates.cv_text IS 'Latest profile CV text; each interview freezes its own copy in interview_configs.cv_text.';


--
-- Name: COLUMN candidates.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.candidates.source IS 'How this candidate entered the system: manual, upload, or ats.';


--
-- Name: COLUMN candidates.external_ats_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.candidates.external_ats_id IS 'Candidate id in the org ATS; used for dedupe/re-import. NULL if not from ATS.';


--
-- Name: document_extractions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_extractions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    requested_by uuid,
    candidate_id uuid,
    job_posting_id uuid,
    jd_document_id uuid,
    cv_document_id uuid,
    external_request_id character varying(255),
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    jd_text text,
    cv_text text,
    questions_json jsonb,
    raw_response jsonb,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT document_extractions_status_valid CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'success'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: TABLE document_extractions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.document_extractions IS 'Per-run JD/CV text + generated questions; copied into interview_questions at join.';


--
-- Name: COLUMN document_extractions.candidate_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.document_extractions.candidate_id IS 'Candidate whose CV drove this generation (NULL only if not yet linked).';


--
-- Name: COLUMN document_extractions.job_posting_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.document_extractions.job_posting_id IS 'Optional job this run belongs to (FK added in 006_job_postings.sql).';


--
-- Name: COLUMN document_extractions.questions_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.document_extractions.questions_json IS 'Generated question list for this JD+CV run.';


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    uploaded_by uuid,
    candidate_id uuid,
    document_type character varying(10) NOT NULL,
    source character varying(20) DEFAULT 'upload'::character varying NOT NULL,
    external_ats_id character varying(255),
    original_filename character varying(512),
    storage_path text,
    mime_type character varying(127),
    file_size_bytes bigint,
    extracted_text text,
    upload_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    job_posting_id uuid,
    content_hash text,
    structured_json jsonb,
    error_message text,
    CONSTRAINT documents_source_valid CHECK (((source)::text = ANY ((ARRAY['upload'::character varying, 'manual'::character varying, 'ats'::character varying, 'bulk_upload'::character varying])::text[]))),
    CONSTRAINT documents_status_valid CHECK (((upload_status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'ready'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT documents_type_valid CHECK (((document_type)::text = ANY ((ARRAY['jd'::character varying, 'cv'::character varying])::text[])))
);


--
-- Name: TABLE documents; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.documents IS 'JD/CV files from upload or ATS; typed text can skip this table and go into extractions/configs.';


--
-- Name: COLUMN documents.candidate_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.documents.candidate_id IS 'CV â†’ candidate link; leave NULL for JD files.';


--
-- Name: COLUMN documents.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.documents.source IS 'Origin of this file: upload, manual (rare file save), or ats.';


--
-- Name: COLUMN documents.external_ats_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.documents.external_ats_id IS 'Document id in the org ATS; NULL if not imported from ATS.';


--
-- Name: domain_taxonomy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.domain_taxonomy (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid,
    slug character varying(64) NOT NULL,
    display_name character varying(128) NOT NULL,
    parent_slug character varying(64),
    aliases text[] DEFAULT '{}'::text[] NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT domain_taxonomy_slug_format CHECK (((slug)::text ~ '^[a-z0-9]+(?:_[a-z0-9]+)*$'::text))
);


--
-- Name: TABLE domain_taxonomy; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.domain_taxonomy IS 'Role/domain family graph for matching related JDs and CVs.';


--
-- Name: COLUMN domain_taxonomy.organization_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.domain_taxonomy.organization_id IS 'NULL = global default taxonomy; set for org-specific tags.';


--
-- Name: COLUMN domain_taxonomy.parent_slug; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.domain_taxonomy.parent_slug IS 'Optional parent domain slug (e.g. frontend parent = web).';


--
-- Name: COLUMN domain_taxonomy.aliases; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.domain_taxonomy.aliases IS 'Alternate labels that map to this slug (e.g. react_dev â†’ frontend).';


--
-- Name: interview_answers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_answers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    interview_question_id uuid,
    question_index smallint NOT NULL,
    external_question_id character varying(64) NOT NULL,
    difficulty character varying(20) NOT NULL,
    source character varying(20) NOT NULL,
    question_text text NOT NULL,
    answer_text text NOT NULL,
    score smallint NOT NULL,
    confident boolean DEFAULT false NOT NULL,
    relevant boolean DEFAULT true NOT NULL,
    strengths text DEFAULT ''::text NOT NULL,
    develop text DEFAULT ''::text NOT NULL,
    fix text DEFAULT ''::text NOT NULL,
    abuse_flag boolean DEFAULT false NOT NULL,
    evaluated_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT interview_answers_difficulty_valid CHECK (((difficulty)::text = ANY ((ARRAY['Low'::character varying, 'Intermediate'::character varying, 'Hard'::character varying])::text[]))),
    CONSTRAINT interview_answers_score_range CHECK (((score >= 0) AND (score <= 10))),
    CONSTRAINT interview_answers_source_valid CHECK (((source)::text = ANY ((ARRAY['jd'::character varying, 'resume'::character varying, 'other'::character varying])::text[])))
);


--
-- Name: TABLE interview_answers; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.interview_answers IS 'Evaluator result per main question; difficulty/source stored for reporting without joins.';


--
-- Name: interview_configs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_configs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    job_posting_id uuid,
    document_extraction_id uuid,
    job_title character varying(255) NOT NULL,
    recruiter_name character varying(255) NOT NULL,
    candidate_name character varying(255) NOT NULL,
    jd_text text NOT NULL,
    cv_text text NOT NULL,
    continue_threshold numeric(4,2) DEFAULT 5.50 NOT NULL,
    rolling_window smallint DEFAULT 6 NOT NULL,
    questions_planned_count smallint DEFAULT 10 NOT NULL,
    settings_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT interview_configs_cv_min_len CHECK ((length(TRIM(BOTH FROM cv_text)) >= 50)),
    CONSTRAINT interview_configs_jd_min_len CHECK ((length(TRIM(BOTH FROM jd_text)) >= 100)),
    CONSTRAINT interview_configs_job_title_nonempty CHECK ((length(TRIM(BOTH FROM job_title)) >= 2)),
    CONSTRAINT interview_configs_planned_range CHECK (((questions_planned_count >= 1) AND (questions_planned_count <= 20)))
);


--
-- Name: TABLE interview_configs; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.interview_configs IS 'Immutable snapshot: job title, recruiter, candidate, JD/CV, thresholds at join time.';


--
-- Name: COLUMN interview_configs.document_extraction_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_configs.document_extraction_id IS 'n8n run that produced JD/CV text and generated questions for this interview.';


--
-- Name: COLUMN interview_configs.settings_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_configs.settings_json IS 'TTS/STT language, speaker, greeting, thresholds at join time.';


--
-- Name: interview_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    slot smallint NOT NULL,
    external_question_id character varying(64) NOT NULL,
    difficulty character varying(20) NOT NULL,
    source character varying(20) NOT NULL,
    question_text text NOT NULL,
    spoken_question text,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    asked_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT interview_questions_difficulty_valid CHECK (((difficulty)::text = ANY ((ARRAY['Low'::character varying, 'Intermediate'::character varying, 'Hard'::character varying])::text[]))),
    CONSTRAINT interview_questions_slot_range CHECK (((slot >= 1) AND (slot <= 20))),
    CONSTRAINT interview_questions_source_valid CHECK (((source)::text = ANY ((ARRAY['jd'::character varying, 'resume'::character varying, 'other'::character varying])::text[]))),
    CONSTRAINT interview_questions_status_valid CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'in_progress'::character varying, 'completed'::character varying, 'remaining'::character varying])::text[]))),
    CONSTRAINT interview_questions_text_nonempty CHECK ((length(TRIM(BOTH FROM question_text)) >= 10))
);


--
-- Name: TABLE interview_questions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.interview_questions IS 'Per-interview question plan from JD+CV generation; status tracks completed vs remaining.';


--
-- Name: COLUMN interview_questions.external_question_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_questions.external_question_id IS 'Id from n8n/frontend for this interview (e.g. "11"), unique per session.';


--
-- Name: COLUMN interview_questions.spoken_question; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_questions.spoken_question IS 'Localized/spoken wording (e.g. Hinglish); falls back to question_text when null.';


--
-- Name: COLUMN interview_questions.status; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_questions.status IS 'pending â†’ in_progress â†’ completed; remaining if interview ends before this slot.';


--
-- Name: interview_reports; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_reports (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    job_title character varying(255) NOT NULL,
    recruiter_name character varying(255) NOT NULL,
    candidate_name character varying(255) NOT NULL,
    questions_planned smallint NOT NULL,
    questions_scored smallint NOT NULL,
    overall_average numeric(4,2),
    last_n_average numeric(4,2),
    stage1_average numeric(4,2),
    stage1_question_count smallint,
    rolling_window smallint DEFAULT 6 NOT NULL,
    continue_threshold numeric(4,2) DEFAULT 5.50 NOT NULL,
    qualified boolean DEFAULT false NOT NULL,
    abuse_warnings smallint DEFAULT 0 NOT NULL,
    stopped_reason character varying(40) NOT NULL,
    summary_develop jsonb DEFAULT '[]'::jsonb NOT NULL,
    summary_fix jsonb DEFAULT '[]'::jsonb NOT NULL,
    report_json jsonb,
    completed_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT interview_reports_stopped_reason_valid CHECK (((stopped_reason)::text = ANY ((ARRAY['none'::character varying, 'completed_all_questions'::character varying, 'low_recent_average'::character varying, 'abuse'::character varying, 'manual'::character varying])::text[])))
);


--
-- Name: TABLE interview_reports; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.interview_reports IS 'Final report card for lists and hiring decisions; prefer this over session for stopped_reason after wrap-up.';


--
-- Name: COLUMN interview_reports.stage1_average; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_reports.stage1_average IS 'Average of the first stage-1 questions used by the continue/wrap gate.';


--
-- Name: COLUMN interview_reports.stage1_question_count; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_reports.stage1_question_count IS 'How many scores were included in stage1_average (e.g. STAGE1_QUESTION_COUNT).';


--
-- Name: COLUMN interview_reports.qualified; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_reports.qualified IS 'TRUE when stage1_average >= continue_threshold (product gate), not overall_average.';


--
-- Name: COLUMN interview_reports.report_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_reports.report_json IS 'Optional full JSON blob for migration/debug; relational columns are the analytics source.';


--
-- Name: interview_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interview_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    bot_id uuid,
    organization_id uuid NOT NULL,
    created_by uuid NOT NULL,
    candidate_id uuid NOT NULL,
    job_posting_id uuid NOT NULL,
    meeting_url text NOT NULL,
    meeting_url_normalized text NOT NULL,
    bot_name character varying(100) DEFAULT 'Prabhat'::character varying NOT NULL,
    language_mode character varying(20) DEFAULT 'english'::character varying NOT NULL,
    interview_started boolean DEFAULT false NOT NULL,
    interview_ended boolean DEFAULT false NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    stopped_reason character varying(40) DEFAULT 'none'::character varying NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT interview_sessions_language_valid CHECK (((language_mode)::text = ANY ((ARRAY['english'::character varying, 'hinglish'::character varying])::text[]))),
    CONSTRAINT interview_sessions_stopped_reason_valid CHECK (((stopped_reason)::text = ANY ((ARRAY['none'::character varying, 'completed_all_questions'::character varying, 'low_recent_average'::character varying, 'abuse'::character varying, 'manual'::character varying])::text[])))
);


--
-- Name: TABLE interview_sessions; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.interview_sessions IS 'Core interview record. bot_id NULL = scheduled (not yet sent to lobby).';


--
-- Name: COLUMN interview_sessions.bot_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_sessions.bot_id IS 'Recall bot id after Send to lobby. NULL while scheduled. On rejoin, update in place; keep interview id stable.';


--
-- Name: COLUMN interview_sessions.created_by; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_sessions.created_by IS 'Recruiter who scheduled this interview.';


--
-- Name: COLUMN interview_sessions.meeting_url_normalized; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_sessions.meeting_url_normalized IS 'Canonical meeting URL for duplicate-join prevention.';


--
-- Name: COLUMN interview_sessions.stopped_reason; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.interview_sessions.stopped_reason IS 'Live/end reason on the session; after wrap-up prefer interview_reports.stopped_reason.';


--
-- Name: job_candidate_links; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_candidate_links (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    job_posting_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    cv_document_id uuid,
    linked_by uuid,
    link_source character varying(20) DEFAULT 'upload'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_candidate_links_source_valid CHECK (((link_source)::text = ANY ((ARRAY['upload'::character varying, 'bulk'::character varying, 'manual'::character varying, 'ats'::character varying])::text[])))
);


--
-- Name: TABLE job_candidate_links; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.job_candidate_links IS 'Upload attachment: this CV was added under this requirement (JD).';


--
-- Name: COLUMN job_candidate_links.cv_document_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_links.cv_document_id IS 'Exact CV file used for this link; prefer over guessing from candidates.primary_cv_document_id.';


--
-- Name: COLUMN job_candidate_links.link_source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_links.link_source IS 'How the link was created: upload, bulk, manual, or ats.';


--
-- Name: job_candidate_matches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_candidate_matches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    job_posting_id uuid NOT NULL,
    candidate_id uuid NOT NULL,
    cv_document_id uuid,
    score numeric(5,2) DEFAULT 0 NOT NULL,
    rank integer,
    score_breakdown jsonb,
    reasons_json jsonb,
    domain_overlap text[] DEFAULT '{}'::text[] NOT NULL,
    model_version text,
    scored_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT job_candidate_matches_score_range CHECK (((score >= (0)::numeric) AND (score <= (100)::numeric)))
);


--
-- Name: TABLE job_candidate_matches; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.job_candidate_matches IS 'JDâ†”CV match scores for shortlisting (hybrid/rerank/LLM breakdown in JSON).';


--
-- Name: COLUMN job_candidate_matches.cv_document_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.cv_document_id IS 'Exact document version used when scoring.';


--
-- Name: COLUMN job_candidate_matches.score; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.score IS 'Final fit score 0â€“100 used for top-N pagination.';


--
-- Name: COLUMN job_candidate_matches.score_breakdown; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.score_breakdown IS 'Component scores e.g. {bm25, vector, rerank, llm, metadata}.';


--
-- Name: COLUMN job_candidate_matches.reasons_json; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.reasons_json IS 'Human-readable match reasons / gaps for recruiter UI.';


--
-- Name: COLUMN job_candidate_matches.domain_overlap; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.domain_overlap IS 'Intersection of JD and CV domain_tags at score time.';


--
-- Name: COLUMN job_candidate_matches.model_version; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_candidate_matches.model_version IS 'Embed/rerank/prompt version for reproducibility.';


--
-- Name: job_postings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_postings (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    created_by uuid NOT NULL,
    job_title character varying(255) NOT NULL,
    jd_text text,
    jd_document_id uuid,
    source character varying(20) DEFAULT 'manual'::character varying NOT NULL,
    external_ats_id character varying(255),
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    description text,
    is_active boolean DEFAULT true NOT NULL,
    deleted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    domain_tags text[] DEFAULT '{}'::text[] NOT NULL,
    structured_json jsonb,
    content_hash text,
    pipeline_status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    CONSTRAINT job_postings_jd_min_len CHECK (((jd_text IS NULL) OR (length(TRIM(BOTH FROM jd_text)) >= 100))),
    CONSTRAINT job_postings_pipeline_status_valid CHECK (((pipeline_status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'ready'::character varying, 'failed'::character varying])::text[]))),
    CONSTRAINT job_postings_source_valid CHECK (((source)::text = ANY ((ARRAY['manual'::character varying, 'upload'::character varying, 'ats'::character varying, 'bulk_upload'::character varying])::text[]))),
    CONSTRAINT job_postings_status_valid CHECK (((status)::text = ANY ((ARRAY['draft'::character varying, 'open'::character varying, 'closed'::character varying, 'filled'::character varying])::text[]))),
    CONSTRAINT job_postings_title_nonempty CHECK ((length(TRIM(BOTH FROM job_title)) >= 2))
);


--
-- Name: TABLE job_postings; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.job_postings IS 'Recruiter-owned job requisitions; may come from manual entry, upload, or ATS.';


--
-- Name: COLUMN job_postings.source; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_postings.source IS 'How this job entered the system: manual, upload, or ats.';


--
-- Name: COLUMN job_postings.external_ats_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.job_postings.external_ats_id IS 'Job id in the org ATS; used for dedupe/re-import. NULL if not from ATS.';


--
-- Name: organization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    slug character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    ats_provider character varying(50),
    ats_config jsonb DEFAULT '{}'::jsonb NOT NULL,
    ats_connected_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    ats_api_key_encrypted text,
    CONSTRAINT organization_slug_format CHECK (((slug)::text ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'::text))
);


--
-- Name: TABLE organization; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.organization IS 'Hiring company or team (multi-tenant root).';


--
-- Name: COLUMN organization.ats_provider; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.organization.ats_provider IS 'ATS system for this org (e.g. greenhouse, lever, custom). NULL = not connected.';


--
-- Name: COLUMN organization.ats_config; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.organization.ats_config IS 'Non-secret ATS settings (base URL, org external id, field maps). Store API secrets in env/vault.';


--
-- Name: COLUMN organization.ats_connected_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.organization.ats_connected_at IS 'When ATS was last successfully connected for this organization.';


--
-- Name: qdrant_document_points; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.qdrant_document_points (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    document_id uuid NOT NULL,
    chunk_index integer DEFAULT 0 NOT NULL,
    chunk_text text NOT NULL,
    content_hash text,
    qdrant_collection character varying(128) NOT NULL,
    qdrant_point_id text NOT NULL,
    doc_type character varying(10),
    domain_tags text[] DEFAULT '{}'::text[] NOT NULL,
    candidate_id uuid,
    job_posting_id uuid,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    embed_model text,
    vector_dim integer,
    synced_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT qdrant_document_points_chunk_nonneg CHECK ((chunk_index >= 0)),
    CONSTRAINT qdrant_document_points_dim_positive CHECK (((vector_dim IS NULL) OR (vector_dim > 0))),
    CONSTRAINT qdrant_document_points_doc_type_valid CHECK (((doc_type IS NULL) OR ((doc_type)::text = ANY ((ARRAY['jd'::character varying, 'cv'::character varying])::text[]))))
);


--
-- Name: TABLE qdrant_document_points; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.qdrant_document_points IS 'Registry linking Postgres documents/chunks to Qdrant vector points (no vectors in PG).';


--
-- Name: COLUMN qdrant_document_points.chunk_text; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.chunk_text IS 'Text that was embedded; kept in PG for BM25/hybrid and audit.';


--
-- Name: COLUMN qdrant_document_points.qdrant_collection; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.qdrant_collection IS 'Qdrant collection name used for upsert/search.';


--
-- Name: COLUMN qdrant_document_points.qdrant_point_id; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.qdrant_point_id IS 'Point id in Qdrant (usually same as this row UUID as string).';


--
-- Name: COLUMN qdrant_document_points.domain_tags; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.domain_tags IS 'Copied into Qdrant payload for filtered vector search.';


--
-- Name: COLUMN qdrant_document_points.embed_model; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.embed_model IS 'Embedding model id (e.g. text-embedding-3-small) for versioning.';


--
-- Name: COLUMN qdrant_document_points.vector_dim; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.vector_dim IS 'Vector size in Qdrant for this point; must match collection config.';


--
-- Name: COLUMN qdrant_document_points.synced_at; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.qdrant_document_points.synced_at IS 'Last successful upsert to Qdrant; NULL/old = needs re-sync.';


--
-- Name: session_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.session_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    event_type character varying(50) NOT NULL,
    payload jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT session_events_type_valid CHECK (((event_type)::text = ANY ((ARRAY['bot_created'::character varying, 'bot_joined_meeting'::character varying, 'lobby_timeout'::character varying, 'interview_started'::character varying, 'question_asked'::character varying, 'answer_scored'::character varying, 'localization_completed'::character varying, 'localization_failed'::character varying, 'playback_done'::character varying, 'interview_ended'::character varying, 'bot_left'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: TABLE session_events; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.session_events IS 'Lightweight audit log; optional but useful for debugging and analytics.';


--
-- Name: transcript_turns; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transcript_turns (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    interview_id uuid NOT NULL,
    sequence_num integer NOT NULL,
    role character varying(20) NOT NULL,
    text text NOT NULL,
    turn_type character varying(30) DEFAULT 'other'::character varying NOT NULL,
    spoken_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT transcript_turns_role_valid CHECK (((role)::text = ANY ((ARRAY['assistant'::character varying, 'user'::character varying])::text[]))),
    CONSTRAINT transcript_turns_text_nonempty CHECK ((length(TRIM(BOTH FROM text)) > 0)),
    CONSTRAINT transcript_turns_type_valid CHECK (((turn_type)::text = ANY ((ARRAY['greeting'::character varying, 'introduction'::character varying, 'question'::character varying, 'answer'::character varying, 'clarifier'::character varying, 'rephrase'::character varying, 'repeat'::character varying, 'presence_check'::character varying, 'continuation'::character varying, 'closing'::character varying, 'other'::character varying])::text[])))
);


--
-- Name: TABLE transcript_turns; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.transcript_turns IS 'Complete raw transcription; separate from scored interview_answers.';


--
-- Name: COLUMN transcript_turns.role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.transcript_turns.role IS 'assistant = bot [AI]; user = candidate [You].';


--
-- Name: upload_batch_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.upload_batch_items (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    batch_id uuid NOT NULL,
    original_filename character varying(512),
    storage_path text,
    mime_type character varying(127),
    file_size_bytes bigint,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    document_id uuid,
    candidate_id uuid,
    job_posting_id uuid,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT upload_batch_items_status_valid CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'processing'::character varying, 'ready'::character varying, 'failed'::character varying, 'skipped'::character varying])::text[])))
);


--
-- Name: TABLE upload_batch_items; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.upload_batch_items IS 'One uploaded file within a batch; tracks pipeline status to documents/candidates.';


--
-- Name: upload_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.upload_batches (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    created_by uuid NOT NULL,
    batch_type character varying(10) NOT NULL,
    job_posting_id uuid,
    status character varying(20) DEFAULT 'queued'::character varying NOT NULL,
    total_count integer DEFAULT 0 NOT NULL,
    success_count integer DEFAULT 0 NOT NULL,
    fail_count integer DEFAULT 0 NOT NULL,
    error_message text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    completed_at timestamp with time zone,
    CONSTRAINT upload_batches_counts_nonneg CHECK (((total_count >= 0) AND (success_count >= 0) AND (fail_count >= 0))),
    CONSTRAINT upload_batches_cv_requires_job CHECK ((((batch_type)::text <> 'cv'::text) OR (job_posting_id IS NOT NULL))),
    CONSTRAINT upload_batches_status_valid CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'processing'::character varying, 'done'::character varying, 'failed'::character varying, 'cancelled'::character varying])::text[]))),
    CONSTRAINT upload_batches_type_valid CHECK (((batch_type)::text = ANY ((ARRAY['jd'::character varying, 'cv'::character varying])::text[])))
);


--
-- Name: TABLE upload_batches; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.upload_batches IS 'Bulk JD or CV upload job; CV batches must reference job_posting_id.';


--
-- Name: COLUMN upload_batches.batch_type; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.upload_batches.batch_type IS 'jd = create requirements from files; cv = attach resumes under selected JD.';


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    organization_id uuid NOT NULL,
    full_name character varying(255) NOT NULL,
    email character varying(320) NOT NULL,
    password_hash character varying(255),
    auth_provider character varying(50),
    auth_provider_id character varying(255),
    role character varying(20) DEFAULT 'recruiter'::character varying NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    last_login_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT users_email_lower CHECK (((email)::text = lower((email)::text))),
    CONSTRAINT users_role_valid CHECK (((role)::text = ANY ((ARRAY['admin'::character varying, 'recruiter'::character varying, 'viewer'::character varying])::text[])))
);


--
-- Name: TABLE users; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON TABLE public.users IS 'Recruiters and admins belonging to an organization.';


--
-- Name: COLUMN users.role; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON COLUMN public.users.role IS 'admin | recruiter | viewer';


--
-- Name: v_interview_overview; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_interview_overview AS
 SELECT s.id AS interview_id,
    s.bot_id,
    s.organization_id,
    s.created_by AS recruiter_id,
    u.full_name AS recruiter_name,
    u.email AS recruiter_email,
    s.job_posting_id,
    jp.job_title,
    jp.status AS job_status,
    s.candidate_id,
    c.full_name AS candidate_name,
    c.email AS candidate_email,
    s.meeting_url,
    s.language_mode,
    s.interview_started,
    s.interview_ended,
    s.is_active,
    s.stopped_reason AS session_stopped_reason,
    s.started_at,
    s.completed_at AS session_completed_at,
    s.created_at AS session_created_at,
    r.overall_average,
    r.stage1_average,
    r.questions_scored,
    r.questions_planned,
    r.qualified,
    r.stopped_reason AS report_stopped_reason,
    r.completed_at AS report_completed_at
   FROM ((((public.interview_sessions s
     JOIN public.users u ON ((u.id = s.created_by)))
     JOIN public.job_postings jp ON ((jp.id = s.job_posting_id)))
     JOIN public.candidates c ON ((c.id = s.candidate_id)))
     LEFT JOIN public.interview_reports r ON ((r.interview_id = s.id)));


--
-- Name: VIEW v_interview_overview; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_interview_overview IS 'Interview list row: people, job title, gate score, qualified flag.';


--
-- Name: v_job_posting_stats; Type: VIEW; Schema: public; Owner: -
--

CREATE VIEW public.v_job_posting_stats AS
 SELECT jp.id AS job_posting_id,
    jp.organization_id,
    jp.created_by AS recruiter_id,
    jp.job_title,
    jp.status,
    count(s.id) AS total_interviews,
    count(s.id) FILTER (WHERE (s.interview_ended = true)) AS completed_interviews,
    count(r.id) FILTER (WHERE ((r.stopped_reason)::text = 'completed_all_questions'::text)) AS completed_fully,
    count(r.id) FILTER (WHERE (r.qualified = true)) AS qualified_count,
    round(avg(r.overall_average), 2) AS avg_score
   FROM ((public.job_postings jp
     LEFT JOIN public.interview_sessions s ON ((s.job_posting_id = jp.id)))
     LEFT JOIN public.interview_reports r ON ((r.interview_id = s.id)))
  WHERE ((jp.is_active = true) AND (jp.deleted_at IS NULL))
  GROUP BY jp.id, jp.organization_id, jp.created_by, jp.job_title, jp.status;


--
-- Name: VIEW v_job_posting_stats; Type: COMMENT; Schema: public; Owner: -
--

COMMENT ON VIEW public.v_job_posting_stats IS 'Per job posting: interview counts, fully completed, qualified, average score.';


--
-- Name: candidate_feedback candidate_feedback_bot_id_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_feedback
    ADD CONSTRAINT candidate_feedback_bot_id_unique UNIQUE (bot_id);


--
-- Name: candidate_feedback candidate_feedback_interview_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_feedback
    ADD CONSTRAINT candidate_feedback_interview_unique UNIQUE (interview_id);


--
-- Name: candidate_feedback candidate_feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_feedback
    ADD CONSTRAINT candidate_feedback_pkey PRIMARY KEY (id);


--
-- Name: candidates candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidates
    ADD CONSTRAINT candidates_pkey PRIMARY KEY (id);


--
-- Name: document_extractions document_extractions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: domain_taxonomy domain_taxonomy_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_taxonomy
    ADD CONSTRAINT domain_taxonomy_pkey PRIMARY KEY (id);


--
-- Name: interview_answers interview_answers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_answers
    ADD CONSTRAINT interview_answers_pkey PRIMARY KEY (id);


--
-- Name: interview_answers interview_answers_question_index_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_answers
    ADD CONSTRAINT interview_answers_question_index_unique UNIQUE (interview_id, question_index);


--
-- Name: interview_configs interview_configs_interview_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_configs
    ADD CONSTRAINT interview_configs_interview_unique UNIQUE (interview_id);


--
-- Name: interview_configs interview_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_configs
    ADD CONSTRAINT interview_configs_pkey PRIMARY KEY (id);


--
-- Name: interview_questions interview_questions_external_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_questions
    ADD CONSTRAINT interview_questions_external_unique UNIQUE (interview_id, external_question_id);


--
-- Name: interview_questions interview_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_questions
    ADD CONSTRAINT interview_questions_pkey PRIMARY KEY (id);


--
-- Name: interview_questions interview_questions_slot_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_questions
    ADD CONSTRAINT interview_questions_slot_unique UNIQUE (interview_id, slot);


--
-- Name: interview_reports interview_reports_interview_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_reports
    ADD CONSTRAINT interview_reports_interview_unique UNIQUE (interview_id);


--
-- Name: interview_reports interview_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_reports
    ADD CONSTRAINT interview_reports_pkey PRIMARY KEY (id);


--
-- Name: interview_sessions interview_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_sessions
    ADD CONSTRAINT interview_sessions_pkey PRIMARY KEY (id);


--
-- Name: job_candidate_links job_candidate_links_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_pkey PRIMARY KEY (id);


--
-- Name: job_candidate_links job_candidate_links_unique_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_unique_pair UNIQUE (job_posting_id, candidate_id);


--
-- Name: job_candidate_matches job_candidate_matches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_pkey PRIMARY KEY (id);


--
-- Name: job_candidate_matches job_candidate_matches_unique_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_unique_pair UNIQUE (job_posting_id, candidate_id);


--
-- Name: job_postings job_postings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_pkey PRIMARY KEY (id);


--
-- Name: organization organization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization
    ADD CONSTRAINT organization_pkey PRIMARY KEY (id);


--
-- Name: qdrant_document_points qdrant_document_points_chunk_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_chunk_unique UNIQUE (document_id, chunk_index);


--
-- Name: qdrant_document_points qdrant_document_points_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_pkey PRIMARY KEY (id);


--
-- Name: qdrant_document_points qdrant_document_points_point_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_point_unique UNIQUE (qdrant_collection, qdrant_point_id);


--
-- Name: session_events session_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.session_events
    ADD CONSTRAINT session_events_pkey PRIMARY KEY (id);


--
-- Name: transcript_turns transcript_turns_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_turns
    ADD CONSTRAINT transcript_turns_pkey PRIMARY KEY (id);


--
-- Name: transcript_turns transcript_turns_sequence_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_turns
    ADD CONSTRAINT transcript_turns_sequence_unique UNIQUE (interview_id, sequence_num);


--
-- Name: upload_batch_items upload_batch_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batch_items
    ADD CONSTRAINT upload_batch_items_pkey PRIMARY KEY (id);


--
-- Name: upload_batches upload_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batches
    ADD CONSTRAINT upload_batches_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_candidate_feedback_submitted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidate_feedback_submitted ON public.candidate_feedback USING btree (submitted_at DESC);


--
-- Name: idx_candidates_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_active ON public.candidates USING btree (created_by, full_name) WHERE ((is_active = true) AND (deleted_at IS NULL));


--
-- Name: idx_candidates_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_created_by ON public.candidates USING btree (created_by);


--
-- Name: idx_candidates_domain_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_domain_tags ON public.candidates USING gin (domain_tags);


--
-- Name: idx_candidates_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_name ON public.candidates USING btree (organization_id, full_name);


--
-- Name: idx_candidates_org_ats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_candidates_org_ats_id ON public.candidates USING btree (organization_id, external_ats_id) WHERE (external_ats_id IS NOT NULL);


--
-- Name: idx_candidates_org_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_org_email ON public.candidates USING btree (organization_id, email) WHERE ((email IS NOT NULL) AND (deleted_at IS NULL));


--
-- Name: idx_candidates_org_phone; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_org_phone ON public.candidates USING btree (organization_id, phone) WHERE ((phone IS NOT NULL) AND (deleted_at IS NULL));


--
-- Name: idx_candidates_organization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_organization ON public.candidates USING btree (organization_id);


--
-- Name: idx_candidates_primary_cv_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_candidates_primary_cv_document ON public.candidates USING btree (primary_cv_document_id) WHERE (primary_cv_document_id IS NOT NULL);


--
-- Name: idx_document_extractions_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_extractions_candidate ON public.document_extractions USING btree (candidate_id) WHERE (candidate_id IS NOT NULL);


--
-- Name: idx_document_extractions_job_posting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_extractions_job_posting ON public.document_extractions USING btree (job_posting_id);


--
-- Name: idx_document_extractions_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_extractions_org ON public.document_extractions USING btree (organization_id);


--
-- Name: idx_document_extractions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_extractions_status ON public.document_extractions USING btree (status);


--
-- Name: idx_documents_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_candidate ON public.documents USING btree (candidate_id) WHERE (candidate_id IS NOT NULL);


--
-- Name: idx_documents_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_content_hash ON public.documents USING btree (organization_id, content_hash) WHERE (content_hash IS NOT NULL);


--
-- Name: idx_documents_job_posting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_job_posting ON public.documents USING btree (job_posting_id) WHERE (job_posting_id IS NOT NULL);


--
-- Name: idx_documents_org_ats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_documents_org_ats_id ON public.documents USING btree (organization_id, document_type, external_ats_id) WHERE (external_ats_id IS NOT NULL);


--
-- Name: idx_documents_organization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_organization ON public.documents USING btree (organization_id);


--
-- Name: idx_documents_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_source ON public.documents USING btree (organization_id, source);


--
-- Name: idx_documents_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_type ON public.documents USING btree (organization_id, document_type);


--
-- Name: idx_domain_taxonomy_aliases; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_taxonomy_aliases ON public.domain_taxonomy USING gin (aliases);


--
-- Name: idx_domain_taxonomy_org_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_domain_taxonomy_org_slug ON public.domain_taxonomy USING btree (organization_id, slug) WHERE (organization_id IS NOT NULL);


--
-- Name: idx_domain_taxonomy_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_domain_taxonomy_parent ON public.domain_taxonomy USING btree (parent_slug) WHERE (parent_slug IS NOT NULL);


--
-- Name: idx_domain_taxonomy_system_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_domain_taxonomy_system_slug ON public.domain_taxonomy USING btree (slug) WHERE (organization_id IS NULL);


--
-- Name: idx_interview_answers_difficulty; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_answers_difficulty ON public.interview_answers USING btree (interview_id, difficulty);


--
-- Name: idx_interview_answers_interview; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_answers_interview ON public.interview_answers USING btree (interview_id);


--
-- Name: idx_interview_answers_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_answers_score ON public.interview_answers USING btree (interview_id, score);


--
-- Name: idx_interview_configs_job_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_configs_job_title ON public.interview_configs USING btree (job_title);


--
-- Name: idx_interview_questions_interview; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_questions_interview ON public.interview_questions USING btree (interview_id);


--
-- Name: idx_interview_questions_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_questions_status ON public.interview_questions USING btree (interview_id, status);


--
-- Name: idx_interview_reports_average; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_reports_average ON public.interview_reports USING btree (overall_average);


--
-- Name: idx_interview_reports_completed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_reports_completed ON public.interview_reports USING btree (completed_at DESC);


--
-- Name: idx_interview_reports_job_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_reports_job_title ON public.interview_reports USING btree (job_title);


--
-- Name: idx_interview_reports_qualified; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_reports_qualified ON public.interview_reports USING btree (job_title, qualified) WHERE (qualified = true);


--
-- Name: idx_interview_sessions_bot_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_interview_sessions_bot_id ON public.interview_sessions USING btree (bot_id) WHERE (bot_id IS NOT NULL);


--
-- Name: idx_interview_sessions_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_candidate ON public.interview_sessions USING btree (candidate_id);


--
-- Name: idx_interview_sessions_completed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_completed ON public.interview_sessions USING btree (completed_at DESC) WHERE (interview_ended = true);


--
-- Name: idx_interview_sessions_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_created_by ON public.interview_sessions USING btree (created_by, completed_at DESC);


--
-- Name: idx_interview_sessions_job_posting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_job_posting ON public.interview_sessions USING btree (job_posting_id, completed_at DESC);


--
-- Name: idx_interview_sessions_meeting; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_meeting ON public.interview_sessions USING btree (meeting_url_normalized);


--
-- Name: idx_interview_sessions_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_org ON public.interview_sessions USING btree (organization_id);


--
-- Name: idx_interview_sessions_scheduled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_interview_sessions_scheduled ON public.interview_sessions USING btree (created_by, created_at DESC) WHERE ((bot_id IS NULL) AND (interview_ended = false));


--
-- Name: idx_job_candidate_links_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_links_candidate ON public.job_candidate_links USING btree (candidate_id);


--
-- Name: idx_job_candidate_links_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_links_document ON public.job_candidate_links USING btree (cv_document_id) WHERE (cv_document_id IS NOT NULL);


--
-- Name: idx_job_candidate_links_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_links_job ON public.job_candidate_links USING btree (job_posting_id);


--
-- Name: idx_job_candidate_links_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_links_org ON public.job_candidate_links USING btree (organization_id);


--
-- Name: idx_job_candidate_matches_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_matches_candidate ON public.job_candidate_matches USING btree (candidate_id);


--
-- Name: idx_job_candidate_matches_domain_overlap; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_matches_domain_overlap ON public.job_candidate_matches USING gin (domain_overlap);


--
-- Name: idx_job_candidate_matches_job_score; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_matches_job_score ON public.job_candidate_matches USING btree (job_posting_id, score DESC);


--
-- Name: idx_job_candidate_matches_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_candidate_matches_org ON public.job_candidate_matches USING btree (organization_id);


--
-- Name: idx_job_postings_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_created_by ON public.job_postings USING btree (created_by);


--
-- Name: idx_job_postings_domain_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_domain_tags ON public.job_postings USING gin (domain_tags);


--
-- Name: idx_job_postings_org_ats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_job_postings_org_ats_id ON public.job_postings USING btree (organization_id, external_ats_id) WHERE (external_ats_id IS NOT NULL);


--
-- Name: idx_job_postings_organization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_organization ON public.job_postings USING btree (organization_id);


--
-- Name: idx_job_postings_pipeline_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_pipeline_status ON public.job_postings USING btree (organization_id, pipeline_status) WHERE ((is_active = true) AND (deleted_at IS NULL));


--
-- Name: idx_job_postings_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_source ON public.job_postings USING btree (organization_id, source);


--
-- Name: idx_job_postings_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_status ON public.job_postings USING btree (organization_id, status) WHERE ((is_active = true) AND (deleted_at IS NULL));


--
-- Name: idx_job_postings_title_trgm; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_job_postings_title_trgm ON public.job_postings USING gin (job_title public.gin_trgm_ops);


--
-- Name: idx_organization_slug; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_organization_slug ON public.organization USING btree (slug);


--
-- Name: idx_qdrant_points_candidate; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_candidate ON public.qdrant_document_points USING btree (candidate_id) WHERE (candidate_id IS NOT NULL);


--
-- Name: idx_qdrant_points_collection; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_collection ON public.qdrant_document_points USING btree (qdrant_collection);


--
-- Name: idx_qdrant_points_content_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_content_hash ON public.qdrant_document_points USING btree (organization_id, content_hash) WHERE (content_hash IS NOT NULL);


--
-- Name: idx_qdrant_points_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_document ON public.qdrant_document_points USING btree (document_id);


--
-- Name: idx_qdrant_points_domain_tags; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_domain_tags ON public.qdrant_document_points USING gin (domain_tags);


--
-- Name: idx_qdrant_points_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_job ON public.qdrant_document_points USING btree (job_posting_id) WHERE (job_posting_id IS NOT NULL);


--
-- Name: idx_qdrant_points_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_qdrant_points_org ON public.qdrant_document_points USING btree (organization_id);


--
-- Name: idx_session_events_interview; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_session_events_interview ON public.session_events USING btree (interview_id, created_at);


--
-- Name: idx_session_events_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_session_events_type ON public.session_events USING btree (event_type, created_at DESC);


--
-- Name: idx_transcript_turns_interview; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcript_turns_interview ON public.transcript_turns USING btree (interview_id, sequence_num);


--
-- Name: idx_transcript_turns_spoken_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcript_turns_spoken_at ON public.transcript_turns USING btree (interview_id, spoken_at);


--
-- Name: idx_upload_batch_items_batch; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_upload_batch_items_batch ON public.upload_batch_items USING btree (batch_id, status);


--
-- Name: idx_upload_batch_items_document; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_upload_batch_items_document ON public.upload_batch_items USING btree (document_id) WHERE (document_id IS NOT NULL);


--
-- Name: idx_upload_batches_job; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_upload_batches_job ON public.upload_batches USING btree (job_posting_id) WHERE (job_posting_id IS NOT NULL);


--
-- Name: idx_upload_batches_org; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_upload_batches_org ON public.upload_batches USING btree (organization_id, created_at DESC);


--
-- Name: idx_upload_batches_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_upload_batches_status ON public.upload_batches USING btree (organization_id, status);


--
-- Name: idx_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_email ON public.users USING btree (email);


--
-- Name: idx_users_organization; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_organization ON public.users USING btree (organization_id);


--
-- Name: candidate_feedback candidate_feedback_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidate_feedback
    ADD CONSTRAINT candidate_feedback_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: candidates candidates_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidates
    ADD CONSTRAINT candidates_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: candidates candidates_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidates
    ADD CONSTRAINT candidates_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: candidates candidates_primary_cv_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.candidates
    ADD CONSTRAINT candidates_primary_cv_document_id_fkey FOREIGN KEY (primary_cv_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: document_extractions document_extractions_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE SET NULL;


--
-- Name: document_extractions document_extractions_cv_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_cv_document_id_fkey FOREIGN KEY (cv_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: document_extractions document_extractions_jd_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_jd_document_id_fkey FOREIGN KEY (jd_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: document_extractions document_extractions_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: document_extractions document_extractions_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: document_extractions document_extractions_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_extractions
    ADD CONSTRAINT document_extractions_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: documents documents_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE SET NULL;


--
-- Name: documents documents_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: documents documents_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: documents documents_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: domain_taxonomy domain_taxonomy_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.domain_taxonomy
    ADD CONSTRAINT domain_taxonomy_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: interview_answers interview_answers_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_answers
    ADD CONSTRAINT interview_answers_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: interview_answers interview_answers_interview_question_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_answers
    ADD CONSTRAINT interview_answers_interview_question_id_fkey FOREIGN KEY (interview_question_id) REFERENCES public.interview_questions(id) ON DELETE SET NULL;


--
-- Name: interview_configs interview_configs_document_extraction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_configs
    ADD CONSTRAINT interview_configs_document_extraction_id_fkey FOREIGN KEY (document_extraction_id) REFERENCES public.document_extractions(id) ON DELETE SET NULL;


--
-- Name: interview_configs interview_configs_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_configs
    ADD CONSTRAINT interview_configs_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: interview_configs interview_configs_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_configs
    ADD CONSTRAINT interview_configs_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: interview_questions interview_questions_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_questions
    ADD CONSTRAINT interview_questions_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: interview_reports interview_reports_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_reports
    ADD CONSTRAINT interview_reports_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: interview_sessions interview_sessions_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_sessions
    ADD CONSTRAINT interview_sessions_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE RESTRICT;


--
-- Name: interview_sessions interview_sessions_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_sessions
    ADD CONSTRAINT interview_sessions_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: interview_sessions interview_sessions_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_sessions
    ADD CONSTRAINT interview_sessions_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE RESTRICT;


--
-- Name: interview_sessions interview_sessions_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interview_sessions
    ADD CONSTRAINT interview_sessions_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: job_candidate_links job_candidate_links_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE CASCADE;


--
-- Name: job_candidate_links job_candidate_links_cv_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_cv_document_id_fkey FOREIGN KEY (cv_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: job_candidate_links job_candidate_links_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE CASCADE;


--
-- Name: job_candidate_links job_candidate_links_linked_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_linked_by_fkey FOREIGN KEY (linked_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: job_candidate_links job_candidate_links_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_links
    ADD CONSTRAINT job_candidate_links_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: job_candidate_matches job_candidate_matches_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE CASCADE;


--
-- Name: job_candidate_matches job_candidate_matches_cv_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_cv_document_id_fkey FOREIGN KEY (cv_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: job_candidate_matches job_candidate_matches_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE CASCADE;


--
-- Name: job_candidate_matches job_candidate_matches_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_candidate_matches
    ADD CONSTRAINT job_candidate_matches_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: job_postings job_postings_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: job_postings job_postings_jd_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_jd_document_id_fkey FOREIGN KEY (jd_document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: job_postings job_postings_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_postings
    ADD CONSTRAINT job_postings_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: qdrant_document_points qdrant_document_points_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE SET NULL;


--
-- Name: qdrant_document_points qdrant_document_points_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: qdrant_document_points qdrant_document_points_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: qdrant_document_points qdrant_document_points_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.qdrant_document_points
    ADD CONSTRAINT qdrant_document_points_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: session_events session_events_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.session_events
    ADD CONSTRAINT session_events_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: transcript_turns transcript_turns_interview_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_turns
    ADD CONSTRAINT transcript_turns_interview_id_fkey FOREIGN KEY (interview_id) REFERENCES public.interview_sessions(id) ON DELETE CASCADE;


--
-- Name: upload_batch_items upload_batch_items_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batch_items
    ADD CONSTRAINT upload_batch_items_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.upload_batches(id) ON DELETE CASCADE;


--
-- Name: upload_batch_items upload_batch_items_candidate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batch_items
    ADD CONSTRAINT upload_batch_items_candidate_id_fkey FOREIGN KEY (candidate_id) REFERENCES public.candidates(id) ON DELETE SET NULL;


--
-- Name: upload_batch_items upload_batch_items_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batch_items
    ADD CONSTRAINT upload_batch_items_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: upload_batch_items upload_batch_items_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batch_items
    ADD CONSTRAINT upload_batch_items_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: upload_batches upload_batches_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batches
    ADD CONSTRAINT upload_batches_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: upload_batches upload_batches_job_posting_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batches
    ADD CONSTRAINT upload_batches_job_posting_id_fkey FOREIGN KEY (job_posting_id) REFERENCES public.job_postings(id) ON DELETE SET NULL;


--
-- Name: upload_batches upload_batches_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upload_batches
    ADD CONSTRAINT upload_batches_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- Name: users users_organization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organization(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict aisBTfNiF34Qb1QNr8EQ9Aotfje5ir26xYCizuFa8U1G20gsngef41iP8YqtI0Q

