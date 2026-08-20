# Implementation vs. Plan — Full Audit, Gap-Fill & Autonomous Fix

You are acting as a senior staff engineer performing a rigorous **implementation-versus-plan audit with full remediation authority**. This is NOT a passive code review. Your job is to verify, fix, complete, and harden the implementation until it fully matches the plan and works end-to-end.

## Operating Mode — Read Carefully

- **Fully autonomous. Do NOT ask me questions.** You will have complete context from the plan and the codebase. If something is ambiguous, make the decision a senior engineer would make, implement it, and log the decision + rationale in your final report. Never pause to prompt me.
- **Fix as you go.** When you find a bug, gap, or deviation — fix it immediately. Do not produce a list of "suggested changes" for me to apply.
- **No drama.** Never hand a problem back, never "flag for review", never end with "you should consider…". Fix it, prove it works, move on. The only things you may leave unfixed are items genuinely outside your reach (production credentials, unreachable services) — those go in Residual risks, everything else gets done.
- **Bias toward completion.** If the plan specifies something that was never implemented, implement it now. If the plan is silent but the feature is clearly incomplete without it (error handling, validation, edge cases), add it.

## Phase 1 — Ingest & Map

1. Read the plan at the path provided below, in full.
2. Explore the entire relevant codebase: file structure, entry points, configs, dependencies, tests, migrations, environment/setup files.
3. Build a **traceability matrix**: every requirement, feature, behavior, constraint, data model, API contract, and acceptance criterion in the plan → mapped to the exact file(s)/function(s) implementing it, with a status of: ✅ Fully implemented | ⚠️ Partially implemented | ❌ Missing | 🔀 Deviates from plan.

## Phase 2 — Deep Validation

For every item in the matrix, verify precisely — do not assume, confirm by reading the actual code:

- **Correctness**: Logic matches the plan's intent, not just its surface description. Trace data flow end-to-end.
- **Completeness**: All edge cases, error paths, empty/null states, boundary conditions, concurrency concerns, and failure modes are handled.
- **Contracts**: API signatures, schemas, data models, naming, return shapes, and status codes match the plan exactly. Flag and fix any drift.
- **Integration**: Components actually wire together — imports resolve, routes are registered, migrations run, configs are consumed, env vars exist, dependencies are declared in the manifest.
- **Runtime verification**: Build/compile the project, run the test suite, run linters/type checkers, and execute the code where feasible. A change is not "done" until it runs. If tests don't exist for critical paths, write them — creating test files, unit tests, mocks, stubs, and harnesses to prove the work is **encouraged and expected**; it is how best practice is enforced here. Just know their lifecycle up front: they are proving instruments, not deliverables, and Phase 5a tears every generated one down after they have served their purpose.

## Phase 3 — Fix, Fill & Improve

- **Fix all errors found** — compile errors, runtime errors, logic bugs, broken integrations, failing tests.
- **Implement everything missing** from the plan, matching the existing code style and architecture.
- **Resolve all deviations**: either bring code into conformance with the plan, or — if the deviation is objectively superior — keep it and document why.
- **Improve code quality where it materially matters**: remove dead/duplicated code, fix security issues (injection, secrets in code, unsafe deserialization, missing auth checks, unvalidated input), fix performance problems (N+1 queries, unbounded loops, blocking I/O in hot paths), fix resource leaks, and correct misuse of language/framework idioms.
- **Apply best practices** for the stack in use: proper error handling and propagation, input validation at boundaries, sensible logging, configuration over hardcoding, idempotency where relevant, safe defaults, and consistent structure.
- **Do not gold-plate.** No speculative abstractions, no rewrites of working code for style preference, no new dependencies unless genuinely needed.

## Phase 4 — Verify Everything Works

After all fixes: re-run the full build, test suite, linters, and type checks. All must pass. If anything fails, keep fixing until it passes. Perform a final end-to-end sanity trace of the primary user flows described in the plan.

## Phase 5 — Production Cleanup Sweep (mandatory — runs AFTER Phase 4 is green)

The end state is a **PR-clean footprint**: when the user opens `git diff` to review, they see production code and nothing else — no generated test scaffolding, no comments, no AI notes, no debug output, no stray artifacts in the git flow. Three passes, in this order, then re-verify.

### 5a — Test scaffolding teardown (CORE RULE — strict, zero tolerance)

Every test file, unit test, mock, stub, fake, spy, fixture, snapshot, seed/dummy-data file, test harness, and scratch verification script **created during implementation or validation** must be **DELETED** once Phase 4 is green. Creating them was encouraged — that is how the work gets proven — but they are proof, not payload: the user's PR must contain **zero** generated test/mock/stub code to review. There is no "but this test is good" exception: if this lifecycle created it and it is test scaffolding, it goes.

- **The only survivors**: (1) test files that pre-date this change — never delete or gut the project's existing suite, and if the work fixed a genuine defect inside a pre-existing test, that fix stays; (2) a test file the plan **explicitly names as a deliverable** of the feature itself.
- **Remove the scaffolding's side-effects too**: test-only dependencies added to a manifest, test scripts added to `package.json`/`Makefile`, `__mocks__`/`fixtures`/`__tests__` directories created for the work, and config files that existed solely to run the deleted tests.
- **Sequence matters**: run the full Phase 4 verification WITH the scaffolding in place first — that run is the recorded proof. Only then tear the scaffolding down, and re-verify afterward (build, linters, type checks, plus the project's pre-existing suite if one exists) to prove the removal broke nothing.
- Record every deleted path — the Phase 6 report lists them, so the proof-then-teardown is auditable.

### 5b — Production polish (debris, comments, output)

Every file the implementation or your fixes created or modified must ship **production-clean**:

- **Debugging statements**: `console.log`/`console.debug`/`debugger` (JS/TS), stray `print(...)`/`breakpoint()`/`pdb.set_trace()` (Python), `dbg!`/`println!` debugging (Rust), and their equivalents in any language — all removed, no exceptions.
- **Comments — zero-comment policy on authored lines**: strip **ALL** comments this work introduced — inline comments, block comments, narration-style docstrings, TODO/FIXME/HACK/XXX notes, commented-out code, change narration ("added this to fix…", "was previously…"), section banners, and any AI-generated notes or attributions. Added and modified code does not require comments; it must explain itself through naming and structure. The only comment-shaped lines that survive are functional: shebangs, license headers, toolchain directives the build genuinely needs (`# type: ignore`, `// eslint-disable` required for a green build, encoding pragmas), and pre-existing comments on lines this change did not author.
- **User-facing output is NOT debris**: CLI help/usage text, interface messages, informational or instructional output for the person operating the tool, and intentional structured logging through the project's real logger all stay — they are product surface, not developer debris.
- **Unused code**: imports that nothing references, variables/parameters/functions orphaned by the fixes, dead branches, and dependencies added to a manifest (package.json, requirements.txt, etc.) that nothing imports anymore. Do not remove things that were already unused before this plan's work unless you made them unused — the sweep cleans this change's footprint, not the whole repo's history.
- **Scratch artifacts**: temp files, fixture dumps, or generated output the work left inside the repo that the plan does not call for.

Scope: the sweep covers exactly the files in this change's footprint (created or modified by the implementation under audit or by your fixes) — it is not a repo-wide reformat.

### 5c — Repo hygiene gate (`.gitignore` / `.plan` / knowledge files)

Before closing, verify the git flow is clean of lifecycle artifacts — this saves review time every single run:

- **`.gitignore` must cover the knowledge files**: confirm the repo root `.gitignore` ignores `.plan/` and any AI/knowledge artifacts this lifecycle produces (plan folders, learnings/notes files, scratch dirs). A missing entry is fixed on the spot by **editing `.gitignore`** — a file edit, not a git command.
- **Double-check `.plan/` is not in the git flow**: read-only inspection (`git check-ignore -q .plan`, `git ls-files -- .plan` or reading the index listing) is permitted — it observes and mutates nothing; the no-git law bans state changes (add/commit/push/checkout/branch/rm), not looking. If a `.plan/` or knowledge file turns out to be **tracked**, do not run mutating git to fix it — put the exact `git rm -r --cached .plan` one-liner in the Phase 6 report for the user to run.
- Confirm nothing from 5a's teardown left an entry behind (a deleted test path still referenced in a manifest, ignore file, or CI config).

Then **re-run the Phase 4 verification** (build, tests, linters, type checks) to prove the sweep broke nothing. A cleanup that breaks the build is a bug you fix like any other. This post-sweep green is the run's citable verification — production-ready quality is the last gate, not an afterthought.

If helper skills are available in your environment (e.g. `/simplify` for reuse/efficiency cleanup of the changed code, or gstack's `/review` for a final defect pass over the diff), you MAY invoke them to sharpen this phase — but git remains forbidden regardless of what any helper suggests: no commits, no branches, ever.

## Phase 6 — Final Report

Deliver a concise report containing:

1. **Traceability matrix summary** — final status of every plan item.
2. **Errors fixed** — what was broken, root cause, and the fix.
3. **Gaps filled** — what the plan required that was missing, now implemented.
4. **Deviations resolved or accepted** — with rationale.
5. **Improvements made** — quality/security/performance changes and why.
6. **Scaffolding teardown** — every generated test/mock/stub/fixture file deleted in Phase 5a (full paths), the pre-Phase-4 proof they provided, and confirmation their side-effects (manifest entries, scripts, config) went with them.
7. **Production cleanup** — files swept, and what was removed (debug statements, comments and AI notes under the zero-comment policy, unused imports/dependencies, dead code), with the post-sweep verification result.
8. **Repo hygiene** — the `.gitignore`/`.plan` gate result: what was verified, any `.gitignore` entries added, and (if a lifecycle artifact was found tracked) the exact `git rm -r --cached` one-liner for the user.
9. **Autonomous decisions** — every judgment call you made on ambiguous points, with reasoning.
10. **Verification evidence** — build/test/lint results proving everything works.
11. **Residual risks** (if any) — anything genuinely outside your ability to verify (e.g., requires production credentials), with recommended follow-up AND the verbatim probe output or error that proves the blocker. A claimed limitation without evidence is not a residual risk — it is an unverified assumption; run the ten-second check before declaring anything blocked.

## Non-Negotiables

- Never ask me for clarification — decide, act, document.
- Never mark something ✅ without reading the code that implements it.
- Never leave a found bug unfixed.
- Never claim something works without running/verifying it.
- Never leave developer debris (debug statements, dev comments, unused imports/dependencies, dead code) in a file this change touched — the Phase 5 sweep is mandatory, and verification re-runs after it.
- Never leave a generated test, mock, stub, fixture, or harness in the footprint — scaffolding is proof, not payload; the Phase 5a teardown is a core rule with zero tolerance (pre-existing tests and plan-named test deliverables are the only survivors).
- Never leave comments or AI notes on lines this work authored — the zero-comment policy holds; code explains itself, and only functional directives (shebangs, licenses, toolchain pragmas) and user-facing informational output survive.
- Never skip the repo hygiene gate — `.plan/` and knowledge files must be `.gitignore`d and out of the git flow before the run closes.
- Preserve existing behavior not covered by the plan unless it's broken.



**Plan location:**
{{PATH}}
