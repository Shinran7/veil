# Orchestrator protocol

The orchestrator **coordinates only**. It scaffolds the ledger, dispatches sub-agents, merges results, runs the validator, and produces a short chat summary pointing at `outcome.md`.

Use the **Task** tool for sub-agents unless the operator explicitly requests solo mode.

**Forensic mode:** read `forensic-mode.md` every Wave 0. If `.active` points at an existing id and operator message is a follow-up, skip full tree respawn — use `follow-ups.md`.

---

## Wave 0 — Init

1. Parse the operator's **question** and **anchor** (infer or ask once).
2. Choose **domain** pack (`references/domains/<domain>.md`).
3. Create:

```
.tmp/investigations/<investigation-id>/
  evidence/
```

4. If **new** investigation: copy `templates/investigation.vbrief.json` → `investigation.vbrief.json`; write `.tmp/investigations/.active` with id. If **follow-up**: load existing ledger (see `follow-ups.md`).
5. Read `references/question-framing.md` — split operator question into **slowness** vs **terminal** (or follow-up scope).
6. Fill: `plan.title` = slowness question; `narratives.Problem` = anchor + both question clauses; `metadata.x-investigation` (domain, anchor, wave: 0).
7. Seed branches: `branch.traps`, `branch.slowness`, `branch.terminal` (not merged). Domain pack `starterTree` items hang under `branch.slowness`.
8. Seed **trap claims** under `branch.traps`.

⊗ Gather evidence in Wave 0.
⊗ Codebase search in application source — traps + runtime config first.

**Allowed in Wave 0 (no interpretation in chat):**

| Pull | Purpose | Save as |
|------|---------|---------|
| Check run / PR metadata | Anchor confirm | `evidence/gh-*.json` |
| Log file date list | Pick persistent log day | `evidence/log-dates.txt` |
| **Day-wide sanity metrics** | Epidemic vs one-off (R10) | `evidence/fleet-day-*.txt` |

**Day-wide sanity (when domain pack defines it):** Before anchor-only grep, pull fleet/day-wide counters per domain pack (e.g. jobs started/failed/completed on anchor day).

Record as `EV-FLEET-*`. ⊗ Conclude epidemic in chat — ledger only.

Set `metadata.x-investigation.chatEmbargo: true`.

---

## Evidence prefetch (before Wave 1 and branch dispatch)

Orchestrator **runs shell adapters**; sub-agents interpret `evidence/` files. Iron law 6.

**Minimum prefetch:** Run every adapter in your domain pack § Evidence adapters for Wave 0–2. Typical pattern:

1. Anchor-scoped log/trace grep → `evidence/log-anchor.txt`
2. Day-wide sanity metrics (Wave 0) if domain pack defines them
3. Runtime config snapshot → `evidence/config.txt`
4. Health/metrics snapshot → `evidence/status.json`

Register each file in `plan.references` before dispatching trap-runner or branch agents.

If prefetch blocked (no fly access): note in `Observation`; sub-agents return `blocked: needs_shell` — orchestrator retries fetch, then re-dispatches. ⊗ Close Wave 2 with trap claims still `pending` due to missing shell.

---

## Wave 1 — Trap-runner

**Goal:** Kill popular wrong theories before expensive branch work.

Dispatch **one** trap-runner sub-agent (or parallel per trap if many). Read `references/subagent-prompts.md` § Trap-runner.

Domain pack lists traps with mandatory falsification checks. On falsified trap:

- Set trap claim `status: failed`
- Add `invalidates` edge to affected branch(es)
- Set branch `failed` if trap was dispositive for that branch

Update `x-investigation.wave` → 1; set `wavesCompleted["1"]: true`.

---

## Wave 2 — Branch investigators

**Goal:** Verify every claim in surviving branches.

For each top-level branch where `status` is not `failed`:

- Dispatch **branch investigator** sub-agent (parallel).
- Pass: investigation path, `branch.<name>` id, domain pack path, anchor.

Branch agent returns: subtree updated, new `EV-*` refs, edges.

Orchestrator spot-checks: branch agent did not edit other branches.

Update `x-investigation.wave` → 2; set `wavesCompleted["2"]: true`.

---

## Wave 2b — Mechanism drill-down (mandatory when slowness asked)

**Trigger:** `branch.slowness` has a completed claim naming dominant phase `P` (e.g. context, static-analysis).

1. Add `branch.mechanism.<P>` with claims from domain pack § Phase mechanisms.
2. Dispatch branch investigator for `branch.mechanism.<P>`.
3. ⊗ Wave 5 if mechanism branch still all `pending`.

**Pass/fail:** Section 2 of `outcome.md` must cite completed mechanism claims or honest "not verified".

⊗ Name embed contention, host sickness, or queue saturation in chat before `branch.mechanism.*` resolves — chat gate applies.

When day-wide metrics show fleet epidemic, seed host/fleet mechanism branches from domain pack.

---

## Wave 3 — Falsifier

**Goal:** Attack every theory still alive.

A theory is alive if its branch is not `failed` and at least one claim is `completed` or `pending` without full branch failure.

Dispatch **one falsifier per alive branch** (parallel). Read subagent-prompts § Falsifier.

Falsifier must attempt the **cheapest disproof** first (domain pack `disproofOrder`).

Update `x-investigation.wave` → 3; set `wavesCompleted["3"]: true`.

⊗ Skip to Wave 5 — validator hard-fails (#1 CF-2).

---

## Wave 4 — Red-team

**Goal:** Assume the leading survivor is wrong.

**Lead survivor** = branch with most `completed` claims and fewest `failed`, excluding `failed` branches. Ties → red-team all tied branches sequentially.

Dispatch red-team sub-agent. Read subagent-prompts § Red-team.

Update `x-investigation.wave` → 4; set `wavesCompleted["4"]: true`.

⊗ Skip — validator hard-fails.

---

## Wave 5 — Synthesize

1. Confirm `wavesCompleted` has 1–4 all `true`.
2. Run **validator** (`investigation-profile.md` § Validator).
3. Dispatch synthesizer **or** orchestrator performs synthesis if small.

Synthesizer writes:

- `plan.narratives.Hypothesis` — ranked survivors
- `plan.narratives.Outcome` — conclusion, ruled-out list, uncertainty
- `plan.status` → `completed` (or `failed` if no verified cause)
- `.tmp/investigations/<id>/outcome.md` — operator-facing summary

Update `x-investigation.wave` → 5.

**Chat response (embargo lifted):** 2–4 sentences paraphrasing `outcome.md` §2–§3 only + path to `outcome.md`. ⊗ New mechanism language not in `outcome.md`. ⊗ Paste ledger or evidence dumps unless operator asks.

---

## Parallelism rules

| Wave | Parallel OK? |
|------|----------------|
| 1 traps | Yes (independent traps) |
| 2 branches | Yes (disjoint subtrees) |
| 3 falsifiers | Yes (per branch) |
| 4 red-team | Prefer one at a time on lead |
| 5 synthesize | Single writer |

**Ledger conflicts:** if two agents race, orchestrator re-reads file and re-dispatches failed branch only. Prefer sequential trap → branch waves to reduce merge pain.

---

## Solo mode (operator override only)

If operator says "no sub-agents" / "solo": orchestrator runs waves sequentially in one context, but must still:

- Maintain the ledger file
- Explicitly mark each claim verified/failed
- Run validator before conclusion

Solo mode is worse for exhaustive work — note in `Outcome` if used.

---

## Graduation to implementation

When operator requests a fix **after** investigation:

1. Point implementation vBRIEF at investigation via `x-vbrief/research` reference.
2. Copy only **verified** claims into story `Problem` / `LockedDecisions`.
3. Leave investigation in `.tmp/` (gitignored).