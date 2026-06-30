-- Scored main Q&A pairs (evaluation records, not full raw transcript).

CREATE TABLE interview_answers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interview_id        UUID NOT NULL REFERENCES interview_sessions (id) ON DELETE CASCADE,
    interview_question_id UUID REFERENCES interview_questions (id) ON DELETE SET NULL,
    question_index      SMALLINT NOT NULL,
    external_question_id VARCHAR(64) NOT NULL,
    question_text       TEXT NOT NULL,
    answer_text         TEXT NOT NULL,
    score               SMALLINT NOT NULL,
    confident           BOOLEAN NOT NULL DEFAULT FALSE,
    relevant            BOOLEAN NOT NULL DEFAULT TRUE,
    strengths           TEXT NOT NULL DEFAULT '',
    develop             TEXT NOT NULL DEFAULT '',
    fix                 TEXT NOT NULL DEFAULT '',
    abuse_flag          BOOLEAN NOT NULL DEFAULT FALSE,
    evaluated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT interview_answers_score_range CHECK (score BETWEEN 0 AND 10),
    CONSTRAINT interview_answers_question_index_unique UNIQUE (interview_id, question_index)
);

CREATE INDEX idx_interview_answers_interview ON interview_answers (interview_id);
CREATE INDEX idx_interview_answers_score ON interview_answers (interview_id, score);

COMMENT ON TABLE interview_answers IS 'Evaluator output per main question; maps to report per_question[].';
