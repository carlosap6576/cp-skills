# code-validation

A `SKILL.md` contract plus a stdlib-only Python helper that audits a completed
implementation against the plan `.md` it was built from — and autonomously
fixes every issue it finds. It validates the plan is a real stepped plan, pins
the working directory to the repo root that contains the plan, renders the
audit prompt, and follows it through six phases (traceability matrix → deep
validation → fix/fill/improve → re-verify → production cleanup sweep →
report). The implementation code is edited to fix findings and then swept
**PR-clean**. The plan file is never edited during validation, and git is
never run.
This is the third and final phase of the plan → execute → validate lifecycle
(`/code-plan` → `/code-execute` → `/code-validation`).

On success the implementation is swept PR-clean — three strict passes ending
with the `Repo hygiene gate` and the `{S} scaffolding files removed` report
counter — and the plan file itself is deleted as the close-out
(`PLAN DELETED — …`), signaling the code is validated and ready.

Works under any `SKILL.md`-aware runtime (Claude Code, Hermes, OpenClaw, …).

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
ln -s "$PWD" ~/.claude/skills/code-validation
```

## Pipeline signal (for automation)

Every run ends by atomically writing one machine-readable JSON file to
`<repo-root>/.plan/.signals/<plan-stem>.validate.json` (stem `pipeline` when
the run stopped before a plan path was resolved). This is the pipeline's
TERMINAL marker: it is written before the close-out, so it survives the plan
file's deletion — external orchestrators read a definitive verdict here
instead of inferring one from a missing plan:

```json
{
  "schema": 1,
  "skill": "code-validation",
  "stage": "validate",
  "status": "success",
  "plan": "/abs/path/.plan/2026-08-26-add-export-plan.md",
  "detail": "VALIDATION COMPLETE — 9 plan items verified, 0 fixed, 0 gaps filled, 4 files production-cleaned, 2 scaffolding files removed.",
  "written_at": "2026-08-26T18:00:00+00:00"
}
```

`status` is `success` only when the audit ended with the
`VALIDATION COMPLETE` report; every failed or aborted audit signals `failed`
with the reason in `detail` (and keeps the plan file for the re-run). The
sibling skills write `<plan-stem>.plan.json` and `<plan-stem>.execute.json`
to the same directory with the same schema.

See SKILL.md for the full contract.
