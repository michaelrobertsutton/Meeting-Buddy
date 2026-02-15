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

CI label:
- `ci:run` — triggers a full CI run (see [When to add ci:run](#when-to-add-cirun) below)

Agent/area labels (optional but recommended):
- `agent:claw` — owned by the OpenClaw agent
- `area:backend` — backend/server work
- `area:ui` — UI/Tauri work
- `area:ingest` — ingestion/retrieval work
- `area:native` — native SwiftUI/AppKit shell

Phase labels (for batched execution):
- `phase-A-cleanup` — independent cleanup tasks, safe to run in parallel
- `phase-B-websocket` — all touch `websocket.py`, must run **serially** in issue-number order
- `phase-C-testing` — test coverage, depends on A+B completing first

## Permissions

Meeting Buddy requires **Screen Recording** (and optionally Microphone) on macOS. Permissions are documented in one place:

- **In-app:** Meeting Buddy Settings → **Permissions** (opens the relevant System Settings panes via deep links).
- **README:** Prerequisites section describes Screen Recording and points to Settings → Permissions.

When adding or changing permission requirements, update both the Settings Permissions view and the README.

## CI policy (personal repo)

GitHub Actions is **opt-in** for PRs to avoid paid CI minutes.

- CI runs automatically on `push` to `main`
- CI runs on PRs **only** when the PR has label: `ci:run`
- CI can also be triggered manually via **Actions → CI → Run workflow** (workflow_dispatch)

### When to add `ci:run`
Add `ci:run` when at least one is true:
- You touched Tauri/Rust/Swift packaging or process-spawning logic
- You changed the WebSocket protocol or cross-component contracts (backend ↔ native ↔ UI)
- You’re ready for review/merge and want CI as the final verification gate

Avoid `ci:run` when:
- You’re iterating quickly on small changes (run local checks instead)
- The change is docs-only or a trivial refactor (unless a reviewer requests CI)

## Local dev quality tools (recommended)

We use `ruff` + `pytest` in CI. For the best experience locally, install pre-commit:

```bash
python3 -m pip install pre-commit
pre-commit install
```

This repo ships a `.pre-commit-config.yaml` that runs ruff (incl. auto-fix) and basic hygiene checks.

## Branch + PR workflow

- **One issue per branch**. Use a name like: `feature/<issue-or-phase>-<short-slug>`
- **Open a PR early** and keep scope tight.
- **No force-push** to shared branches.
- Prefer small, reviewable commits. Prefix commit messages with the issue key when practical (e.g., `G.3:`).

## Branch Protection

The `main` branch is protected to ensure code quality and prevent accidental changes:

- **No direct pushes to `main`**: All changes must go through pull requests
- **Pre-push hook**: A git hook automatically blocks direct pushes to `main` locally
- **Required workflow**: 
  1. Create a feature branch: `git checkout -b feature/my-feature`
  2. Make your changes and commit
  3. Push to your branch: `git push origin feature/my-feature`
  4. Create a PR: `gh pr create --base main --head feature/my-feature`
  5. Get review and merge via GitHub

**Setting up the pre-push hook** (first-time setup):
```bash
cp git-hooks/pre-push .git/hooks/pre-push
chmod +x .git/hooks/pre-push
```

**Note**: Full GitHub branch protection (status checks, required reviews) requires GitHub Pro for private repos. The pre-push hook provides basic protection for all contributors.

To bypass the hook in emergencies (not recommended):
```bash
git push origin main --no-verify
```

## Hot file coordination

Some files are likely to be edited by multiple issues (e.g., WebSocket protocol, UI state). When you touch these:
- call it out in the PR description
- keep changes localized (or split into separate commits) to reduce merge pain

Known hot files:
- `backend/server/websocket.py` — touched by many issues; check phase labels for serial ordering
- `ui/src-tauri/src/lib.rs` — sidecar spawn logic, hotkeys, tray menu

## Review feedback discipline (required)

We use automated PR reviews (Codex) which often leave **inline review threads** (not top-level PR comments).

Before merging any PR, reviewers/agents must check:
- Top-level PR comments
- Inline review threads

Tip (CLI): use the GraphQL `reviewThreads` query to avoid missing inline feedback.

## Claude / other agents

If you are an AI agent:
- assign yourself to the issue before starting
- set `status:in-progress`
- open a PR and move to `status:review`
- add an agent label if available
- follow the Workflow Orchestration guidelines in [CLAUDE.md](CLAUDE.md)
- after any correction: record the pattern in `tasks/lessons.md`

