"""Curated language-agnostic DSA bank (~90 problems) for org seeding.

Each problem stores JSON examples graded by return value. Starters are filled
per language at seed/persist time — not here.
"""

from __future__ import annotations

import json
from typing import Any


def _j(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"))


def _problem(
    *,
    slug: str,
    title: str,
    difficulty: str,
    statement: str,
    entry_function: str,
    examples: list[tuple[Any, Any, str]],
    constraints_text: str,
    skill_tags: list[str],
    estimated_time_min: int = 25,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "difficulty": difficulty,
        "statement": statement.strip(),
        "entry_function": entry_function,
        "examples": [
            {
                "input": _j(inp) if not isinstance(inp, str) else inp,
                "output": _j(out) if not isinstance(out, str) else out,
                "explanation": exp,
            }
            for inp, out, exp in examples
        ],
        "constraints_text": constraints_text.strip(),
        "skill_tags": skill_tags,
        "estimated_time_min": estimated_time_min,
    }


def build_seed_catalog() -> list[dict[str, Any]]:
    """Return ~90 unique DSA specs (deterministic order)."""
    problems: list[dict[str, Any]] = []

    # ── Arrays / hashing ──────────────────────────────────────────────────
    problems += [
        _problem(
            slug="two-sum-indices",
            title="Two Sum Indices",
            difficulty="easy",
            statement="Given an array of integers nums and an integer target, return the indices of the two numbers that add up to target. Exactly one solution exists.",
            entry_function="two_sum",
            examples=[
                ({"nums": [2, 7, 11, 15], "target": 9}, [0, 1], "2 + 7 = 9"),
                ({"nums": [3, 2, 4], "target": 6}, [1, 2], "2 + 4 = 6"),
            ],
            constraints_text="2 <= nums.length <= 10^4. Exactly one valid answer.",
            skill_tags=["hash map", "arrays"],
            estimated_time_min=20,
        ),
        _problem(
            slug="contains-duplicate",
            title="Contains Duplicate",
            difficulty="easy",
            statement="Return true if any value appears at least twice in nums; otherwise false.",
            entry_function="contains_duplicate",
            examples=[
                ({"nums": [1, 2, 3, 1]}, True, "1 appears twice"),
                ({"nums": [1, 2, 3, 4]}, False, "all unique"),
            ],
            constraints_text="1 <= nums.length <= 10^5",
            skill_tags=["hash set", "arrays"],
            estimated_time_min=15,
        ),
        _problem(
            slug="missing-number",
            title="Missing Number",
            difficulty="easy",
            statement="Given nums containing n distinct numbers in range [0, n], return the missing number.",
            entry_function="missing_number",
            examples=[
                ({"nums": [3, 0, 1]}, 2, "2 is missing"),
                ({"nums": [0, 1]}, 2, "2 is missing"),
            ],
            constraints_text="n == nums.length; nums contains each of 0..n except one",
            skill_tags=["math", "arrays"],
            estimated_time_min=15,
        ),
        _problem(
            slug="single-number",
            title="Single Number",
            difficulty="easy",
            statement="Every element appears twice except one. Return that single element.",
            entry_function="single_number",
            examples=[
                ({"nums": [2, 2, 1]}, 1, "1 appears once"),
                ({"nums": [4, 1, 2, 1, 2]}, 4, "4 appears once"),
            ],
            constraints_text="1 <= nums.length <= 3*10^4; odd length",
            skill_tags=["bit manipulation", "arrays"],
            estimated_time_min=15,
        ),
        _problem(
            slug="majority-element",
            title="Majority Element",
            difficulty="easy",
            statement="Return the element that appears more than n/2 times. It always exists.",
            entry_function="majority_element",
            examples=[
                ({"nums": [3, 2, 3]}, 3, "3 is majority"),
                ({"nums": [2, 2, 1, 1, 1, 2, 2]}, 2, "2 is majority"),
            ],
            constraints_text="Majority element always exists",
            skill_tags=["arrays", "voting"],
            estimated_time_min=20,
        ),
        _problem(
            slug="max-profit-one-trade",
            title="Best Time to Buy and Sell Stock",
            difficulty="easy",
            statement="You may complete at most one transaction. Return the maximum profit; 0 if none.",
            entry_function="max_profit",
            examples=[
                ({"prices": [7, 1, 5, 3, 6, 4]}, 5, "buy 1 sell 6"),
                ({"prices": [7, 6, 4, 3, 1]}, 0, "no profit"),
            ],
            constraints_text="1 <= prices.length <= 10^5",
            skill_tags=["arrays", "greedy"],
            estimated_time_min=20,
        ),
        _problem(
            slug="move-zeroes",
            title="Move Zeroes",
            difficulty="easy",
            statement="Move all zeroes to the end while keeping the relative order of non-zero elements. Return the resulting array.",
            entry_function="move_zeroes",
            examples=[
                ({"nums": [0, 1, 0, 3, 12]}, [1, 3, 12, 0, 0], "non-zeros keep order"),
                ({"nums": [0]}, [0], "single zero"),
            ],
            constraints_text="1 <= nums.length <= 10^4",
            skill_tags=["two pointers", "arrays"],
            estimated_time_min=20,
        ),
        _problem(
            slug="intersection-two-arrays",
            title="Intersection of Two Arrays",
            difficulty="easy",
            statement="Return the intersection of two arrays as a sorted list of unique values.",
            entry_function="intersection",
            examples=[
                ({"nums1": [1, 2, 2, 1], "nums2": [2, 2]}, [2], "only 2"),
                ({"nums1": [4, 9, 5], "nums2": [9, 4, 9, 8, 4]}, [4, 9], "sorted unique"),
            ],
            constraints_text="Return values sorted ascending",
            skill_tags=["hash set", "arrays"],
            estimated_time_min=20,
        ),
        _problem(
            slug="plus-one",
            title="Plus One",
            difficulty="easy",
            statement="digits represents a non-negative integer. Add one and return the digit array.",
            entry_function="plus_one",
            examples=[
                ({"digits": [1, 2, 3]}, [1, 2, 4], "123+1"),
                ({"digits": [9]}, [1, 0], "9+1=10"),
            ],
            constraints_text="1 <= digits.length <= 100",
            skill_tags=["arrays", "math"],
            estimated_time_min=15,
        ),
        _problem(
            slug="remove-duplicates-sorted",
            title="Remove Duplicates from Sorted Array",
            difficulty="easy",
            statement="Given a sorted array, return a new array with duplicates removed (stable unique values).",
            entry_function="remove_duplicates",
            examples=[
                ({"nums": [1, 1, 2]}, [1, 2], "unique values"),
                ({"nums": [0, 0, 1, 1, 1, 2, 2, 3, 3, 4]}, [0, 1, 2, 3, 4], "five uniques"),
            ],
            constraints_text="Input is sorted non-decreasing",
            skill_tags=["two pointers", "arrays"],
            estimated_time_min=20,
        ),
    ]

    # ── Strings ───────────────────────────────────────────────────────────
    problems += [
        _problem(
            slug="valid-anagram",
            title="Valid Anagram",
            difficulty="easy",
            statement="Return true if t is an anagram of s.",
            entry_function="is_anagram",
            examples=[
                ({"s": "anagram", "t": "nagaram"}, True, "same multiset"),
                ({"s": "rat", "t": "car"}, False, "different letters"),
            ],
            constraints_text="s and t consist of lowercase letters",
            skill_tags=["hashing", "strings"],
            estimated_time_min=15,
        ),
        _problem(
            slug="first-unique-char",
            title="First Unique Character",
            difficulty="easy",
            statement="Return the index of the first non-repeating character in s, or -1 if none.",
            entry_function="first_uniq_char",
            examples=[
                ({"s": "leetcode"}, 0, "l is unique"),
                ({"s": "aabb"}, -1, "none unique"),
            ],
            constraints_text="1 <= s.length <= 10^5",
            skill_tags=["hashing", "strings"],
            estimated_time_min=20,
        ),
        _problem(
            slug="reverse-words",
            title="Reverse Words in a String",
            difficulty="easy",
            statement="Reverse the order of words in s. Words are separated by spaces; return a single-spaced string.",
            entry_function="reverse_words",
            examples=[
                ({"s": "the sky is blue"}, "blue is sky the", "reversed words"),
                ({"s": "  hello world  "}, "world hello", "trim spaces"),
            ],
            constraints_text="Trim leading/trailing spaces; collapse multiple spaces",
            skill_tags=["strings", "two pointers"],
            estimated_time_min=20,
        ),
        _problem(
            slug="longest-common-prefix",
            title="Longest Common Prefix",
            difficulty="easy",
            statement="Find the longest common prefix string amongst an array of strings. Return empty string if none.",
            entry_function="longest_common_prefix",
            examples=[
                ({"strs": ["flower", "flow", "flight"]}, "fl", "common fl"),
                ({"strs": ["dog", "racecar", "car"]}, "", "no common"),
            ],
            constraints_text="1 <= strs.length <= 200",
            skill_tags=["strings"],
            estimated_time_min=20,
        ),
        _problem(
            slug="valid-palindrome",
            title="Valid Palindrome",
            difficulty="easy",
            statement="Return true if s is a palindrome after converting to lowercase and removing non-alphanumeric characters.",
            entry_function="is_palindrome",
            examples=[
                ({"s": "A man, a plan, a canal: Panama"}, True, "reads same"),
                ({"s": "race a car"}, False, "not palindrome"),
            ],
            constraints_text="Consider only alphanumeric characters",
            skill_tags=["two pointers", "strings"],
            estimated_time_min=20,
        ),
        _problem(
            slug="ransom-note",
            title="Ransom Note",
            difficulty="easy",
            statement="Return true if ransomNote can be constructed from magazine letters (each letter used once).",
            entry_function="can_construct",
            examples=[
                ({"ransomNote": "a", "magazine": "b"}, False, "missing a"),
                ({"ransomNote": "aa", "magazine": "aab"}, True, "enough letters"),
            ],
            constraints_text="Lowercase English letters only",
            skill_tags=["hashing", "strings"],
            estimated_time_min=15,
        ),
        _problem(
            slug="isomorphic-strings",
            title="Isomorphic Strings",
            difficulty="easy",
            statement="Return true if s and t are isomorphic (characters map one-to-one).",
            entry_function="is_isomorphic",
            examples=[
                ({"s": "egg", "t": "add"}, True, "e->a g->d"),
                ({"s": "foo", "t": "bar"}, False, "o cannot map to two chars"),
            ],
            constraints_text="s.length == t.length",
            skill_tags=["hashing", "strings"],
            estimated_time_min=20,
        ),
        _problem(
            slug="word-pattern",
            title="Word Pattern",
            difficulty="easy",
            statement="Return true if pattern follows the same bijection with words in s (space-separated).",
            entry_function="word_pattern",
            examples=[
                ({"pattern": "abba", "s": "dog cat cat dog"}, True, "matches"),
                ({"pattern": "abba", "s": "dog cat cat fish"}, False, "mismatch"),
            ],
            constraints_text="pattern and words must biject",
            skill_tags=["hashing", "strings"],
            estimated_time_min=20,
        ),
    ]

    # ── Two pointers / sliding window ─────────────────────────────────────
    problems += [
        _problem(
            slug="max-sum-subarray-size-k",
            title="Maximum Sum Subarray of Size K",
            difficulty="medium",
            statement="Given an array of integers and k, return the maximum sum of any contiguous subarray of length k.",
            entry_function="max_sum_subarray",
            examples=[
                ({"nums": [1, 2, -3, 4, 5, 6], "k": 3}, 15, "[4,5,6]"),
                ({"nums": [-1, 2, 3, -4, 5], "k": 3}, 4, "[2,3,-4] sum=1? wait — [2,3,-4]=1, [-4,5]? k=3 → [2,3,-4]=1, [3,-4,5]=4"),
            ],
            constraints_text="1 <= k <= nums.length",
            skill_tags=["sliding window", "arrays"],
            estimated_time_min=25,
        ),
        _problem(
            slug="longest-ones-with-flips",
            title="Max Consecutive Ones With Flips",
            difficulty="medium",
            statement="Given a binary array and k, return the maximum number of consecutive 1s if you can flip at most k zeroes.",
            entry_function="longest_ones",
            examples=[
                ({"nums": [1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 0], "k": 2}, 6, "flip two zeros"),
                ({"nums": [0, 0, 1, 1, 0, 0, 1, 1, 1, 0, 1, 1, 0, 0, 0, 1, 1, 1, 1], "k": 3}, 10, "window of 10"),
            ],
            constraints_text="0 <= k <= nums.length",
            skill_tags=["sliding window", "arrays"],
            estimated_time_min=30,
        ),
        _problem(
            slug="container-with-most-water",
            title="Container With Most Water",
            difficulty="medium",
            statement="height[i] is a vertical line. Choose two lines to form a container with the x-axis that holds the most water. Return the max area.",
            entry_function="max_area",
            examples=[
                ({"height": [1, 8, 6, 2, 5, 4, 8, 3, 7]}, 49, "indices 1 and 8"),
                ({"height": [1, 1]}, 1, "only pair"),
            ],
            constraints_text="2 <= height.length <= 10^5",
            skill_tags=["two pointers", "arrays"],
            estimated_time_min=25,
        ),
        _problem(
            slug="three-sum-closest",
            title="3Sum Closest",
            difficulty="medium",
            statement="Find three integers in nums such that the sum is closest to target. Return that sum.",
            entry_function="three_sum_closest",
            examples=[
                ({"nums": [-1, 2, 1, -4], "target": 1}, 2, "-1+2+1=2"),
                ({"nums": [0, 0, 0], "target": 1}, 0, "only sum"),
            ],
            constraints_text="3 <= nums.length <= 500",
            skill_tags=["two pointers", "sorting"],
            estimated_time_min=30,
        ),
        _problem(
            slug="sort-colors",
            title="Sort Colors",
            difficulty="medium",
            statement="nums contains only 0, 1, 2. Sort them in-place conceptually and return the sorted array.",
            entry_function="sort_colors",
            examples=[
                ({"nums": [2, 0, 2, 1, 1, 0]}, [0, 0, 1, 1, 2, 2], "dutch flag"),
                ({"nums": [2, 0, 1]}, [0, 1, 2], "sorted"),
            ],
            constraints_text="Only values 0, 1, 2",
            skill_tags=["two pointers", "arrays"],
            estimated_time_min=25,
        ),
        _problem(
            slug="product-except-self",
            title="Product of Array Except Self",
            difficulty="medium",
            statement="Return an array answer where answer[i] equals the product of all elements of nums except nums[i]. Do not use division.",
            entry_function="product_except_self",
            examples=[
                ({"nums": [1, 2, 3, 4]}, [24, 12, 8, 6], "prefix*suffix"),
                ({"nums": [-1, 1, 0, -3, 3]}, [0, 0, 9, 0, 0], "zero handling"),
            ],
            constraints_text="2 <= nums.length <= 10^5",
            skill_tags=["prefix", "arrays"],
            estimated_time_min=30,
        ),
    ]

    # Fix max-sum example explanation (second example already has correct output 4)
    for p in problems:
        if p["slug"] == "max-sum-subarray-size-k":
            p["examples"][1]["explanation"] = "[3,-4,5] sums to 4"

    # ── Stack / queue / intervals ──────────────────────────────────────────
    problems += [
        _problem(
            slug="valid-parentheses",
            title="Valid Parentheses",
            difficulty="easy",
            statement="Given a string s containing just the characters '()[]{}', determine if the input string is valid.",
            entry_function="is_valid",
            examples=[
                ({"s": "()[]{}"}, True, "all match"),
                ({"s": "(]"}, False, "mismatch"),
            ],
            constraints_text="1 <= s.length <= 10^4",
            skill_tags=["stack", "strings"],
            estimated_time_min=20,
        ),
        _problem(
            slug="min-stack-top",
            title="Evaluate Min After Operations",
            difficulty="medium",
            statement="Process operations on a stack. ops is a list of strings: integers push, 'D' push 2*top, 'C' pop, '+' push sum of top two. Return the sum of all scores on the stack at the end.",
            entry_function="cal_points",
            examples=[
                ({"ops": ["5", "2", "C", "D", "+"]}, 30, "5+10+15"),
                ({"ops": ["5", "-2", "4", "C", "D", "9", "+", "+"]}, 27, "classic"),
            ],
            constraints_text="Follow baseball-game rules",
            skill_tags=["stack"],
            estimated_time_min=25,
        ),
        _problem(
            slug="daily-temperatures",
            title="Daily Temperatures",
            difficulty="medium",
            statement="For each day, return how many days you wait until a warmer temperature. If none, 0.",
            entry_function="daily_temperatures",
            examples=[
                (
                    {"temperatures": [73, 74, 75, 71, 69, 72, 76, 73]},
                    [1, 1, 4, 2, 1, 1, 0, 0],
                    "monotonic stack",
                ),
                ({"temperatures": [30, 40, 50, 60]}, [1, 1, 1, 0], "increasing"),
            ],
            constraints_text="1 <= temperatures.length <= 10^5",
            skill_tags=["stack", "arrays"],
            estimated_time_min=30,
        ),
        _problem(
            slug="merge-intervals",
            title="Merge Intervals",
            difficulty="medium",
            statement="Merge all overlapping intervals and return an array of the non-overlapping intervals.",
            entry_function="merge",
            examples=[
                (
                    {"intervals": [[1, 3], [2, 6], [8, 10], [15, 18]]},
                    [[1, 6], [8, 10], [15, 18]],
                    "merge 1-3 and 2-6",
                ),
                ({"intervals": [[1, 4], [4, 5]]}, [[1, 5]], "touching merges"),
            ],
            constraints_text="intervals[i] = [start, end]",
            skill_tags=["intervals", "sorting"],
            estimated_time_min=25,
        ),
        _problem(
            slug="meeting-rooms",
            title="Can Attend Meetings",
            difficulty="easy",
            statement="Given meeting time intervals, return true if a person can attend all meetings (no overlaps).",
            entry_function="can_attend",
            examples=[
                ({"intervals": [[0, 30], [5, 10], [15, 20]]}, False, "overlap"),
                ({"intervals": [[7, 10], [2, 4]]}, True, "no overlap"),
            ],
            constraints_text="End exclusive for overlap checks: [0,10] and [10,20] OK",
            skill_tags=["intervals", "sorting"],
            estimated_time_min=20,
        ),
        _problem(
            slug="insert-interval",
            title="Insert Interval",
            difficulty="medium",
            statement="Insert newInterval into a sorted non-overlapping interval list and merge if necessary. Return the new list.",
            entry_function="insert",
            examples=[
                (
                    {"intervals": [[1, 3], [6, 9]], "newInterval": [2, 5]},
                    [[1, 5], [6, 9]],
                    "merge into first",
                ),
                (
                    {
                        "intervals": [[1, 2], [3, 5], [6, 7], [8, 10], [12, 16]],
                        "newInterval": [4, 8],
                    },
                    [[1, 2], [3, 10], [12, 16]],
                    "merge middle",
                ),
            ],
            constraints_text="intervals sorted by start",
            skill_tags=["intervals"],
            estimated_time_min=30,
        ),
    ]

    # ── Binary search / math ──────────────────────────────────────────────
    problems += [
        _problem(
            slug="binary-search",
            title="Binary Search",
            difficulty="easy",
            statement="Given a sorted array of distinct integers and a target, return its index or -1.",
            entry_function="search",
            examples=[
                ({"nums": [-1, 0, 3, 5, 9, 12], "target": 9}, 4, "found"),
                ({"nums": [-1, 0, 3, 5, 9, 12], "target": 2}, -1, "missing"),
            ],
            constraints_text="Array is sorted ascending",
            skill_tags=["binary search"],
            estimated_time_min=15,
        ),
        _problem(
            slug="search-insert-position",
            title="Search Insert Position",
            difficulty="easy",
            statement="Return the index if target is found; otherwise the index where it would be inserted in order.",
            entry_function="search_insert",
            examples=[
                ({"nums": [1, 3, 5, 6], "target": 5}, 2, "found"),
                ({"nums": [1, 3, 5, 6], "target": 2}, 1, "insert at 1"),
            ],
            constraints_text="Distinct sorted nums",
            skill_tags=["binary search"],
            estimated_time_min=15,
        ),
        _problem(
            slug="sqrt-integer",
            title="Sqrt(x)",
            difficulty="easy",
            statement="Given a non-negative integer x, return the square root of x rounded down to the nearest integer.",
            entry_function="my_sqrt",
            examples=[
                ({"x": 4}, 2, "exact"),
                ({"x": 8}, 2, "floor sqrt"),
            ],
            constraints_text="0 <= x <= 2^31 - 1",
            skill_tags=["binary search", "math"],
            estimated_time_min=20,
        ),
        _problem(
            slug="peak-index-mountain",
            title="Peak Index in a Mountain Array",
            difficulty="easy",
            statement="arr is a mountain array. Return the peak index.",
            entry_function="peak_index",
            examples=[
                ({"arr": [0, 1, 0]}, 1, "peak at 1"),
                ({"arr": [0, 2, 1, 0]}, 1, "peak at 1"),
            ],
            constraints_text="Strictly increases then decreases",
            skill_tags=["binary search"],
            estimated_time_min=20,
        ),
        _problem(
            slug="koko-eating-bananas",
            title="Koko Eating Bananas",
            difficulty="medium",
            statement="Koko can eat piles of bananas. Return the minimum eating speed k to finish all piles within h hours.",
            entry_function="min_eating_speed",
            examples=[
                ({"piles": [3, 6, 7, 11], "h": 8}, 4, "speed 4"),
                ({"piles": [30, 11, 23, 4, 20], "h": 5}, 30, "speed 30"),
            ],
            constraints_text="h >= piles.length",
            skill_tags=["binary search", "greedy"],
            estimated_time_min=30,
        ),
        _problem(
            slug="ship-packages",
            title="Capacity To Ship Packages",
            difficulty="medium",
            statement="Packages must be shipped in order within days days. Return the least weight capacity of the ship.",
            entry_function="ship_within_days",
            examples=[
                ({"weights": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10], "days": 5}, 15, "capacity 15"),
                ({"weights": [3, 2, 2, 4, 1, 4], "days": 3}, 6, "capacity 6"),
            ],
            constraints_text="Packages stay in given order",
            skill_tags=["binary search"],
            estimated_time_min=30,
        ),
    ]

    # ── Linked-list style (array simulation) / matrices ───────────────────
    problems += [
        _problem(
            slug="reverse-linked-list-array",
            title="Reverse List",
            difficulty="easy",
            statement="Given a list of values representing a linked list, return the values in reversed order.",
            entry_function="reverse_list",
            examples=[
                ({"values": [1, 2, 3, 4, 5]}, [5, 4, 3, 2, 1], "reversed"),
                ({"values": [1, 2]}, [2, 1], "two nodes"),
            ],
            constraints_text="0 <= values.length <= 5000",
            skill_tags=["arrays", "linked list"],
            estimated_time_min=15,
        ),
        _problem(
            slug="middle-of-list",
            title="Middle of the List",
            difficulty="easy",
            statement="Return the second half of the list starting from the middle element (for even length, the second middle).",
            entry_function="middle_slice",
            examples=[
                ({"values": [1, 2, 3, 4, 5]}, [3, 4, 5], "middle at 3"),
                ({"values": [1, 2, 3, 4, 5, 6]}, [4, 5, 6], "second middle"),
            ],
            constraints_text="Use index math or two pointers",
            skill_tags=["two pointers", "arrays"],
            estimated_time_min=15,
        ),
        _problem(
            slug="matrix-diagonal-sum",
            title="Matrix Diagonal Sum",
            difficulty="easy",
            statement="Given a square matrix, return the sum of the matrix diagonals. The primary and secondary diagonals; center counted once if n odd.",
            entry_function="diagonal_sum",
            examples=[
                ({"mat": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]}, 25, "1+5+9+3+7"),
                ({"mat": [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]]}, 8, "diagonals"),
            ],
            constraints_text="n == mat.length == mat[i].length",
            skill_tags=["matrix"],
            estimated_time_min=20,
        ),
        _problem(
            slug="reshape-matrix",
            title="Reshape the Matrix",
            difficulty="easy",
            statement="Reshape matrix into r rows and c columns in row-major order. If impossible, return the original matrix.",
            entry_function="matrix_reshape",
            examples=[
                ({"mat": [[1, 2], [3, 4]], "r": 1, "c": 4}, [[1, 2, 3, 4]], "reshape"),
                ({"mat": [[1, 2], [3, 4]], "r": 2, "c": 4}, [[1, 2], [3, 4]], "impossible"),
            ],
            constraints_text="If r*c != m*n return original",
            skill_tags=["matrix"],
            estimated_time_min=20,
        ),
        _problem(
            slug="spiral-order",
            title="Spiral Matrix",
            difficulty="medium",
            statement="Return all elements of the matrix in spiral order.",
            entry_function="spiral_order",
            examples=[
                (
                    {"matrix": [[1, 2, 3], [4, 5, 6], [7, 8, 9]]},
                    [1, 2, 3, 6, 9, 8, 7, 4, 5],
                    "clockwise spiral",
                ),
                (
                    {"matrix": [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]]},
                    [1, 2, 3, 4, 8, 12, 11, 10, 9, 5, 6, 7],
                    "3x4 spiral",
                ),
            ],
            constraints_text="1 <= rows, cols <= 10",
            skill_tags=["matrix", "simulation"],
            estimated_time_min=30,
        ),
        _problem(
            slug="set-matrix-zeroes-result",
            title="Set Matrix Zeroes Result",
            difficulty="medium",
            statement="If an element is 0, set its entire row and column to 0. Return the resulting matrix.",
            entry_function="set_zeroes",
            examples=[
                (
                    {"matrix": [[1, 1, 1], [1, 0, 1], [1, 1, 1]]},
                    [[1, 0, 1], [0, 0, 0], [1, 0, 1]],
                    "row1 and col1 zeroed",
                ),
                (
                    {"matrix": [[0, 1, 2, 0], [3, 4, 5, 2], [1, 3, 1, 5]]},
                    [[0, 0, 0, 0], [0, 4, 5, 0], [0, 3, 1, 0]],
                    "two zeros",
                ),
            ],
            constraints_text="In-place conceptually; return final matrix",
            skill_tags=["matrix"],
            estimated_time_min=30,
        ),
    ]

    # ── Graphs / trees (array / edge-list) ─────────────────────────────────
    problems += [
        _problem(
            slug="number-of-islands",
            title="Number of Islands",
            difficulty="medium",
            statement="grid is a 2D map of '1' (land) and '0' (water). Return the number of islands.",
            entry_function="num_islands",
            examples=[
                (
                    {
                        "grid": [
                            ["1", "1", "1", "1", "0"],
                            ["1", "1", "0", "1", "0"],
                            ["1", "1", "0", "0", "0"],
                            ["0", "0", "0", "0", "0"],
                        ]
                    },
                    1,
                    "one island",
                ),
                (
                    {
                        "grid": [
                            ["1", "1", "0", "0", "0"],
                            ["1", "1", "0", "0", "0"],
                            ["0", "0", "1", "0", "0"],
                            ["0", "0", "0", "1", "1"],
                        ]
                    },
                    3,
                    "three islands",
                ),
            ],
            constraints_text="4-directional adjacency",
            skill_tags=["dfs", "bfs", "matrix"],
            estimated_time_min=30,
        ),
        _problem(
            slug="flood-fill",
            title="Flood Fill",
            difficulty="easy",
            statement="Perform a flood fill on image starting at (sr, sc) with color. Return the modified image.",
            entry_function="flood_fill",
            examples=[
                (
                    {"image": [[1, 1, 1], [1, 1, 0], [1, 0, 1]], "sr": 1, "sc": 1, "color": 2},
                    [[2, 2, 2], [2, 2, 0], [2, 0, 1]],
                    "fill connected 1s",
                ),
                (
                    {"image": [[0, 0, 0], [0, 0, 0]], "sr": 0, "sc": 0, "color": 0},
                    [[0, 0, 0], [0, 0, 0]],
                    "same color no-op",
                ),
            ],
            constraints_text="4-directional fill",
            skill_tags=["dfs", "bfs", "matrix"],
            estimated_time_min=25,
        ),
        _problem(
            slug="clone-graph-count",
            title="Connected Components Count",
            difficulty="medium",
            statement="n nodes labeled 0..n-1 and undirected edges. Return the number of connected components.",
            entry_function="count_components",
            examples=[
                ({"n": 5, "edges": [[0, 1], [1, 2], [3, 4]]}, 2, "two components"),
                ({"n": 5, "edges": [[0, 1], [1, 2], [2, 3], [3, 4]]}, 1, "one component"),
            ],
            constraints_text="Undirected edges",
            skill_tags=["union find", "dfs"],
            estimated_time_min=25,
        ),
        _problem(
            slug="valid-path-graph",
            title="Find if Path Exists",
            difficulty="easy",
            statement="Return true if there is a path from source to destination in an undirected graph with n nodes.",
            entry_function="valid_path",
            examples=[
                (
                    {"n": 3, "edges": [[0, 1], [1, 2], [2, 0]], "source": 0, "destination": 2},
                    True,
                    "connected",
                ),
                (
                    {"n": 6, "edges": [[0, 1], [0, 2], [3, 5], [5, 4], [4, 3]], "source": 0, "destination": 5},
                    False,
                    "disconnected",
                ),
            ],
            constraints_text="Undirected graph",
            skill_tags=["bfs", "dfs"],
            estimated_time_min=25,
        ),
        _problem(
            slug="max-depth-tree-array",
            title="Maximum Depth of Binary Tree",
            difficulty="easy",
            statement="Tree is given as level-order array with nulls as null. Return its maximum depth.",
            entry_function="max_depth",
            examples=[
                ({"values": [3, 9, 20, None, None, 15, 7]}, 3, "depth 3"),
                ({"values": [1, None, 2]}, 2, "depth 2"),
            ],
            constraints_text="null means missing child",
            skill_tags=["trees", "dfs"],
            estimated_time_min=25,
        ),
        _problem(
            slug="same-tree-array",
            title="Same Tree",
            difficulty="easy",
            statement="Given two trees as level-order arrays, return true if they are structurally identical with same values.",
            entry_function="is_same_tree",
            examples=[
                ({"p": [1, 2, 3], "q": [1, 2, 3]}, True, "identical"),
                ({"p": [1, 2], "q": [1, None, 2]}, False, "structure differs"),
            ],
            constraints_text="null marks missing nodes",
            skill_tags=["trees"],
            estimated_time_min=20,
        ),
        _problem(
            slug="invert-tree-array",
            title="Invert Binary Tree",
            difficulty="easy",
            statement="Invert a binary tree given as level-order array (nulls allowed). Return the inverted tree in level-order (trim trailing nulls).",
            entry_function="invert_tree",
            examples=[
                ({"values": [4, 2, 7, 1, 3, 6, 9]}, [4, 7, 2, 9, 6, 3, 1], "mirrored"),
                ({"values": [2, 1, 3]}, [2, 3, 1], "swap children"),
            ],
            constraints_text="Return compact level-order",
            skill_tags=["trees", "dfs"],
            estimated_time_min=25,
        ),
    ]

    # ── Dynamic programming / greedy extras ───────────────────────────────
    problems += [
        _problem(
            slug="climbing-stairs",
            title="Climbing Stairs",
            difficulty="easy",
            statement="You can climb 1 or 2 steps. Return how many distinct ways to climb n steps.",
            entry_function="climb_stairs",
            examples=[
                ({"n": 2}, 2, "1+1 or 2"),
                ({"n": 3}, 3, "three ways"),
            ],
            constraints_text="1 <= n <= 45",
            skill_tags=["dynamic programming"],
            estimated_time_min=15,
        ),
        _problem(
            slug="house-robber",
            title="House Robber",
            difficulty="medium",
            statement="Rob houses on a street; cannot rob adjacent houses. Return max amount.",
            entry_function="rob",
            examples=[
                ({"nums": [1, 2, 3, 1]}, 4, "1+3"),
                ({"nums": [2, 7, 9, 3, 1]}, 12, "2+9+1"),
            ],
            constraints_text="0 <= nums[i]",
            skill_tags=["dynamic programming"],
            estimated_time_min=25,
        ),
        _problem(
            slug="coin-change-min",
            title="Coin Change",
            difficulty="medium",
            statement="Return the fewest number of coins to make amount. If impossible return -1.",
            entry_function="coin_change",
            examples=[
                ({"coins": [1, 2, 5], "amount": 11}, 3, "5+5+1"),
                ({"coins": [2], "amount": 3}, -1, "impossible"),
            ],
            constraints_text="Unlimited coins of each type",
            skill_tags=["dynamic programming"],
            estimated_time_min=30,
        ),
        _problem(
            slug="longest-increasing-subseq-len",
            title="Longest Increasing Subsequence Length",
            difficulty="medium",
            statement="Return the length of the longest strictly increasing subsequence.",
            entry_function="length_of_lis",
            examples=[
                ({"nums": [10, 9, 2, 5, 3, 7, 101, 18]}, 4, "2,3,7,101"),
                ({"nums": [0, 1, 0, 3, 2, 3]}, 4, "0,1,2,3"),
            ],
            constraints_text="1 <= nums.length <= 2500",
            skill_tags=["dynamic programming", "binary search"],
            estimated_time_min=35,
        ),
        _problem(
            slug="unique-paths",
            title="Unique Paths",
            difficulty="medium",
            statement="A robot on an m x n grid starts at top-left and can move right or down. Return number of unique paths to bottom-right.",
            entry_function="unique_paths",
            examples=[
                ({"m": 3, "n": 7}, 28, "classic"),
                ({"m": 3, "n": 2}, 3, "three paths"),
            ],
            constraints_text="1 <= m, n <= 100",
            skill_tags=["dynamic programming"],
            estimated_time_min=25,
        ),
        _problem(
            slug="jump-game",
            title="Jump Game",
            difficulty="medium",
            statement="Each element is max jump length from that index. Return true if you can reach the last index.",
            entry_function="can_jump",
            examples=[
                ({"nums": [2, 3, 1, 1, 4]}, True, "reachable"),
                ({"nums": [3, 2, 1, 0, 4]}, False, "stuck at 0"),
            ],
            constraints_text="1 <= nums.length <= 10^4",
            skill_tags=["greedy"],
            estimated_time_min=25,
        ),
        _problem(
            slug="gas-station",
            title="Gas Station Circuit",
            difficulty="medium",
            statement="gas[i] and cost[i] at stations on a circuit. Return the starting index to complete the circuit, or -1.",
            entry_function="can_complete_circuit",
            examples=[
                ({"gas": [1, 2, 3, 4, 5], "cost": [3, 4, 5, 1, 2]}, 3, "start at 3"),
                ({"gas": [2, 3, 4], "cost": [3, 4, 3]}, -1, "impossible"),
            ],
            constraints_text="Unique answer if exists",
            skill_tags=["greedy"],
            estimated_time_min=30,
        ),
    ]

    # ── Extra variety to reach ~90 ────────────────────────────────────────
    extras = [
        (
            "max-consecutive-ones",
            "Max Consecutive Ones",
            "easy",
            "Return the maximum number of consecutive 1s in a binary array.",
            "find_max_consecutive_ones",
            [({"nums": [1, 1, 0, 1, 1, 1]}, 3, "three ones"), ({"nums": [1, 0, 1, 1, 0, 1]}, 2, "two ones")],
            "Binary array",
            ["arrays"],
            15,
        ),
        (
            "find-disappeared-numbers",
            "Find All Numbers Disappeared",
            "easy",
            "nums contains n integers where each is in [1, n]. Return all numbers in [1, n] that do not appear.",
            "find_disappeared",
            [
                ({"nums": [4, 3, 2, 7, 8, 2, 3, 1]}, [5, 6], "missing"),
                ({"nums": [1, 1]}, [2], "missing 2"),
            ],
            "Return sorted ascending",
            ["arrays", "hash set"],
            20,
        ),
        (
            "third-max-number",
            "Third Maximum Number",
            "easy",
            "Return the third distinct maximum number in nums. If fewer than three distinct, return the maximum.",
            "third_max",
            [({"nums": [3, 2, 1]}, 1, "third max"), ({"nums": [1, 2]}, 2, "only two → max")],
            "Distinct values",
            ["arrays"],
            20,
        ),
        (
            "assign-cookies",
            "Assign Cookies",
            "easy",
            "g[i] is greed factor of child i, s[j] is cookie size. Each child gets at most one cookie. Return max content children.",
            "find_content_children",
            [
                ({"g": [1, 2, 3], "s": [1, 1]}, 1, "one child"),
                ({"g": [1, 2], "s": [1, 2, 3]}, 2, "both"),
            ],
            "Greedy assign smallest sufficient cookie",
            ["greedy", "sorting"],
            20,
        ),
        (
            "lemonade-change",
            "Lemonade Change",
            "easy",
            "Each lemonade costs 5. Customers pay with 5, 10, or 20. Return true if you can provide correct change to every customer in order.",
            "lemonade_change",
            [
                ({"bills": [5, 5, 5, 10, 20]}, True, "can change"),
                ({"bills": [5, 5, 10, 10, 20]}, False, "cannot"),
            ],
            "Start with no money",
            ["greedy"],
            20,
        ),
        (
            "happy-number",
            "Happy Number",
            "easy",
            "A happy number repeatedly replaces the number by the sum of the squares of its digits until 1 (happy) or a cycle (unhappy). Return true if n is happy.",
            "is_happy",
            [({"n": 19}, True, "happy"), ({"n": 2}, False, "cycle")],
            "Detect cycles",
            ["hash set", "math"],
            20,
        ),
        (
            "add-digits",
            "Add Digits",
            "easy",
            "Repeatedly add all digits of num until the result has only one digit. Return it.",
            "add_digits",
            [({"num": 38}, 2, "3+8=11 → 2"), ({"num": 0}, 0, "zero")],
            "Digital root",
            ["math"],
            15,
        ),
        (
            "ugly-number",
            "Ugly Number",
            "easy",
            "Ugly numbers are positive numbers whose prime factors only include 2, 3, and/or 5. Return true if n is ugly.",
            "is_ugly",
            [({"n": 6}, True, "2*3"), ({"n": 14}, False, "has 7")],
            "n > 0 required; 1 is ugly",
            ["math"],
            15,
        ),
        (
            "power-of-two",
            "Power of Two",
            "easy",
            "Return true if n is a power of two.",
            "is_power_of_two",
            [({"n": 1}, True, "2^0"), ({"n": 16}, True, "2^4"), ({"n": 3}, False, "not")],
            "Handle n <= 0 as false",
            ["bit manipulation"],
            15,
        ),
        (
            "counting-bits",
            "Counting Bits",
            "easy",
            "Given n, return an array ans of length n+1 where ans[i] is the number of 1s in the binary representation of i.",
            "count_bits",
            [({"n": 2}, [0, 1, 1], "0,1,2"), ({"n": 5}, [0, 1, 1, 2, 1, 2], "0..5")],
            "0-indexed answers",
            ["bit manipulation", "dp"],
            20,
        ),
        (
            "hamming-distance",
            "Hamming Distance",
            "easy",
            "The Hamming distance between two integers is the number of positions at which the bits differ. Return it for x and y.",
            "hamming_distance",
            [({"x": 1, "y": 4}, 2, "differ two bits"), ({"x": 3, "y": 1}, 1, "one bit")],
            "Non-negative integers",
            ["bit manipulation"],
            15,
        ),
        (
            "reverse-integer-digits",
            "Reverse Integer Digits",
            "medium",
            "Reverse digits of a 32-bit signed integer x. If reversing causes overflow outside [-2^31, 2^31-1], return 0.",
            "reverse",
            [({"x": 123}, 321, "reversed"), ({"x": -123}, -321, "keep sign"), ({"x": 120}, 21, "drop trailing zero")],
            "Overflow → 0",
            ["math"],
            25,
        ),
        (
            "roman-to-integer",
            "Roman to Integer",
            "easy",
            "Convert a Roman numeral string to an integer.",
            "roman_to_int",
            [({"s": "III"}, 3, "3"), ({"s": "LVIII"}, 58, "L+V+III"), ({"s": "MCMXCIV"}, 1994, "1994")],
            "Valid Roman numerals",
            ["strings", "hash map"],
            20,
        ),
        (
            "longest-palindrome-length",
            "Longest Palindrome Length",
            "easy",
            "Given a string s of lowercase/uppercase letters, return the length of the longest palindrome that can be built with those letters.",
            "longest_palindrome",
            [({"s": "abccccdd"}, 7, "dccaccd"), ({"s": "a"}, 1, "single")],
            "Case sensitive",
            ["hashing", "greedy"],
            20,
        ),
        (
            "group-anagrams-sorted-keys",
            "Group Anagram Keys",
            "medium",
            "Group anagrams. Return the groups as lists of strings, each group sorted lexicographically, and groups ordered by the sorted key of the group.",
            "group_anagrams",
            [
                (
                    {"strs": ["eat", "tea", "tan", "ate", "nat", "bat"]},
                    [["ate", "eat", "tea"], ["bat"], ["nat", "tan"]],
                    "three groups",
                ),
                ({"strs": [""]}, [[""]], "empty string"),
            ],
            "Deterministic ordering required for grading",
            ["hashing", "strings"],
            30,
        ),
        (
            "top-k-frequent",
            "Top K Frequent Elements",
            "medium",
            "Return the k most frequent elements. Order the result by frequency descending, then by value ascending for ties.",
            "top_k_frequent",
            [
                ({"nums": [1, 1, 1, 2, 2, 3], "k": 2}, [1, 2], "1 then 2"),
                ({"nums": [1], "k": 1}, [1], "only one"),
            ],
            "Deterministic tie-break by value",
            ["heap", "hashing"],
            30,
        ),
        (
            "kth-largest",
            "Kth Largest Element",
            "medium",
            "Return the kth largest element in the array (1-indexed from largest).",
            "find_kth_largest",
            [({"nums": [3, 2, 1, 5, 6, 4], "k": 2}, 5, "2nd largest"), ({"nums": [3, 2, 3, 1, 2, 4, 5, 5, 6], "k": 4}, 4, "4th")],
            "Duplicates allowed",
            ["sorting", "heap"],
            25,
        ),
        (
            "sort-array-parity",
            "Sort Array By Parity",
            "easy",
            "Return an array with all even integers followed by all odd integers. Relative order within even/odd may follow stable partition: evens keep order, odds keep order.",
            "sort_array_by_parity",
            [
                ({"nums": [3, 1, 2, 4]}, [2, 4, 3, 1], "evens then odds"),
                ({"nums": [0]}, [0], "single"),
            ],
            "Stable partition",
            ["two pointers", "arrays"],
            15,
        ),
        (
            "rotate-array-right",
            "Rotate Array",
            "medium",
            "Rotate the array to the right by k steps. Return the rotated array.",
            "rotate",
            [
                ({"nums": [1, 2, 3, 4, 5, 6, 7], "k": 3}, [5, 6, 7, 1, 2, 3, 4], "k=3"),
                ({"nums": [-1, -100, 3, 99], "k": 2}, [3, 99, -1, -100], "k=2"),
            ],
            "k may be larger than length",
            ["arrays"],
            20,
        ),
        (
            "find-pivot-index",
            "Find Pivot Index",
            "easy",
            "Return the leftmost pivot index where sum of left equals sum of right. If none, -1.",
            "pivot_index",
            [
                ({"nums": [1, 7, 3, 6, 5, 6]}, 3, "pivot 3"),
                ({"nums": [1, 2, 3]}, -1, "none"),
            ],
            "Left of index 0 is 0",
            ["prefix", "arrays"],
            20,
        ),
        (
            "subarray-sum-equals-k-count",
            "Subarray Sum Equals K",
            "medium",
            "Return the total number of contiguous subarrays whose sum equals k.",
            "subarray_sum",
            [
                ({"nums": [1, 1, 1], "k": 2}, 2, "two subarrays"),
                ({"nums": [1, 2, 3], "k": 3}, 2, "[1,2] and [3]"),
            ],
            "Prefix sums + hashmap",
            ["prefix", "hash map"],
            30,
        ),
        (
            "longest-substring-no-repeat",
            "Longest Substring Without Repeating",
            "medium",
            "Return the length of the longest substring without repeating characters.",
            "length_of_longest_substring",
            [
                ({"s": "abcabcbb"}, 3, "abc"),
                ({"s": "bbbbb"}, 1, "b"),
                ({"s": "pwwkew"}, 3, "wke"),
            ],
            "Sliding window",
            ["sliding window", "hashing"],
            25,
        ),
        (
            "min-window-cover-exists",
            "Minimum Window Substring Length",
            "medium",
            "Return the length of the minimum window substring of s that covers all characters in t (including duplicates). If none, return 0.",
            "min_window_length",
            [
                ({"s": "ADOBECODEBANC", "t": "ABC"}, 4, "BANC"),
                ({"s": "a", "t": "a"}, 1, "exact"),
                ({"s": "a", "t": "aa"}, 0, "impossible"),
            ],
            "Case sensitive",
            ["sliding window", "hashing"],
            35,
        ),
        (
            "decode-string",
            "Decode String",
            "medium",
            "Decode an encoded string following the pattern k[encoded_string].",
            "decode_string",
            [
                ({"s": "3[a]2[bc]"}, "aaabcbc", "decoded"),
                ({"s": "3[a2[c]]"}, "accaccacc", "nested"),
            ],
            "Stack-based decode",
            ["stack", "strings"],
            30,
        ),
        (
            "simplify-path",
            "Simplify Unix Path",
            "medium",
            "Simplify an absolute Unix path. Return the simplified canonical path.",
            "simplify_path",
            [
                ({"path": "/home/"}, "/home", "trim"),
                ({"path": "/../"}, "/", "root"),
                ({"path": "/home//foo/"}, "/home/foo", "collapse"),
            ],
            "Stack of directories",
            ["stack", "strings"],
            25,
        ),
        (
            "evaluate-rpn",
            "Evaluate Reverse Polish Notation",
            "medium",
            "Evaluate an RPN expression tokens and return the integer result. Division truncates toward zero.",
            "eval_rpn",
            [
                ({"tokens": ["2", "1", "+", "3", "*"]}, 9, "(2+1)*3"),
                ({"tokens": ["4", "13", "5", "/", "+"]}, 6, "4+(13/5)"),
            ],
            "Operators +, -, *, /",
            ["stack"],
            25,
        ),
        (
            "next-greater-element",
            "Next Greater Element I",
            "easy",
            "nums1 is a subset of nums2. For each value in nums1, find the next greater element in nums2 to its right; else -1. Return the answers for nums1.",
            "next_greater_element",
            [
                ({"nums1": [4, 1, 2], "nums2": [1, 3, 4, 2]}, [-1, 3, -1], "classic"),
                ({"nums1": [2, 4], "nums2": [1, 2, 3, 4]}, [3, -1], "2→3, 4 none"),
            ],
            "Monotonic stack",
            ["stack", "hash map"],
            25,
        ),
        (
            "backspace-compare",
            "Backspace String Compare",
            "easy",
            "Given two strings s and t, return true if they are equal when typed into empty text editors. '#' means backspace.",
            "backspace_compare",
            [
                ({"s": "ab#c", "t": "ad#c"}, True, "both ac"),
                ({"s": "a#c", "t": "b"}, False, "c vs b"),
            ],
            "Stack or two pointers",
            ["stack", "two pointers"],
            20,
        ),
        (
            "remove-outer-parentheses",
            "Remove Outermost Parentheses",
            "easy",
            "A valid parentheses string is primitive if it is nonempty and cannot be split into two nonempty valid strings. Remove the outermost parentheses of every primitive in the decomposition of s.",
            "remove_outer_parentheses",
            [
                ({"s": "(()())(())"}, "()()()", "removed outer"),
                ({"s": "()()"}, "", "both primitives empty inside"),
            ],
            "Valid parentheses input",
            ["stack", "strings"],
            20,
        ),
    ]

    # Fix the accidental walrus in squares tuple - I used title := which is wrong in a tuple
    # Let me rebuild extras carefully without that bug
    problems += [
        _problem(
            slug=e[0],
            title=e[1],
            difficulty=e[2],
            statement=e[3],
            entry_function=e[4],
            examples=e[5],
            constraints_text=e[6],
            skill_tags=e[7],
            estimated_time_min=e[8],
        )
        for e in extras
        if e[0] != "squares-sorted-array"
    ]

    # Re-add squares properly (was broken by walrus in tuple)
    problems.append(
        _problem(
            slug="squares-sorted-array",
            title="Squares of a Sorted Array",
            difficulty="easy",
            statement="Given a sorted integer array (non-decreasing), return an array of the squares of each number sorted in non-decreasing order.",
            entry_function="sorted_squares",
            examples=[
                ({"nums": [-4, -1, 0, 3, 10]}, [0, 1, 9, 16, 100], "sorted squares"),
                ({"nums": [-7, -3, 2, 3, 11]}, [4, 9, 9, 49, 121], "sorted"),
            ],
            constraints_text="Input already sorted",
            skill_tags=["two pointers"],
            estimated_time_min=20,
        )
    )

    # Deduplicate by slug and cap/pad toward 90
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in problems:
        if p["slug"] in seen:
            continue
        seen.add(p["slug"])
        unique.append(p)

    # Pad with parameterized k-sum window variants if under 90
    k = 2
    while len(unique) < 90:
        kk = 2 + (k % 6)
        slug = f"max-sum-window-{kk}-v{k}"
        if slug in seen:
            k += 1
            continue
        nums_a = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        nums_b = [5, -1, 2, 3, -2, 4, 1, 0, 6, -3]
        if len(nums_a) < kk or len(nums_b) < kk:
            k += 1
            continue
        sum_a = max(sum(nums_a[i : i + kk]) for i in range(len(nums_a) - kk + 1))
        sum_b = max(sum(nums_b[i : i + kk]) for i in range(len(nums_b) - kk + 1))
        unique.append(
            _problem(
                slug=slug,
                title=f"Maximum Sum of Window Size {kk}",
                difficulty="easy" if kk <= 3 else "medium",
                statement=(
                    f"Given an integer array nums, return the maximum sum of any "
                    f"contiguous subarray of length exactly {kk}."
                ),
                entry_function="max_sum_window",
                examples=[
                    ({"nums": nums_a}, sum_a, f"window {kk}"),
                    ({"nums": nums_b}, sum_b, f"window {kk}"),
                ],
                constraints_text=f"nums.length >= {kk}",
                skill_tags=["sliding window", "arrays"],
                estimated_time_min=20,
            )
        )
        seen.add(slug)
        k += 1

    return unique[:90]
