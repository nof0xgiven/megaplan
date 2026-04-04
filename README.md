# Megaplan

A general-purpose planning and execution harness for LLMs. Megaplan helps any model solve complex tasks through structured phases — prep, plan, critique, gate, execute, and review.

Instead of attempting tasks in one shot, Megaplan gives models a rigorous process: plan the approach, critique it for issues, gate whether to proceed or revise, then execute with verification.

## Features

- **Structured phases**: prep → plan → critique → gate → finalize → execute → review
- **Critique with flags**: Parallel per-check critique that raises typed flags (blocking, significant, minor)
- **Gate enforcement**: LLM-driven gate decides proceed vs iterate, with structured flag resolutions
- **Provider routing**: Support for multiple LLM providers (OpenRouter, Zhipu/GLM, MiniMax, Google Gemini) with API key pooling and automatic failover
- **Robustness levels**: light (no structured critique), standard (4 checks), heavy (8 checks + prep research)
- **Model-agnostic**: Use different models for different phases (e.g. GLM for execution, MiniMax for critique)

## Quick Start

```bash
pip install megaplan-harness
megaplan init --project-dir . "Fix the authentication bug in login.py"
megaplan plan --plan <name>
megaplan critique --plan <name>
megaplan gate --plan <name>
megaplan finalize --plan <name>
megaplan execute --plan <name>
```

## SWE-bench Experiment

Megaplan is being used in a live experiment to test whether open-source models can beat Claude Opus 4.5 on [SWE-bench Verified](https://www.swebench.com):

- **Live dashboard**: [peteromallet.github.io/swe-bench-challenge](https://peteromallet.github.io/swe-bench-challenge/)
- **Experiment code**: [megaplan-autoimprover](https://github.com/peteromallet/megaplan-autoimprover)

## License

MIT
