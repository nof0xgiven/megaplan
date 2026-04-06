"""Review-phase prompt builders."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from megaplan._core import (
    collect_git_diff_summary,
    intent_and_notes_block,
    json_dump,
    latest_plan_meta_path,
    latest_plan_path,
    read_json,
)
from megaplan.types import PlanState



def _settled_decisions_block(gate: dict[str, object]) -> str:
    settled_decisions = gate.get("settled_decisions", [])
    if not isinstance(settled_decisions, list) or not settled_decisions:
        return ""
    lines = ["Settled decisions (verify the executor implemented these correctly):"]
    for item in settled_decisions:
        if not isinstance(item, dict):
            continue
        decision_id = item.get("id", "DECISION")
        decision = item.get("decision", "")
        rationale = item.get("rationale", "")
        line = f"- {decision_id}: {decision}"
        if rationale:
            line += f" ({rationale})"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def _settled_decisions_instruction(gate: dict[str, object]) -> str:
    settled_decisions = gate.get("settled_decisions", [])
    if not isinstance(settled_decisions, list) or not settled_decisions:
        return ""
    return "- The decisions listed above were settled at the gate stage. Verify that the executor implemented each settled decision correctly. Flag deviations from these decisions, but do not question the decisions themselves."


def _write_review_template(plan_dir: Path, state: PlanState) -> Path:
    """Write a pre-populated review output template and return its path.

    Pre-fills ``task_verdicts`` and ``sense_check_verdicts`` with the actual
    task IDs and sense-check IDs from ``finalize.json`` so the model only has
    to fill in verdict text instead of inventing IDs from scratch.  This is
    the same pattern used for critique templates and fixes MiniMax-M2.7's
    tendency to return empty verdict arrays.
    """
    finalize_data = read_json(plan_dir / "finalize.json")

    task_verdicts = []
    for task in finalize_data.get("tasks", []):
        task_id = task.get("id", "")
        if task_id:
            task_verdicts.append({
                "task_id": task_id,
                "reviewer_verdict": "",
                "evidence_files": [],
            })

    sense_check_verdicts = []
    for sc in finalize_data.get("sense_checks", []):
        sc_id = sc.get("id", "")
        if sc_id:
            sense_check_verdicts.append({
                "sense_check_id": sc_id,
                "verdict": "",
            })

    # Pre-populate criteria from finalize success_criteria if available
    criteria = []
    for crit in finalize_data.get("success_criteria", []):
        if isinstance(crit, dict) and crit.get("name"):
            criteria.append({
                "name": crit["name"],
                "priority": crit.get("priority", "must"),
                "pass": "",
                "evidence": "",
            })

    template = {
        "review_verdict": "",
        "criteria": criteria,
        "issues": [],
        "rework_items": [],
        "summary": "",
        "task_verdicts": task_verdicts,
        "sense_check_verdicts": sense_check_verdicts,
    }

    output_path = plan_dir / "review_output.json"
    output_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    return output_path


def _review_prompt(
    state: PlanState,
    plan_dir: Path,
    *,
    review_intro: str,
    criteria_guidance: str,
    task_guidance: str,
    sense_check_guidance: str,
) -> str:
    project_dir = Path(state["config"]["project_dir"])
    latest_plan = latest_plan_path(plan_dir, state).read_text(encoding="utf-8")
    latest_meta = read_json(latest_plan_meta_path(plan_dir, state))
    execution = read_json(plan_dir / "execution.json")
    gate = read_json(plan_dir / "gate.json")
    finalize_data = read_json(plan_dir / "finalize.json")
    settled_decisions_block = _settled_decisions_block(gate)
    settled_decisions_instruction = _settled_decisions_instruction(gate)
    diff_summary = collect_git_diff_summary(project_dir)
    audit_path = plan_dir / "execution_audit.json"
    if audit_path.exists():
        audit_block = textwrap.dedent(
            f"""
            Execution audit (`execution_audit.json`):
            {json_dump(read_json(audit_path)).strip()}
            """
        ).strip()
    else:
        audit_block = "Execution audit (`execution_audit.json`): not present. Skip that artifact gracefully and rely on `finalize.json`, `execution.json`, and the git diff."
    return textwrap.dedent(
        f"""
        {review_intro}

        Project directory:
        {project_dir}

        {intent_and_notes_block(state)}

        Approved plan:
        {latest_plan}

        Execution tracking state (`finalize.json`):
        {json_dump(finalize_data).strip()}

        Plan metadata:
        {json_dump(latest_meta).strip()}

        Gate summary:
        {json_dump(gate).strip()}

        {settled_decisions_block}

        Execution summary:
        {json_dump(execution).strip()}

        {audit_block}

        Git diff summary:
        {diff_summary}

        Requirements:
        - {criteria_guidance}
        - Trust executor evidence by default. Dig deeper only where the git diff, `execution_audit.json`, or vague notes make the claim ambiguous.
        - Each criterion has a `priority` (`must`, `should`, or `info`). Apply these rules:
          - `must` criteria are hard gates. A `must` criterion that fails means `needs_rework`.
          - `should` criteria are quality targets. If the spirit is met but the letter is not, mark `pass` with evidence explaining the gap. Only mark `fail` if the intent was clearly missed. A `should` failure alone does NOT require `needs_rework`.
          - `info` criteria are for human reference. Mark them `waived` with a note — do not evaluate them.
          - If a criterion (any priority) cannot be verified in this context (e.g., requires manual testing or runtime observation), mark it `waived` with an explanation.
        - Set `review_verdict` to `needs_rework` only when at least one `must` criterion fails or actual implementation work is incomplete. Use `approved` when all `must` criteria pass, even if some `should` criteria are flagged.
        {settled_decisions_instruction}
        - {task_guidance}
        - {sense_check_guidance}
        - Follow this JSON shape exactly:
        ```json
        {{
          "review_verdict": "approved",
          "criteria": [
            {{
              "name": "All existing tests pass",
              "priority": "must",
              "pass": "pass",
              "evidence": "Test suite ran green — 42 passed, 0 failed."
            }},
            {{
              "name": "File under ~300 lines",
              "priority": "should",
              "pass": "pass",
              "evidence": "File is 375 lines — above the target but reasonable given the component's responsibilities. Spirit met."
            }},
            {{
              "name": "Manual smoke tests pass",
              "priority": "info",
              "pass": "waived",
              "evidence": "Cannot be verified in automated review. Noted for manual QA."
            }}
          ],
          "issues": [],
          "rework_items": [],
          "summary": "Approved. All must criteria pass. The should criterion on line count is close enough given the component scope.",
          "task_verdicts": [
            {{
              "task_id": "T6",
              "reviewer_verdict": "Pass. Claimed handler changes and command evidence match the repo state.",
              "evidence_files": ["megaplan/handlers.py", "megaplan/evaluation.py"]
            }}
          ],
          "sense_check_verdicts": [
            {{
              "sense_check_id": "SC6",
              "verdict": "Confirmed. The execute blocker only fires when both evidence arrays are empty."
            }}
          ]
        }}
        ```
        - `rework_items` must be an array of structured rework directives. When `review_verdict` is `needs_rework`, populate one entry per issue with:
          - `task_id`: which finalize task this issue relates to
          - `issue`: what is wrong
          - `expected`: what correct behavior looks like
          - `actual`: what was observed
          - `evidence_file` (optional): file path supporting the finding
        - `issues` must still be populated as a flat one-line-per-item summary derived from `rework_items` (for backward compatibility). When approved, both `issues` and `rework_items` should be empty arrays.
        - When the work needs another execute pass, keep the same shape and change only `review_verdict` to `needs_rework`; make `issues`, `rework_items`, `summary`, and task verdicts specific enough for the executor to act on directly.
        """
    ).strip()
