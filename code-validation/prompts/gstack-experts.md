# gstack Expert Roster — validation tier

Reference for `/code-validation`'s Step 4 (audit-time awareness) and Step 6
(expert-aware recommendation / `--skill` chaining).
Verified against gstack 1.68.2.0 (`~/.claude/skills/gstack/VERSION`).

**This file is enrichment, never a dependency.** No gstack installed → the
plain `next: /review — …` advisory stands (or is dropped if even /review is
absent); never block or warn beyond one line. `/code-plan` owns the
*plan-tier* lens distillates; `/code-execute` carries the implementation-tier
twin of this file. This one is tuned to validation's seat in the lifecycle:
the code is already written AND audited/fixed when Step 6 runs, so the
experts here are the pre-landing and landing tier.

---

## The roster

| Skill | What it is | Reach for it when |
|---|---|---|
| `/review` | Pre-landing diff review; dispatches specialist subagents (see below) and fixes findings | **The default next step** after a validated audit — the diff is exactly what it wants |
| `/ship` | Landing workflow: merge base, run tests, review diff, version bump, CHANGELOG, commit, push, PR — **runs git under its own contract** | The validated diff is clean and ready to land |
| `/qa` | Live browser QA of a web app via the browse daemon; **fixes** the bugs it finds | The audited work is user-observable web behavior |
| `/qa-only` | Same QA sweep, **report-only** (no fixes) | You want findings without another skill editing the just-validated code |
| `/cso` | Chief Security Officer mode — deep security audit | The audit's fixes touched auth, secrets, user input, uploads, subprocess, or network-facing code and a diff-scoped `--security` pass is not enough |
| `/design-review` | Designer's-eye QA: visual inconsistency, spacing, hierarchy, AI-slop patterns, slow interactions — then fixes them | The audited work touched UI components, pages, or styling |
| `/devex-review` | Live developer-experience audit | The audited work is CLIs, tooling, scripts, or install/setup flows |
| `/investigate` | Systematic debugging with root-cause investigation | A Residual-risk item hides a suspected real defect the audit could not reach |
| `/benchmark` | Performance regression detection using the browse daemon | The plan had a perf target the audit should be held to |
| `/health` | Code-quality dashboard | A quality snapshot of the touched area is wanted |

**Phase-5 sharpeners** (invoked DURING the audit, not chained after it): the
built-in `/simplify` (reuse/efficiency cleanup of the changed code) and
gstack `/review` may sharpen the cleanup sweep — LAW 1 still binds: no
helper's suggestion ever justifies git.

**Wrong tier here:** `plan-eng-review`, `plan-design-review`,
`plan-ceo-review`, `plan-devex-review`, and `autoplan` review *plans*. The
plan is about to be DELETED by the LAW 6 close-out — never recommend a
plan-tier review from this skill.

---

## `/review` specialist mechanics (gstack 1.64+, verified 1.68.2)

`/review` reviews the working-tree diff against the base branch, then
dispatches specialist subagents in parallel. Since the Step 6 advisory
recommends it by default, knowing the dispatch rules lets the advisory name
the force flags that guarantee the right coverage:

- **Always dispatched** (diff ≥ 50 lines): `testing`, `maintainability`.
- **Diff < 50 lines → ALL specialists are skipped** ("Small diff" notice).
  A small-but-risky validated diff needs a force flag to get specialist eyes.
- **Scope-gated**: `security` (auth scope, or backend scope + >100 lines),
  `performance` (backend or frontend scope), `data-migration` (migration
  files present), `api-contract` (API scope).
- **Adaptive gating**: a conditional specialist with 0 findings in 10+ past
  dispatches is auto-gated OFF — except `security` and `data-migration`,
  which are `[NEVER_GATE]` insurance policies.
- **`red-team`**: activates only when the diff exceeds 200 lines OR any
  specialist reported a CRITICAL finding; it attacks the already-reviewed
  code and merges extra findings (tagged `"specialist":"red-team"`).
  Fails/timeouts are skipped silently — no force flag summons it.
- **Force flags** (append to the advisory line or the chained `args`):
  `--security`, `--performance`, `--testing`, `--maintainability`,
  `--data-migration`, `--api-contract`, `--design`, `--all-specialists` —
  each force-includes its specialist regardless of scope and gating.
- Since gstack 1.67 its checklists resolve from the installed skill root, so
  it works in ANY target repo (before that, only inside gstack's checkout).

---

## Routing table — what the audit's fixes touched → what to recommend

Used by Step 6's advisory: the `/review` line comes first, carrying every
matching force flag; at most ONE extra expert line follows. Judge "touched"
from the files the audit actually fixed or filled, not from the plan's
aspirations.

| The audit's fixes touched | Advisory addition |
|---|---|
| Auth, secrets, user input, subprocess, network-facing code | `--security` on the /review line; `/cso` as the extra line when the surface is broad |
| DB schema or data migrations | `--data-migration` on the /review line |
| Public/consumed API surface | `--api-contract` on the /review line |
| UI components, pages, styling | `--design` on the /review line; `/design-review` as the extra line for a live visual pass |
| User-observable web behavior | `/qa` (fixes) or `/qa-only` (report only) as the extra line |
| CLI, tooling, scripts, install/setup flows | `/devex-review` as the extra line |
| A perf target the plan named | `/benchmark` as the extra line |
| Residual risk hiding a suspected real defect | `/investigate` as the extra line |
| Diff under 50 lines but risk-bearing | The matching force flag(s) — without them /review dispatches NO specialists at this size |
| Clean and ready to land | `/ship` as the extra line |

---

## Audit-time awareness (facts that change how Step 4 behaves)

- **Verification evidence binds to tree content (gstack ≥ 1.66.1).** A
  "tests pass" claim is only citable for the exact tree it ran on — any edit
  afterward voids it. The Phase-5 post-sweep re-verification is therefore
  the run that matters: it comes after the LAST edit, so its green is the
  citable one. `/ship` re-runs anything the tree has outgrown, so a
  verify-then-tweak ordering wastes the evidence.
- **Residual risks need evidence (gstack ≥ 1.65).** Declaring a service
  "unreachable" or an API "can't do this" is a material claim — cite the
  verbatim probe output or error next to each Residual-risk item; a chained
  gstack skill may re-probe and challenge an unverified "can't".
- **A blocked turn-end may be the verify-gate (gstack ≥ 1.65, opt-in Stop
  hook).** If the repo declares a verify command in CLAUDE.md and the user
  armed `gstack-verify-gate`, the turn cannot end until it passes. Run the
  declared command and fix; do not treat the block as a harness bug.
- **Guardrails fail closed (gstack ≥ 1.66.1).** `/freeze`/`/guard` deny
  edits outside their boundary (including symlink escapes), and `/careful`'s
  HIGH tier hard-denies `rm -rf /`-class deletes and default-branch force
  pushes. A fix denied by a guardrail is reported (which item, blocked by
  what), never worked around — it lands in Residual risks if it cannot be
  fixed inside the boundary.
- **Chained-skill behaviors that are NOT bugs:** a chained gstack skill may
  resolve its own gate questions silently when the target is named in `args`
  (≥ 1.62), may run a live probe before accepting a "can't" (≥ 1.65), and
  ends with an explicit durable-learnings close-out line even when there are
  none (≥ 1.68). `/review` spawns subagents and `/ship` runs git — each
  under its OWN contract; code-validation's laws end at the hand-off (but
  LAW 6's close-out still runs afterward, in Step 7).
