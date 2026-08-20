#!/usr/bin/env python3
"""
selftest.py — offline unit tests for code_execute.py.

Stdlib only. No network, no LM Studio. Run:

    python3 skills/code-execute/scripts/selftest.py -v

Covers:
  render: substitutes {{PATH}} with the absolute path; exit 3 on an unknown
          {{FOO}} token in a custom --template; exit 1 on a missing/unreadable
          --template; exit 1 (no traceback) on a non-UTF-8 --template.
  plan-check: passes on a real stepped .md and prints an absolute path;
          exits 2 on a missing file, an empty file, a non-.md file, a .md
          with no "### " headings, an empty flag value, a directory, and a
          binary *.md (no traceback); the .md suffix gate runs before the read.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make the script under test importable regardless of cwd.
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import code_execute  # noqa: E402  (after sys.path insert above)


# ---------------------------------------------------------------------------
# stdout/stderr capture helper
# ---------------------------------------------------------------------------

class _Captured:
    def __init__(self):
        self.code: int | None = None
        self.stdout = ""
        self.stderr = ""


class io_StringIO:
    """Minimal StringIO stand-in so we don't need the io module's full API."""
    def __init__(self):
        self._parts = []
    def write(self, s):
        self._parts.append(s)
    def flush(self):
        pass
    def getvalue(self):
        return "".join(self._parts)


def io_capture(fn, argv):
    """Run code_execute.main(argv) with stdout/stderr captured. main() returns
    the int exit code; we also intercept sys.stdout/sys.stderr writes."""
    cap = _Captured()
    out_buf = io_StringIO()
    err_buf = io_StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = out_buf
    sys.stderr = err_buf
    try:
        cap.code = int(fn(argv))
    except SystemExit as exc:
        cap.code = int(exc.code) if isinstance(exc.code, int) else 1
    finally:
        sys.stdout = old_out
        sys.stderr = old_err
    cap.stdout = out_buf.getvalue()
    cap.stderr = err_buf.getvalue()
    return cap


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class RenderTests(unittest.TestCase):

    def test_render_substitutes_path_with_absolute(self):
        template = "The plan to execute is at: {{PATH}}\n"
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_text(template, encoding="utf-8")
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_execute.main, [
                "render", "--template", str(tpath), "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertNotIn("{{", out.stdout)
            # PATH resolves to the absolute path of the plan file.
            self.assertIn(str(ppath.resolve()), out.stdout)

    def test_render_rejects_unsubstituted_token(self):
        """A custom template carrying an unknown {{FOO}} token must exit 3."""
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_text("A {{FOO}} B {{PATH}}\n", encoding="utf-8")
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_execute.main, [
                "render", "--template", str(tpath), "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 3, out.stderr)
            self.assertIn("FOO", out.stderr)

    def test_render_exits_1_on_missing_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_execute.main, [
                "render", "--template", str(Path(tmp) / "nope.md"),
                "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 1, out.stderr)
            self.assertIn("cannot read template", out.stderr)

    def test_render_exits_1_on_binary_template(self):
        """A non-UTF-8 template must exit 1 cleanly, never raise
        UnicodeDecodeError as a traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_bytes(b"\xff\xfe\x00binary\x00{{PATH}}\n")
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_execute.main, [
                "render", "--template", str(tpath), "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 1, out.stderr)
            self.assertIn("cannot read template", out.stderr)
            self.assertEqual(out.stdout, "")


class PlanCheckTests(unittest.TestCase):

    def _write(self, tmp, name, body):
        p = Path(tmp) / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_plan_check_passes_on_stepped_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "good.md", "# Title\n\n### Step 1\n\ndo thing\n")
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 0, out.stderr)
            # Prints the absolute path.
            printed = out.stdout.strip()
            self.assertTrue(printed.endswith("good.md"))
            self.assertTrue(os.path.isabs(printed), f"not absolute: {printed}")

    def test_plan_check_exits_2_on_missing_file(self):
        out = io_capture(code_execute.main, [
            "plan-check", "--plan", "/nonexistent/code-execute-selftest.md",
        ])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("does not exist", out.stderr)

    def test_plan_check_exits_2_on_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "empty.md", "")
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("empty", out.stderr)

    def test_plan_check_exits_2_on_non_md_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "plan.txt", "### Step 1\n\ndo thing\n")
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn(".md", out.stderr)

    def test_plan_check_exits_2_on_md_without_step_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "readme.md", "# A README\n\nSome prose only.\n")
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("### ", out.stderr)

    def test_plan_check_exits_2_on_empty_flag_value(self):
        """`-p ""` counts as not provided (SKILL.md Step 1) — clean exit 2,
        not an argparse traceback."""
        out = io_capture(code_execute.main, ["plan-check", "--plan", ""])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("no plan file given", out.stderr)

    def test_plan_check_exits_2_on_directory(self):
        """A directory is not a plan file — is_file() gate, no traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            out = io_capture(code_execute.main, ["plan-check", "--plan", tmp])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertEqual(out.stdout, "")

    def test_plan_check_exits_2_on_binary_md(self):
        """A binary file named *.md must exit 2 cleanly. Before the fix this
        raised UnicodeDecodeError and dumped a traceback at exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "binary.md"
            p.write_bytes(b"### Step 1\n\xd8\xff\x00\x80not utf8\n")
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("not UTF-8", out.stderr)
            self.assertEqual(out.stdout, "")

    def test_plan_check_suffix_gate_precedes_read(self):
        """A non-.md binary is rejected on the cheap suffix gate — we never
        slurp it. Guards the check-ordering fix."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "blob.bin"
            p.write_bytes(b"\x00\xff" * 32)
            out = io_capture(code_execute.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn(".md", out.stderr)
            self.assertNotIn("UTF-8", out.stderr)


class DefaultPlanTests(unittest.TestCase):
    """STRICT auto-discovery for an omitted -p: exactly one *.md in
    <repo-root>/.plan resolves; missing/empty/ambiguous all exit 2 with a
    message telling the user to pass -p. The rules are deliberately rigid —
    a regression that makes this guess would execute the wrong plan."""

    def _in_tmp(self, build, cwd_rel="."):
        """Create a temp tree via build(root), chdir to root/cwd_rel, run
        default-plan, restore cwd. Returns the captured result."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            prev = os.getcwd()
            os.chdir(root / cwd_rel)
            try:
                return io_capture(code_execute.main, ["default-plan"]), root
            finally:
                os.chdir(prev)

    def test_missing_plan_folder_exits_2(self):
        out, _ = self._in_tmp(lambda root: (root / ".git").mkdir())
        self.assertEqual(out.code, 2)
        self.assertIn("no .plan/ folder", out.stderr)
        self.assertIn("-p", out.stderr)

    def test_empty_plan_folder_exits_2(self):
        def build(root):
            (root / ".git").mkdir()
            (root / ".plan").mkdir()
            (root / ".plan" / "notes.txt").write_text("x", encoding="utf-8")
        out, _ = self._in_tmp(build)
        self.assertEqual(out.code, 2)
        self.assertIn("no plan files", out.stderr)

    def test_two_plans_exits_2_and_lists_candidates(self):
        def build(root):
            (root / ".git").mkdir()
            d = root / ".plan"
            d.mkdir()
            (d / "a-plan.md").write_text("### Step\n", encoding="utf-8")
            (d / "b-plan.md").write_text("### Step\n", encoding="utf-8")
        out, _ = self._in_tmp(build)
        self.assertEqual(out.code, 2)
        self.assertIn("2 plans", out.stderr)
        self.assertIn("a-plan.md", out.stderr)
        self.assertIn("b-plan.md", out.stderr)

    def test_single_plan_resolves_from_repo_subdir(self):
        def build(root):
            (root / ".git").mkdir()
            d = root / ".plan"
            d.mkdir()
            (d / "only-plan.md").write_text("### Step\n", encoding="utf-8")
            (d / "sidecar.json").write_text("{}", encoding="utf-8")
            (root / "src").mkdir()
        out, root = self._in_tmp(build, cwd_rel="src")
        self.assertEqual(out.code, 0, out.stderr)
        got = Path(out.stdout.strip())
        self.assertEqual(got.name, "only-plan.md")
        # Resolved at the repo ROOT even though cwd was a subdir; non-.md
        # files in .plan never count toward the plan tally.
        self.assertEqual(got.parent, (root / ".plan").resolve())

    def test_no_git_uses_cwd_as_root(self):
        def build(root):
            d = root / ".plan"
            d.mkdir()
            (d / "solo-plan.md").write_text("### Step\n", encoding="utf-8")
        out, root = self._in_tmp(build)
        self.assertEqual(out.code, 0, out.stderr)
        self.assertEqual(Path(out.stdout.strip()).parent,
                         (root / ".plan").resolve())


class DocsContractTests(unittest.TestCase):
    """Pins the expert-awareness contract added in v1.3.0: the gstack expert
    roster ships with the skill, carries a verifiable gstack version pin
    (install.sh's doctor greps it for drift detection), SKILL.md actually
    routes to it, and the two version declarations stay in lockstep."""

    SKILL_DIR = SCRIPTS_DIR.parent

    def test_gstack_experts_file_exists_with_version_pin(self):
        experts = self.SKILL_DIR / "prompts" / "gstack-experts.md"
        self.assertTrue(experts.is_file(), "prompts/gstack-experts.md missing")
        text = experts.read_text(encoding="utf-8")
        import re
        # Same single-line shape install.sh's doctor greps for; the HIGHEST
        # version found is the effective pin (mirrors its `sort -V | tail`).
        versions = re.findall(r"gstack (\d+\.\d+(?:\.\d+)*)", text)
        self.assertTrue(versions, "no 'gstack X.Y.Z' pin in gstack-experts.md")
        pin = max(tuple(int(p) for p in v.split(".")) for v in versions)
        # The pin must be 1.68+ (the roster facts — /review dispatch rules,
        # guardrail fail-closed, evidence binding — were verified there).
        self.assertGreaterEqual(pin[:2], (1, 68))

    def test_skill_md_references_the_experts_file(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("gstack-experts.md", text)

    def test_experts_file_names_the_review_specialists(self):
        """The /review mechanics section must keep the full specialist set —
        the force-flag advice in SKILL.md Step 6 depends on it."""
        text = (self.SKILL_DIR / "prompts" / "gstack-experts.md").read_text(
            encoding="utf-8")
        for specialist in ("testing", "maintainability", "security",
                           "performance", "data-migration", "api-contract",
                           "red-team", "--all-specialists"):
            self.assertIn(specialist, text, f"missing specialist: {specialist}")

    def test_versions_in_lockstep(self):
        import json
        import re
        skill_text = (self.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', skill_text, re.MULTILINE)
        assert m is not None, "no version in SKILL.md frontmatter"
        plugin = json.loads(
            (self.SKILL_DIR / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(m.group(1), plugin["version"],
                         "SKILL.md and plugin.json versions drifted")

    def test_real_template_renders_cleanly(self):
        """The shipped execute-plan.md must carry exactly the {{PATH}} token —
        render it for real and require a clean exit 0."""
        with tempfile.TemporaryDirectory() as tmp:
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_execute.main, [
                "render", "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertIn(str(ppath.resolve()), out.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
