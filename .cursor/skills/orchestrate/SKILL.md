---
name: orchestrate
description: >
  Coordinate other cloud agents: split a plan into tasks, launch a worker per
  task, watch their pull requests, report to the owner, and hand off to a
  fresh orchestrator. Use when asked to orchestrate, coordinate, or manage
  agents, and before launching any worker. Read `docs/orchestration.md` first.
---

# Orchestrate

Read `docs/orchestration.md` in full before you launch or message any agent.
It holds the procedure; this file only says when it applies and what you must
not forget.

- Launch each worker as a top-level cloud agent through the API, so the owner
  can open it. Use a subagent only for a short read-only question.
- Wait for events with `subscribe_github_pr` instead of polling, and end the
  turn while waiting.
- Hand off to a fresh orchestrator after about 5 merges or when your context
  is large, because each step re-reads the whole context and costs more as it
  grows.
- Check spend at each pause with `mise run spend`, and stop launching near the
  dashboard limit.
- Never merge a PR or enable auto-merge yourself.
