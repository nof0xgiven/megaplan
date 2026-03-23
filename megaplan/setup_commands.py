from __future__ import annotations

import argparse
from importlib import resources
from pathlib import Path
from typing import Any

from megaplan.types import (
    CliError,
    DEFAULT_AGENT_ROUTING,
    KNOWN_AGENTS,
    StepResponse,
)
from megaplan._core import (
    atomic_write_text,
    config_dir,
    detect_available_agents,
    load_config,
    save_config,
)


def _canonical_instructions() -> str:
    return resources.files("megaplan").joinpath("data", "instructions.md").read_text(encoding="utf-8")


_SKILL_HEADER = """\
---
name: megaplan
description: AI agent harness for coordinating Claude and GPT to make and execute extremely robust plans.
---

"""

_CURSOR_HEADER = """\
---
description: Use megaplan for high-rigor planning on complex, high-risk, or multi-stage tasks.
alwaysApply: false
---

"""


def bundled_agents_md() -> str:
    return _canonical_instructions()


def bundled_global_file(name: str) -> str:
    content = _canonical_instructions()
    if name == "skill.md":
        return _SKILL_HEADER + content
    if name == "cursor_rule.mdc":
        return _CURSOR_HEADER + content
    return content


GLOBAL_TARGETS = [
    {"agent": "claude", "detect": ".claude", "path": ".claude/skills/megaplan/SKILL.md", "data": "skill.md"},
    {"agent": "codex", "detect": ".codex", "path": ".codex/skills/megaplan/SKILL.md", "data": "skill.md"},
    {"agent": "cursor", "detect": ".cursor", "path": ".cursor/rules/megaplan.mdc", "data": "cursor_rule.mdc"},
]


def _install_owned_file(path: Path, content: str, *, force: bool = False) -> dict[str, bool | str]:
    existed = path.exists()
    if existed and not force:
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return {"path": str(path), "skipped": True, "existed": True}
    atomic_write_text(path, content)
    return {"path": str(path), "skipped": False, "existed": existed}


def _detect_available_agents() -> list[str]:
    return detect_available_agents()


def handle_setup_global(force: bool = False, home: Path | None = None) -> StepResponse:
    if home is None:
        home = Path.home()

    installed: list[dict[str, Any]] = []
    detected_count = 0

    for target in GLOBAL_TARGETS:
        agent_dir = home / target["detect"]
        if not agent_dir.is_dir():
            installed.append(
                {
                    "agent": target["agent"],
                    "path": str(home / target["path"]),
                    "skipped": True,
                    "reason": "not installed",
                }
            )
            continue

        detected_count += 1
        content = bundled_global_file(target["data"])
        dest = home / target["path"]
        result = _install_owned_file(dest, content, force=force)
        result["agent"] = target["agent"]
        installed.append(result)

    if detected_count == 0:
        return {
            "success": False,
            "step": "setup",
            "mode": "global",
            "summary": (
                "No supported agents detected. "
                "Create one of ~/.claude/, ~/.codex/, or ~/.cursor/ and re-run, "
                "or use 'megaplan setup' to install AGENTS.md into a specific project."
            ),
            "installed": installed,
        }

    available = _detect_available_agents()
    config_path = None
    routing = None
    if available:
        agents_config: dict[str, str] = {}
        for step, default in DEFAULT_AGENT_ROUTING.items():
            agents_config[step] = default if default in available else available[0]
        config = load_config(home)
        config["agents"] = agents_config
        config_path = save_config(config, home)
        routing = agents_config

    lines = []
    for install_record in installed:
        if install_record.get("reason") == "not installed":
            lines.append(f"  {install_record['agent']}: skipped (not installed)")
        elif install_record["skipped"]:
            lines.append(f"  {install_record['agent']}: up to date")
        else:
            verb = "overwrote" if install_record["existed"] else "created"
            lines.append(f"  {install_record['agent']}: {verb} {install_record['path']}")

    result_data: dict[str, Any] = {
        "success": True,
        "step": "setup",
        "mode": "global",
        "summary": "Global setup complete:\n" + "\n".join(lines),
        "installed": installed,
    }
    if config_path is not None:
        result_data["config_path"] = str(config_path)
        result_data["routing"] = routing
    return result_data


def handle_setup(args: argparse.Namespace) -> StepResponse:
    local = args.local or args.target_dir
    if not local:
        return handle_setup_global(force=args.force)
    target_dir = Path(args.target_dir).resolve() if args.target_dir else Path.cwd()
    target = target_dir / "AGENTS.md"
    content = bundled_agents_md()
    if target.exists() and not args.force:
        existing = target.read_text(encoding="utf-8")
        if "megaplan" in existing.lower():
            return {
                "success": True,
                "step": "setup",
                "summary": f"AGENTS.md already contains megaplan instructions at {target}",
                "skipped": True,
            }
        combined = existing + "\n\n" + content
        atomic_write_text(target, combined)
        return {
            "success": True,
            "step": "setup",
            "summary": f"Appended megaplan instructions to existing {target}",
            "file": str(target),
        }
    atomic_write_text(target, content)
    return {
        "success": True,
        "step": "setup",
        "summary": f"Created {target}",
        "file": str(target),
    }


def handle_config(args: argparse.Namespace) -> StepResponse:
    action = args.config_action

    if action == "show":
        config = load_config()
        effective: dict[str, str] = {}
        file_agents = config.get("agents", {})
        for step, default in DEFAULT_AGENT_ROUTING.items():
            effective[step] = file_agents.get(step, default)
        return {
            "success": True,
            "step": "config",
            "action": "show",
            "config_path": str(config_dir() / "config.json"),
            "routing": effective,
            "raw_config": config,
        }

    if action == "set":
        key = args.key
        value = args.value
        parts = key.split(".", 1)
        if len(parts) != 2 or parts[0] != "agents":
            raise CliError("invalid_args", f"Key must be 'agents.<step>', got '{key}'")
        step = parts[1]
        if step not in DEFAULT_AGENT_ROUTING:
            raise CliError("invalid_args", f"Unknown step '{step}'. Valid steps: {', '.join(DEFAULT_AGENT_ROUTING)}")
        if value not in KNOWN_AGENTS:
            raise CliError("invalid_args", f"Unknown agent '{value}'. Valid agents: {', '.join(KNOWN_AGENTS)}")
        config = load_config()
        config.setdefault("agents", {})[step] = value
        save_config(config)
        return {
            "success": True,
            "step": "config",
            "action": "set",
            "key": key,
            "value": value,
        }

    if action == "reset":
        path = config_dir() / "config.json"
        if path.exists():
            path.unlink()
        return {
            "success": True,
            "step": "config",
            "action": "reset",
            "summary": "Config file removed. Using defaults.",
        }

    raise CliError("invalid_args", f"Unknown config action: {action}")
