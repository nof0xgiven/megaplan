from __future__ import annotations

from megaplan.checks import (
    build_empty_template,
    checks_for_robustness,
    validate_critique_checks,
)


def _payload_for(checks: tuple[dict[str, str], ...]) -> dict[str, object]:
    return {
        "checks": [
            {
                "id": check["id"],
                "question": check["question"],
                "findings": [{"detail": "No issue found", "flagged": False}],
            }
            for check in checks
        ]
    }


def test_checks_for_robustness_returns_expected_check_sets() -> None:
    heavy_checks = checks_for_robustness("heavy")
    standard_checks = checks_for_robustness("standard")
    light_checks = checks_for_robustness("light")

    assert len(heavy_checks) == 8
    assert [check["id"] for check in standard_checks] == [
        "issue_hints",
        "correctness",
        "scope",
        "verification",
    ]
    assert light_checks == ()


def test_build_empty_template_uses_filtered_checks() -> None:
    template = build_empty_template(checks_for_robustness("standard"))

    assert [entry["id"] for entry in template] == [
        "issue_hints",
        "correctness",
        "scope",
        "verification",
    ]
    assert all(entry["findings"] == [] for entry in template)


def test_validate_critique_checks_accepts_filtered_standard_ids() -> None:
    standard_checks = checks_for_robustness("standard")
    payload = _payload_for(standard_checks)

    assert validate_critique_checks(
        payload,
        expected_ids=[check["id"] for check in standard_checks],
    ) == []


def test_validate_critique_checks_accepts_light_mode_empty_checks() -> None:
    assert validate_critique_checks({"checks": []}, expected_ids=[]) == []


def test_validate_critique_checks_rejects_light_mode_stray_checks() -> None:
    stray_payload = _payload_for((checks_for_robustness("standard")[0],))

    assert validate_critique_checks(stray_payload, expected_ids=[]) == ["issue_hints"]
