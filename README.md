# Megaplan

An AI agent harness for coordinating Claude and GPT to make and execute extremely robust plans.

Structured plan/critique/execute loop with auditable artifacts, gated behind human approval.

## Setup

Send this to your agent:

```
pip install megaplan && megaplan setup
```

That's it. Your agent now knows how to use megaplan automatically.

## Usage

Tell your agent to megaplan a task:

```
megaplan this: migrate the database to PostgreSQL
```

Or invoke directly:

```bash
megaplan init --project-dir . "migrate the database to PostgreSQL"
megaplan plan
megaplan critique
megaplan evaluate
# ... follow next_step from each response
```
