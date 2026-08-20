# stock-eval prompts — fundamental analysis suite

Nine expert-persona analysis prompts that turn a single ticker into a full
fundamental report. Each file is a self-contained system prompt. The runner
substitutes the ticker, runs each prompt as its own query, and assembles the
nine outputs **in numeric order** into one report.

This is the **fundamental** lane (SEC EDGAR primary filings + WebSearch). It is
distinct from the social-sentiment engine in `scripts/stock_eval.py`, which ranks
what people are saying on Reddit / X / YouTube. The two are complementary: prompt
`08_price_and_sentiment` is the natural place to fold in the social engine's
output if you wire them together later.

## Execution model

```
/stock-eval META   →  all nine sections, in order
  01_business_phase.md         🧭 Lifecycle Stage          provides: phase ─┐
  02_business_analysis.md      🏢 Business Model                            │
  03_moat_analysis.md          🏰 Competitive Moat                          │
  04_growth_drivers.md         🚀 Growth Drivers                            │
  05_key_metrics.md            📊 Key Metrics              requires: phase ◄┤
  06_risk_analysis.md          ⚠️ Risk Profile             + social         │
  07_valuation_analysis.md     💰 Valuation                optional phase ◄─┘
  08_price_and_sentiment.md    📈 Price & Sentiment        + social
  09_disruption_resilience.md  🛡️ Disruption Resilience
assemble sections 1..9 → final report
```

Each prompt runs **independently** with its own persona and output template.
They are assembled in order, not fused into one mega-prompt.

## Placeholder contract

The runner string-substitutes these tokens in each file's body before sending:

| Token         | Meaning                                              | Source                          |
|---------------|------------------------------------------------------|---------------------------------|
| `{{TICKER}}`  | The symbol under analysis, e.g. `META`               | the `/stock-eval` argument      |
| `{{PHASE}}`   | Lifecycle phase (Phase 1–6) — only in `05` and `07`  | the output of `01_business_phase` |

Rules:
- Replace every `{{TICKER}}` occurrence with the literal symbol.
- `[Company Name]` is **not** a placeholder — the model resolves the issuer name
  from the ticker. Leave it.
- If a token is left unsubstituted (standalone / manual use), each prompt has a
  documented fallback: `{{TICKER}}` → ask the user; `{{PHASE}}` → self-determine.

## Frontmatter contract

Every file starts with YAML frontmatter the assembler parses, then **strips**
before sending the body to the model:

```yaml
---
order: 1                  # assembly order (1–9)
id: business_phase        # stable machine id (kept stable for page consumers)
title: Lifecycle Stage    # display title — the section heading in the report
emoji: "🧭"
placeholders:             # tokens the runner must substitute
  - "{{TICKER}}"
provides:                 # context this prompt produces for later prompts
  - phase
requires: []              # context this prompt needs from earlier prompts
---
```

The dependency wiring is fully declared: `01` has `provides: [phase]`; `05` has
`requires: [phase]`. A runner can therefore order and wire the suite from
frontmatter alone — no hard-coded knowledge.

## Files

| # | File                              | id                    | Title                  | provides | requires |
|---|-----------------------------------|-----------------------|------------------------|----------|----------|
| 1 | `01_business_phase.md`            | business_phase        | 🧭 Lifecycle Stage      | phase    | —        |
| 2 | `02_business_analysis.md`         | business_analysis     | 🏢 Business Model       | —        | —        |
| 3 | `03_moat_analysis.md`             | moat                  | 🏰 Competitive Moat     | —        | —        |
| 4 | `04_growth_drivers.md`            | growth_drivers        | 🚀 Growth Drivers       | —        | —        |
| 5 | `05_key_metrics.md`               | key_metrics           | 📊 Key Metrics          | —        | phase    |
| 6 | `06_risk_analysis.md`             | risk                  | ⚠️ Risk Profile         | —        | —        |
| 7 | `07_valuation_analysis.md`        | valuation             | 💰 Valuation            | —        | (phase)  |
| 8 | `08_price_and_sentiment.md`       | price_sentiment       | 📈 Price & Sentiment    | —        | —        |
| 9 | `09_disruption_resilience.md`     | disruption_resilience | 🛡️ Disruption Resilience| —        | —        |

## Assembly sketch (for whoever wires this next)

```python
import re, pathlib, yaml

PROMPTS = sorted(pathlib.Path("prompts").glob("[0-9][0-9]_*.md"))

def load(path):
    text = path.read_text()
    fm, body = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S).groups()
    return yaml.safe_load(fm), body

def render(body, ticker, phase=None):
    body = body.replace("{{TICKER}}", ticker)
    if phase is not None:
        body = body.replace("{{PHASE}}", phase)
    return body

# sequential: run 01..09 in order; each section's output is fed as context to the next.
```

The runner lives in `SKILL.md` → **"Fundamental Report (sequential, accumulating)"**.
A bare ticker runs all nine prompts in order into one saved report.

## How the report runs (sequential accumulation)

`/stock-eval META` (bare ticker) runs the **fundamental report**: all nine prompts,
in order (01→09), each building on the outputs of the ones before it, assembled into
one document saved to `../outputs/{linux-epoch}_{ticker}.md`.

```
/stock-eval META                                       # add --emit to also save a file
  resolve META → Meta Platforms, Inc.
  SOCIAL = run stock_eval.py once (--emit=compact)     # real Reddit/X/YT/Polymarket, ONCE  (skip if --no-social)
  ACC = ""                                              # accumulated prior sections
  for i in 01..09:
      body      = strip-frontmatter(read 0i_*.md); sub {{TICKER}}
      ctx       = ACC + (SOCIAL if i in {06,08} else "") # corpus injected into §06 + §08 ONLY
      section_i = run( ctx + body )                      # SEC EDGAR + WebSearch (+ social for §06/§08)
      ACC      += section_i                              # learn, carry forward (§06/§08: synthesized text only)
  report = "At a glance" block + section_01..09
  if --emit: save → outputs/{ts}_META.md                # FILE written ONLY when --emit; else chat-only
```

**Accumulate outputs, not instructions.** Each step loads ONE prompt's instructions
plus the *prior section outputs*. The nine instruction sets never combine, so context
per step stays small while the report gains one consistent thesis. The lifecycle phase
from 01 flows to 05/07 for free (it is already in the accumulated context) — the old
`{{PHASE}}` plumbing is no longer load-bearing; the placeholder stays as harmless
reinforcement.

## Social merge — real sentiment in §06 + §08

By default the report pulls **real engagement-ranked social data** so two sections read
actual Reddit / X / YouTube / Polymarket posts instead of generic WebSearch: **§08
(Price & Sentiment)** for the mood and bull/bear voices, and **§06 (Risk)** for the
risks filings under-report (reputational/headline, litigation chatter, short-squeeze /
crowded-trade positioning). Built for token efficiency:

- **Run the engine ONCE** per report (step 1.5 in the runner), before the loop.
- **Inject the corpus into §06 + §08 only** — never into the global `ACC` buffer, or
  every later step would re-read the whole corpus. Only those two sections' short
  *synthesized* outputs enter `ACC`, so the rest of the report sees the distilled
  signal, not the raw clusters.
- **Graceful fallback:** if the engine errors / has no API keys / returns thin, §06 and
  §08 fall back to WebSearch. A social miss never aborts the report.
- **`--no-social`** skips the pull entirely for a fast filings-only run.
- Both sections cite social voices in **plain text** (`r/stocks`, `@handle`) — no links,
  per the clean-report rule.

## Routing (only two lanes, no modes/menu)

```
/stock-eval                       → ask for a ticker
/stock-eval META                  → report (all 9 + real social in §06/§08) → CHAT ONLY (no file)
/stock-eval META --emit           → same report, ALSO saved → outputs/{ts}_META.md
/stock-eval META --emit=html      → saved as outputs/{ts}_META.html  (json also supported)
/stock-eval META --no-social      → report, filings only (skip the social pull; faster)
/stock-eval META --social         → social sentiment engine ALONE (scripts/stock_eval.py)
/stock-eval META earnings         → social topic (free text)
/stock-eval AMD vs NVDA           → social comparison ("vs" wins)
```

`--emit` and `--no-social` combine (`/stock-eval META --emit=html --no-social`). No
`--mode`, no per-section selection, no menu.

## Output — file written ONLY on `--emit`

A bare `/stock-eval META` shows the report in chat and **writes nothing to disk**. Pass
`--emit` to save a file (and the social raw alongside it); without it, the social pull
runs in memory and is discarded.

When `--emit` is given: `../outputs/{linux-epoch}_{ticker}.{ext}`
- `--emit`/`--emit=md` → `.md` · `--emit=html` → shareable HTML · `--emit=json` → structured data.
- The Linux epoch timestamp records exactly when the report ran.
- **Nice to read:** opens with a 5-line **At a glance** (phase · moat · valuation · sentiment · bottom line) composed from the sections already written (no extra research), then one `##` section per analysis under a single H1.
- **Clean content:** no inline `[name](url)` links, no raw URLs, no trailing `Sources:`
  block. Provenance is the header `Basis:` line (plain text); per-section `## 🔗 Sources`
  blocks were removed from the templates.
- `outputs/` is gitignored (generated, not source); `.gitkeep` keeps the folder.

## JSON & HTML output — page-ready (`--emit=json` / `--emit=html`)

For serving the report on a web page. The full schema lives in `SKILL.md` → step 4;
the short version:

**JSON (`stock-eval.fundamental-report/v1`)** is a metadata envelope around the **same
Markdown** the `--emit=md` report uses — so all three formats carry identical content.
Top level: `ticker`, `issuer`, `exchange`, `generated_utc`, `generated_unix`, `basis`,
`social_included`, `at_a_glance` (always the 5 labels, structured label/value), and
`sections` (**always all 9**, `order` 1..9, `id` matching the prompt). Each section has
`order` · `id` · `emoji` · `title` · `summary` · `basis` · **`body`**.

**`body` is GitHub-flavored Markdown** — byte-for-byte that section's content in the
`.md` file (tables, `-`/`1.` lists, `**bold**`, paragraphs; no links, no `##` heading
line). Newlines JSON-escaped as `\n`. Same content, three shapes:
- `--emit=md` → the flat Markdown report,
- `--emit=json` → metadata + each section's Markdown in `body`,
- `--emit=html` → that Markdown rendered to semantic HTML.

**Worked example** (one section: JSON `body` Markdown → HTML out):

```json
{ "order": 1, "id": "business_phase", "emoji": "🧭", "title": "Lifecycle Stage",
  "summary": "Phase 4: Operating Leverage", "basis": "SEC Q1 2026 10-Q",
  "body": "| Category | Value |\n|---|---|\n| **Stage** | Phase 4: Operating Leverage |\n| **Confidence** | High |\n\n- Operating margin ~41%\n- Revenue +33% YoY" }
```

```html
<section class="se-section" data-section-id="business_phase">
  <h2 class="se-section-title">🧭 1. Lifecycle Stage</h2>
  <table><thead><tr><th>Category</th><th>Value</th></tr></thead>
    <tbody><tr><td><strong>Stage</strong></td><td>Phase 4: Operating Leverage</td></tr>
    <tr><td><strong>Confidence</strong></td><td>High</td></tr></tbody></table>
  <ul><li>Operating margin ~41%</li><li>Revenue +33% YoY</li></ul>
</section>
```

The HTML emit **renders each section's `body` Markdown** to these semantic elements, so
md / json / html never drift. Class hooks only (`se-report`, `se-glance`, `se-section`,
`se-section-title`, `data-section-id`) — no `<style>`, no `style=`, no colors. Drop it in
your page and style with your own CSS.

## Frontmatter — what's still used

`order` (run order 01→09) and `title` / `emoji` (section headers in the assembled
report) are live. `requires` / `provides` / `placeholders` are now informational
only — sequential accumulation subsumes the dependency wiring they described.
