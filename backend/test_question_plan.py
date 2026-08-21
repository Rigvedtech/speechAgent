"""Unit tests for question count auto-adjust."""

from question_plan import resolve_question_plan


def test_exact_sum_unchanged():
    plan = resolve_question_plan(16, 4, 7, 5)
    assert plan.total == 16
    assert (plan.beginner, plan.intermediate, plan.hard) == (4, 7, 5)
    assert not plan.adjusted
    assert len(plan.difficulty_pattern) == 16
    assert plan.jd_count == 11
    assert plan.resume_count == 5


def test_scale_up_when_max_higher():
    plan = resolve_question_plan(18, 4, 7, 5)
    assert plan.total == 18
    assert plan.beginner + plan.intermediate + plan.hard == 18
    assert plan.adjusted
    assert plan.beginner >= 1 and plan.intermediate >= 1 and plan.hard >= 1


def test_scale_down_when_max_lower():
    plan = resolve_question_plan(15, 4, 7, 5)
    assert plan.total == 15
    assert plan.beginner + plan.intermediate + plan.hard == 15
    assert plan.adjusted


def test_default_15_matches_legacy():
    plan = resolve_question_plan(15, 5, 5, 5)
    assert (plan.beginner, plan.intermediate, plan.hard) == (5, 5, 5)
    assert plan.id_range("beginner") == (1, 5)
    assert plan.id_range("intermediate") == (6, 10)
    assert plan.id_range("hard") == (11, 15)


def test_zero_buckets_fill_defaults_then_scale():
    plan = resolve_question_plan(15, 0, 0, 0)
    assert plan.total == 15
    assert plan.beginner + plan.intermediate + plan.hard == 15
