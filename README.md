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

```bash
git clone https://github.com/carlosap6576/cp-skills.git
cd cp-skills/<skill-name>
./install.sh          # symlinks into every detected skills root
./install.sh --copy   # copy instead of symlink
```

Each skill's own README covers its specific install flags.

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
