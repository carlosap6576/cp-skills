---
name: code-validation
version: "1.6.0"
description: "Validate a completed implementation against its plan. -p/--path points at the plan .md the implementation was built from; when omitted, auto-discovery looks in the .plan folder at the repo root — exactly one plan there is validated with ZERO prompts, and only ambiguity (missing folder, no plans, or 2+ plans) asks for the path. Audits the implementation item-by-item and autonomously FIXES every issue found (code edits allowed; the plan file is never edited during validation). Creating tests/mocks/stubs to prove the work is encouraged, but they are proof, not payload: a mandatory production-cleanup sweep DELETES every generated test/mock/stub file after verification is green (pre-existing tests and plan-named test deliverables survive), polishes every touched file to a zero-comment production standard (no debug statements, no comments or AI notes on authored lines, no unused imports/dependencies — only functional directives and user-facing CLI/interface output survive), and passes a repo hygiene gate (.gitignore covers .plan/ and knowledge files; nothing lifecycle-generated is in the git flow), re-verified after the sweep. After a fully successful run, the plan file itself is DELETED as the close-out, and the run's final line states the deletion plus a same-session continuation note (any follow-up concerns keep going right here). Never runs git. --skill=<skill> chains a follow-up skill (e.g. --skill=review runs gstack's pre-landing /review) after the audit completes; otherwise an expert-aware next-step recommendation is printed (gstack roster in prompts/gstack-experts.md: /review specialists + force flags, /qa, /cso, /design-review, /devex-review, /ship, …)."
argument-hint: 'code-validation -p skills/plans/<plan>.md [--skill=review]'
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Skill
license: "Proprietary - All Rights Reserved (see LICENSE)"
user-invocable: true
metadata:
  emoji: "✅"
  requires:
    env: []
    optionalEnv: []
    bins: [python3]
    files: ["scripts/*", "prompts/*"]
    tags: [validation, audit, remediation, agent-skill, code-validation]
---

# SKILL CONTRACT — READ BEFORE ANY TOOL CALL

You are inside the `/code-validation` skill. It takes one input (the path to the
plan `.md` that a completed implementation was built from), renders the
validation audit prompt, and then follows that prompt as instructions — auditing
the implementation against the plan and FIXING every issue it finds, from the
repo root that contains the plan file.

Six laws govern this skill. Each maps to a specific failure mode:

- **LAW 1 — NEVER run git.** No `git add` / `commit` / `push` / `checkout` /
  `branch`. The user reviews and commits the fixes. Running git here is a
  contract violation.
- **LAW 2 — The rendered prompt is INSTRUCTIONS TO FOLLOW, never text to echo.**
  Do not print it, summarize it, or paste it into chat. Read it and act on it.
- **LAW 3 — Never modify the plan file during validation.** The plan `.md` is
  the source of truth you validate the implementation AGAINST — never edit or
  rename it, and never delete it while any phase is still running. An mtime
  check at the end verifies it is byte-for-byte untouched. This is the one law
  whose *scope* differs from code-execute: implementation edits are not just
  allowed, they are the job — fixes land in the implementation code, never in
  the plan. The ONLY sanctioned deletion is the LAW 6 close-out, which runs
  strictly after the integrity check has passed.
- **LAW 4 — Report faithfully.** Never mark a matrix item ✅ without reading the
  implementing code. Never claim something works without running it. Never leave
  a found bug unfixed. (Lifted from the prompt's Non-Negotiables so the contract
  survives even a truncated prompt read.)
- **LAW 5 — Ship production-clean and PR-clean, no drama.** Fix everything
  found — never hand a problem back, never "flag for the user's attention"
  what you can fix yourself. Creating test files, unit tests, mocks, and
  stubs to prove the work is encouraged — best practice demands it — but
  after verification is green, the mandatory Phase 5 sweep enforces three
  strict rules over this change's footprint:
  1. **Scaffolding teardown (core rule, zero tolerance)** — every test/mock/
     stub/fixture/harness file *created during implementation or validation*
     is DELETED after it has served as proof, so the PR contains zero
     generated test code to review. Pre-existing tests and test files the
     plan explicitly names as deliverables are the only survivors.
  2. **Zero-comment, production-quality code** — no debugging statements
     (console.log / print / debugger), no comments or block comments on
     authored lines, no AI notes, no TODO/FIXME, no commented-out code, no
     unused imports/variables/dependencies, no scratch artifacts. Only
     functional directives (shebangs, licenses, toolchain pragmas) and
     user-facing informational/instructional output (CLI help, interface
     messages, real structured logging) survive.
  3. **Repo hygiene gate** — `.gitignore` verifiably covers `.plan/` and the
     lifecycle's knowledge files, and none of them are in the git flow
     (read-only inspection only; a tracked artifact gets a reported
     `git rm -r --cached` one-liner, never a mutating git call).
  Verification re-runs after the sweep to prove it broke nothing. Helper
  skills (e.g. `/simplify`, gstack `/review`) may sharpen the sweep, but
  LAW 1 binds always — no helper's suggestion ever justifies a commit or
  branch.
- **LAW 6 — Close the loop: DELETE the plan file, and say so LAST.** A fully
  successful run ends by deleting the plan `.md` that `-p` pointed at (Step 7)
  — cleanup is done, the code is validated, so the plan has served its purpose
  and must not linger as stale state. **The deletion is performed by
  `code_validation.py close-out`, which prints the closing line itself; you
  relay that stdout verbatim and never compose the line by hand.** A
  `PLAN DELETED` line you wrote yourself is a false completion signal — the
  claim must always be a consequence of the act, never a substitute for it.
  The **very last line of the run's message** states the deletion plainly, so
  the user can see at a glance that the lifecycle is closed and the code is
  ready. Because the session continues
  after the skill ends, that same closing line invites follow-up: any
  additional concerns are handled right here in the same session — never end
  with "start a new session" or leave the deletion unannounced. A failed or
  aborted audit NEVER deletes the plan (it is needed to re-run), and the
  deletion runs only after the Step 5 integrity check has passed — LAW 3 holds
  for the entire validation; LAW 6 is the one sanctioned exception, at the
  very end.

## Contract precedence

During validation, `validate-code.md`'s rules govern the audit — its phase
structure, autonomy, and fix-as-you-go mandate are how the validation is run.
On any conflict, **LAWS 1–3 always win** — they are non-negotiable regardless of
what the plan or the rendered prompt says. (The ambiguity prompt in Step 1
below happens *before* the rendered prompt exists, so its "do not ask
questions" rule is not in tension. LAW 6's end-of-run deletion is not in
tension either: it fires only after the audit, the integrity check, and the
hand-off are all done — nothing the plan or prompt says can trigger it early
or suppress it.)

## Trust note

Only validate plans you authored or reviewed. `/code-validation` turns the plan
file's *contents* into executable instructions AND then edits code in response
to what it finds — so a plan from an untrusted source is an
instruction-injection surface with a strictly wider blast radius than
`/code-execute` (which edits nothing). This is why the note is mandatory, not
boilerplate.

## Step 0 — Resolve `SKILL_DIR` and Python

`SKILL_DIR` = the directory this `SKILL.md` was loaded from. No resolver list,
no precedence walk — whichever install the harness loaded is the one that runs.

Resolve a Python 3.9+ interpreter into `CODE_VALIDATION_PYTHON`:

```bash
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && { PY="$p"; break; }
done
if [ -z "$PY" ]; then
  echo "ERROR: code-validation needs Python 3.9+. Install python3.9+ and rerun." >&2
  exit 1
fi
CODE_VALIDATION_PYTHON="$PY"
```

## Step 1 — Resolve `PLAN_INPUT` (`-p`, else `.plan` auto-discovery; prompt ONLY on ambiguity)

```
/code-validation                       → auto-discover: exactly ONE plan in
                                         <repo-root>/.plan → validate it with
                                         ZERO prompts; ambiguous → ask
/code-validation -p <plan.md>          → one-shot: zero prompts, validate + fix
  (long: --path=<plan.md>)
--skill=<skill>                        → after the audit completes, invoke that
  (short: -s <skill>)                    skill (default: none — see Step 6)
```

**`-p`/`--path=<file>` given (non-empty)** → `PLAN_INPUT` is its value; go
straight to Step 2, no prompt. An empty flag value (`--path=` / `-p ""`)
counts as not provided. `--skill` is optional and never prompted for; an
empty `--skill=` means no chaining.

**`-p` absent or empty** → run auto-discovery FIRST — never ask while the
answer is discoverable:

```bash
PLAN_INPUT="$("$CODE_VALIDATION_PYTHON" "$SKILL_DIR/scripts/code_validation.py" default-plan)"
rc=$?
```

`default-plan` looks in the `.plan` folder at the repo root (found by walking
up from the cwd for a `.git` entry — a pure filesystem walk, no git commands,
LAW 1 intact; exactly where `/code-plan` saves by default):

- **Exactly ONE `.md` file** → exit 0; `PLAN_INPUT` is the printed absolute
  path. Announce it in one line — *"No `-p` given — auto-selected the only
  plan in `.plan/`: `<file>`"* — then proceed DIRECTLY to Step 2. **Do NOT
  ask for confirmation, do NOT restate the path as a question** — a single
  plan is unambiguous and the run stays zero-prompt end to end. (Asking
  "just confirm the one above" here is the exact regression this rule
  exists to prevent.)
- **`.plan/` missing, empty of `.md` files, or holding 2+ plans** → exit 2.
  ONLY NOW ask — this is the one genuinely ambiguous case. Relay the stderr
  reason (the 2+ case lists every candidate as a ready-to-paste `-p` line),
  then ask plainly (open prose, not `AskUserQuestion`):

  > Which plan should I validate the implementation against? Give me the path to the plan `.md`.

  **STOP and wait for the reply.** The reply is `PLAN_INPUT`.

## Step 2 — Validate with `plan-check`

```bash
PLAN_ABS="$("$CODE_VALIDATION_PYTHON" "$SKILL_DIR/scripts/code_validation.py" plan-check --plan "$PLAN_INPUT")"
# NOT `status=$?` — `status` is a READ-ONLY special parameter in zsh (an alias
# for `$?`), so that assignment aborts the block and a valid plan is falsely
# rejected. `rc` is safe in bash, zsh, and dash alike.
rc=$?
if [ "$rc" -ne 0 ]; then
  # PLAN_ABS is empty here — the one-line reason is on stderr.
  echo "code-validation: $PLAN_INPUT rejected — see error above." >&2
  exit 2
fi
# GNU stat first, BSD/macOS stat as fallback — the LAW 3 check must work on
# both, and must never silently no-op because `stat -c` is unsupported.
PLAN_MTIME="$(stat -c %Y "$PLAN_ABS" 2>/dev/null || stat -f %m "$PLAN_ABS")"
```

- Exit 2 + stderr reason (`plan file does not exist`, `not a .md file`,
  `plan file is not UTF-8 text`, `plan file is empty`,
  `no "### " step headings — not an executable plan`) → report
  the one-line reason and STOP. Do not loop.
- `plan-check` prints the **absolute** path on success; capture it as `PLAN_ABS`
  and use it everywhere downstream (never re-resolve the raw `-p` value).
- Record `PLAN_MTIME` now for the Step 5 integrity check.

## Step 3 — Resolve the execution root and render

```bash
EXEC_ROOT="$(git -C "$(dirname "$PLAN_ABS")" rev-parse --show-toplevel 2>/dev/null || dirname "$PLAN_ABS")"
cd "$EXEC_ROOT"
TMP="$(mktemp -d -t code-validation-XXXXXX)"
chmod 700 "$TMP"
"$CODE_VALIDATION_PYTHON" "$SKILL_DIR/scripts/code_validation.py" render \
  --plan "$PLAN_ABS" > "$TMP/rendered-prompt.md"
```

- The cwd contract: the audit runs from the repo root that **contains** the plan
  file — that is where the implementation lives, and the prompt uses
  repo-root-relative paths. Auditing from elsewhere silently targets the wrong
  tree. `cd "$EXEC_ROOT"` for all subsequent validation work.
- `render` substitutes exactly one token: `{{PATH}}` → the absolute plan path.
  A leftover `{{TOKEN}}` (template was hand-edited) exits 3 — see
  Troubleshooting.

## Step 4 — Execute the rendered prompt

`Read` `$TMP/rendered-prompt.md` and **follow it as your instructions** (LAW 2).
That means: read the plan file at `$PLAN_ABS`, then run the full six-phase
audit `validate-code.md` prescribes — build the traceability matrix, deep-
validate every item, fix/fill/improve the implementation, re-run build/tests/
linters until green, run the production cleanup sweep (tear down every
generated test/mock/stub after it has served as proof, polish every touched
file to the zero-comment production standard, pass the `.gitignore`/`.plan`
repo hygiene gate, and re-verify after it — LAW 5), then deliver the Phase-6
report. The report's final line must be exactly:

```
VALIDATION COMPLETE — {N} plan items verified, {F} fixed, {G} gaps filled, {C} files production-cleaned, {S} scaffolding files removed.
```

(`N`, `F`, `G`, `C`, `S` are the counts from the actual audit — never
fabricated. `C` counts the files swept in Phase 5; a footprint already clean
still counts as swept — the sweep ran, that is what `C` attests. `S` counts
the generated test/mock/stub files deleted in the Phase 5a teardown; `0` is a
legitimate value when the work needed no scaffolding, but it must be the
truth of the teardown pass, not a skipped pass.)

Every fix lands in implementation code; the plan file is never touched (LAW 3).

**Audit-time gstack awareness.** When gstack is installed, the "Audit-time
awareness" section of `$SKILL_DIR/prompts/gstack-experts.md` applies while
running the phases: the Phase-5 post-sweep re-verification is the citable
green (verification evidence binds to tree content on gstack ≥ 1.66.1 — it
must come after the LAST edit), each Residual-risk item cites the verbatim
probe output that proves the blocker, a fix denied by
`/freeze`/`/guard`/`/careful` is a deliberate guardrail to report rather
than circumvent, and an armed `gstack-verify-gate` holds the turn open until
the repo's declared verify command passes. No gstack → none of this applies;
audit normally.

## Step 5 — Integrity check and cleanup

Run on EVERY exit path, including failure:

```bash
PLAN_MTIME_NOW="$(stat -c %Y "$PLAN_ABS" 2>/dev/null || stat -f %m "$PLAN_ABS")"
if [ -z "$PLAN_MTIME" ] || [ -z "$PLAN_MTIME_NOW" ]; then
  echo "WARN: could not stat the plan file — LAW 3 integrity check did not run." >&2
elif [ "$PLAN_MTIME_NOW" != "$PLAN_MTIME" ]; then
  echo "LAW 3 VIOLATION: the plan file was modified during validation." >&2
fi
rm -rf "$TMP"
```

An empty `PLAN_MTIME` on either side means the check could not run — say so
loudly rather than reporting a false all-clear. This check must run BEFORE the
Step 7 deletion — a deleted plan can no longer be stat'd, so skipping ahead
would silently void the LAW 3 guarantee.

## Step 6 — Recommend or chain the follow-up (only after a successful Step 4)

Run this ONLY when Step 4 ended with the `VALIDATION COMPLETE` report. A
failed or aborted audit gets no recommendation and no chaining.

**No `--skill` given → print the expert-aware advisory and stop.** The first
line is always:

```
next: /review — pre-landing review of the validated diff{ --security --data-migration …}
```

Force flags are appended ONLY when the audit's fixes touched that ground —
`--security` (auth, secrets, user input, subprocess, network-facing code),
`--data-migration` (schema/migrations), `--api-contract` (public API
surface), `--design` (UI/styling) — per the routing table in
`$SKILL_DIR/prompts/gstack-experts.md`. Flags matter: a diff under 50 lines
dispatches NO `/review` specialists without them. Then, when the table
matches, append **at most ONE** extra expert line of the form:

```
also: /<skill> — <one-line reason tied to what the fixes touched>
```

e.g. `also: /qa — the audited flow is user-walkable in the browser` or
`also: /ship — the validated diff is clean and ready to land`. Nothing
matches, or no gstack → the bare `next: /review — …` line stands alone.
Maximum 2 advisory lines total — a recommendation, not a report. Advisory
means advisory: never auto-invoke any of it.

**`--skill`/`-s` given → chain it.** This makes
`/code-validation -p plan.md --skill=review` behave as "validate + fix, then
run the pre-landing review" — one command, zero extra prompts.

Resolve the skill name first:
- Strip a leading `/`.
- Apply the **alias map**: `review|pr → review`, `test|tests|qa → qa`,
  `security|sec → cso`, `design → design-review`, `devex|dx → devex-review`,
  `perf|benchmark → benchmark`, `debug|investigate → investigate`,
  `ship → ship`. An unknown name is passed through unchanged — the Skill
  tool reports it if unavailable. (The roster of what each expert does is
  in `$SKILL_DIR/prompts/gstack-experts.md`.)
- `code-validation` itself → refuse in one line ("won't chain code-validation
  into itself") and skip this step. The audit is already done; nothing is
  lost.

Then invoke it with the `Skill` tool — never by printing the slash command as
text — with `args`: `The review target is the working-tree diff: an
implementation validated and fixed against the plan at {PLAN_ABS}. The
changes are uncommitted.` For `review`, append the matching specialist force
flag(s) (`--security`, `--data-migration`, `--api-contract`, `--design`, …)
when the audit's fixes touched that ground — a diff under 50 lines
dispatches NO specialists without them (see gstack-experts.md).

Rules for this step:
- **code-validation's laws end at the hand-off.** The chained skill runs
  under its OWN contract — `/review` spawns its specialist subagents,
  `/ship` runs git (tests, commit, push, PR) under its own contract; LAW 1
  binds THIS skill, not the skill the user explicitly chained. Do not police
  the chained skill with LAWS 1-4.
- **The Phase-6 report and the Step 5 integrity check must already have run**
  before chaining. A chained-skill failure must never cost the user their
  fixes — report it in ONE line ("`/{name}` isn't available — validation is
  complete, run it manually") and stop; do not retry.
- **gstack contract notes (verified against gstack 1.68.2.0; details in
  `prompts/gstack-experts.md`):** a chained skill may resolve its own gate
  questions silently when the target is named in `args` (≥ 1.62) — asking
  nothing is not broken. `/review` dispatches its specialist subagents
  itself (testing, maintainability, security, performance, data-migration,
  api-contract, red-team) and works in any target repo since 1.67; do not
  pre-select specialists beyond force flags and context in `args`. A
  durable-learnings close-out line at the end of a chained gstack skill is
  expected (≥ 1.68), not noise.
- **Step 7 still runs after this step** — whether the run ended with the
  advisory line or a chained skill, the LAW 6 close-out (plan deletion + the
  final announcement line) is what actually ends the run.

## Step 7 — LAW 6 close-out: delete the plan and announce it LAST (strict)

Run this ONLY when ALL of the following are true — otherwise skip it entirely
and leave the plan file in place:

1. Step 4 ended with the `VALIDATION COMPLETE` report (a failed or aborted
   audit keeps its plan for the re-run);
2. the Step 5 integrity check ran and reported no LAW 3 violation;
3. Step 6 has finished (the advisory line was printed, or the chained skill
   returned — success or failure of the *chained* skill does not matter; the
   validation itself succeeded and its lifecycle closes regardless).

**The deletion and the announcement are ONE tool call.** You do not write the
closing line — `close-out` deletes the plan, verifies it is gone, and prints
the line for you. Run it:

```bash
"$CODE_VALIDATION_PYTHON" "$SKILL_DIR/scripts/code_validation.py" close-out \
  --plan "$PLAN_ABS"
rc=$?
```

- **exit 0** → stdout holds the `PLAN DELETED — …` line. Copy that line
  **verbatim** as the very last line of your message.
- **exit 1** → the file could not be removed. stdout is EMPTY and stderr holds
  a `WARN: could not delete …` line. Relay the WARN instead. There is no
  deletion line to write.
- **exit 2** → the path was not a plan-shaped file (a directory, or not
  `.md`). `$PLAN_ABS` is wrong; relay the stderr reason and delete nothing.

Strict rules for this step:
- **Never type the `PLAN DELETED` line yourself.** It is output to relay, not
  a sentence to compose. If `close-out` did not print it, it does not go in
  your message — no exceptions, no paraphrase, no "for completeness". Writing
  it by hand is exactly the bug this design removes: the claim must remain a
  consequence of the deletion, never a substitute for it.
- The line is the LAST line — nothing prints after it. If anything else still
  needs saying, say it first.
- Never point `close-out` at any path other than `$PLAN_ABS` (the exact path
  `plan-check` resolved) — not sibling plans, not the `.plan/` folder. The
  subcommand refuses directories and non-`.md` files, but the right path is
  still yours to pass.
- The same-session continuation note is part of the contract, not flourish:
  the user must see that follow-up concerns are handled here, in this
  session, without re-running the skill. It is already in the printed line.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `default-plan` exits 2: "no .plan/ folder" | No `-p` and the repo root has no `.plan` directory | Answer the prompt with a path, or create a plan first with `/code-plan` (it saves to `.plan/` by default). |
| `default-plan` exits 2: "has no plan files" / "has N plans" | `.plan/` empty of `.md`, or ambiguous (2+) | Answer the prompt — the N-plans case lists every candidate as a ready-to-paste `-p` line. |
| `plan-check` exits 2: "does not exist" | Path typo or wrong cwd | Re-run with the correct path; the plan must already exist. |
| `plan-check` exits 2: "is empty" | File is zero bytes | Point at a real plan; the file must have content. |
| `plan-check` exits 2: "not a .md file" | Wrong file type | Only `.md` files are accepted. |
| `plan-check` exits 2: "is not UTF-8 text" | A binary file named `*.md` | Point at a real text plan. |
| `plan-check` exits 2: "no `### ` step headings" | Not a stepped plan (e.g. a README) | Use a plan authored by `/code-plan` or equivalent — it must have `###` step sections. |
| `render` exits 3: unsubstituted placeholder | The `validate-code.md` template was hand-edited and a token other than `{{PATH}}` was introduced | Restore the canonical `prompts/validate-code.md` (it carries only `{{PATH}}`). |
| `render` exits 1: cannot read template | `prompts/validate-code.md` is missing or unreadable | Reinstall the skill; the template ships in `prompts/`. |
| Audit reports failures it cannot fix (missing prod credentials, unreachable service) | Genuinely unverifiable environment | Listed under Residual risks in the report (with the verbatim probe output as evidence); verify manually. |
| A fix is denied mid-audit | A gstack guardrail (`/freeze`, `/guard`, `/careful` HIGH tier) fails closed on that path/command | Report which matrix item is blocked and by what; it lands in Residual risks. The user lifts the boundary (`/unfreeze`) if the fix should proceed. Never work around it. |
| The turn will not end after the close-out | The repo armed `gstack-verify-gate` (opt-in Stop hook) and its declared verify command is failing | Run the CLAUDE.md-declared verify command, fix the failure, and let the gate pass — it is a gate, not a bug. |
| Plan file still exists after the run | The audit failed/aborted, the integrity check flagged a violation, or `close-out` exited 1 (a WARN was printed) | Intentional on failure — the plan is kept for the re-run. On a WARN, delete it manually. |
| Plan file is gone after a successful run | LAW 6 close-out (Step 7) — deletion is the contract | Nothing to fix; regenerate with `/code-plan` if you need a new plan. |
| The run printed `PLAN DELETED` but the plan is still on disk | Step 7 was never executed — the line was composed by hand instead of relayed from `close-out` | A contract violation, not a script bug. The line may only ever be `close-out`'s stdout; re-run Step 7 (`close-out --plan "$PLAN_ABS"`) to actually delete it. |
| `close-out` exits 2: "refusing to delete a directory" / "a non-.md file" | `$PLAN_ABS` is wrong — it is not the path `plan-check` resolved | Nothing was deleted. Re-derive `PLAN_ABS` from `plan-check` and re-run. |
| `close-out` prints "note: plan file was already absent" | The plan was removed earlier (a re-run, or a manual delete) | Not an error — the end state is correct, so the deletion line is still printed and exit is 0. |
