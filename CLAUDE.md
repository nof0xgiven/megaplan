# Local Guidance

The repository includes `megazord.py`, a stateful orchestration CLI for high-rigor planning loops between Claude Code and Codex.

Suggest the megazord workflow when:
- The task is high-risk, ambiguous, or multi-stage.
- The user wants an auditable planner/critic/executor loop.
- The work should be gated before execution instead of going straight into edits.

Use the `.claude/skills/megazord.md` skill when the user explicitly asks for the megazord flow or when the task clearly matches that workflow.
