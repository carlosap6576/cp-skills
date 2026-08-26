# code-execute

A `SKILL.md` contract plus a stdlib-only Python helper that executes an
implementation-plan `.md` file step-by-step. It validates the plan is a real
stepped plan, pins the working directory to the repo root that contains the
plan, renders the execution prompt, and follows it — never editing the plan
file, never running git. Works under any `SKILL.md`-aware runtime (Claude Code,
Hermes, OpenClaw, …).

## Install

Requirements: `python3` 3.9+. No LM Studio dependency.

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
ln -s "$PWD" ~/.claude/skills/code-execute
```

## Pipeline signal (for automation)

Every run ends by atomically writing one machine-readable JSON file to
`<repo-root>/.plan/.signals/<plan-stem>.execute.json` (stem `pipeline` when
the run stopped before a plan path was resolved). External orchestrators
drive the plan → execute → validate lifecycle by polling this git-ignored
directory — no chat parsing:

```json
{
  "schema": 1,
  "skill": "code-execute",
  "stage": "execute",
  "status": "success",
  "plan": "/abs/path/.plan/2026-08-26-add-export-plan.md",
  "detail": "IMPLEMENTATION COMPLETE — all 9 steps executed and verified.",
  "written_at": "2026-08-26T18:00:00+00:00"
}
```

`status` is `success` only when execution ended with the
`IMPLEMENTATION COMPLETE` report; every failed, partial, or stopped run
signals `failed` with the reason in `detail`. On success the orchestrator's
next stage is `/code-validation -p <plan>`. The sibling skills write
`<plan-stem>.plan.json` and `<plan-stem>.validate.json` to the same directory
with the same schema. The `.signals` directory never interferes with `.plan`
auto-discovery (only `*.md` files count as plans).

See SKILL.md for the full contract.
