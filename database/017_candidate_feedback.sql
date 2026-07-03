-- Candidate post-interview feedback (one submission per interview).

CREATE TABLE candidate_feedback (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    bot_id              UUID NOT NULL,
    overall_rating      SMALLINT NOT NULL,
    clarity_rating      SMALLINT NOT NULL,
    tech_issues         VARCHAR(10) NOT NULL DEFAULT 'none',
    improve_text        VARCHAR(500) NOT NULL,
    would_repeat        VARCHAR(10),
    candidate_name      VARCHAR(255),
    submitted_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT candidate_feedback_bot_id_unique UNIQUE (bot_id),
    CONSTRAINT candidate_feedback_interview_unique UNIQUE (interview_id),
    CONSTRAINT candidate_feedback_overall_range CHECK (overall_rating BETWEEN 1 AND 5),
    CONSTRAINT candidate_feedback_clarity_range CHECK (clarity_rating BETWEEN 1 AND 5),
    CONSTRAINT candidate_feedback_tech_valid CHECK (tech_issues IN ('none', 'minor', 'major')),
    CONSTRAINT candidate_feedback_repeat_valid CHECK (
        would_repeat IS NULL OR would_repeat IN ('yes', 'maybe', 'no')
    ),
    CONSTRAINT candidate_feedback_improve_nonempty CHECK (LENGTH(TRIM(improve_text)) >= 1)
);

CREATE INDEX idx_candidate_feedback_submitted ON candidate_feedback (submitted_at DESC);

COMMENT ON TABLE candidate_feedback IS 'One candidate feedback form per interview; keyed by bot_id for public links.';
