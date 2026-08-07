-- Entry function name for LeetCode-style harness (system calls this; candidate does not print).

ALTER TABLE coding_tasks
    ADD COLUMN IF NOT EXISTS entry_function VARCHAR(64);

COMMENT ON COLUMN coding_tasks.entry_function IS
    'Function the runner calls with example input; candidate implements this only.';

UPDATE coding_tasks SET entry_function = 'second_largest'
WHERE slug = 'second-largest' AND organization_id IS NULL;

UPDATE coding_tasks SET entry_function = 'group_anagrams'
WHERE slug = 'group-anagrams' AND organization_id IS NULL;

UPDATE coding_tasks SET entry_function = 'min_meeting_rooms'
WHERE slug = 'meeting-rooms' AND organization_id IS NULL;

-- Function-only starters (harness is injected at run time).
UPDATE coding_tasks
SET starter_code_json = $starter${
  "python": "def second_largest(nums):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
  "javascript": "function secondLargest(nums) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
}$starter$::jsonb,
    updated_at = NOW()
WHERE slug = 'second-largest' AND organization_id IS NULL;

UPDATE coding_tasks
SET starter_code_json = $starter${
  "python": "def group_anagrams(words):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
  "javascript": "function groupAnagrams(words) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
}$starter$::jsonb,
    updated_at = NOW()
WHERE slug = 'group-anagrams' AND organization_id IS NULL;

UPDATE coding_tasks
SET starter_code_json = $starter${
  "python": "def min_meeting_rooms(intervals):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
  "javascript": "function minMeetingRooms(intervals) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
}$starter$::jsonb,
    updated_at = NOW()
WHERE slug = 'meeting-rooms' AND organization_id IS NULL;
