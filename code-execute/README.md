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

See SKILL.md for the full contract.
