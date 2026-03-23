from __future__ import annotations

import shutil

from megaplan.types import (
    CliError,
    PlanState,
    STATE_CRITIQUED,
    STATE_EXECUTED,
    STATE_GATED,
    STATE_INITIALIZED,
    STATE_PLANNED,
)


def infer_next_steps(state: PlanState) -> list[str]:
    current = state["current_state"]
    if current == STATE_INITIALIZED:
        return ["plan"]
    if current == STATE_PLANNED:
        return ["plan", "critique"]
    if current == STATE_CRITIQUED:
        gate = state.get("last_gate", {})
        recommendation = gate.get("recommendation")
        if not recommendation:
            return ["gate"]
        if recommendation == "ITERATE":
            return ["revise"]
        if recommendation == "ESCALATE":
            return ["override add-note", "override force-proceed", "override abort"]
        if recommendation == "PROCEED" and not gate.get("passed", False):
            return ["revise", "override force-proceed"]
        return ["gate"]
    if current == STATE_GATED:
        return ["execute", "override replan"]
    if current == STATE_EXECUTED:
        return ["review"]
    return []


def require_state(state: PlanState, step: str, allowed: set[str]) -> None:
    current = state["current_state"]
    if current not in allowed:
        raise CliError(
            "invalid_transition",
            f"Cannot run '{step}' while current state is '{current}'",
            valid_next=infer_next_steps(state),
            extra={"current_state": current},
        )


def find_command(name: str) -> str | None:
    return shutil.which(name)
