#!/usr/bin/env python3
"""
code_execute.py — stdlib-only helper for the /code-execute skill.

Subcommands:
  plan-check   Validate a plan file is an executable plan (.md with steps).
  default-plan Resolve the single plan in <repo-root>/.plan when -p was omitted
               (STRICT: missing folder, empty folder, or >1 plan all exit 2).
  render       Substitute the {{PATH}} placeholder in the execute-prompt template.

Portable: Python 3.9+, standard library only (argparse, os, re, sys, pathlib).
Deliberately minimal — no LM Studio / enhance code (code-execute has no enhance step).
Mirrors the patterns in skills/code-plan/scripts/code_plan.py (_read_text, _err,
_UNSUBSTITUTED) without cross-folder importing it, so this skill folder stays
independently installable.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Any remaining {{UPPER_TOKEN}} after substitution is a half-rendered prompt.
_UNSUBSTITUTED = re.compile(r"{{[A-Z_]+}}")

# An executable plan has at least one step heading (### ...). This is the
# structure code-plan guarantees; without it any README would "execute".
_STEP_HEADING = re.compile(r"^###\s+\S", re.MULTILINE)


# ---------------------------------------------------------------------------
# Helpers shared by subcommands
# ---------------------------------------------------------------------------

def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _err(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# `plan-check` — structure validation
# ---------------------------------------------------------------------------

def cmd_plan_check(args: argparse.Namespace) -> int:
    raw = args.plan
    if not raw:
        _err("no plan file given")
        return 2

    path = Path(raw).expanduser()
    if not path.is_file():
        _err(f"plan file does not exist: {raw}")
        return 2

    # Cheap suffix gate BEFORE reading — no point slurping a binary blob.
    if not path.name.endswith(".md"):
        _err(f'not a .md file: {path}')
        return 2

    try:
        content = _read_text(path)
    except OSError as exc:
        _err(f"cannot read plan file {path}: {exc}")
        return 2
    except UnicodeDecodeError:
        # A binary file named *.md — clean exit 2, never a traceback.
        _err(f"plan file is not UTF-8 text: {path}")
        return 2

    if not content.strip():
        _err("plan file is empty")
        return 2

    if not _STEP_HEADING.search(content):
        _err('no "### " step headings — not an executable plan')
        return 2

    # Print the absolute path — reused downstream as the canonical PLAN_ABS,
    # never re-resolved from the raw -p value.
    print(str(path.resolve()))
    return 0


# ---------------------------------------------------------------------------
# `default-plan` — strict auto-discovery for an omitted -p
# ---------------------------------------------------------------------------
#
# Mirrors code-plan's default save location: the `.plan` folder at the repo
# root (found by walking up from the cwd for a `.git` entry — pure filesystem
# walk, no git commands, so LAW 1 stays intact; no repo → the cwd itself).
# The rules are STRICT by design — this resolves ambiguity, it never guesses:
#   exactly one *.md in .plan  → print its absolute path, exit 0
#   .plan missing              → exit 2 ("provide -p")
#   .plan has no *.md files    → exit 2 ("provide -p")
#   .plan has 2+ *.md files    → exit 2 ("provide -p", candidates listed)

DEFAULT_PLAN_DIRNAME = ".plan"


def _find_repo_root(start: Path) -> Path:
    """Walk up from `start` looking for a `.git` entry (dir for normal repos,
    file for worktrees/submodules). No git binary is invoked. No `.git`
    anywhere → `start` itself."""
    cur = start.resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / ".git").exists():
            return candidate
    return cur


def cmd_default_plan(_args: argparse.Namespace) -> int:
    root = _find_repo_root(Path.cwd())
    plan_dir = root / DEFAULT_PLAN_DIRNAME

    if not plan_dir.is_dir():
        _err(f"no {DEFAULT_PLAN_DIRNAME}/ folder at {root} — pass -p <plan.md> "
             "(or create a plan there first with /code-plan)")
        return 2

    plans = sorted(p for p in plan_dir.iterdir()
                   if p.is_file() and p.name.endswith(".md"))

    if not plans:
        _err(f"{plan_dir} has no plan files (*.md) — pass -p <plan.md>")
        return 2

    if len(plans) > 1:
        _err(f"{plan_dir} has {len(plans)} plans — pass -p to choose one:")
        for p in plans:
            _err(f"  -p {p}")
        return 2

    print(str(plans[0].resolve()))
    return 0


# ---------------------------------------------------------------------------
# `render` — placeholder substitution (single token: {{PATH}})
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    template_path = Path(args.template)
    try:
        template = _read_text(template_path)
    except OSError as exc:
        _err(f"cannot read template {template_path}: {exc}")
        return 1
    except UnicodeDecodeError:
        _err(f"cannot read template {template_path}: not UTF-8 text")
        return 1

    plan_abs = str(Path(args.plan).expanduser().resolve())

    out = template.replace("{{PATH}}", plan_abs)

    leftover = _UNSUBSTITUTED.findall(out)
    if leftover:
        _err("ERROR: unsubstituted placeholder(s): " + ", ".join(sorted(set(leftover))))
        return 3

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
        prog="code_execute.py",
        description="Helper for the /code-execute skill (stdlib only).",
    )
    p.add_argument("--skill-dir", default=None,
                   help="skill directory (default: parent of this script)")

    sub = p.add_subparsers(dest="command", required=True)

    # plan-check
    sp = sub.add_parser("plan-check", help="validate a plan file is executable")
    sp.add_argument("--plan", required=True, help="path to the plan .md file")
    sp.set_defaults(func=cmd_plan_check)

    # default-plan
    sp = sub.add_parser("default-plan",
                        help="resolve the single plan in <repo-root>/.plan "
                             "(exit 2 unless exactly one *.md exists)")
    sp.set_defaults(func=cmd_default_plan)

    # render
    sp = sub.add_parser("render", help="substitute {{PATH}} in the execute-prompt template")
    sp.add_argument("--template", default=None,
                    help="path to execute-plan.md (default: {skill_dir}/prompts/execute-plan.md)")
    sp.add_argument("--plan", required=True, help="absolute path to the plan .md file")
    sp.set_defaults(func=cmd_render)

    return p


def _apply_skill_dir_defaults(args: argparse.Namespace) -> None:
    """Fill in --template default from the resolved skill dir."""
    if args.skill_dir:
        skill_dir = Path(args.skill_dir).resolve()
    else:
        skill_dir = Path(__file__).resolve().parent.parent
    if args.command == "render" and not args.template:
        args.template = str(skill_dir / "prompts" / "execute-plan.md")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_skill_dir_defaults(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
