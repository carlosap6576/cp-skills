#!/usr/bin/env python3
"""
code_plan.py — stdlib-only helper for the /code-plan skill.

Subcommands:
  enhance-prompt  Compose the instruction-rewrite prompt (frontmatter strip +
                  {{RAW_INSTRUCTIONS}} substitution). The NATIVE model running
                  the skill executes the composed prompt — no external LLM.
  route           Deterministic expert-lens routing for instructions.
  render          Substitute placeholders in the plan prompt template.
  plan-path       Derive the {YYYY-MM-DD}-{slug}-plan.md path for a plan.

Portable: Python 3.9+, standard library only (argparse, json, os, re, sys,
pathlib, datetime). No network, no config resolution — the enhancement runs
in the model that is already executing the skill.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# Any remaining {{UPPER_TOKEN}} after substitution is a half-rendered prompt.
_UNSUBSTITUTED = re.compile(r"{{[A-Z_]+}}")

# Leading YAML frontmatter block (--- ... ---) on a prompt file. Metadata for
# humans/tooling — never part of the prompt the model executes.
_FRONTMATTER = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


# ---------------------------------------------------------------------------
# Helpers shared by subcommands
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# `enhance-prompt` — compose the native rewrite prompt (stdout)
# ---------------------------------------------------------------------------
#
# The old `enhance` subcommand POSTed this composed prompt to LM Studio and
# printed the model's answer. The rewrite now runs in the NATIVE model that is
# already executing the skill: this subcommand only does the deterministic,
# testable part (frontmatter strip + placeholder substitution) and prints the
# ready-to-follow prompt. SKILL.md Step 6 reads it and produces enhanced.txt
# itself — same prompt contract, zero external dependencies.

def cmd_enhance_prompt(args: argparse.Namespace) -> int:
    # Read raw instructions from --instructions-file or stdin. Never argv.
    if args.instructions_file:
        try:
            raw = _read_text(Path(args.instructions_file))
        except OSError as exc:
            _err(f"WARN: cannot read instructions file: {exc}")
            return 2
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        _err("WARN: empty instructions input — nothing to enhance.")
        return 2

    try:
        prompt_template = _read_text(Path(args.prompt))
    except OSError as exc:
        _err(f"WARN: cannot read prompt template {args.prompt}: {exc}")
        return 1

    # Strip YAML frontmatter (metadata, not prompt), then substitute the single
    # placeholder. str.replace, not format/regex — the raw instructions may
    # legitimately contain { } or \ . One replace pass, so prose that itself
    # contains a literal {{RAW_INSTRUCTIONS}} is never re-substituted.
    prompt_template = _FRONTMATTER.sub("", prompt_template, count=1)
    if "{{RAW_INSTRUCTIONS}}" not in prompt_template:
        _err(f"WARN: template {args.prompt} has no {{{{RAW_INSTRUCTIONS}}}} placeholder.")
        return 1
    composed = prompt_template.replace("{{RAW_INSTRUCTIONS}}", raw)

    sys.stdout.write(composed)
    if not composed.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# `plan-path` — filename derivation
# ---------------------------------------------------------------------------

def _slugify(objective_first_line: str) -> str:
    """Lowercase the first 8 words, strip non-[a-z0-9 ], collapse spaces to -,
    trim to 48 chars, strip trailing -. Empty -> 'plan'."""
    words = objective_first_line.split()[:8]
    joined = " ".join(words).lower()
    cleaned = re.sub(r"[^a-z0-9 ]", "", joined)
    cleaned = re.sub(r"\s+", "-", cleaned.strip())
    cleaned = cleaned[:48].rstrip("-")
    return cleaned or "plan"


DEFAULT_PLAN_DIRNAME = ".plan"
GITIGNORE_ENTRY = ".plan/"
GITIGNORE_COMMENT = "# code-plan output — local plans, never committed"


def _find_repo_root(start: Path) -> Path:
    """Walk up from `start` looking for a `.git` entry (a dir for normal
    repos, a file for worktrees/submodules). Pure filesystem walk — no git
    binary is ever invoked (LAW 1 stays intact). No `.git` found → `start`
    itself is the root (non-repo folders still get a local .plan)."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return cur


def _plan_dir_is_ignored(gitignore_text: str) -> bool:
    """True if any line of .gitignore already covers the .plan directory."""
    for line in gitignore_text.splitlines():
        if line.strip() in (".plan", ".plan/", "/.plan", "/.plan/"):
            return True
    return False


def _ensure_plan_ignored(root: Path) -> None:
    """Idempotently guarantee `.plan/` is git-ignored in `root`. Only acts
    when `root/.git` exists. Creates .gitignore if absent, appends the entry
    if missing, does nothing if already covered. Best-effort: an unwritable
    .gitignore degrades to a loud WARN (never blocks planning) — plans must
    not be lost because ignore-hygiene failed."""
    if not (root / ".git").exists():
        return
    gi = root / ".gitignore"
    block = f"{GITIGNORE_COMMENT}\n{GITIGNORE_ENTRY}\n"
    try:
        if gi.exists():
            text = _read_text(gi)
            if _plan_dir_is_ignored(text):
                return
            prefix = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
            with gi.open("a", encoding="utf-8") as fh:
                fh.write(prefix + block)
            _err(f"NOTE: added '{GITIGNORE_ENTRY}' to {gi}")
        else:
            gi.write_text(block, encoding="utf-8")
            _err(f"NOTE: created {gi} with '{GITIGNORE_ENTRY}'")
    except OSError as exc:
        _err(f"WARN: could not update {gi} ({exc}) — add '{GITIGNORE_ENTRY}' "
             "manually so plans stay out of commits")


def cmd_plan_path(args: argparse.Namespace) -> int:
    if args.objective_file:
        try:
            objective = _read_text(Path(args.objective_file))
        except OSError as exc:
            _err(f"cannot read objective file: {exc}")
            return 2
    elif args.objective is not None:
        objective = args.objective
    else:
        _err("plan-path requires --objective or --objective-file")
        return 2

    first_line = objective.splitlines()[0] if objective.splitlines() else objective.strip()
    slug = _slugify(first_line)
    stamp = date.today().isoformat()
    base_name = f"{stamp}-{slug}-plan.md"

    if args.path:
        target_dir = Path(args.path).expanduser().resolve()
    else:
        # Default mode: no --path → <repo-root>/.plan, auto-created and
        # git-ignored. Validate/update on EVERY run (a re-run after someone
        # deleted the folder or the .gitignore entry heals both).
        root = _find_repo_root(Path.cwd())
        target_dir = root / DEFAULT_PLAN_DIRNAME
        if not target_dir.exists():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                _err(f"NOTE: created {target_dir}")
            except OSError as exc:
                _err(f"cannot create directory {target_dir}: {exc}")
                return 2
        _ensure_plan_ignored(root)

    # Directory handling (explicit --path only; the default mode above has
    # already created its directory).
    if not target_dir.exists():
        if args.mkdir:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                _err(f"cannot create directory {target_dir}: {exc}")
                return 2
        else:
            _err(f"directory does not exist: {target_dir} (pass --mkdir to create it)")
            return 2
    elif not target_dir.is_dir():
        _err(f"not a directory: {target_dir}")
        return 2

    if target_dir.exists() and not os.access(str(target_dir), os.W_OK):
        _err(f"directory not writable: {target_dir}")
        return 2

    # Collision handling: never overwrite. Suffix goes before the .md, keeping
    # the -plan marker: 2026-07-25-slug-plan-2.md.
    candidate = target_dir / base_name
    if candidate.exists():
        stem = target_dir / f"{stamp}-{slug}-plan"
        n = 2
        while n < 100:
            alt = Path(str(stem) + f"-{n}.md")
            if not alt.exists():
                candidate = alt
                break
            n += 1
        else:
            _err(f"could not find a free filename after 99 collisions in {target_dir}")
            return 2

    print(str(candidate))
    return 0


# ---------------------------------------------------------------------------
# `route` — deterministic expert-lens routing (model may adjust by ±1 lens)
# ---------------------------------------------------------------------------
#
# The router maps the (enhanced) instruction text to a lens set and a
# recommended follow-up skill via a keyword-signal table — no LLM, no
# randomness, same input always yields the same output. Step 8 of SKILL.md
# keeps model judgment but only as a bounded add/drop on top of this floor.
#
# Invariants (enforced by selftest RoutingTableConsistencyTests):
#   - LENS_PRIORITY, LENS_SKILL and SIGNALS share the SAME set of lens ids.
#   - every LENS_SKILL value is a gstack skill name that appears in the
#     "Known follow-up skills" table in prompts/expert-lenses.md.

LENS_PRIORITY = ["investigate", "security", "eng", "design", "devex",
                 "qa", "perf", "docs", "product", "ios"]

LENS_SKILL = {
    "design": "plan-design-review",
    "eng": "plan-eng-review",
    "security": "cso",
    "qa": "qa",
    "devex": "plan-devex-review",
    "product": "plan-ceo-review",
    "investigate": "investigate",
    "docs": "docs-refresh",
    "ios": "plan-eng-review",
    "perf": "plan-eng-review",
}

SIGNALS = {
    "design": ["ui", "ux", "component", "page", "screen", "css", "style",
               "styling", "layout", "button", "modal", "form", "dashboard",
               "react", "tailwind", "responsive", "design system", "visual",
               "theme", "dark mode", "accessibility", "a11y", "frontend",
               "hover", "tile", "chart", "tooltip", "dropdown", "animation"],
    "eng": ["api", "endpoint", "backend", "service", "schema", "database",
            "migration", "refactor", "architecture", "concurrency", "queue",
            "worker", "pipeline", "cache", "sql", "module", "class",
            "integration", "server"],
    "security": ["auth", "authentication", "authorization", "token", "secret",
                 "credential", "password", "oauth", "permission", "sanitize",
                 "injection", "xss", "csrf", "ssrf", "encrypt", "vulnerability"],
    "qa": ["test", "tests", "testing", "regression", "coverage", "verify",
           "validation", "flaky", "e2e", "smoke", "qa"],
    "devex": ["cli", "skill", "script", "developer experience", "dx",
              "tooling", "install", "setup", "onboarding", "slash command",
              "workflow", "prompt", "agent", "makefile", "flag"],
    "product": ["feature", "users", "customer", "mvp", "launch", "roadmap",
                "pricing", "metric", "adoption"],
    "investigate": ["bug", "broken", "fails", "failing", "crash", "error",
                    "root cause", "stopped working", "debug", "hang",
                    "timeout", "intermittent"],
    "docs": ["readme", "documentation", "docs", "changelog", "guide",
             "claude.md", "docstring"],
    "ios": ["ios", "swift", "swiftui", "xcode", "iphone", "ipad", "app store"],
    "perf": ["performance", "latency", "slow", "optimize", "optimization",
             "benchmark", "profiling", "profile", "throughput", "memory usage",
             "n+1", "hot path", "speed up", "bottleneck"],
}

MAX_LENSES = 3

# Pre-compiled word-boundary matcher per single-word signal (so "ui" never
# matches "build"). Multi-word signals are matched as plain substrings.
_word_re_cache: dict[str, "re.Pattern[str]"] = {}


def _word_pattern(signal: str) -> "re.Pattern[str]":
    pat = _word_re_cache.get(signal)
    if pat is None:
        pat = re.compile(r"\b" + re.escape(signal) + r"\b", re.IGNORECASE)
        _word_re_cache[signal] = pat
    return pat


def _match_signal(text: str, signal: str) -> bool:
    """True if `signal` occurs in `text`. Single-word signals match on a
    \\b-anchored word boundary (so "ui" never matches "build"); multi-word
    signals match as a plain substring (so "design system" still matches)."""
    if " " in signal or "\t" in signal:
        return signal.lower() in text.lower()
    return _word_pattern(signal).search(text) is not None


def route_lenses(text: str) -> dict:
    """Compute the deterministic lens set + recommended follow-up skill for
    `text`. Returns:
        {
          "lenses": [lens, ...],            # <= MAX_LENSES, priority-ordered
          "scores": {lens: int, ...},       # distinct matched signal count
          "recommended_skill": str | None,  # LENS_SKILL[lenses[0]], or
                                            #   "autoplan" when 3 lenses,
                                            #   None when no candidates
          "matched": {lens: [signal, ...]}, # the distinct matched signals
        }
    No candidates → {"lenses": [], "recommended_skill": None} (generalist is
    a valid outcome, never an error).
    """
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for lens, signals in SIGNALS.items():
        hits = [s for s in signals if _match_signal(text, s)]
        if hits:
            scores[lens] = len(set(hits))
            matched[lens] = sorted(set(hits))

    # Candidates: score >= 1, sorted by (-score, LENS_PRIORITY.index).
    candidates = sorted(
        scores,
        key=lambda lens: (-scores[lens], LENS_PRIORITY.index(lens)),
    )
    selected = candidates[:MAX_LENSES]

    if not selected:
        return {"lenses": [], "scores": scores, "recommended_skill": None,
                "matched": matched}

    if len(selected) == MAX_LENSES:
        # One combo review beats three separate ones (matches SKILL.md Step 11).
        recommended = "autoplan"
    else:
        recommended = LENS_SKILL[selected[0]]

    return {"lenses": selected, "scores": scores,
            "recommended_skill": recommended, "matched": matched}


def cmd_route(args: argparse.Namespace) -> int:
    # Read instructions from --instructions-file (or stdin). Never argv.
    if args.instructions_file:
        try:
            text = _read_text(Path(args.instructions_file))
        except OSError as exc:
            _err(f"cannot read instructions file: {exc}")
            return 2
    else:
        text = sys.stdin.read()

    # --experts forces the lens set verbatim (or "none" → empty).
    if args.experts is not None:
        raw = args.experts.strip()
        if raw.lower() == "none":
            forced: list[str] = []
        else:
            forced = [x.strip() for x in raw.split(",") if x.strip()]
            valid = set(SIGNALS)
            unknown = [x for x in forced if x not in valid]
            if unknown:
                valid_list = ", ".join(sorted(valid))
                _err(
                    "ERROR: unknown expert lens "
                    f"'{unknown[0]}' — valid: {valid_list}"
                )
                return 2
        lenses = forced
        # recommended_skill follows the same 3-lens → autoplan rule.
        if lenses and len(lenses) == MAX_LENSES:
            recommended_skill: str | None = "autoplan"
        elif lenses:
            recommended_skill = LENS_SKILL[lenses[0]]
        else:
            recommended_skill = None
        scores: dict[str, int] = {}
        matched: dict[str, list[str]] = {}
        payload = {"lenses": lenses, "scores": scores,
                   "recommended_skill": recommended_skill, "matched": matched}
    else:
        payload = route_lenses(text)

    if args.json:
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
    else:
        lenses_str = ",".join(payload["lenses"]) if payload["lenses"] else "none"
        skill = payload.get("recommended_skill")
        skill_str = skill if skill else "none"
        sys.stdout.write(f"lenses: {lenses_str}\n")
        sys.stdout.write(f"skill: {skill_str}\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# `render` — placeholder substitution
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    instructions_path = Path(args.instructions_file)
    try:
        template = _read_text(template_path)
    except OSError as exc:
        _err(f"cannot read template {template_path}: {exc}")
        return 1
    try:
        instructions = _read_text(instructions_path)
    except OSError as exc:
        _err(f"cannot read instructions {instructions_path}: {exc}")
        return 1

    lenses = "No expert lenses selected — plan as a seasoned generalist senior engineer."
    if args.lenses_file:
        try:
            lenses = _read_text(Path(args.lenses_file))
        except OSError as exc:
            _err(f"cannot read lenses {args.lenses_file}: {exc}")
            return 1

    # Substitution ORDER MATTERS: instructions last, so user prose containing
    # a literal {{PATH}} cannot be re-substituted by the PATH replacement.
    out = template
    out = out.replace("{{PROJECT_TAG}}", args.tag or "ui-data")
    out = out.replace("{{PATH}}", args.path or "")
    out = out.replace("{{PLAN_FILENAME}}", args.plan_filename or "")

    # Leftover guard runs BEFORE lenses and instructions go in: it must only
    # ever see template tokens. Lens text and user prose may legitimately
    # contain {{TOKEN}}-shaped text, and that must never trip an exit 3.
    leftover = [t for t in _UNSUBSTITUTED.findall(out)
                if t not in ("{{INSTRUCTIONS}}", "{{EXPERT_LENSES}}")]
    if leftover:
        _err("ERROR: unsubstituted placeholder(s): " + ", ".join(sorted(set(leftover))))
        return 3

    out = out.replace("{{EXPERT_LENSES}}", lenses)
    out = out.replace("{{INSTRUCTIONS}}", instructions)

    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="code_plan.py",
        description="Helper for the /code-plan skill (stdlib only).",
    )
    p.add_argument("--skill-dir", default=None,
                   help="skill directory (default: parent of this script)")

    sub = p.add_subparsers(dest="command", required=True)

    # enhance-prompt
    sp = sub.add_parser("enhance-prompt",
                        help="compose the native instruction-rewrite prompt")
    sp.add_argument("--prompt", default=None,
                    help="path to enhance-instructions.md (default: {skill_dir}/prompts/enhance-instructions.md)")
    sp.add_argument("--instructions-file", default=None,
                    help="read raw instructions from this file (default: stdin)")
    sp.set_defaults(func=cmd_enhance_prompt)

    # route
    sp = sub.add_parser("route",
                        help="deterministic expert-lens routing for instructions")
    sp.add_argument("--instructions-file", default=None,
                    help="read instructions from this file (default: stdin)")
    sp.add_argument("--experts", default=None,
                    help="force lens set verbatim (comma list, or 'none'); "
                         "valid ids validated against the routing table")
    sp.add_argument("--json", action="store_true", dest="json",
                    help="emit a JSON object (lenses, scores, recommended_skill, matched)")
    sp.set_defaults(func=cmd_route)

    # render
    sp = sub.add_parser("render", help="substitute placeholders in the plan template")
    sp.add_argument("--template", default=None,
                    help="path to create-plan.md (default: {skill_dir}/prompts/create-plan.md)")
    sp.add_argument("--tag", default="ui-data",
                    help="data-* debug tag (default: ui-data — the skill never prompts for it)")
    sp.add_argument("--lenses-file", default=None,
                    help="file with the expert-lens block for {{EXPERT_LENSES}}; omitted → generalist default")
    sp.add_argument("--path", default=None)
    sp.add_argument("--plan-filename", default=None)
    sp.add_argument("--instructions-file", required=True,
                    help="read instructions from this file (required)")
    sp.set_defaults(func=cmd_render)

    # plan-path
    sp = sub.add_parser("plan-path", help="derive the plan file path")
    sp.add_argument("--path", default=None,
                    help="destination directory (omitted → <repo-root>/.plan, "
                         "auto-created and git-ignored)")
    grp = sp.add_mutually_exclusive_group(required=True)
    grp.add_argument("--objective", default=None, help="objective text")
    grp.add_argument("--objective-file", default=None, help="read objective from file")
    sp.add_argument("--mkdir", action="store_true", help="create the directory if missing")
    sp.set_defaults(func=cmd_plan_path)

    return p


def _apply_skill_dir_defaults(args: argparse.Namespace) -> None:
    """Fill in --prompt / --template defaults from the resolved skill dir."""
    if args.skill_dir:
        skill_dir = Path(args.skill_dir).resolve()
    else:
        skill_dir = Path(__file__).resolve().parent.parent
    if args.command == "enhance-prompt" and not args.prompt:
        args.prompt = str(skill_dir / "prompts" / "enhance-instructions.md")
    if args.command == "render" and not args.template:
        args.template = str(skill_dir / "prompts" / "create-plan.md")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_skill_dir_defaults(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
