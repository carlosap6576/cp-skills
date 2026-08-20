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

See SKILL.md for the full contract.
