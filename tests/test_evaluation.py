"""Direct tests for megaplan.evaluation module."""
from __future__ import annotations

import pytest

from megaplan.evaluation import build_evaluation, flag_weight


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
