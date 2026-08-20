# gstack Expert Roster — post-implementation tier

Reference for `/code-execute`'s Step 4 (execution-time awareness) and Step 6
(expert-aware recommendation / `--skill` chaining).
Verified against gstack 1.68.2.0 (`~/.claude/skills/gstack/VERSION`).

**This file is enrichment, never a dependency.** No gstack installed → the
default `/code-validation` recommendation stands alone; never block or warn
beyond one line. `/code-plan` owns the *plan-tier* lens distillates
(`skills/code-plan/prompts/expert-lenses.md`); this file covers the
*implementation-tier* experts — the ones that act on written code, a working
tree, or a running app, which is what exists after this skill finishes.

---

## The roster

| Skill | What it is | Reach for it when |
|---|---|---|
| `/code-validation` | Sibling skill: audits the implementation against the plan item-by-item and FIXES gaps; deletes the plan on full success | **Always the default next step** after execution |
| `/review` | Pre-landing diff review; dispatches specialist subagents (see below) and fixes findings | The changes are about to land; broad or risky diffs |
| `/qa` | Live browser QA of a web app via the browse daemon; **fixes** the bugs it finds | The plan built user-observable web behavior |
| `/qa-only` | Same QA sweep, **report-only** (no fixes) | You want findings without another skill editing code |
| `/cso` | Chief Security Officer mode — deep security audit | Execution touched auth, secrets, user input, uploads, subprocess, or network-facing code |
| `/design-review` | Designer's-eye QA: visual inconsistency, spacing, hierarchy, AI-slop patterns, slow interactions — then fixes them | Execution touched UI components, pages, or styling |
| `/devex-review` | Live developer-experience audit | Execution built CLIs, tooling, scripts, or install/setup flows |
| `/investigate` | Systematic debugging with root-cause investigation | Execution surfaced a failure it could not root-cause, or `[MOCKED]` hides a suspected real bug |
| `/benchmark` | Performance regression detection using the browse daemon | The plan had a perf goal or touched a hot path |
| `/health` | Code-quality dashboard | A quality snapshot of the touched area is wanted |
| `/ship` | Landing workflow: merge base, run tests, review diff, version bump, CHANGELOG, commit, push, PR — **runs git under its own contract** | Everything is validated and ready to land |

**Wrong tier here:** `plan-eng-review`, `plan-design-review`,
`plan-ceo-review`, `plan-devex-review`, and `autoplan` review *plans*, not
implementations. Post-execution they are the wrong tool — never recommend
them from this skill; they belong to `/code-plan`'s hand-off.

---

## `/review` specialist mechanics (gstack 1.64+, verified 1.68.2)

`/review` reviews the working-tree diff against the base branch, then
dispatches specialist subagents in parallel. Knowing the dispatch rules lets
you predict — and force — coverage:

- **Always dispatched** (diff ≥ 50 lines): `testing`, `maintainability`.
- **Diff < 50 lines → ALL specialists are skipped** ("Small diff" notice).
  A tiny-but-risky change needs a force flag to get specialist eyes.
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
- **Force flags** (put them in the `args` when chaining): `--security`,
  `--performance`, `--testing`, `--maintainability`, `--data-migration`,
  `--api-contract`, `--design`, `--all-specialists` — each force-includes
  its specialist regardless of scope and gating.
- Since gstack 1.67 its checklists resolve from the installed skill root, so
  it works in ANY target repo (before that, only inside gstack's checkout).

Practical rule: when chaining `/review` after a security-, migration-, or
API-relevant execution, append the matching force flag(s) in `args` rather
than trusting scope detection.

---

## Routing table — what execution touched → which expert to name

Used by Step 6's advisory (pick at most TWO rows; the `/code-validation`
line always comes first). Judge "touched" from the files the plan actually
changed, not from the plan's aspirations.

| Execution touched | Recommend (after validation) |
|---|---|
| Auth, secrets, user input, subprocess, network-facing code | `/cso` (deep audit) — or `/review --security` when a diff-scoped pass is enough |
| UI components, pages, styling, interaction flows | `/design-review`; add `/qa` if the flow is user-walkable |
| User-observable web behavior (a flow, a page, an endpoint UI) | `/qa` (fixes) or `/qa-only` (report only) |
| CLI, tooling, scripts, install/setup, developer-facing APIs | `/devex-review` |
| DB schema or data migrations | `/review --data-migration` |
| Public/consumed API surface | `/review --api-contract` |
| A perf target the plan named | `/benchmark` (baseline vs. after) |
| Large diff (>200 lines) or several subsystems | `/review` (red team self-activates at this size) |
| `[MOCKED]` items masking a suspected real defect, or an unexplained failure | `/investigate` |
| Clean, validated, ready to land | `/ship` |

---

## Execution-time awareness (facts that change how Step 4 behaves)

- **Verification evidence binds to tree content (gstack ≥ 1.66.1).** A
  "tests pass" claim is only citable for the exact tree it ran on — any edit
  afterward voids it. Consequence for the executor: run the FINAL full
  verification pass after the LAST edit, never before; `/ship` will re-run
  anything the tree has outgrown, so a stale green wastes nobody's trust but
  a final-pass-then-tweak ordering wastes yours.
- **A blocked turn-end may be the verify-gate (gstack ≥ 1.65, opt-in Stop
  hook).** If the repo declares a verify command in CLAUDE.md and the user
  armed `gstack-verify-gate`, the turn cannot end until it passes. Run the
  declared command and fix; do not treat the block as a harness bug.
- **Guardrails fail closed (gstack ≥ 1.66.1).** `/freeze`/`/guard` deny
  edits outside their boundary (including symlink escapes), and `/careful`'s
  HIGH tier hard-denies `rm -rf /`-class deletes and default-branch force
  pushes. A denied tool call during execution may be a deliberate guardrail:
  report which step is blocked and by what; never work around it.
- **Claimed limitations need evidence (gstack ≥ 1.65).** Declaring a backend
  "unreachable" or an API "can't do this" is a material claim — the
  execute-prompt's single reachability probe IS that evidence; cite its
  verbatim failure next to each `[MOCKED]` flag.
- **Chained-skill behaviors that are NOT bugs:** a chained gstack skill may
  resolve its own gate questions silently when the target is named in `args`
  (≥ 1.62), may run a live probe before accepting a "can't" (≥ 1.65), and
  ends with an explicit durable-learnings close-out line even when there are
  none (≥ 1.68). `/review` spawns subagents and `/ship` runs git — each
  under its OWN contract; code-execute's laws end at the hand-off.
