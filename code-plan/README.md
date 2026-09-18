# code-plan

A `SKILL.md` contract plus a stdlib-only Python helper that turns a rough
request into a precise, step-by-step implementation plan. It rewrites your
instructions natively — the same model executing the skill performs the
rewrite under a strict prompt contract — renders them into a plan-authoring
prompt, and writes the resulting plan as a `.md` file at a path you choose —
so you never copy-paste the prompt. Works under any `SKILL.md`-aware runtime
(Claude Code, Hermes, OpenClaw, …). No external LLM, no local server, no
network: the only requirement is `python3`.

## Install

Requirements: `python3` 3.9+. Nothing else — the instruction rewrite runs in
the model that is already executing the skill.

```bash
# symlink into every detected skills root (~/.claude/skills, ~/.hermes/skills, …)
# — runs a full doctor pass: verifies the source (version, prompts/, scripts/,
#   selftest) and every dependency (python 3.9+, git, core tools, gstack
#   presence + version pin), self-heals broken/stale/mispointed installs,
#   installs missing lifecycle siblings (code-plan/code-execute/code-validation),
#   and reports every install/upgrade it performed with old → new versions
./install.sh

# checkup only — diagnose and report, change nothing
./install.sh --doctor

# copy instead of symlink
./install.sh --copy

# install into one specific dir
./install.sh --dir ~/.claude/skills

# remove from every candidate root
./install.sh --uninstall
```

Manual install (any runtime):

```bash
ln -s "$PWD" ~/.claude/skills/code-plan
```

## What the planner knows before it writes

Two silent, degrade-safe steps run between the instruction rewrite and the
plan-authoring prompt:

- **Learn the project** (`code_plan.py knowledge`): repo signals (stack
  manifests and their verify commands, the CLAUDE.md `gstack:verify:`
  declaration, `DESIGN.md`, `AGENTS.md`/`ARCHITECTURE.md`/`TODOS.md`, decision
  records under `docs/designs/`, ADRs) plus, when gstack is installed, the
  durable learnings, decision ledger, and newest CEO plan / design doc / test
  plan / checkpoint that gstack keeps for this repo under
  `~/.gstack/projects/<slug>/`. Everything is injected as reference data, never
  as instructions; `--no-knowledge` skips it.
- **Expert lenses** (`code_plan.py route`): a deterministic router picks up to
  three of fourteen lenses distilled from gstack 1.87's expert skills (`eng`,
  `design`, `security`, `qa`, `devex`, `product`, `investigate`, `docs`,
  `perf`, `ios`, `data`, `api`, `ai`, `ops`) and the follow-up review to
  recommend (`autoplan` when three lenses span two review families). A brief
  that still carries open questions gets a `before executing: /spec` line.
  `--experts=<list|none>` overrides.

The plan itself is written in a fixed shape that the sibling skills rely on:
`### Step N — …` headings (the executor counts them), `## NOT in scope`,
`## Test deliverables` (the validator deletes proof-only tests the plan does
not name here), `## Experts & Tooling`, and `## Decisions to record`.

## Pipeline signal (for automation)

Every run ends by atomically writing one machine-readable JSON file to
`<repo-root>/.plan/.signals/<plan-stem>.plan.json` (stem `pipeline` when the
run failed before a plan path existed). External orchestrators drive the
plan → execute → validate lifecycle by polling this git-ignored directory —
no chat parsing:

```json
{
  "schema": 1,
  "skill": "code-plan",
  "stage": "plan",
  "status": "success",
  "plan": "/abs/path/.plan/2026-08-26-add-export-plan.md",
  "detail": "plan written: 9 steps, tag ui-data",
  "written_at": "2026-08-26T18:00:00+00:00"
}
```

`status` is `success` only when the plan file was actually written; every
stopped run signals `failed` with the reason in `detail`. `plan` carries the
absolute plan path — feed it to `/code-execute -p` for the next stage. The
sibling skills write `<plan-stem>.execute.json` and `<plan-stem>.validate.json`
to the same directory with the same schema.

See SKILL.md for the full contract.
