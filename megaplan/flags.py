from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from megaplan._core import load_flag_registry, save_flag_registry
from megaplan.types import FlagRecord, FlagRegistry


def next_flag_number(flags: list[FlagRecord]) -> int:
    highest = 0
    for flag in flags:
        match = re.fullmatch(r"FLAG-(\d+)", flag["id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return highest + 1


def make_flag_id(number: int) -> str:
    return f"FLAG-{number:03d}"


def resolve_severity(hint: str) -> str:
    if hint == "likely-significant":
        return "significant"
    if hint == "likely-minor":
        return "minor"
    if hint == "uncertain":
        return "significant"
    return "significant"


def normalize_flag_record(raw_flag: dict[str, Any], fallback_id: str) -> FlagRecord:
    category = raw_flag.get("category", "other")
    if category not in {"correctness", "security", "completeness", "performance", "maintainability", "other"}:
        category = "other"
    severity_hint = raw_flag.get("severity_hint") or "uncertain"
    if severity_hint not in {"likely-significant", "likely-minor", "uncertain"}:
        severity_hint = "uncertain"
    raw_id = raw_flag.get("id")
    return {
        "id": fallback_id if raw_id in {None, "", "FLAG-000"} else raw_id,
        "concern": raw_flag.get("concern", "").strip(),
        "category": category,
        "severity_hint": severity_hint,
        "evidence": raw_flag.get("evidence", "").strip(),
    }


def update_flags_after_critique(plan_dir: Path, critique: dict[str, Any], *, iteration: int) -> FlagRegistry:
    registry = load_flag_registry(plan_dir)
    flags = registry.setdefault("flags", [])
    by_id: dict[str, FlagRecord] = {flag["id"]: flag for flag in flags}
    next_number = next_flag_number(flags)

    for verified_id in critique.get("verified_flag_ids", []):
        if verified_id in by_id:
            by_id[verified_id]["status"] = "verified"
            by_id[verified_id]["verified"] = True
            by_id[verified_id]["verified_in"] = f"critique_v{iteration}.json"

    for disputed_id in critique.get("disputed_flag_ids", []):
        if disputed_id in by_id:
            by_id[disputed_id]["status"] = "disputed"

    # Convert flagged findings from structured checks into standard flags.
    from megaplan.checks import build_check_category_map, get_check_by_id

    check_category_map = build_check_category_map()
    for check in critique.get("checks", []):
        check_id = check.get("id", "")
        flagged_findings = [finding for finding in check.get("findings", []) if finding.get("flagged")]
        for index, finding in enumerate(flagged_findings, start=1):
            check_def = get_check_by_id(check_id)
            severity = check_def.get("default_severity", "uncertain") if check_def else "uncertain"
            flag_id = check_id if len(flagged_findings) == 1 else f"{check_id}-{index}"
            synthetic_flag = {
                "id": flag_id,
                "concern": f"{check.get('question', '')}: {finding.get('detail', '')}",
                "category": check_category_map.get(check_id, "correctness"),
                "severity_hint": severity,
                "evidence": finding.get("detail", ""),
            }
            critique.setdefault("flags", []).append(synthetic_flag)

    for raw_flag in critique.get("flags", []):
        proposed_id = raw_flag.get("id")
        if not proposed_id or proposed_id in {"", "FLAG-000"}:
            proposed_id = make_flag_id(next_number)
            next_number += 1
        normalized = normalize_flag_record(raw_flag, proposed_id)
        if normalized["id"] in by_id:
            existing = by_id[normalized["id"]]
            existing.update(normalized)
            existing["status"] = "open"
            existing["severity"] = resolve_severity(normalized.get("severity_hint", "uncertain"))
            existing["raised_in"] = f"critique_v{iteration}.json"
            continue
        severity = resolve_severity(normalized.get("severity_hint", "uncertain"))
        created: FlagRecord = {
            **normalized,
            "raised_in": f"critique_v{iteration}.json",
            "status": "open",
            "severity": severity,
            "verified": False,
        }
        flags.append(created)
        by_id[created["id"]] = created

    save_flag_registry(plan_dir, registry)
    return registry


def update_flags_after_revise(
    plan_dir: Path,
    flags_addressed: list[str],
    *,
    plan_file: str,
    summary: str,
) -> FlagRegistry:
    registry = load_flag_registry(plan_dir)
    for flag in registry["flags"]:
        if flag["id"] in flags_addressed:
            flag["status"] = "addressed"
            flag["addressed_in"] = plan_file
            flag["evidence"] = summary
    save_flag_registry(plan_dir, registry)
    return registry
