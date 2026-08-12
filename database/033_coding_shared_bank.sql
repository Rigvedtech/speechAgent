-- Shared DSA bank is org-scoped (coding_tasks.organization_id) with domain_id NULL.
-- Product limits (enforced in API, not DB CHECKs):
--   MAX_PROBLEMS_PER_ORG = 100
--   SEED_TARGET_COUNT = 90
--   GENERATE_BATCH_SIZE = 10
-- Domains remain language tracks for schedule/demo locking.
-- No schema change required; this file documents the product contract.

SELECT 1;
