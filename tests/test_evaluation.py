"""Direct tests for megaplan.evaluation module."""
from __future__ import annotations

from megaplan.evaluation import (
    build_evaluation,
    flag_weight,
    _is_over_budget,
    _is_all_flags_resolved,
    _is_low_weight_trending_down,
    _is_stagnant_with_unresolved,
    _is_stagnant_all_addressed,
    _is_first_iteration_with_flags,
    _has_recurring_critiques,
    _is_score_stagnating,
    _is_score_improving,
    _is_max_iterations_with_unresolved,
    compute_plan_delta_percent,
)


class TestFlagWeight:
    def test_security_flag_highest_weight(self) -> None:
        flag = {"category": "security", "concern": "SQL injection risk"}
        assert flag_weight(flag) == 3.0

    def test_correctness_flag(self) -> None:
        assert flag_weight({"category": "correctness", "concern": "logic error"}) == 2.0

    def test_completeness_flag(self) -> None:
        assert flag_weight({"category": "completeness", "concern": "missing feature"}) == 1.5

    def test_performance_flag(self) -> None:
        assert flag_weight({"category": "performance", "concern": "slow query"}) == 1.0

    def test_maintainability_flag(self) -> None:
        assert flag_weight({"category": "maintainability", "concern": "tangled code"}) == 0.75

    def test_other_flag(self) -> None:
        assert flag_weight({"category": "other", "concern": "misc"}) == 1.0

    def test_unknown_category_defaults_to_1(self) -> None:
        assert flag_weight({"category": "nonexistent", "concern": "something"}) == 1.0

    def test_missing_category_defaults_to_other(self) -> None:
        assert flag_weight({"concern": "no category"}) == 1.0

    def test_implementation_detail_signals_reduce_weight(self) -> None:
        """Flags with implementation-detail keywords get 0.5 weight."""
        for signal in ["column", "schema", "field", "as written", "pseudocode", "seed sql", "placeholder"]:
            flag = {"category": "correctness", "concern": f"The {signal} is wrong"}
            assert flag_weight(flag) == 0.5, f"Signal '{signal}' should reduce weight"

    def test_security_overrides_implementation_signal(self) -> None:
        """Security category takes priority over implementation-detail signals."""
        flag = {"category": "security", "concern": "the schema allows injection"}
        assert flag_weight(flag) == 3.0

    def test_empty_flag(self) -> None:
        assert flag_weight({}) == 1.0


class TestBuildEvaluation:
    """build_evaluation requires filesystem state; just verify it is importable and callable."""

    def test_is_callable(self) -> None:
        assert callable(build_evaluation)


# ---------------------------------------------------------------------------
# Decision-table predicate tests with explicit input/output pairs
# ---------------------------------------------------------------------------

class TestIsOverBudget:
    def test_over_budget(self) -> None:
        assert _is_over_budget(total_cost=30.0, budget=25.0) is True

    def test_under_budget(self) -> None:
        assert _is_over_budget(total_cost=10.0, budget=25.0) is False

    def test_exactly_at_budget(self) -> None:
        assert _is_over_budget(total_cost=25.0, budget=25.0) is False


class TestIsAllFlagsResolved:
    def test_all_resolved(self) -> None:
        assert _is_all_flags_resolved(significant_count=0, unresolved=[]) is True

    def test_significant_count_nonzero(self) -> None:
        assert _is_all_flags_resolved(significant_count=2, unresolved=[]) is False

    def test_unresolved_nonempty(self) -> None:
        assert _is_all_flags_resolved(significant_count=0, unresolved=[{"id": "FLAG-001"}]) is False

    def test_both_nonzero(self) -> None:
        assert _is_all_flags_resolved(significant_count=1, unresolved=[{"id": "FLAG-001"}]) is False


class TestIsLowWeightTrendingDown:
    def test_trending_down(self) -> None:
        assert _is_low_weight_trending_down(
            iteration=2, weighted_score=1.0, skip_threshold=2.0,
            weighted_history=[3.0],
        ) is True

    def test_first_iteration_returns_false(self) -> None:
        assert _is_low_weight_trending_down(
            iteration=1, weighted_score=1.0, skip_threshold=2.0,
            weighted_history=[3.0],
        ) is False

    def test_above_threshold_returns_false(self) -> None:
        assert _is_low_weight_trending_down(
            iteration=2, weighted_score=3.0, skip_threshold=2.0,
            weighted_history=[4.0],
        ) is False

    def test_not_improving_returns_false(self) -> None:
        assert _is_low_weight_trending_down(
            iteration=2, weighted_score=1.5, skip_threshold=2.0,
            weighted_history=[1.0],
        ) is False

    def test_empty_history_returns_false(self) -> None:
        assert _is_low_weight_trending_down(
            iteration=2, weighted_score=1.0, skip_threshold=2.0,
            weighted_history=[],
        ) is False


class TestIsStagnantWithUnresolved:
    def test_stagnant_with_flags(self) -> None:
        assert _is_stagnant_with_unresolved(plan_delta=2.0, unresolved=[{"id": "F"}]) is True

    def test_stagnant_no_flags(self) -> None:
        assert _is_stagnant_with_unresolved(plan_delta=2.0, unresolved=[]) is False

    def test_large_delta(self) -> None:
        assert _is_stagnant_with_unresolved(plan_delta=10.0, unresolved=[{"id": "F"}]) is False

    def test_none_delta(self) -> None:
        assert _is_stagnant_with_unresolved(plan_delta=None, unresolved=[{"id": "F"}]) is False


class TestIsStagnantAllAddressed:
    def test_stagnant_addressed(self) -> None:
        assert _is_stagnant_all_addressed(plan_delta=3.0, unresolved=[]) is True

    def test_stagnant_with_unresolved(self) -> None:
        assert _is_stagnant_all_addressed(plan_delta=3.0, unresolved=[{"id": "F"}]) is False

    def test_large_delta(self) -> None:
        assert _is_stagnant_all_addressed(plan_delta=10.0, unresolved=[]) is False


class TestIsFirstIterationWithFlags:
    def test_first_with_flags(self) -> None:
        assert _is_first_iteration_with_flags(iteration=1, significant_count=2) is True

    def test_first_without_flags(self) -> None:
        assert _is_first_iteration_with_flags(iteration=1, significant_count=0) is False

    def test_later_iteration(self) -> None:
        assert _is_first_iteration_with_flags(iteration=2, significant_count=5) is False


class TestHasRecurringCritiques:
    def test_has_recurring(self) -> None:
        assert _has_recurring_critiques(recurring=["concern A"]) is True

    def test_no_recurring(self) -> None:
        assert _has_recurring_critiques(recurring=[]) is False


class TestIsScoreStagnating:
    def test_stagnating(self) -> None:
        # score >= last * factor means stagnating
        assert _is_score_stagnating(
            weighted_score=9.0, weighted_history=[10.0], stagnation_factor=0.9,
        ) is True

    def test_improving(self) -> None:
        assert _is_score_stagnating(
            weighted_score=5.0, weighted_history=[10.0], stagnation_factor=0.9,
        ) is False

    def test_empty_history(self) -> None:
        assert _is_score_stagnating(
            weighted_score=5.0, weighted_history=[], stagnation_factor=0.9,
        ) is False


class TestIsScoreImproving:
    def test_improving(self) -> None:
        assert _is_score_improving(
            weighted_score=5.0, weighted_history=[10.0], stagnation_factor=0.9,
        ) is True

    def test_not_improving(self) -> None:
        assert _is_score_improving(
            weighted_score=9.5, weighted_history=[10.0], stagnation_factor=0.9,
        ) is False

    def test_empty_history(self) -> None:
        assert _is_score_improving(
            weighted_score=5.0, weighted_history=[], stagnation_factor=0.9,
        ) is False


class TestIsMaxIterationsWithUnresolved:
    def test_at_max_with_unresolved(self) -> None:
        state = {"config": {"max_iterations": 3}}
        assert _is_max_iterations_with_unresolved(
            iteration=3, state=state, unresolved=[{"id": "F"}],
        ) is True

    def test_below_max(self) -> None:
        state = {"config": {"max_iterations": 3}}
        assert _is_max_iterations_with_unresolved(
            iteration=2, state=state, unresolved=[{"id": "F"}],
        ) is False

    def test_at_max_no_unresolved(self) -> None:
        state = {"config": {"max_iterations": 3}}
        assert _is_max_iterations_with_unresolved(
            iteration=3, state=state, unresolved=[],
        ) is False


class TestComputePlanDeltaPercent:
    def test_identical_texts(self) -> None:
        assert compute_plan_delta_percent("hello", "hello") == 0.0

    def test_completely_different(self) -> None:
        delta = compute_plan_delta_percent("aaa", "zzz")
        assert delta is not None
        assert delta > 50.0

    def test_none_previous(self) -> None:
        assert compute_plan_delta_percent(None, "any") is None
