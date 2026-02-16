# Meeting Buddy Roadmap

This repo uses GitHub Issues/labels as the source of truth.

## Current status (high level)
- Phases **G–J**: implemented (see closed issues / merged PRs)
- Phase **UI** (macOS redesign): implemented (see `phase-UI` labeled issues)
- Phase **K** (Contextual Intent Synthesis): implemented (see `phase-K` labeled issues)

## Phase K — Contextual Intent Synthesis

### 3.4. Intelligent Response Compounding

To ensure answers are actionable and "execute-ready," the AI implements a triple-pass response structure:

1. **Semantic Fallback:** If a specific term (e.g., "SLA") is missing, the agent automatically pivots to related synonym clusters (e.g., "Remediation," "Deadlines," "Turnaround") and reports the mapping transparently.
2. **Contextual Augmentation:** Every answer includes the 'How-To' execution context.
   - *Example:* "SLA is 30 days. [Process: To trigger an extension, email the DevOps alias]."
3. **The Compounder Logic:**
   - **Layer 1** (`bullets`): Answer the question — the direct fact from sources
   - **Layer 2** (`process_bullets`): The execution layer — how to act on this answer
   - **Layer 3** (`next_step`): Single most important follow-up action right now

**Inferred answers** (not directly in docs but derivable from pattern data) are surfaced with an explicit `inferred: true` flag and a `reasoning` explanation, preserving the "never fabricate" contract while allowing helpful inference.

### Synonym Cluster Examples

| User asks | AI also searches |
|-----------|-----------------|
| "SLA" | Timeline, Deadline, Remediation, Policy, Severity, Standard |
| "NCQA" | Compliance, Audit, Quality Standard, Accreditation, RFI |
| "owner" | Assignee, DRI, responsible party, point of contact |
| "budget" | Cost, spend, allocation, funding, estimate |
| "offboarding" | Account termination, deprovisioning, access removal |
| "incident" | Breach, security event, vulnerability, finding |

### 3.5. Proactive Suggestion Engine _(deferred — separate issue)_

When a question about a process is detected, the AI proactively drafts the "next action":
- *Example:* If a High vulnerability is discussed, the AI drafts an email/ticket template in the HUD for one-click "Copy & Send."
- Requires template generation and copy-to-clipboard UX — tracked as a separate issue.

## How to track work
- Use **Issues + labels**:
  - `status:ready | status:in-progress | status:review | status:blocked`
  - `phase-UI`, `phase-G/H/I/J`, `phase-K`
  - `area:ui | area:backend | area:ingest`

## What's next
- Check the issue list filtered by `status:ready`.
