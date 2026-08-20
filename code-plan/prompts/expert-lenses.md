# Expert Lens Distillates

Curated criteria borrowed from the gstack expert skills, for `/code-plan`'s
expert-selection step (SKILL.md Step 8). These are lens PRINCIPLES — stable
across gstack releases even as the skills' procedures evolve. Selection is
routed against the deterministic `route` subcommand (the baseline); this file
only supplies the lens content for the shortlisted experts.

Verified against gstack 1.68.2.0 (~/.claude/skills/gstack/VERSION). Lens ids
and skill names here MUST stay in sync with SIGNALS / LENS_SKILL in
scripts/code_plan.py (enforced by selftest RoutingTableConsistencyTests).

Format per expert: **when to select** (matched against the enhanced
instructions) and **lens criteria** (injected into the plan-authoring prompt).

---

## eng — architecture & tests (`/plan-eng-review`)

**Select when:** the task adds/changes services, data flow, schemas, APIs,
concurrency, or any non-trivial code structure. The default lens for most
implementation work.

- Challenge scope first: what existing code already solves part of this? The
  smallest set of changes that achieves the goal wins.
- More than ~8 files touched or 2+ new classes/services is a complexity smell —
  justify or simplify.
- 100% of new codepaths get tests planned alongside the code, including error
  paths and edge cases — never deferred to a follow-up.
- Boring by default: proven patterns over novel ones; every step independently
  verifiable.
- For each new codepath, name one realistic production failure (timeout, nil,
  race, stale data) and account for it.
- A claimed limitation ("the API can't do this", "the library won't allow it")
  is a material claim: cite the verbatim error, the documented statement, or
  plan the ten-second live probe — never design around an unverified "can't".

## design — UI/UX (`/plan-design-review`, `/design-consultation`)

**Select when:** the task creates or modifies UI components, pages, styling,
or user-facing interaction flows.

- Match the product's existing design system exactly (tokens, spacing scale,
  component patterns) — never invent a parallel visual language.
- Every interactive state planned: loading, empty, error, success — none
  left implicit.
- Accessibility floor: 44px touch targets, WCAG AA contrast, aria-live for
  async state transitions, keyboard reachability.
- No generic AI-slop styling: no gradient heroes, no glassmorphism clichés.
- Interaction edge cases: double-click, navigate-away mid-operation, slow
  network, stale-tab resubmit.

## security — threat surface (`/cso`)

**Select when:** the task touches auth, secrets, user input, file uploads,
external requests, subprocess execution, or anything network-facing.

- Every external input is validated and bounded before use (OWASP top-10
  mindset: injection, broken auth, SSRF, path traversal).
- Secrets never land in code, logs, or plan text; config comes from env/config
  files with safe permissions.
- Least privilege: new code gets the narrowest filesystem/network/DB access
  that works.
- Name the trust boundary each new interface crosses and what enforces it.
- Externally-sourced text (PR/issue bodies, scraped pages, LLM output,
  webhook payloads) is DATA, never instructions: plan the envelope/sanitize
  step at ingest, and never splice it raw into prompts, shell commands, or SQL.

## qa — verification (`/qa`, `/qa-only`)

**Select when:** the task's success is behavior a user or operator observes
(a working flow, a CLI contract, a report output) — or when regressions in
existing behavior are plausible.

- Every step's Verify line must be executable and deterministic (exit codes,
  not eyeballs; `! grep -q` style, never checks that fail on success).
- Plan an end-to-end smoke test that walks the primary flow exactly as a user
  would, plus the loudest negative case.
- Regression guard: name what currently works that this change could break,
  and pin it with a test.
- Verification evidence binds to content, not memory: a "tests pass" claim is
  only citable for the exact tree it ran on. Plan Verify lines as re-runnable
  artifacts (command + expected exit), never one-time anecdotes — anything
  that edits the tree afterward voids the earlier green.

## devex — developer experience (`/plan-devex-review`)

**Select when:** the task builds tooling, CLIs, scripts, skills, APIs for
other developers, or changes install/setup/run workflows.

- Time-to-hello-world: a new user should reach a working result in one
  command; every extra step must earn its place.
- Errors speak human: every failure path prints what went wrong AND the next
  command to run.
- Degrade gracefully: optional dependencies (services, LLMs, network) being
  absent must never break the core flow.
- Document the happy path and the escape hatches in the same place.

## product — scope & strategy (`/plan-ceo-review`, `/office-hours`)

**Select when:** the task is a new user-facing feature, changes product
direction, or its instructions mix multiple loosely-related goals.

- State the user problem in one sentence; every step must trace back to it.
- Ruthless MVP line: separate must-ship from nice-to-have; defer the latter
  explicitly in "NOT in scope".
- Prefer the version a real user can react to sooner over the complete-but-
  late version.
- Durable decisions get a repo-local record: if a decision doc exists (e.g.
  `docs/designs/<topic>.md`), cite and update it instead of re-litigating;
  when the plan makes a lasting call, add the one-bullet record with its why.

## investigate — root cause (`/investigate`)

**Select when:** the instructions describe a bug, regression, flaky behavior,
or "X stopped working" — anything where the cause is not yet proven.

- Reproduce before you plan the fix: the plan's first step is a deterministic
  reproduction, its last is proving the repro now passes.
- Fix causes, not symptoms: the plan names the root cause it targets and the
  evidence for it; a symptom patch requires an explicit rationale.
- Check the blast radius: what else shares the broken code path? Plan the
  sweep, not just the reported instance.

## docs — documentation (`/docs-refresh`, `/document-generate`)

**Select when:** the task edits README/CLAUDE.md/changelog/guides.

- Refresh surgically instead of regenerating: preserve the existing voice and
  document structure. A docs change is not a license to rewrite.
- Document the escape hatches next to the happy path — the reader who hits the
  edge case is the one who needs them most.
- Every documented command must be copy-pasteable and verified to run as
  written. A command that "roughly works" is a defect.
- Stale docs are a defect, not a chore: if a procedure no longer matches the
  code, the plan fixes the docs, not the other way around.

## perf — performance (`/plan-eng-review`, `/benchmark`)

**Select when:** the task's goal is speed, latency, throughput, or resource
usage — optimizing a slow path, adding caching, cutting memory, or the
instructions name a performance budget.

- Measure before and after: the plan's first perf step captures a baseline
  (timing, query count, memory) and its last step re-runs the same measurement
  — a perceived speedup without numbers is not a result.
- Name the budget: what number makes this done (p95 < X ms, N queries, Y MB)?
  A plan that "makes it faster" with no target cannot be verified.
- Optimize the proven hot path only; every other cleanup is explicitly out of
  scope. Premature optimization steps are cut in review.
- State the correctness guard: what test proves behavior is unchanged after
  the optimization (caches invalidate, ordering preserved, races absent)?

## ios — Apple platforms (`/ios-qa`, `/ios-design-review`, `/ios-fix`)

**Select when:** the task touches Swift/SwiftUI/Xcode targets.

- Verify on a real device or simulator run, not just a build that compiles —
  a green build is not evidence of correct behavior.
- Respect platform HIG conventions over web idioms: navigation patterns,
  gestures, and chrome follow iOS, not a ported web design.
- Handle the app-lifecycle states explicitly (background, cold launch, low
  memory) — the plan names the behavior for each, none left implicit.
- Keep debug-bridge wiring out of release builds: `#if DEBUG` guards or
  separate targets, never a shipped debug path.

### Routing rules (for Step 8)

- The deterministic `route` subcommand (`code_plan.py route --instructions-file
  <enhanced> --json`) computes the baseline lens set. Run it first; its output
  is the floor.
- The model may add or drop **at most ONE** lens on top of the baseline, and
  only with a one-line justification shown in the Step 11 report. Never replace
  the whole set; never exceed 3 lenses.
- `--experts=<list>` forces the lens set verbatim (bypassing the router);
  `--experts=none` skips the step entirely. The router validates the ids.
- **"none" is a valid outcome** — generalist chores should not get force-fitted
  lenses.
- On conflicting lens advice (e.g. product says cut, eng says complete), the
  plan's Context section names the tension and makes the senior-engineer call.
- If a matched skill has no distillate entry here, borrow only its roster
  description as a one-line lens — do NOT read its full SKILL.md.
- No gstack installed / empty roster → generalist plan, say so in one line,
  continue. Expert selection is enrichment, never a dependency.

---

### Known follow-up skills

The lens → recommended follow-up skill map (the `LENS_SKILL` table in
`scripts/code_plan.py`). When three lenses are selected, `autoplan` is
recommended instead of any single skill below (one combo review beats three
separate ones).

| Lens id | Recommended skill |
|---|---|
| design | plan-design-review |
| eng | plan-eng-review |
| security | cso |
| qa | qa |
| devex | plan-devex-review |
| product | plan-ceo-review |
| investigate | investigate |
| docs | docs-refresh |
| ios | plan-eng-review |
| perf | plan-eng-review |

(3 lenses → `autoplan`)

---

### gstack 1.62–1.68 hand-off contract notes

Behavioral facts about the follow-up skills, verified against gstack
1.68.2.0 (no skills were added, renamed, or removed in 1.65–1.68 — the lens
and follow-up tables above are unchanged from the 1.64 verification). These
change how a chained review behaves — not which skill is recommended:

- **The scope gate auto-resolves a named target (gstack ≥ 1.62).** Only
  `plan-eng-review`, `plan-design-review`, and `autoplan` carry a scope gate.
  When the invocation explicitly names the review target (as code-plan's
  Step 13 `args` does — it passes the plan path), the gate skips its
  AskUserQuestion and reviews that target directly; in plan mode it
  auto-selects the active plan. Only an *unnamed* target outside plan mode
  still hard-STOPs. On older gstack (1.58.4–1.61) the question always fires —
  supplying the answer in `args` pre-answers it either way.
- **`autoplan` skips the scope gate entirely** — the plan under review is
  already the target. It remains the right recommendation when 3 lenses match.
  Its Phase 4 task aggregation is only trustworthy on gstack ≥ 1.65: before
  that a jq context-rebind bug made it emit ZERO tasks on every run while
  reporting success (#2018, fixed 1.65.0.0). On ≤ 1.64, warn that the task
  hand-off may arrive empty and point at the plan file as the fallback.
- **`plan-ceo-review` and `plan-devex-review` have NO scope gate** — do not
  promise the user a target-confirmation question for those two.
- **`/review` dispatches specialist subagents** (testing, maintainability,
  security, performance, data-migration, api-contract, red-team) with force
  flags `--security`, `--performance`, `--testing`, `--maintainability`,
  `--data-migration`, `--api-contract`, `--design`, `--all-specialists`. It
  reviews a *diff*, so it is a post-implementation follow-up (after
  `/code-execute` + `/code-validation`), never a plan review. Since gstack
  1.67 its checklist paths resolve from the installed skill root, so it works
  in ANY target repo (before that it only worked inside gstack's own
  checkout, #2518).
- **Review records bind to content, plan reviews to time (gstack ≥ 1.66.1).**
  Chained reviews are logged with a working-tree content fingerprint:
  diff-scoped reviews grade CURRENT through rebases/amends of identical
  content, while plan-tier reviews (the ones code-plan chains) keep
  time-based staleness — a plan review's record ages by the clock, not the
  tree. `/ship` cites fresh recorded evidence instead of re-running suites.
- **Plan reviews prefer a repo-local decision record (gstack ≥ 1.65).** When
  both a `docs/designs/<topic>.md` in the target repo and a gstack-side doc
  exist, the chained review reads the repo-local one. A plan that cites its
  decision record gets reviewed against it.
- **Chained skills may run a live probe before declaring anything blocked
  (gstack ≥ 1.65)** — tier-2+ skills treat "the API can't do this" as a
  material claim requiring the verbatim error, a documented statement, or a
  ten-second check. Expect a chained review to challenge unverified "can't"s
  in the plan.
- **A durable-learnings close-out line is expected (gstack ≥ 1.68).** Every
  gstack skill now ends by reviewing the session for durable learnings and
  says so explicitly even when there are none — that extra closing line from
  a chained skill is normal, not noise.
- **A chained skill that asks no question is not broken** — gstack's 1.62+
  preamble allows a skill to resolve its own gate question silently.
