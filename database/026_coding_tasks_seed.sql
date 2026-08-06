-- Global seed coding tasks (fixed UUIDs for stable references across envs).

INSERT INTO coding_tasks (
    id,
    organization_id,
    slug,
    title,
    difficulty,
    statement,
    examples_json,
    constraints_text,
    starter_code_json,
    entry_function,
    allowed_languages,
    skill_tags,
    is_active
) VALUES
(
    'a1111111-1111-4111-8111-111111111101',
    NULL,
    'second-largest',
    'Find Second Largest',
    'easy',
    $stmt$Given an array of integers, return the second largest distinct number. If it does not exist, return -1.$stmt$,
    $ex$[
      {"input": "[10, 5, 10, 8]", "output": "8", "explanation": "Distinct values are 10, 5, 8; second largest is 8."},
      {"input": "[4, 4, 4]", "output": "-1", "explanation": "Only one distinct value."}
    ]$ex$::jsonb,
    '1 <= nums.length <= 10^5. -10^9 <= nums[i] <= 10^9.',
    $starter${
      "python": "def second_largest(nums):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
      "javascript": "function secondLargest(nums) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
    }$starter$::jsonb,
    'second_largest',
    ARRAY['python', 'javascript']::text[],
    ARRAY['arrays', 'basics']::text[],
    TRUE
),
(
    'a1111111-1111-4111-8111-111111111102',
    NULL,
    'group-anagrams',
    'Group Anagrams',
    'medium',
    $stmt$Given a list of words, group anagrams together and return the groups. Order of groups and words within a group may vary.$stmt$,
    $ex$[
      {"input": "[\"eat\",\"tea\",\"tan\",\"ate\",\"nat\",\"bat\"]", "output": "[[\"eat\",\"tea\",\"ate\"],[\"tan\",\"nat\"],[\"bat\"]]", "explanation": "Words with the same letter multiset belong together."},
      {"input": "[\"\"]", "output": "[[\"\"]]", "explanation": "Single empty string."}
    ]$ex$::jsonb,
    '1 <= words.length <= 10^4. 0 <= words[i].length <= 100. Lowercase English letters only.',
    $starter${
      "python": "def group_anagrams(words):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
      "javascript": "function groupAnagrams(words) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
    }$starter$::jsonb,
    'group_anagrams',
    ARRAY['python', 'javascript']::text[],
    ARRAY['strings', 'hashing']::text[],
    TRUE
),
(
    'a1111111-1111-4111-8111-111111111103',
    NULL,
    'meeting-rooms',
    'Meeting Rooms Needed',
    'medium',
    $stmt$Given meeting intervals [start, end], return the minimum number of meeting rooms required.$stmt$,
    $ex$[
      {"input": "[[0,30],[5,10],[15,20]]", "output": "2", "explanation": "First meeting overlaps the next two; two rooms needed."},
      {"input": "[[7,10],[2,4]]", "output": "1", "explanation": "No overlap."}
    ]$ex$::jsonb,
    '1 <= intervals.length <= 10^4. 0 <= start < end <= 10^6.',
    $starter${
      "python": "def min_meeting_rooms(intervals):\n    # Write your solution. Do not print — Run checks examples automatically.\n    pass\n",
      "javascript": "function minMeetingRooms(intervals) {\n  // Write your solution. Do not print — Run checks examples automatically.\n}\n"
    }$starter$::jsonb,
    'min_meeting_rooms',
    ARRAY['python', 'javascript']::text[],
    ARRAY['intervals', 'sorting', 'heaps']::text[],
    TRUE
)
ON CONFLICT (slug) WHERE organization_id IS NULL
DO UPDATE SET
    title = EXCLUDED.title,
    difficulty = EXCLUDED.difficulty,
    entry_function = EXCLUDED.entry_function,
    statement = EXCLUDED.statement,
    examples_json = EXCLUDED.examples_json,
    constraints_text = EXCLUDED.constraints_text,
    starter_code_json = EXCLUDED.starter_code_json,
    allowed_languages = EXCLUDED.allowed_languages,
    skill_tags = EXCLUDED.skill_tags,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();
