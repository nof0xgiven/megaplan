"""Direct tests for megaplan.workers module."""
from __future__ import annotations

import json

import pytest

from megaplan._core import CliError
from megaplan.workers import parse_claude_envelope, validate_payload


class TestParsClaudeEnvelope:
    def test_valid_envelope_with_result(self) -> None:
        raw = json.dumps({"result": json.dumps({"plan": "hello"}), "total_cost_usd": 0.01})
        envelope, payload = parse_claude_envelope(raw)
        assert payload["plan"] == "hello"
        assert envelope["total_cost_usd"] == 0.01

    def test_structured_output_preferred(self) -> None:
        raw = json.dumps({
            "result": "ignored",
            "structured_output": {"plan": "from structured"},
        })
        envelope, payload = parse_claude_envelope(raw)
        assert payload["plan"] == "from structured"

    def test_direct_dict_payload(self) -> None:
        """When the entire output is just the payload dict."""
        raw = json.dumps({"plan": "direct"})
        _envelope, payload = parse_claude_envelope(raw)
        assert payload["plan"] == "direct"

    def test_is_error_raises(self) -> None:
        raw = json.dumps({"is_error": True, "result": "something broke"})
        with pytest.raises(CliError) as exc_info:
            parse_claude_envelope(raw)
        assert exc_info.value.code == "worker_error"

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(CliError) as exc_info:
            parse_claude_envelope("not json at all")
        assert exc_info.value.code == "parse_error"

    def test_empty_result_raises(self) -> None:
        raw = json.dumps({"result": ""})
        with pytest.raises(CliError) as exc_info:
            parse_claude_envelope(raw)
        assert exc_info.value.code == "parse_error"

    def test_non_object_payload_raises(self) -> None:
        raw = json.dumps({"result": json.dumps([1, 2, 3])})
        with pytest.raises(CliError) as exc_info:
            parse_claude_envelope(raw)
        assert exc_info.value.code == "parse_error"


class TestValidatePayload:
    def test_clarify_valid(self) -> None:
        validate_payload("clarify", {"questions": [], "refined_idea": "x", "intent_summary": "y"})

    def test_clarify_missing_key(self) -> None:
        with pytest.raises(CliError) as exc_info:
            validate_payload("clarify", {"questions": []})
        assert "refined_idea" in exc_info.value.message

    def test_plan_valid(self) -> None:
        validate_payload("plan", {"plan": "p", "questions": [], "success_criteria": [], "assumptions": []})

    def test_plan_missing_key(self) -> None:
        with pytest.raises(CliError) as exc_info:
            validate_payload("plan", {"plan": "p"})
        assert "questions" in exc_info.value.message

    def test_critique_valid(self) -> None:
        validate_payload("critique", {"flags": []})

    def test_critique_missing_flags(self) -> None:
        with pytest.raises(CliError):
            validate_payload("critique", {})

    def test_integrate_valid(self) -> None:
        validate_payload("integrate", {"plan": "p", "changes_summary": "s", "flags_addressed": []})

    def test_execute_valid(self) -> None:
        validate_payload("execute", {"output": "o", "files_changed": [], "commands_run": [], "deviations": []})

    def test_review_valid(self) -> None:
        validate_payload("review", {"criteria": [], "issues": []})

    def test_unknown_step_does_not_raise(self) -> None:
        """Unknown steps are silently accepted (no schema to check)."""
        validate_payload("unknown_step", {"anything": "goes"})
