"""Critique- and revise-phase prompt builders."""

from __future__ import annotations

import textwrap
from pathlib import Path

from megaplan.checks import CRITIQUE_CHECKS, build_empty_template
from megaplan._core import (
    configured_robustness,
    intent_and_notes_block,
    json_dump,
    latest_plan_meta_path,
    latest_plan_path,
    load_flag_registry,
    read_json,
    robustness_critique_instruction,
    unresolved_significant_flags,
)
from megaplan.types import PlanState

from ._shared import _planning_debt_block, _render_prep_block, _render_research_block
from .planning import PLAN_TEMPLATE


def _revise_prompt(state: PlanState, plan_dir: Path) -> str:
    project_dir = Path(state["config"]["project_dir"])
    prep_block, prep_instruction = _render_prep_block(plan_dir)
    latest_plan = latest_plan_path(plan_dir, state).read_text(encoding="utf-8")
    latest_meta = read_json(latest_plan_meta_path(plan_dir, state))
    gate = read_json(plan_dir / "gate.json")
    unresolved = unresolved_significant_flags(load_flag_registry(plan_dir))
    open_flags = [
        {
            "id": flag["id"],
            "severity": flag.get("severity"),
            "status": flag["status"],
            "concern": flag["concern"],
            "evidence": flag.get("evidence"),
        }
        for flag in unresolved
    ]
    return textwrap.dedent(
        f"""
        You are revising an implementation plan after critique and gate feedback.

        Project directory:
        {project_dir}

        {prep_block}
        {prep_instruction}

        {intent_and_notes_block(state)}

        Current plan (markdown):
        {latest_plan}

        Current plan metadata:
        {json_dump(latest_meta).strip()}

        Gate summary:
        {json_dump(gate).strip()}

        Open significant flags:
        {json_dump(open_flags).strip()}

        Requirements:
        - Before addressing individual flags, check: does any flag suggest the plan is targeting the wrong code or the wrong root cause? If so, consider whether the plan needs a new approach rather than adjustments. Explain your reasoning.
        - Update the plan to address the significant issues.
        - Keep the plan readable and executable.
        - Return flags_addressed with the exact flag IDs you addressed.
        - Preserve or improve success criteria quality. Each criterion must have a `priority` of `must`, `should`, or `info`. Promote or demote priorities if critique feedback reveals a criterion was over- or under-weighted.
        - Verify that the plan remains aligned with the user's original intent, not just internal plan quality.
        - Remove unjustified scope growth. If critique raised scope creep, narrow the plan back to the original idea unless the broader work is strictly required.
        - Maintain the structural template: H1 title, ## Overview, phase sections with numbered step sections, ## Execution Order or ## Validation Order.

        {PLAN_TEMPLATE}
        """
    ).strip()


def _render_critique_checks() -> str:
    """Render check questions and guidance from CRITIQUE_CHECKS."""
    lines = []
    for i, check in enumerate(CRITIQUE_CHECKS, 1):
        lines.append(
            f"{i}. id=\"{check['id']}\" — \"{check['question']}\"\n"
            f"           {check.get('guidance', check.get('instruction', ''))}"
        )
    return "\n\n        ".join(lines)


def _render_critique_template(plan_dir: Path, state: PlanState) -> str:
    """Render the JSON template the model fills in, with prior findings if iteration 2+."""
    iteration = state.get("iteration", 1)
    if iteration > 1:
        prior_path = plan_dir / f"critique_v{iteration - 1}.json"
        if prior_path.exists():
            prior = read_json(prior_path)
            prior_checks = prior.get("checks", [])
            if prior_checks:
                # Build template showing what was found last time
                registry = load_flag_registry(plan_dir)
                # Build status lookup: flag IDs can be check_id or check_id-N
                flag_status = {}
                for f in registry.get("flags", []):
                    flag_status[f["id"]] = f.get("status", "open")
                enriched = []
                for check in prior_checks:
                    cid = check.get("id", "")
                    flagged_indices: dict[int, int] = {}
                    flagged_counter = 0
                    for finding_index, finding in enumerate(check.get("findings", [])):
                        if finding.get("flagged"):
                            flagged_counter += 1
                            flagged_indices[finding_index] = flagged_counter
                    prior_findings_list = []
                    for fi, f in enumerate(check.get("findings", [])):
                        pf = {
                            "detail": f.get("detail", ""),
                            "flagged": f.get("flagged", False),
                        }
                        if f.get("flagged"):
                            # Match flag ID: check_id for single, check_id-N for multiple
                            if flagged_counter == 1:
                                fid = cid
                            else:
                                fid = f"{cid}-{flagged_indices[fi]}"
                            pf["status"] = flag_status.get(
                                fid, flag_status.get(cid, "open")
                            )
                        else:
                            pf["status"] = "n/a"
                        prior_findings_list.append(pf)
                    entry = {
                        "id": cid,
                        "question": check.get("question", ""),
                        "prior_findings": prior_findings_list,
                        "findings": [],
                    }
                    enriched.append(entry)
                # Add any new checks not in prior
                prior_ids = {c.get("id") for c in prior_checks}
                for check_def in CRITIQUE_CHECKS:
                    if check_def["id"] not in prior_ids:
                        enriched.append(
                            {
                                "id": check_def["id"],
                                "question": check_def["question"],
                                "findings": [],
                            }
                        )
                return textwrap.dedent(
                    f"""
                    This is critique iteration {iteration}. Prior findings are shown with their status.
                    - Verify addressed flags were actually fixed
                    - Re-flag if the fix is inadequate
                    - Check for new issues introduced by the revision

                    {json_dump(enriched).strip()}
                """
                ).strip()
    return textwrap.dedent(
        f"""
        Fill in this template with your findings:
        {json_dump(build_empty_template()).strip()}
    """
    ).strip()


def _critique_prompt(state: PlanState, plan_dir: Path, root: Path | None = None) -> str:
    project_dir = Path(state["config"]["project_dir"])
    prep_block, prep_instruction = _render_prep_block(plan_dir)
    research_block, research_instruction = _render_research_block(plan_dir)
    latest_plan = latest_plan_path(plan_dir, state).read_text(encoding="utf-8")
    latest_meta = read_json(latest_plan_meta_path(plan_dir, state))
    structure_warnings = latest_meta.get("structure_warnings", [])
    flag_registry = load_flag_registry(plan_dir)
    robustness = configured_robustness(state)
    unresolved = [
        {
            "id": flag["id"],
            "concern": flag["concern"],
            "status": flag["status"],
            "severity": flag.get("severity"),
        }
        for flag in flag_registry["flags"]
        if flag["status"] in {"addressed", "open", "disputed"}
    ]
    debt_block = _planning_debt_block(plan_dir, root)
    return textwrap.dedent(
        f"""
        You are an independent reviewer. Critique the plan against the actual repository.

        Project directory:
        {project_dir}

        {prep_block}

        {prep_instruction}

        {intent_and_notes_block(state)}

        Plan:
        {latest_plan}

        Plan metadata:
        {json_dump(latest_meta).strip()}

        Plan structure warnings from validator:
        {json_dump(structure_warnings).strip()}

        Existing flags:
        {json_dump(unresolved).strip()}

        {research_block}

        {debt_block}

        Fill in ALL {len(CRITIQUE_CHECKS)} checks below. For each, add at least one finding with "detail" (what you found) and "flagged" (true if it's a problem). {{"detail": "No issue found", "flagged": false}} is valid. You can add multiple findings per check.

        {_render_critique_checks()}

        After filling in checks, add any additional concerns to the `flags` array (e.g., security, performance, dependencies). Use the standard format (id, concern, category, severity_hint, evidence). This array can be empty.

        {_render_critique_template(plan_dir, state)}

        Additional guidelines:
        - Robustness level: {robustness}. {robustness_critique_instruction(robustness)}
        - Over-engineering: prefer the simplest approach that fully solves the problem.
        - Reuse existing flag IDs when the same concern is still open.
        - `verified_flag_ids` should list previously addressed flags that now appear resolved.
        - Verify that the plan follows the expected structure when validator warnings or the outline suggest drift.
        - Additional flags may use these categories: correctness, security, completeness, performance, maintainability, other.
        - Focus on concrete issues, not structural formatting.
        {research_instruction}
        """
    ).strip()
