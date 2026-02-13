# Contributing (Multi-agent workflow)

This repo may have multiple AI agents (and humans) working in parallel. To avoid conflicts and duplicated work, follow the workflow below.

## Source of truth: GitHub Issues

- Every piece of work should correspond to a GitHub Issue.
- Issues are the canonical place to track ownership and status.

## Ownership rules

- **Exactly one assignee per issue**: the person/agent actively implementing it.
- If others are supporting, coordinate via comments and labels (don’t stack multiple assignees).

## Required labels

Status labels (pick exactly one):
- `status:ready` — groomed, ok to pick up
- `status:in-progress` — someone is actively working it
- `status:review` — PR open; needs review/merge
- `status:blocked` — waiting on a dependency or decision

Agent/area labels (optional but recommended):
- `agent:claw` — owned by the OpenClaw agent
- `area:backend` — backend/server work
- `area:ui` — UI/Tauri work
- `area:ingest` — ingestion/retrieval work

## Branch + PR workflow

- **One issue per branch**. Use a name like: `feature/<issue-or-phase>-<short-slug>`
- **Open a PR early** and keep scope tight.
- **No force-push** to shared branches.
- Prefer small, reviewable commits. Prefix commit messages with the issue key when practical (e.g., `G.3:`).

## Hot file coordination

Some files are likely to be edited by multiple issues (e.g., WebSocket protocol, UI state). When you touch these:
- call it out in the PR description
- keep changes localized (or split into separate commits) to reduce merge pain

## Claude / other agents

If you are an AI agent:
- assign yourself to the issue before starting
- set `status:in-progress`
- open a PR and move to `status:review`
- add an agent label if available
