# cp-skills

A collection of self-contained agent skills for Claude Code and any
SKILL.md-aware runtime. Each folder is one skill: a `SKILL.md` contract, a
stdlib-only install script, and deterministic helpers. Install one, install
all — they are independent except where noted.

| Skill | Purpose |
|---|---|
| `code-plan` | Turn a rough request into a step-by-step implementation plan. |
| `code-execute` | Execute an existing plan file step-by-step, with verification gates. |
| `code-validation` | Audit an implementation against its plan and fix the gaps. |
| `stock-eval` | Engagement-ranked social/market read on a ticker, with a strict synthesis voice contract. |

## Install

One command installs every skill in this repo into every skills root your
agent harnesses scan (Claude Code, Codex, Gemini CLI, Cursor, Copilot,
OpenCode, Hermes, OpenClaw, `~/.agents`). It runs as a doctor: checks the
source and dependencies, symlinks or upgrades each skill, and reports every
change with its version.

```bash
git clone https://github.com/carlosap6576/cp-skills.git
cd cp-skills
./install.sh              # install/upgrade all skills into every detected root
./install.sh --doctor     # checkup only: diagnose, change nothing
./install.sh --copy       # copy instead of symlink (upgraded in place on rerun)
./install.sh --only code-plan,stock-eval   # a subset (or --skip a,b)
./install.sh --dir ~/.claude/skills        # one root only
./install.sh --list       # discovered skills + versions
./install.sh --uninstall  # remove from every root
```

The same run keeps gstack current and the `code-*` skills in step with it:
gstack is cloned if missing, an existing git checkout is fast-forwarded to
`origin/main` and its `./setup` rerun, and the hand-off contract is then
re-verified against what is actually installed. The verified facts land in
each `code-*` skill's `prompts/gstack-contract.md` (every installed gstack
expert with its description, `/review`'s specialists, force flags and
thresholds, `/autoplan`'s phase order, plan-review scope gates), the skills'
"verified against gstack X" pins are bumped, and their patch version is bumped
when the snapshot changed. The skills treat that snapshot as the live roster
and pick the best-suited installed expert, so new gstack experts are usable as
soon as the installer has run. `--no-gstack` skips all of it, `--no-sync`
upgrades gstack but leaves the snapshot alone.

A skill is any top-level folder with a `SKILL.md`, so new skills are picked
up automatically. Versions come from each skill's `SKILL.md` frontmatter
(cross-checked against its `plugin.json`); a record of what is installed
where lives in `~/.config/cp-skills/installed.tsv`. Set
`CP_SKILLS_ROOTS="dir1:dir2"` to override the candidate roots.

Each skill also ships its own `install.sh` with the same flags for
installing that one skill on its own.

## Requirements

- `python3` ≥ 3.9 for the `code-*` skills.
- `python3` ≥ 3.12 for `stock-eval`'s optional sources.

## License

**Proprietary — All Rights Reserved.** See [LICENSE](LICENSE).

These skills are **not** open source. You may view and evaluate them for
personal, non-commercial use only. Copying, redistribution, modification,
hosting, or any commercial use requires prior written permission and a
royalty agreement with the copyright holder — to get in touch, [open an
issue](https://github.com/carlosap6576/cp-skills/issues) on this repo or
reach out via [GitHub profile](https://github.com/carlosap6576).

## Disclaimer — No Financial Advice

The author is **not a financial advisor** and is not registered with any
regulatory body. `stock-eval` and every other skill here are **experimental
research prototypes** provided for informational and educational purposes
only. Nothing they produce is investment advice or a recommendation to buy,
hold, or sell any security. Outputs may be wrong, incomplete, or out of
date. **We take no responsibility whatsoever for your investments, trades,
or any financial losses.** Always consult a licensed financial professional
before making investment decisions — anything you do with these tools is
entirely at your own risk.
