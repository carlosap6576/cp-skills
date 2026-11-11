#!/usr/bin/env python3
"""
code_validation.py — stdlib-only helper for the /code-validation skill.

Subcommands:
  plan-check    Validate a plan file is an executable plan (.md with steps).
  render        Substitute the {{PATH}} placeholder in the validate-code template.
  default-plan  Auto-discover the plan in <repo-root>/.plan (omitted -p): the only
                plan, or the one the pipeline signals single out.
  repo-root     Print the repo root containing the plan (filesystem walk, no git).
  sweep-scan    Scan the change's added lines / new files for production debris.
  close-out     Delete the plan file and print the LAW 6 announcement line.
  signal        Write the machine-readable pipeline stage signal
                (.plan/.signals/<plan-stem>.validate.json) for automation.

Portable: Python 3.9+, standard library only (argparse, json, os, re, sys,
pathlib, datetime).
Deliberately minimal — no LM Studio / enhance machinery (validation has no
rewrite step, exactly like code-execute).
Mirrors the patterns in skills/code-execute/scripts/code_execute.py
(_read_text, _err, _UNSUBSTITUTED) without cross-folder importing it, so this
skill folder stays independently installable.

The ONE functional difference from code_execute.py: `render`'s default template
resolves to `{skill_dir}/prompts/validate-code.md` (the audit prompt) instead of
`execute-plan.md`. Everything else — subcommands, exit codes, gate ordering — is
identical, by design: this skill solves the same problem shape (one path
parameter → validate → pin cwd → substitute {{PATH}} → follow the prompt →
mtime-check the plan file).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
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
        _err(f"not a .md file: {path}")
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
# `default-plan` — auto-discovery for an omitted -p
# ---------------------------------------------------------------------------
#
# Mirrors code-execute's discovery of code-plan's default save location: the
# `.plan` folder at the repo root (found by walking up from the cwd for a
# `.git` entry — pure filesystem walk, no git commands, so LAW 1 stays
# intact; no repo → the cwd itself). Exit-code contract:
#   exactly one *.md in .plan  → print its absolute path, exit 0
#   .plan missing              → exit 2
#   .plan has no *.md files    → exit 2
#   .plan has 2+ *.md files    → the ONE plan whose pipeline signals show it
#                                waiting for this stage (code-execute
#                                succeeded, validation has not since) →
#                                exit 0; otherwise exit 2 (candidates listed)
# Exit 2 is a STOP with a failed signal in SKILL.md — the skill never prompts.

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


def _signal_time(signal_dir: Path, stem: str, stage: str):
    """`written_at` of a SUCCESS signal for (stem, stage), else None. A
    missing, unreadable, malformed or failed signal is simply "no signal"."""
    try:
        data = json.loads((signal_dir / f"{stem}.{stage}.json")
                          .read_text(encoding="utf-8"))
        if data.get("status") != "success":
            return None
        return datetime.fromisoformat(data["written_at"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _pending_plans(plans: list, signal_dir: Path) -> list:
    """Plans the pipeline says are waiting for THIS stage: the upstream stage
    succeeded and this stage has not succeeded since. Evidence, not a guess —
    it reads only the signal files the sibling skills wrote."""
    pending = []
    for plan in plans:
        upstream = _signal_time(signal_dir, plan.stem, UPSTREAM_STAGE)
        if upstream is None:
            continue
        done = _signal_time(signal_dir, plan.stem, SIGNAL_STAGE)
        if done is None or done < upstream:
            pending.append(plan)
    return pending


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
        pending = _pending_plans(plans, plan_dir / SIGNAL_DIRNAME)
        if len(pending) == 1:
            _err(f"NOTE: {len(plans)} plans in {plan_dir}; the pipeline signals "
                 f"show exactly one waiting for the {SIGNAL_STAGE} stage — "
                 f"selected {pending[0].name}")
            print(str(pending[0].resolve()))
            return 0
        _err(f"{plan_dir} has {len(plans)} plans and the pipeline signals do "
             f"not single one out — pass -p to choose one:")
        for p in plans:
            _err(f"  -p {p}")
        return 2

    print(str(plans[0].resolve()))
    return 0


# ---------------------------------------------------------------------------
# `repo-root` — the directory the plan's repo-relative paths resolve against
# ---------------------------------------------------------------------------
#
# Pure filesystem walk from the plan file's own directory (never the git
# binary), so the skill resolves its working directory without running git.

def cmd_repo_root(args: argparse.Namespace) -> int:
    plan = Path(args.plan).expanduser().resolve()
    start = plan.parent
    root = _find_repo_root(start)
    # A plan saved in <root>/.plan with no .git above it still belongs to <root>.
    if root == start and start.name == DEFAULT_PLAN_DIRNAME:
        root = start.parent
    print(str(root))
    return 0


# ---------------------------------------------------------------------------
# `close-out` — LAW 6: delete the plan, then print the announcement
# ---------------------------------------------------------------------------
#
# WHY THIS IS A SUBCOMMAND AND NOT A LINE OF SKILL.md PROSE
# ---------------------------------------------------------
# Step 7 used to be two uncoupled things: a `rm -f "$PLAN_ABS"` the model had
# to remember to run, and a "PLAN DELETED — …" sentence the model wrote itself.
# Writing a sentence is free; running a tool is not. At the end of a long audit
# report the model reliably emitted the claim and skipped the act, leaving the
# plan on disk under a message saying it was gone — a false completion signal
# with nothing able to catch it.
#
# Folding both halves in here makes the claim a CONSEQUENCE of the act: the
# announcement is printed to stdout only after the file is confirmed absent, so
# a run that did not delete cannot produce the line to relay. That is the same
# shape as plan-check/render/default-plan — the steps that never had this bug,
# because the model consumes their output instead of re-deriving it.

_DELETED_TEMPLATE = (
    "PLAN DELETED — {path} removed; cleanup is done and the code is validated "
    "and ready. We're in the same session, so raise any additional concerns "
    "and we'll continue right here."
)

_DELETE_FAILED_TEMPLATE = (
    "WARN: could not delete the plan file at {path} — remove it manually."
)


def cmd_close_out(args: argparse.Namespace) -> int:
    raw = args.plan
    if not raw:
        _err("no plan file given")
        return 2

    path = Path(raw).expanduser().resolve()

    # Deletion guards. This is the one destructive operation in the skill, so
    # it refuses anything that is not shaped like a plan file rather than
    # trusting an upstream variable to be set correctly.
    if path.is_dir():
        _err(f"refusing to delete a directory: {path}")
        return 2
    if not path.name.endswith(".md"):
        _err(f"refusing to delete a non-.md file: {path}")
        return 2

    if path.exists():
        try:
            path.unlink()
        except OSError as exc:
            _err(f"{_DELETE_FAILED_TEMPLATE.format(path=path)} ({exc})")
            return 1
        # Confirm rather than assume — a successful unlink() on a path that is
        # still there (odd filesystems, races) must not print the success line.
        if path.exists():
            _err(_DELETE_FAILED_TEMPLATE.format(path=path))
            return 1
    else:
        # Idempotent: the end state the contract promises already holds, so
        # this is success — but say on stderr that we did not do the removing.
        _err(f"note: plan file was already absent at {path}")

    print(_DELETED_TEMPLATE.format(path=path))
    return 0


# ---------------------------------------------------------------------------
# `sweep-scan` — mechanical proof for the Phase 5 production sweep
# ---------------------------------------------------------------------------
#
# The sweep used to be prose the model had to remember at the end of a long
# audit. This turns its checkable half into a tool result: feed it the
# change's ADDED lines (a unified diff) and its NEW files, and it reports the
# debris a production PR must not carry. Two tiers:
#   BLOCK   — never ships: debugger hooks, conflict markers, AI attributions,
#             focused tests, credential-shaped literals, scratch files,
#             TODO-class notes, generated test scaffolding the plan does not
#             name under "## Test deliverables".
#   REVIEW  — legitimate only with a reason: print-style output (may be the
#             product's CLI surface), lint/type suppressions, comment-only
#             lines (the zero-comment policy), skipped tests, secret-named
#             string assignments.
# It reads only what it is handed — it never runs git and never edits a file.
# Exit 0 = no BLOCK findings, 1 = BLOCK findings, 2 = usage error.

_CODE_SUFFIXES = frozenset("""
.py .pyi .rb .sh .bash .zsh .js .jsx .mjs .cjs .ts .tsx .go .rs .java .kt .kts
.swift .c .h .cc .cpp .hpp .cs .php .scala .lua .sql .dart .vue .svelte .ex .exs
""".split())
_HASH_COMMENT_SUFFIXES = frozenset(
    ".py .pyi .rb .sh .bash .zsh .ex .exs".split())
_SCRATCH_NAME = re.compile(r"(\.(orig|rej|bak|tmp|swp|log)|~|\.DS_Store)$")
_SCAFFOLD_PATH = re.compile(
    r"(^|/)(__tests__|__mocks__|__snapshots__|__fixtures__|fixtures|mocks|stubs|"
    r"testdata)/|(^|/)(test_[^/]+|conftest)\.py$|_test\.[A-Za-z]+$|"
    r"\.(test|spec|stories)\.[A-Za-z]+$|(^|/)[^/]*Tests?\.(java|kt|swift|cs)$")
_FUNCTIONAL_COMMENT = re.compile(
    r"^\s*(#!|#\s*(type:|noqa|pragma|pylint:|mypy:|ruff:|shellcheck|-\*-|frozen_string_literal)|"
    r"//\s*(eslint-|@ts-|go:|nolint|prettier-|istanbul|biome-|swiftlint:|"
    r"SPDX-|Copyright|\+build)|///|/\*\*?\s*(@|eslint|istanbul|Copyright|SPDX)|"
    r"#\s*(SPDX-|Copyright)|.*gstack-shortcut\(dec-)", re.IGNORECASE)

_BLOCK_RULES = (
    ("debug", re.compile(
        r"\bconsole\.(log|debug|trace|dir)\s*\(|\bdebugger\b\s*;?\s*$|"
        r"\bpdb\.set_trace\s*\(|\bbreakpoint\s*\(\s*\)|\bdbg!\s*\(|"
        r"\bbinding\.(pry|irb)\b|\bbyebug\b|\bvar_dump\s*\(|\bdd\s*\(\s*\$")),
    ("conflict-marker", re.compile(r"^(<{7}|>{7}) \S")),
    ("ai-note", re.compile(
        r"Generated (with|by) \[?(Claude|ChatGPT|Copilot|Cursor|Gemini|AI)\b|"
        r"Co-Authored-By:\s*(Claude|Copilot|ChatGPT)|\bAs an AI\b|"
        r"\bAI-generated\b|🤖", re.IGNORECASE)),
    ("note", re.compile(r"\b(TODO|FIXME|HACK|XXX)\b(?=\s*[:(\-]|\s|$)")),
    ("focused-test", re.compile(
        r"\b(describe|it|test|context)\.only\s*\(|\b(fdescribe|fit|fcontext)\s*\(")),
    ("secret", re.compile(
        r"AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|"
        r"\bgh[pousr]_[A-Za-z0-9]{36,}|\bsk-[A-Za-z0-9_-]{24,}|"
        r"\bxox[baprs]-[A-Za-z0-9-]{10,}|\bAIza[0-9A-Za-z_-]{35}\b")),
)
_REVIEW_RULES = (
    ("output", re.compile(
        r"^\s*(print\s*\(|println!\s*\(|eprintln!\s*\(|fmt\.Print(ln|f)?\s*\(|"
        r"System\.(out|err)\.print|puts\s|p\s+\w|echo\s+['\"]?DEBUG)")),
    ("suppression", re.compile(
        r"eslint-disable|@ts-ignore|@ts-nocheck|@ts-expect-error|#\s*noqa|"
        r"#\s*type:\s*ignore|#\[allow\(|//\s*nolint|rubocop:disable|"
        r"@SuppressWarnings|pylint:\s*disable")),
    ("skipped-test", re.compile(
        r"\b(describe|it|test)\.skip\s*\(|\b(xit|xdescribe|xtest)\s*\(|"
        r"@pytest\.mark\.(skip|xfail)|@unittest\.skip|@Ignore\b|@Disabled\b|"
        r"t\.Skip\s*\(")),
    ("secret-name", re.compile(
        r"(?i)\b(pass(word|wd)?|secret|api[_-]?key|auth[_-]?token|access[_-]?token|"
        r"private[_-]?key)\b\s*[:=]\s*['\"][^'\"\s${}<>]{8,}['\"]")),
)
_SLASH_COMMENT = re.compile(r"^\s*(//|/\*|\*/|\*\s)")
_HASH_COMMENT = re.compile(r"^\s*#")
_DASH_COMMENT = re.compile(r"^\s*--\s")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def _comment_only(path: str, line: str) -> bool:
    suffix = Path(path).suffix.lower()
    if suffix not in _CODE_SUFFIXES or _FUNCTIONAL_COMMENT.search(line):
        return False
    if suffix in _HASH_COMMENT_SUFFIXES:
        return bool(_HASH_COMMENT.match(line))
    if suffix == ".sql" or suffix == ".lua":
        return bool(_DASH_COMMENT.match(line))
    return bool(_SLASH_COMMENT.match(line))


def _scan_line(path: str, line: str) -> list:
    """[(tier, category)] for one added line."""
    found = [("BLOCK", cat) for cat, rx in _BLOCK_RULES if rx.search(line)]
    found += [("REVIEW", cat) for cat, rx in _REVIEW_RULES if rx.search(line)]
    if _comment_only(path, line) and not any(c == "note" for _, c in found):
        found.append(("REVIEW", "comment"))
    return found


def _added_lines(diff_text: str):
    """Yield (path, line_no, text) for every added line of a unified diff."""
    path, line_no = None, 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            target = raw[4:].split("\t")[0].strip()
            path = None if target == "/dev/null" else re.sub(r"^[ab]/", "", target)
            continue
        if raw.startswith("--- "):
            continue
        m = _HUNK.match(raw)
        if m:
            line_no = int(m.group(1))
            continue
        if path is None:
            continue
        if raw.startswith("+"):
            yield path, line_no, raw[1:]
            line_no += 1
        elif raw.startswith(" "):
            line_no += 1


def _test_deliverables(plan_path) -> set:
    """Paths the plan names under `## Test deliverables` (backticked or bare)."""
    if not plan_path:
        return set()
    try:
        text = _read_text(Path(plan_path).expanduser())
    except (OSError, UnicodeDecodeError):
        return set()
    m = re.search(r"^## Test deliverables\s*\n(.*?)(?=^## |\Z)", text,
                  re.MULTILINE | re.DOTALL)
    if not m:
        return set()
    return {tok.strip("`*,.;:()[]\"'").lstrip("./")
            for tok in re.findall(r"[`\w./\-\[\]()@+]+", m.group(1))
            if "/" in tok or "." in tok}


def _read_arg(value) -> str:
    if value == "-":
        return sys.stdin.read()
    return Path(value).expanduser().read_text(encoding="utf-8", errors="replace")


def cmd_sweep_scan(args: argparse.Namespace) -> int:
    if not args.diff and not args.files_from:
        _err("sweep-scan needs --diff and/or --files-from")
        return 2
    if args.diff == "-" and args.files_from == "-":
        _err("only one of --diff / --files-from may read stdin")
        return 2

    findings = []            # (tier, category, path, line_no, text)
    files_seen = set()
    try:
        if args.diff:
            for path, line_no, text in _added_lines(_read_arg(args.diff)):
                files_seen.add(path)
                for tier, cat in _scan_line(path, text):
                    findings.append((tier, cat, path, line_no, text))
        new_files = []
        if args.files_from:
            new_files = [ln.strip() for ln in _read_arg(args.files_from).splitlines()
                         if ln.strip()]
    except OSError as exc:
        _err(f"sweep-scan: cannot read input: {exc}")
        return 2

    keep = _test_deliverables(args.plan)
    for rel in new_files:
        files_seen.add(rel)
        norm = rel.lstrip("./")
        if _SCRATCH_NAME.search(norm):
            findings.append(("BLOCK", "scratch-file", rel, 0, "scratch or backup artifact"))
            continue
        if _SCAFFOLD_PATH.search(norm) and norm not in keep:
            findings.append(("BLOCK", "scaffolding", rel, 0,
                             "generated test/mock/fixture not named under "
                             "'## Test deliverables' — delete it (Phase 5a)"))
        fpath = Path(rel)
        try:
            if not fpath.is_file() or fpath.stat().st_size > 2_000_000:
                continue
            content = fpath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, text in enumerate(content.splitlines(), 1):
            for tier, cat in _scan_line(rel, text):
                findings.append((tier, cat, rel, i, text))

    blocking = sum(1 for f in findings if f[0] == "BLOCK")
    for tier, cat, path, line_no, text in sorted(findings, key=lambda f: (f[0], f[2], f[3])):
        where = f"{path}:{line_no}" if line_no else path
        shown = "[redacted]" if cat in ("secret", "secret-name") else text.strip()[:140]
        print(f"{tier} {cat} {where}: {shown}")
    print(f"sweep-scan: {blocking} blocking, {len(findings) - blocking} to review, "
          f"{len(files_seen)} file(s) scanned")
    return 1 if blocking else 0


# ---------------------------------------------------------------------------
# `signal` — machine-readable pipeline stage marker
# ---------------------------------------------------------------------------
#
# The plan → execute → validate lifecycle is driven by external automation
# that cannot parse chat output. Each skill therefore ends every run by
# writing one JSON signal file to <repo-root>/.plan/.signals/ — git-ignored
# with the rest of .plan/, invisible to `default-plan` discovery (it counts
# only *.md files, and .signals is a directory), and written ATOMICALLY
# (tmp + os.replace) so a watcher never reads a half-written file. The signal
# is emitted by this subcommand, never composed by the model — same shape as
# close-out: the claim is a consequence of the act.
#
# The validate signal is the pipeline's TERMINAL marker: it is written before
# the LAW 6 close-out and survives the plan file's deletion, so automation
# reads a definitive success/failed verdict instead of inferring one from a
# missing plan file.
#
# File:   .plan/.signals/<plan-stem>.<stage>.json   (stem "pipeline" when no
#         plan path is known — e.g. a run that stopped before resolving one)
# Status: "success" | "failed" — success may ONLY be passed when Step 4 ended
#         with the VALIDATION COMPLETE report (SKILL.md enforces this).

SIGNAL_SCHEMA = 1
SIGNAL_DIRNAME = ".signals"
SIGNAL_SKILL = "code-validation"
SIGNAL_STAGE = "validate"
UPSTREAM_STAGE = "execute"


def cmd_signal(args: argparse.Namespace) -> int:
    root = _find_repo_root(Path.cwd())
    signal_dir = root / DEFAULT_PLAN_DIRNAME / SIGNAL_DIRNAME

    plan_abs = ""
    stem = "pipeline"
    if args.plan:
        p = Path(args.plan).expanduser()
        plan_abs = str(p.resolve())
        stem = p.stem or "pipeline"

    payload = {
        "schema": SIGNAL_SCHEMA,
        "skill": SIGNAL_SKILL,
        "stage": SIGNAL_STAGE,
        "status": args.status,
        "plan": plan_abs,
        "detail": args.detail or "",
        "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    target = signal_dir / f"{stem}.{SIGNAL_STAGE}.json"
    tmp = signal_dir / f"{stem}.{SIGNAL_STAGE}.json.tmp"
    try:
        signal_dir.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, target)
    except OSError as exc:
        _err(f"WARN: could not write pipeline signal {target} ({exc}) — "
             "automation watching for it will not see this run.")
        return 1

    print(str(target))
    return 0


# ---------------------------------------------------------------------------
# argparse wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="code_validation.py",
        description="Helper for the /code-validation skill (stdlib only).",
    )
    p.add_argument("--skill-dir", default=None,
                   help="skill directory (default: parent of this script)")

    sub = p.add_subparsers(dest="command", required=True)

    # plan-check
    sp = sub.add_parser("plan-check", help="validate a plan file is executable")
    sp.add_argument("--plan", required=True, help="path to the plan .md file")
    sp.set_defaults(func=cmd_plan_check)

    # render
    sp = sub.add_parser("render", help="substitute {{PATH}} in the validate-code template")
    sp.add_argument("--template", default=None,
                    help="path to validate-code.md (default: {skill_dir}/prompts/validate-code.md)")
    sp.add_argument("--plan", required=True, help="absolute path to the plan .md file")
    sp.set_defaults(func=cmd_render)

    # default-plan
    sp = sub.add_parser("default-plan",
                        help="auto-discover the single plan in <repo-root>/.plan")
    sp.set_defaults(func=cmd_default_plan)

    # repo-root
    sp = sub.add_parser("repo-root",
                        help="print the repo root that contains the plan "
                             "(filesystem walk, no git)")
    sp.add_argument("--plan", required=True, help="path to the plan .md file")
    sp.set_defaults(func=cmd_repo_root)

    # close-out
    sp = sub.add_parser("close-out",
                        help="delete the plan file and print the LAW 6 announcement")
    sp.add_argument("--plan", required=True,
                    help="absolute path to the plan .md file (the PLAN_ABS from plan-check)")
    sp.set_defaults(func=cmd_close_out)

    # sweep-scan
    sp = sub.add_parser("sweep-scan",
                        help="scan the change's added lines and new files for "
                             "production debris (exit 1 on blocking findings)")
    sp.add_argument("--diff", default=None,
                    help="unified diff of the change (file path, or - for stdin)")
    sp.add_argument("--files-from", default=None,
                    help="newline-separated list of NEW files to scan in full "
                         "(file path, or - for stdin)")
    sp.add_argument("--plan", default=None,
                    help="the plan .md — its '## Test deliverables' paths are "
                         "exempt from the scaffolding rule")
    sp.set_defaults(func=cmd_sweep_scan)

    # signal
    sp = sub.add_parser("signal",
                        help="write the pipeline stage signal to "
                             "<repo-root>/.plan/.signals/")
    sp.add_argument("--status", required=True, choices=("success", "failed"),
                    help="stage outcome; success ONLY after the "
                         "VALIDATION COMPLETE report")
    sp.add_argument("--plan", default=None,
                    help="path to the validated plan .md (omit if the run "
                         "stopped before a path was resolved)")
    sp.add_argument("--detail", default=None,
                    help="one-line human-readable outcome summary")
    sp.set_defaults(func=cmd_signal)

    return p


def _apply_skill_dir_defaults(args: argparse.Namespace) -> None:
    """Fill in --template default from the resolved skill dir."""
    if args.skill_dir:
        skill_dir = Path(args.skill_dir).resolve()
    else:
        skill_dir = Path(__file__).resolve().parent.parent
    if args.command == "render" and not args.template:
        args.template = str(skill_dir / "prompts" / "validate-code.md")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_skill_dir_defaults(args)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
