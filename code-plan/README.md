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
