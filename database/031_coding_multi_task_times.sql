-- Multi-task coding rounds + AI/recruiter per-task time limits.

ALTER TABLE coding_tasks
    ADD COLUMN IF NOT EXISTS estimated_time_min SMALLINT NOT NULL DEFAULT 25;

ALTER TABLE coding_tasks
    DROP CONSTRAINT IF EXISTS coding_tasks_estimated_time_range;

ALTER TABLE coding_tasks
    ADD CONSTRAINT coding_tasks_estimated_time_range CHECK (
        estimated_time_min BETWEEN 5 AND 180
    );

-- Seed defaults by difficulty for existing rows that still have the column default.
UPDATE coding_tasks
SET estimated_time_min = CASE difficulty
    WHEN 'easy' THEN 15
    WHEN 'hard' THEN 45
    ELSE 25
END
WHERE estimated_time_min = 25;

COMMENT ON COLUMN coding_tasks.estimated_time_min IS
    'AI (or difficulty default) estimate of minutes needed to complete this problem.';

ALTER TABLE interview_coding_configs
    ADD COLUMN IF NOT EXISTS task_time_limits_json JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN interview_coding_configs.task_time_limits_json IS
    'Map of task_id (UUID string) -> recruiter time_limit_min for that assigned task.';

COMMENT ON COLUMN interview_coding_configs.task_ids IS
    'Ordered list of assigned coding tasks for this interview (candidate works them one-by-one).';

COMMENT ON COLUMN interview_coding_configs.assigned_task_id IS
    'Current task for the candidate (first incomplete in task_ids).';

COMMENT ON COLUMN interview_coding_configs.time_limit_min IS
    'Time limit for the current assigned_task_id (kept for backward compatibility).';
