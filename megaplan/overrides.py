from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from megaplan.types import (
    CliError,
    PlanState,
    STATE_ABORTED,
    STATE_CRITIQUED,
    STATE_GATED,
    STATE_PLANNED,
    StepResponse,
)
from megaplan._core import (
    atomic_write_json,
    atomic_write_text,
    latest_plan_path,
    now_utc,
    save_state,
)
from megaplan.evaluation import build_gate_artifact, build_gate_signals, run_gate_checks
from megaplan.handlers import _append_to_meta
from megaplan.state_machine import find_command, infer_next_steps


def _override_add_note(plan_dir: Path, state: PlanState, args: argparse.Namespace) -> StepResponse:
    action = "add-note"
    note = args.note
    override_entry = {"action": action, "timestamp": now_utc(), "note": note}
    note_record = {"timestamp": now_utc(), "note": note}
    _append_to_meta(state, "notes", note_record)
    _append_to_meta(state, "overrides", override_entry)
    save_state(plan_dir, state)
    next_steps = infer_next_steps(state)
    return {
        "success": True,
        "step": "override",
        "summary": "Attached note to the plan.",
        "next_step": next_steps[0] if next_steps else None,
        "state": state["current_state"],
    }


def _override_abort(plan_dir: Path, state: PlanState, args: argparse.Namespace) -> StepResponse:
    override_entry = {"action": "abort", "timestamp": now_utc(), "reason": args.reason}
    state["current_state"] = STATE_ABORTED
    _append_to_meta(state, "overrides", override_entry)
    save_state(plan_dir, state)
    return {
        "success": True,
        "step": "override",
        "summary": "Plan aborted.",
        "next_step": None,
        "state": STATE_ABORTED,
    }


def _override_force_proceed(plan_dir: Path, state: PlanState, args: argparse.Namespace) -> StepResponse:
    if state["current_state"] != STATE_CRITIQUED:
        raise CliError(
            "invalid_transition",
            "force-proceed is only supported from critiqued state",
            valid_next=infer_next_steps(state),
        )
    gate_checks = run_gate_checks(plan_dir, state, command_lookup=find_command)
    if not gate_checks["preflight_results"]["project_dir_exists"] or not gate_checks["preflight_results"]["success_criteria_present"]:
        raise CliError("unsafe_override", "force-proceed cannot bypass missing project directory or success criteria")
    signals = build_gate_signals(plan_dir, state)
    merged_signals = {
        "robustness": signals["robustness"],
        "signals": signals["signals"],
        "warnings": signals.get("warnings", []),
        "criteria_check": gate_checks["criteria_check"],
        "preflight_results": gate_checks["preflight_results"],
        "unresolved_flags": gate_checks["unresolved_flags"],
    }
    gate = build_gate_artifact(
        merged_signals,
        {
            "recommendation": "PROCEED",
            "rationale": args.reason or "User forced execution past the gate.",
            "signals_assessment": "Forced proceed override applied by the orchestrator.",
            "warnings": signals.get("warnings", []),
        },
        override_forced=True,
        orchestrator_guidance="Force-proceed override applied. Proceed to execute.",
    )
    atomic_write_json(plan_dir / "gate.json", gate)
    final_plan = latest_plan_path(plan_dir, state).read_text(encoding="utf-8")
    atomic_write_text(plan_dir / "final.md", final_plan)
    state["current_state"] = STATE_GATED
    state["meta"].pop("user_approved_gate", None)
    state["last_gate"] = {}
    _append_to_meta(state, "overrides", {"action": "force-proceed", "timestamp": now_utc(), "reason": args.reason})
    save_state(plan_dir, state)
    return {
        "success": True,
        "step": "override",
        "summary": "Force-proceeded past gate judgment into gated state.",
        "next_step": "execute",
        "state": STATE_GATED,
        "orchestrator_guidance": gate["orchestrator_guidance"],
    }


def _override_replan(plan_dir: Path, state: PlanState, args: argparse.Namespace) -> StepResponse:
    allowed = {STATE_GATED, STATE_CRITIQUED}
    if state["current_state"] not in allowed:
        raise CliError(
            "invalid_transition",
            f"replan requires state {', '.join(sorted(allowed))}, got '{state['current_state']}'",
            valid_next=infer_next_steps(state),
        )
    reason = args.reason or args.note or "Re-entering planning loop"
    plan_file = latest_plan_path(plan_dir, state)
    state["current_state"] = STATE_PLANNED
    state["last_gate"] = {}
    _append_to_meta(state, "overrides", {"action": "replan", "timestamp": now_utc(), "reason": reason})
    if args.note:
        _append_to_meta(state, "notes", {"timestamp": now_utc(), "note": args.note})
    save_state(plan_dir, state)
    return {
        "success": True,
        "step": "override",
        "summary": f"Re-entered planning loop at iteration {state['iteration']}. Reason: {reason}",
        "next_step": "critique",
        "state": STATE_PLANNED,
        "plan_file": str(plan_file),
        "message": f"Edit {plan_file.name} to incorporate your changes, then run critique. Or run critique directly if the note provides enough context for the loop to address.",
    }


_OVERRIDE_ACTIONS: dict[str, Callable[[Path, PlanState, argparse.Namespace], StepResponse]] = {
    "add-note": _override_add_note,
    "abort": _override_abort,
    "force-proceed": _override_force_proceed,
    "replan": _override_replan,
}


def handle_override(root: Path, args: argparse.Namespace) -> StepResponse:
    from megaplan._core import load_plan

    plan_dir, state = load_plan(root, args.plan)
    action = args.override_action
    handler = _OVERRIDE_ACTIONS.get(action)
    if handler is None:
        raise CliError("invalid_override", f"Unknown override action: {action}")
    return handler(plan_dir, state, args)
