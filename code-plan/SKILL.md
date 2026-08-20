---
name: code-plan
version: "1.12.0"
description: "Turn a rough request into a precise, step-by-step implementation plan. One-shot: --desc/-d alone runs with zero prompts — the plan saves to a git-ignored .plan/ folder at the repo root (auto-created, .gitignore validated/updated every run); --path/-p overrides the destination. Auto-selects gstack expert lenses (eng/design/security/qa/…) to sharpen the plan; --skill=<skill> chains a follow-up skill on the finished plan. Debug tag defaults to ui-data (never prompted). Rewrites the instructions natively (in the model running the skill — no external LLM); writes a detailed, human-executable .md plan another agent can execute."
argument-hint: 'code-plan | code-plan -d "add a CSV export button" [-p skills/plans] [--skill=plan-eng-review]'
allowed-tools: Bash, Read, Write, Glob, Grep, AskUserQuestion, Skill
license: "Proprietary - All Rights Reserved (see LICENSE)"
user-invocable: true
metadata:
  emoji: "🧭"
  requires:
    env: []
    optionalEnv: []
    bins: [python3]
    files: ["scripts/*", "prompts/*"]
    tags: [planning, implementation-plan, prompt-template, spec, agent-skill]
---

# SKILL CONTRACT — READ BEFORE ANY TOOL CALL

You are inside the `/code-plan` skill. It collects two inputs (instructions
and save folder — the debug tag is a fixed default, never asked), rewrites the
instructions natively (you execute the rewrite prompt yourself — no external
LLM, no local server, no network), renders them into a plan-authoring prompt,
and writes a detailed implementation plan as a `.md` file at the path the user
chose. The user never copy-pastes the prompt.

Four laws govern this skill. Each maps to a specific failure mode:

- **LAW 1 — NEVER run git.** No `git add` / `commit` / `push` / `checkout` /
  `branch`. The user reviews and commits. The plan file is a regular file the
  user will commit themselves. Running git here is a contract violation.
- **LAW 2 — The rendered prompt is INSTRUCTIONS TO FOLLOW, never text to echo.**
  Do not print it, summarize it, or paste it into chat. Read it and act on it.
  Dumping the scratchpad instead of executing it is the classic failure.
  This applies to BOTH rendered prompts: the enhancement prompt (Step 6) and
  the plan-authoring prompt (Step 10).
- **LAW 3 — Do not implement the task.** The only artifact you produce is the
  plan `.md` at the resolved path. Writing code during `/code-plan` is a
  contract violation. (A skill chained via `--skill` runs AFTER code-plan
  completes and under its own contract — its outputs are not yours; see
  Step 13.)
- **LAW 4 — The enhancement is prompt-governed, never freestyle.** The rewrite
  happens in your own context, but ONLY by executing the composed prompt from
  `enhance-prompt` (Step 6) — never from memory of its rules, and never as an
  excuse to answer, design, or implement the request. If `enhance-prompt`
  prints a `WARN:`, say so plainly in one line and proceed with the raw
  instructions — do not improvise a rewrite without the prompt.

## Step 0 — Resolve `SKILL_DIR` and Python

`SKILL_DIR` = the directory this `SKILL.md` was loaded from. No resolver list,
no precedence walk — whichever install the harness loaded is the one that runs.

Resolve a Python 3.9+ interpreter into `CODE_PLAN_PYTHON`:

```bash
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null && { PY="$p"; break; }
done
if [ -z "$PY" ]; then
  echo "ERROR: code-plan needs Python 3.9+. Install python3.9+ and rerun." >&2
  exit 1
fi
CODE_PLAN_PYTHON="$PY"
```

## Step 1 — Parse arguments

```
/code-plan                          → prompt for instructions; path defaults to .plan/
/code-plan <free text>              → free text IS the instructions; path defaults to .plan/
--desc=<text>                       → the instructions, as an explicit flag
  (short: -d <text>)                  (skips the Step 3 question)
  (long:  --description=<text>)
--path=<dir>                        → save the plan in <dir> instead of the
  (short: -p <dir>)                   default <repo-root>/.plan/ (see Step 4)
--tag=<value>                       → override the default tag (ui-data); NEVER prompted
--no-enhance                        → skip the instruction rewrite entirely
--yes                               → skip the pre-flight review (Step 5) AND the
                                      post-enhancement confirmation (Step 7)
--skill=<skill>                  → after the plan is written, invoke that skill
  (short: -s <skill>)                 on it (default: none — see Step 13)
--experts=<list|none>               → force the expert lenses (comma list, e.g.
                                      eng,design) or disable them; default:
                                      auto-selected in Step 8, never prompted
```

**ONE-SHOT RULE: a description flag implies `--yes` whenever the path
resolves without a question** (any spelling — `-d`/`--desc`/`--description`).
The path resolves without a question when `-p`/`--path` was given OR when the
default applies (no folder named in the instructions prose — see Step 4). In
either case run start to finish with ZERO prompts (no Step 3, no Step 4, no
Step 5 review, no Step 7 confirmation). Both are fast paths:

```
/code-plan -d "add a CSV export button"                  → plan lands in <repo-root>/.plan/
/code-plan -d "add a CSV export button" -p skills/plans  → plan lands in skills/plans/
```

`-p` without `-d` still runs one-shot for the path and prompts ONLY for the
instructions. Never prompt for an input that was flag-provided, and never
prompt for the path when the `.plan` default applies.

Split the raw argument string:
- Anything after the first non-flag token is `INSTRUCTIONS` (free prose).
- `--desc=…`/`--description=…`/`-d …`, `--path=…`/`-p …`, `--tag=…`,
  `--skill=…`/`-s …`, `--experts=…`, `--no-enhance`, `--yes` are flags; strip them from the prose.
  Long flags take `=`-joined values; short flags (`-d`, `-p`) take the next
  token (or quoted string) as their value. Values may be quoted (single or
  double) and contain spaces — take the quoted value verbatim.
- If BOTH free text and a description flag appear, the flag wins; say so
  in one line and continue (do not ask which one they meant).
- An empty flag value (`--desc=` / `--path=` / `--skill=`) counts as
  NOT provided — for the two mandatory inputs, prompt normally; for
  `--skill`, simply no chaining (it is optional, never prompted).
- **A folder mentioned INSIDE the instructions prose is NOT `--path`.** Prose
  like "save it in skills/plans" makes that folder the *suggested default* in
  the Step 4 question — the question is still asked, because silently saving
  to `.plan/` would contradict what the user wrote, and silently honoring the
  prose would infer a path they never confirmed. A prose-named folder is the
  ONLY case where Step 4 still asks; with no `-p` and no prose folder, the
  `.plan` default applies silently. The tag is never interactive — see Step 2.

## Step 2 — PROJECT_TAG (fixed default — NO question, EVER)

`PROJECT_TAG` is resolved silently. Do NOT call `AskUserQuestion`, do not ask
in prose, do not mention the tag as a pending decision:

- If `--tag=<value>` was passed: validate it against `^[a-z][a-z0-9-]{0,23}$`.
  Invalid → report the one-line error and stop (do not fall into a prompt loop).
- Otherwise: `PROJECT_TAG=ui-data`. Always. No confirmation.

## Step 3 — INSTRUCTIONS (free-text ask; skip the ASK if a description flag or inline text was given)

Even when instructions came via `-d`/`--desc`/`--description` or inline in Step 1, the file
work below still runs — create `$TMP` and write the provided prose verbatim to
`$TMP/raw.txt`, then move on. Only the question is skipped.

This is open prose, not a choice — do NOT use `AskUserQuestion`. Ask plainly:

> What do you want planned? Describe it however it comes out — rough,
> unordered, typos fine. I'll clean it up before planning. Include anything
> that matters: files, constraints, what NOT to touch.

**STOP and wait for the reply.** Then create a private temp dir and write the
reply **verbatim** to `"$TMP/raw.txt"` using the Write tool — never `echo`
prose through Bash (apostrophes, backticks, and newlines are the classic
shell-escaping footgun):

```bash
TMP="$(mktemp -d -t code-plan-XXXXXX)"
chmod 700 "$TMP"
```

Write the user's reply to `"$TMP/raw.txt"` with the Write tool.

## Step 4 — PATH (defaults to `.plan/`; ask ONLY when the prose names a folder and `-p` is absent)

Resolve `USER_PATH` by the first matching rule:

1. **`-p`/`--path=<dir>` was passed** → `USER_PATH` is its value. No question.
   Validate with `plan-path` (below) exactly as before — the flag's behavior
   is unchanged.
2. **No flag, and the instructions prose names NO save folder** → the
   **`.plan` default**: leave `USER_PATH` empty and call `plan-path` WITHOUT
   `--path`. No question. The script resolves `<repo-root>/.plan` — the repo
   root is found by walking up from the cwd for a `.git` entry (a pure
   filesystem walk, no git commands, so LAW 1 is intact; no `.git` anywhere →
   the cwd itself). On every run it validates and heals the destination:
   creates `.plan/` if missing, and when the root is a git repo guarantees
   `.plan/` is listed in `.gitignore` (creates the file or appends the entry
   as needed) so plans NEVER land in a commit. Relay each `NOTE:` line it
   prints (folder created, .gitignore updated) in one short line — the user
   should know where the plan will live and that it is git-ignored.
3. **No flag, but the prose names a folder** → the ONLY case that still asks
   (silently saving to `.plan/` would contradict the user's own words; see
   Step 1). Ask, naming the prose folder as the default:

   > Where should I save the plan? Your instructions mention `<folder>` —
   > reply "yes" to use it, reply `.plan` for the default git-ignored folder,
   > or give me a different folder.

Paths are resolved relative to the shell's current working directory (normally
the repo root) — run the validation below from the repo root.

Then validate with `plan-path` (omit `--path` in the default case):

```bash
"$CODE_PLAN_PYTHON" "$SKILL_DIR/scripts/code_plan.py" plan-path \
  ${USER_PATH:+--path "$USER_PATH"} --objective-file "$TMP/raw.txt"
```

- Exit 2 + "directory does not exist" → ask the user to confirm creation, then
  re-run with `--mkdir` (explicit-path case only; the default case creates
  its folder itself).
- Exit 2 + "not writable" → report and stop.
- A `WARN: could not update .gitignore` line (default case, read-only
  .gitignore) → relay it verbatim and continue; the plan still gets written.

Keep the path `plan-path` printed — it is the provisional plan file shown in
the Step 5 review.

## Step 5 — Review & confirm the inputs (skip if `--yes` OR one-shot)

One-shot invocations (description flag given AND the path resolved without a
question — via `-p` or the `.plan` default) skip this step entirely — see the
ONE-SHOT RULE in Step 1.

Both interactive inputs are now in hand (the tag resolved silently in Step 2).
Before ANY work starts — before the enhancement rewrite, before touching the
codebase — show the user one compact review so the hand-off is clean and
deliberate. Render exactly this shape in chat:

```
📋 Ready to plan — review your inputs

  Tag           ui-data                 (default — override with --tag=…)
  Save folder   skills/plans            (exists · writable)
  Plan file     2026-07-25-add-a-csv-export-button-plan.md   (provisional)
  Enhancement   on — native rewrite, you confirm the result first
  Instructions  ────────────────────────────────────────────
  <the user's instructions verbatim — first 15 lines; if longer, add
   "… (+N more lines)">
```

- `Plan file` is the name `plan-path` resolved in Step 4. Label it
  **(provisional)** — the final name is re-derived from the enhanced wording
  in Step 9 and may differ slightly.
- `Save folder` states `(will be created)` if the user confirmed creation in
  Step 4. When the `.plan` default applied, the line reads
  `Save folder   .plan   (default — repo root, git-ignored)`.
- With `--no-enhance`, the Enhancement line reads `off — planning from your
  wording as written`.

Then ask (AskUserQuestion):

> Everything correct? This is the last stop before I explore the codebase and
> write the plan.

Options:
- **A) Start planning (recommended)**
- **B) Edit the instructions** → return to Step 3, then show this review again
- **C) Change the save folder** → return to Step 4, then show this review again

(The tag is not an option here — it is a fixed default. A user who wants a
different tag re-runs with `--tag=<value>`.)

Loop through this review after every adjustment until the user picks **A**.
Only A leaves this step. Do NOT proceed on any other answer.

## Step 6 — Enhance (native rewrite; skip if `--no-enhance`)

The rewrite runs in YOUR context — no external LLM, no local server, no
network. The rules live in `prompts/enhance-instructions.md`; the script only
composes them deterministically (frontmatter strip + `{{RAW_INSTRUCTIONS}}`
substitution), and you execute the result. Same render-then-execute pattern
as Steps 9-10.

1. **Compose the enhancement prompt:**

   ```bash
   "$CODE_PLAN_PYTHON" "$SKILL_DIR/scripts/code_plan.py" enhance-prompt \
     --instructions-file "$TMP/raw.txt" > "$TMP/enhance-prompt.md" 2> "$TMP/enhance.err"
   ```

2. **If the command exited non-zero or `enhance.err` contains `WARN:`**, follow
   LAW 4: tell the user in one line — *"The enhancement prompt couldn't be
   composed — planning from your instructions as written."* — copy `raw.txt`
   over `enhanced.txt`, and skip to Step 8. Never improvise the rewrite
   without the composed prompt.

3. **Otherwise `Read` `$TMP/enhance-prompt.md` and follow it as your
   instructions** (LAW 2). Honor every rule in it: rewrite only — never
   answer, design, or implement; invent nothing; preserve every concrete
   token character-for-character; respect the length cap; return near-verbatim
   with a trailing `NOTE:` line when the input is too vague to rewrite safely.
   Then `Write` the rewritten brief — the brief ONLY, no preamble, no
   commentary — to `$TMP/enhanced.txt`.

## Step 7 — Confirm the enhanced wording (skip if `--yes` OR one-shot OR `--no-enhance` OR a WARN fired)

Show the user the enhanced brief and ask:

- **A) Use it (recommended)**
- **B) Use my original wording**
- **C) Let me revise and re-run**

On B, copy `raw.txt` over `enhanced.txt`. On C, return to Step 3 (the Step 5
review will run again on the way back through).

## Step 8 — Expert selection (silent; skip ONLY if `--experts=none`)

This is what makes the plan sharp: before authoring, pick the expert lenses
that fit the task. It costs seconds, never prompts, and never blocks. Lens
selection is now **two-tier**: a deterministic `route` subcommand computes the
baseline lens set, and you may adjust it by at most one lens.

1. **Run the router** (never fails the skill):
   ```bash
   ROUTE_JSON="$("$CODE_PLAN_PYTHON" "$SKILL_DIR/scripts/code_plan.py" route \
     --instructions-file "$TMP/enhanced.txt" --json ${EXPERTS:+--experts "$EXPERTS"} \
     2>"$TMP/route.err" || true)"
   ```
   Empty/failed output → treat as `{"lenses": [], "recommended_skill": null}`,
   print one line, continue (mirrors LAW 4's degrade-never-block stance).
2. `lenses` from the JSON is the **BASELINE**. You may add or drop **at most
   one** lens, and only with a one-line justification shown in the Step 11
   report (e.g. `Experts: eng+design (+design: the endpoint is only consumed
   by a new settings panel)`). Never replace the whole set; never exceed 3.
3. `recommended_skill` from the JSON is what Step 11's `next:` line prints and
   what a missing `--skill` would have chained.
4. **Lens CONTENT** still comes from `Read "$SKILL_DIR/prompts/expert-lenses.md"`;
   compose the selected sections verbatim, each under a
   `Selected because: <one line>` header, and `Write` them to `$TMP/lenses.md`.
   Empty selection → do not write the file (the renderer substitutes the
   generalist default on its own).
5. `--experts=<list>` is passed straight through to `route` (it validates the
   ids); `--experts=none` skips the step entirely.
6. **Degrade-safe:** unreadable distillate file → no lenses file, one line in
   chat, continue.

In interactive runs (no one-shot), print one line before authoring:
`Experts: eng+design (routed) — architecture change touching UI` (or
`Experts: none`). Never ask a question about it; `--experts` is the override
mechanism.

## Step 9 — Resolve the plan path and render

```bash
# USER_PATH is empty in the .plan-default case — plan-path re-resolves (and
# re-heals) the default destination itself; --mkdir covers the explicit case.
PLAN_FILE=$("$CODE_PLAN_PYTHON" "$SKILL_DIR/scripts/code_plan.py" plan-path \
  ${USER_PATH:+--path "$USER_PATH"} --objective-file "$TMP/enhanced.txt" --mkdir)

LENSES_ARG=""
[ -f "$TMP/lenses.md" ] && LENSES_ARG="--lenses-file $TMP/lenses.md"

"$CODE_PLAN_PYTHON" "$SKILL_DIR/scripts/code_plan.py" render \
  --tag "$PROJECT_TAG" --path "$(dirname "$PLAN_FILE")" \
  --plan-filename "$(basename "$PLAN_FILE")" \
  $LENSES_ARG \
  --instructions-file "$TMP/enhanced.txt" > "$TMP/rendered-prompt.md"
```

## Step 10 — Execute the rendered prompt

`Read` `$TMP/rendered-prompt.md` and **follow it as your instructions** (LAW 2).
That means: explore the codebase first (Glob / Grep / Read — never reference a
file you have not verified exists), then author the plan, then `Write` it to
`$PLAN_FILE`. Honor every rule in the rendered prompt, including "no git."

## Step 11 — Report

Exactly this shape, nothing more:

```
🧭 code-plan v{version}

Plan written to {PLAN_FILE}{ · default .plan folder, git-ignored}
{N} steps · tag `{PROJECT_TAG}` · {enhanced|raw} instructions · experts: {LENSES|none}
{one-sentence summary of what the plan covers}
next: /{RECOMMENDED} — {one-line why}   ← ONLY when --skill was NOT given and
                                          Step 8 matched a review skill worth running
↪ handing off to /{SKILL} — the plan file is named as the review target (gstack ≥ 1.62 auto-selects it; older versions confirm first).   ← ONLY when --skill was given
```

`{version}` comes from `plugin.json`. The ` · default .plan folder,
git-ignored` suffix appears ONLY when the path defaulted (no `-p`) — the user
must always know exactly where the plan landed and that it will not be
committed. `{N}` is the count of `###`-level steps
in the plan you just wrote. `{enhanced|raw}` reflects whether the native
rewrite was used. `{LENSES}` is the Step 8 selection **with its source
stated**: `eng+design (routed)` (deterministic baseline, untouched),
`eng+design (routed, +design: <why>)` (baseline with one model adjustment),
`eng,design (forced)` (`--experts` override), or `none`. The `next:`
recommendation prints `recommended_skill` from the router verbatim
(e.g. `next: /plan-design-review — UI-heavy plan; a designer's eye catches
state/spacing gaps before code`); it is ADVISORY — never auto-invoke it; the
user runs it (or re-runs with `-s`) if they want it. For large product-shaped
plans the router returns `autoplan` (it combos the CEO/design/eng/DX reviews)
— recommend it instead of listing several review skills. When `--skill` was
given, the `↪ handing off to` line states that the plan file is passed as the
named review target (gstack's scope gate — see Step 13).

## Step 12 — Cleanup

```bash
rm -rf "$TMP"
```

Run this on EVERY exit path, including the failure ones. The user's prose and
the rendered prompt must not leak into a second invocation or another skill.
(The Step 13 hand-off does not need `$TMP` — the enhanced brief is already in
your context, and the plan file is a regular file on disk.)

## Step 13 — Chain the follow-up skill (ONLY if `--skill`/`-s` was given)

This makes `/code-plan --skill=plan-eng-review …` behave as an alias for
"plan it, then run that skill on the result" — one command, no second prompt.

Resolve the skill name first:
- Strip a leading `/` (`--skill=/plan-eng-review` → `plan-eng-review`).
- Apply the **alias map** (after stripping the slash): `eng|engineering →
  plan-eng-review`, `design|ui|ux → plan-design-review`,
  `devex|dx → plan-devex-review`, `ceo|product → plan-ceo-review`,
  `security|sec → cso`, `test|tests → qa`, `docs → docs-refresh`. So
  `--skill=eng` resolves to `plan-eng-review` automatically.
- An unknown name (not in the alias map, not a verbatim skill id) is still
  passed through unchanged — the Skill tool reports it if it is unavailable.
- `code-plan` itself → refuse in one line ("won't chain code-plan into
  itself") and skip this step. The plan is already written; nothing is lost.

Then invoke it with the `Skill` tool — never by printing the slash command as
text:

- `skill`: the resolved name
- `args`: `Scope gate answer: option B — a plan/design doc. The review target
  is the implementation plan at {PLAN_FILE} (read it directly; do not review
  the branch diff). It was generated from these (enhanced) instructions:
  {the enhanced brief, verbatim}.`

Rules for this step:
- **code-plan's laws end at the hand-off.** The chained skill runs under its
  OWN contract — if it edits the plan file, asks its own questions, or writes
  a review report, that is its business. Do not police it with LAW 1-4, and do
  not implement code yourself between the hand-off and the chained skill taking
  over.
- **The gstack plan-review scope gate auto-resolves a named target
  (gstack ≥ 1.62).** `plan-eng-review` and `plan-design-review` open with a
  scope gate ("What should I review? A) branch diff B) a plan or design doc
  C) a path") — but since gstack 1.62 the gate skips its question when the
  target is explicitly named, which the `args` below do (they pass the plan
  path). Expect the review to proceed directly on gstack ≥ 1.62 and to
  confirm first on 1.58.4–1.61 — either behavior is correct, and a chained
  skill that asks no question is NOT broken. `autoplan` skips the gate
  entirely; `plan-ceo-review` / `plan-devex-review` have no scope gate at
  all — never promise a confirmation question for those.
- **Chained-skill behaviors on gstack ≥ 1.65 that are NOT bugs:**
  `autoplan`'s task aggregation is trustworthy only on gstack ≥ 1.65 (before
  that, Phase 4 silently emitted zero tasks — on ≤ 1.64, if the chained
  autoplan hands off an empty task list, say so and point at the plan file).
  Since 1.68 every gstack skill ends with an explicit durable-learnings
  close-out line even when there are none — expected, not noise. Since 1.65 a
  chained review may run a live probe before accepting a "the API can't do
  this" claim in the plan, and it prefers a repo-local
  `docs/designs/<topic>.md` decision record over gstack-side docs when both
  exist.
- **The plan must already be written and reported (Steps 10-11) before
  chaining.** A chained-skill failure must never cost the user their plan.
- If the Skill tool errors (unknown/unavailable skill), report it in ONE line
  — "`/{name}` isn't available — plan is written at {PLAN_FILE}, run the
  review manually" — and stop. Do not retry, do not guess at a similar name.
- No `--skill` → this step does not exist; end at Step 12 exactly as
  before.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Enhancement degraded (WARN) | `prompts/enhance-instructions.md` missing or unreadable | Skill still works; plan is built from your raw wording. Restore/reinstall the skill's `prompts/` folder for a cleaner brief. |
| Enhancement changed my meaning | The rewrite over-compressed or dropped a detail | Answer **B) Use my original wording** at the Step 7 confirmation, or re-run with `--no-enhance`. |
| `plan-path` exits 2 | Destination directory missing or not writable | Re-run with `--mkdir`, or pick a writable folder. |
| `WARN: could not update .gitignore` | `.gitignore` unwritable in the `.plan` default case | The plan is still written to `.plan/`; add `.plan/` to `.gitignore` manually so plans stay out of commits. |
| Plan saved to `.plan/` but I wanted another folder | No `-p` was passed, so the default applied | Re-run with `-p <dir>` — the flag always wins over the default. |
