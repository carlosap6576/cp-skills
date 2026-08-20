# stock-eval

Evaluate a stock or company by what people are **actually saying right now**.

`/stock-eval META` (or `/stock-eval Apple`, `/stock-eval NVDA earnings reaction`)
researches a ticker or company name across Reddit, X, YouTube, TikTok, Hacker
News, Polymarket, GitHub, and the web, ranks every result by **real
engagement** (upvotes, likes, comments, prediction-market money — not editors),
and returns a single synthesized, citation-backed read on sentiment over the
last 30 days.

It is a **research tool, not financial advice.**

> **Disclaimer — No Financial Advice.** The author is **not a financial
> advisor**, broker, or registered investment adviser. This skill is an
> **experimental research prototype** for informational and educational
> purposes only. Nothing it outputs is investment advice or a recommendation
> to buy, hold, or sell any security; outputs may be wrong, incomplete, or
> stale. **We take no responsibility whatsoever for your investments or any
> financial losses.** Consult a licensed financial professional before making
> any investment decision — everything you do with this tool is at your own
> risk.
>
> **License.** Proprietary — All Rights Reserved. Personal, non-commercial
> evaluation only; any copying, redistribution, or commercial use requires
> prior written permission and a royalty agreement. See [LICENSE](LICENSE).

## Install

From this directory:

```bash
./install.sh            # symlink into ~/.claude/skills/stock-eval (default)
./install.sh --copy     # copy instead of symlinking
./install.sh --uninstall
```

Or install by hand — drop (or symlink) the whole `stock-eval/` folder into any
skills directory your agent scans, e.g.:

```bash
ln -s "$PWD" ~/.claude/skills/stock-eval
```

Requirements: **Python 3.12+** on `PATH`. That's it for the core path.

See SKILL.md for the full contract.
