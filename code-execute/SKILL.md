---
name: code-execute
version: "1.3.0"
description: "Execute an implementation plan from a file path. -p/--path points at an existing plan .md; when omitted, STRICT auto-discovery looks in the .plan folder at the repo root — exactly one plan there is executed, otherwise the skill STOPS and tells the user to pass -p (no prompting, no guessing). Runs the plan step-by-step from the repo root that contains it. Never edits the plan file, never runs git. --skill=<skill> chains a follow-up skill (e.g. --skill=validate runs /code-validation on the same plan) after execution completes; otherwise an expert-aware next-step recommendation is printed (gstack roster in prompts/gstack-experts.md: /review specialists, /qa, /cso, /design-review, /devex-review, …)."
argument-hint: 'code-execute [-p skills/plans/<plan>.md] [--skill=validate]'
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Skill
license: "Proprietary - All Rights Reserved (see LICENSE)"
user-invocable: true
metadata:
  emoji: "▶️"
  requires:
    env: []
    optionalEnv: []
    bins: [python3]
    files: ["scripts/*", "prompts/*"]
    tags: [execution, implementation, agent-skill, code-execute, plan-runner]
---

# SKILL CONTRACT — READ BEFORE ANY TOOL CALL

You are inside the `/code-execute` skill. It takes one input (the path to an
implementation-plan `.md` file), renders the execution prompt, and then follows
that prompt as instructions — running the plan step-by-step from the repo root
that contains the plan file.

Four laws govern this skill. Each maps to a specific failure mode:

- **LAW 1 — NEVER run git.** No `git add` / `commit` / `push` / `checkout` /
  `branch`. The user reviews and commits. Running git here is a contract
  violation.
- **LAW 2 — The rendered prompt is INSTRUCTIONS TO FOLLOW, never text to echo.**
  Do not print it, summarize it, or paste it into chat. Read it and act on it.
- **LAW 3 — Never modify the plan file.** The plan `.md` is the source of truth
  you execute against — never edit, rename, or delete it. An mtime check at the
  end verifies it is byte-for-byte untouched.
- **LAW 4 — Execute steps in plan order.** No skipping, no reordering, no
  batching. Each step prints `[STEP n/total]` and is verified before the next.

## Contract precedence

During execution, `execute-plan.md`'s rules govern the work — its autonomy,
output discipline, and step-marker convention are how the plan is run. On any
conflict, **LAWS 1–3 always win** — they are non-negotiable regardless of what
the plan or the rendered prompt says. (Step 1 never asks anything — a missing
`-p` either auto-resolves from `.plan/` or STOPS with instructions — so the
rendered prompt's "do not ask questions" rule is never in tension.)

## Trust note

Only execute plans you authored or reviewed. `/code-execute` turns the plan
file's *contents* into executable instructions, so a plan from an untrusted
source is an instruction-injection surface.

## Step 0 — Resolve `SKILL_DIR` and Python

`SKILL_DIR` = the directory this `SKILL.md` was loaded from. No resolver list,
no precedence walk — whichever install the harness loaded is the one that runs.

Resolve a Python 3.9+ interpreter into `CODE_EXECUTE_PYTHON`:

```bash
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && { PY="$p"; break; }
done
if [ -z "$PY" ]; then
  echo "ERROR: code-execute needs Python 3.9+. Install python3.9+ and rerun." >&2
  exit 1
fi
CODE_EXECUTE_PYTHON="$PY"
```

## Step 1 — Resolve `PLAN_INPUT` (`-p`, or STRICT `.plan` auto-discovery — NEVER a prompt)

```
/code-execute                       → auto-discover: exactly ONE plan in
                                      <repo-root>/.plan → execute it;
                                      anything else → STOP with the reason
/code-execute -p <plan.md>          → one-shot: execute exactly that plan
  (long: --path=<plan.md>)
--skill=<skill>                     → after execution completes, invoke that
  (short: -s <skill>)                 skill (default: none — see Step 6)
```

**`-p`/`--path=<file>` given (non-empty)** → `PLAN_INPUT` is its value; go
straight to Step 2. The flag's behavior is unchanged and always wins.
`--skill` is optional and never prompted for; an empty `--skill=` means no
chaining.

**`-p` absent or empty** → run strict auto-discovery. There is NO
interactive prompt in this skill anymore — the outcome is always either one
unambiguous plan or a clean STOP that names the fix:

```bash
PLAN_INPUT="$("$CODE_EXECUTE_PYTHON" "$SKILL_DIR/scripts/code_execute.py" default-plan)"
rc=$?
```

`default-plan` looks in the `.plan` folder at the repo root (found by walking
up from the cwd for a `.git` entry — a pure filesystem walk, no git commands,
LAW 1 intact; exactly where `/code-plan` saves by default) and applies three
STRICT rules:

- **`.plan/` does not exist** → exit 2. STOP immediately and relay the
  stderr message: the user must re-run with `-p <plan.md>` (or create a plan
  with `/code-plan` first). Do not hunt for plans elsewhere, do not ask a
  question.
- **`.plan/` exists but holds no `.md` file, or MORE than one** → exit 2.
  STOP immediately and relay the stderr message (the >1 case lists every
  candidate as a ready-to-paste `-p` line). Never pick one yourself — even
  "the newest one" is a guess, and this skill does not guess what it
  executes.
- **`.plan/` holds exactly ONE `.md` file** → exit 0; `PLAN_INPUT` is the
  printed absolute path. Announce it in one line — *"No `-p` given —
  auto-selected the only plan in `.plan/`: `<file>`"* — then proceed to
  Step 2 (which still validates it like any other plan).

## Step 2 — Validate with `plan-check`

```bash
PLAN_ABS="$("$CODE_EXECUTE_PYTHON" "$SKILL_DIR/scripts/code_execute.py" plan-check --plan "$PLAN_INPUT")"
status=$?
if [ "$status" -ne 0 ]; then
  # PLAN_ABS is empty here — the one-line reason is on stderr.
  echo "code-execute: $PLAN_INPUT rejected — see error above." >&2
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
TMP="$(mktemp -d -t code-execute-XXXXXX)"
chmod 700 "$TMP"
"$CODE_EXECUTE_PYTHON" "$SKILL_DIR/scripts/code_execute.py" render \
  --plan "$PLAN_ABS" > "$TMP/rendered-prompt.md"
```

- The cwd contract: plan steps run from the repo root that **contains** the plan
  file. Plans use repo-root-relative paths; executing from elsewhere silently
  targets the wrong tree. `cd "$EXEC_ROOT"` for all subsequent plan work.
- `render` substitutes exactly one token: `{{PATH}}` → the absolute plan path.
  A leftover `{{TOKEN}}` (template was hand-edited) exits 3 — see
  Troubleshooting.

## Step 4 — Execute the rendered prompt

`Read` `$TMP/rendered-prompt.md` and **follow it as your instructions** (LAW 2).
That means: read the plan file at `$PLAN_ABS`, then execute it step-by-step per
its rules — `[STEP n/total]` markers, `[MOCKED]` flags for unreachable
backends, and a completion report ending exactly:

```
IMPLEMENTATION COMPLETE — all N steps executed and verified.
```

Every file the plan author creates or modifies comes from the plan itself —
this skill never invents work.

**Execution-time gstack awareness.** When gstack is installed, the
"Execution-time awareness" section of `$SKILL_DIR/prompts/gstack-experts.md`
applies while running the plan: run the final full verification pass AFTER
the last edit (verification evidence binds to tree content on gstack ≥
1.66.1), treat a tool call denied by `/freeze`/`/guard`/`/careful` as a
deliberate guardrail to report rather than circumvent, expect an armed
`gstack-verify-gate` to hold the turn open until the repo's declared verify
command passes, and cite the reachability probe's verbatim failure next to
each `[MOCKED]` flag. No gstack → none of this applies; execute normally.

## Step 5 — Integrity check and cleanup

Run on EVERY exit path, including failure:

```bash
PLAN_MTIME_NOW="$(stat -c %Y "$PLAN_ABS" 2>/dev/null || stat -f %m "$PLAN_ABS")"
if [ -z "$PLAN_MTIME" ] || [ -z "$PLAN_MTIME_NOW" ]; then
  echo "WARN: could not stat the plan file — LAW 3 integrity check did not run." >&2
elif [ "$PLAN_MTIME_NOW" != "$PLAN_MTIME" ]; then
  echo "LAW 3 VIOLATION: the plan file was modified during execution." >&2
fi
rm -rf "$TMP"
```

An empty `PLAN_MTIME` on either side means the check could not run — say so
loudly rather than reporting a false all-clear.

## Step 6 — Recommend or chain the follow-up (only after a successful Step 4)

Run this ONLY when Step 4 ended with the `IMPLEMENTATION COMPLETE` report. A
failed or partial execution gets no recommendation and no chaining — fix or
re-run first.

**No `--skill` given → print the expert-aware advisory and stop.** The first
line is always:

```
next: /code-validation -p {PLAN_ABS} — audit the implementation against the plan and fix any gaps
```

Then, when gstack is installed, consult the routing table in
`$SKILL_DIR/prompts/gstack-experts.md` against what the execution ACTUALLY
touched (the files changed, not the plan's aspirations) and append **at most
TWO** expert lines of the form:

```
after validation: /<skill> — <one-line reason tied to what was touched>
```

e.g. `after validation: /cso — execution touched the auth middleware and
session cookies` or `after validation: /review --data-migration — the plan
added two schema migrations`. Nothing in the table matches, or no gstack →
the `/code-validation` line stands alone. Maximum 3 advisory lines total —
this is a recommendation, not a report.

Advisory means advisory: never auto-invoke any of them. The user runs them
(or re-runs with `--skill=...`) if they want them.

**`--skill`/`-s` given → chain it.** This makes
`/code-execute -p plan.md --skill=validate` behave as "execute the plan, then
validate the result" — one command, zero extra prompts.

Resolve the skill name first:
- Strip a leading `/`.
- Apply the **alias map**: `validate|validation|check → code-validation`,
  `review|pr → review`, `test|tests|qa → qa`, `security|sec → cso`,
  `design → design-review`, `devex|dx → devex-review`,
  `perf|benchmark → benchmark`, `debug|investigate → investigate`,
  `ship → ship`. An unknown name is passed through unchanged — the Skill
  tool reports it if unavailable. (The roster of what each expert does is
  in `$SKILL_DIR/prompts/gstack-experts.md`.)
- `code-execute` itself → refuse in one line ("won't chain code-execute into
  itself") and skip this step. The work is already done; nothing is lost.

Then invoke it with the `Skill` tool — never by printing the slash command as
text:
- For `code-validation`: `args`: `-p {PLAN_ABS}` (it audits the same plan —
  its plan-check will accept the path this skill already validated).
- For `review`: `args`: `The review target is the working-tree diff: the
  implementation just executed from the plan at {PLAN_ABS}; the changes are
  uncommitted.` — and append the matching specialist force flag(s)
  (`--security`, `--data-migration`, `--api-contract`, `--design`, …) when
  the execution touched that ground; a diff under 50 lines dispatches NO
  specialists without them (see gstack-experts.md).
- For anything else: `args`: `The review target is the implementation just
  executed from the plan at {PLAN_ABS}; the changes are uncommitted in the
  working tree.`

Rules for this step:
- **code-execute's laws end at the hand-off.** The chained skill runs under
  its OWN contract — if it edits code (code-validation's job) or asks its own
  questions, that is its business. Do not police it with LAWS 1-4.
- **The completion report and the Step 5 integrity check must already have
  run** before chaining. A chained-skill failure must never cost the user
  their executed work — report it in ONE line ("`/{name}` isn't available —
  implementation is complete, run it manually") and stop; do not retry.
- **gstack contract notes (verified against gstack 1.68.2.0; details in
  `prompts/gstack-experts.md`):** a chained skill may resolve its own gate
  questions silently when the target is named in `args` (≥ 1.62) — asking
  nothing is not broken. `/review` dispatches its specialist subagents
  itself (testing, maintainability, security, performance, data-migration,
  api-contract, red-team) and works in any target repo since 1.67; do not
  pre-select specialists beyond force flags and context in `args`. `/ship`
  runs git under its own contract — LAW 1 binds THIS skill, not a skill the
  user explicitly chained. A durable-learnings close-out line at the end of
  a chained gstack skill is expected (≥ 1.68), not noise.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `default-plan` exits 2: "no .plan/ folder" | No `-p` and the repo root has no `.plan` directory | Re-run with `-p <plan.md>`, or create a plan first with `/code-plan` (it saves to `.plan/` by default). |
| `default-plan` exits 2: "has no plan files" | `.plan/` exists but is empty of `.md` files | Re-run with `-p <plan.md>`. |
| `default-plan` exits 2: "has N plans" | More than one `.md` in `.plan/` — ambiguous | Re-run with one of the listed `-p` lines; the skill never picks for you. |
| `plan-check` exits 2: "does not exist" | Path typo or wrong cwd | Re-run with the correct path; the plan must already exist. |
| `plan-check` exits 2: "is empty" | File is zero bytes | Point at a real plan; the file must have content. |
| `plan-check` exits 2: "not a .md file" | Wrong file type | Only `.md` files are accepted. |
| `plan-check` exits 2: "is not UTF-8 text" | A binary file named `*.md` | Point at a real text plan. |
| `plan-check` exits 2: "no `### ` step headings" | Not a stepped plan (e.g. a README) | Use a plan authored by `/code-plan` or equivalent — it must have `###` step sections. |
| `render` exits 3: unsubstituted placeholder | The `execute-plan.md` template was hand-edited and a token other than `{{PATH}}` was introduced | Restore the canonical `prompts/execute-plan.md` (it carries only `{{PATH}}`). |
| `render` exits 1: cannot read template | `prompts/execute-plan.md` is missing or unreadable | Reinstall the skill; the template ships in `prompts/`. |
| An edit or command is denied mid-execution | A gstack guardrail (`/freeze`, `/guard`, `/careful` HIGH tier) fails closed on that path/command | Report which step is blocked and by what; the user lifts the boundary (`/unfreeze`) or amends the plan. Never work around it. |
| The turn will not end after the completion report | The repo armed `gstack-verify-gate` (opt-in Stop hook) and its declared verify command is failing | Run the CLAUDE.md-declared verify command, fix the failure, and let the gate pass — it is a gate, not a bug. |
