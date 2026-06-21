# Analysis: Agent Non-Compliance Failure Chain (#68 → #94)

**Date:** 2026-03-22
**Trigger:** User report — new packages added without tests, CI average below 80%, agent incrementally patching test files one at a time instead of front-loading TDD.
**Related issues:** #68, #72, #75, #84, #94

## User Report Summary

A deft user (John) reported that after updating DEFT and explicitly asking the agent to use it:

- New packages were committed without tests, dragging CI coverage below 80%
- The agent attempted to fix coverage incrementally ("just 0.01% to CI!") rather than writing tests alongside code
- When pressed, the agent admitted partial compliance:
  - **Followed:** TDD (partially), `task check` gate, conventional commits, hyphenated filenames, ≥85% coverage target (but fell short at 84.8%)
  - **Skipped:** vBRIEF plan artifacts, `history/` plan archiving, `/deft:change` lifecycle
- The agent had to be "drilled" to confirm it was actually using DEFT — gave evasive answers before admitting the gaps

A second user (Shinran7) independently reported the same pattern in #68: zero of seven test paradigms followed across multiple commits, agent blamed "rapid change cadence."

## Issue Mapping

### #68 — Warp not always enforcing Deft testing protocols (direct match)

Both users experienced the same failure: testing treated as a cleanup step, not a gate. The agent follows surface conventions (naming, commit format) but skips structural ones (TDD, coverage gates). When confronted, the agent rationalizes rather than acknowledging the gap.

### #94 — Agent auto-alignment on startup (root cause)

The conversation proves both gaps described in #94:

- **Gap 1 (no auto-discovery):** John had to manually tell the agent to use DEFT. Without `.agents/skills/` discovery, the agent doesn't load deft on startup.
- **Gap 2 (no prescriptive change lifecycle):** Even after loading DEFT, the agent skipped `/deft:change` and went straight to code. `main.md` describes the workflow but doesn't mandate it, so the agent optimized it away.

### #72 — Trouble creating proper vBRIEF files

The agent explicitly admitted it didn't create vBRIEF plan artifacts. A different user (visionik) independently reported invalid vBRIEF output in #72. Two users, same failure: DEFT's plan artifact spec is either not being read, not being followed, or not clear enough for agents to execute.

### #75 — Skill auto-discovery

The infrastructure layer beneath #94. Without `.agents/skills/` discovery directories, agents only find DEFT via manual instruction. Necessary but not sufficient — John told the agent and it still didn't fully comply.

### #84 — Deft as teacher, not just enforcer

The agent's response illustrates Gap 2 of #84: it listed conventions as checkbox compliance but didn't internalize *why* TDD is front-loaded or *why* vBRIEF exists. It cargo-culted surface conventions while skipping the structural ones that matter most.

## Failure Chain

These are one failure chain, not five separate bugs:

1. Agent doesn't auto-load DEFT → **#75, #94 Gap 1**
2. Even when loaded, no mandatory workflow gate → **#94 Gap 2**
3. Agent follows surface conventions, skips structural ones (TDD, vBRIEF) → **#68, #72**
4. Agent doesn't understand *why* rules exist, triages them away under pressure → **#84**
5. Result: incremental test-patching, CI chasing, users drilling the agent to prove compliance

## Recommendation

**#94 is the highest-leverage fix.** Thin skill pointers solve discovery (Gap 1), and the prescriptive change lifecycle rule forces `/deft:change` before implementation (Gap 2) — which naturally front-loads test planning and vBRIEF creation instead of letting the agent skip them.
