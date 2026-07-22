-- Scored main Q&A for one interview (not the full transcript).

CREATE TABLE interview_answers (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id          UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    interview_question_id UUID REFERENCES interview_questions (id) ON DELETE SET NULL,
    question_index        SMALLINT NOT NULL,
    external_question_id  VARCHAR(64) NOT NULL,
    difficulty            VARCHAR(20) NOT NULL,
    source                VARCHAR(20) NOT NULL,
    question_text         TEXT NOT NULL,
    answer_text           TEXT NOT NULL,
    score                 SMALLINT NOT NULL,
    confident             BOOLEAN NOT NULL DEFAULT FALSE,
    relevant              BOOLEAN NOT NULL DEFAULT TRUE,
    strengths             TEXT NOT NULL DEFAULT '',
    develop               TEXT NOT NULL DEFAULT '',
    fix                   TEXT NOT NULL DEFAULT '',
    abuse_flag            BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_answers_score_range CHECK (score BETWEEN 0 AND 10),
    CONSTRAINT interview_answers_question_index_unique UNIQUE (interview_id, question_index),
    CONSTRAINT interview_answers_difficulty_valid CHECK (
        difficulty IN ('Low', 'Intermediate', 'Hard')
    ),
    CONSTRAINT interview_answers_source_valid CHECK (
        source IN ('jd', 'resume', 'other')
    )
);

CREATE INDEX idx_interview_answers_interview ON interview_answers (interview_id);
CREATE INDEX idx_interview_answers_score ON interview_answers (interview_id, score);
CREATE INDEX idx_interview_answers_difficulty ON interview_answers (interview_id, difficulty);

COMMENT ON TABLE interview_answers IS
    'Evaluator result per main question; difficulty/source stored for reporting without joins.';
