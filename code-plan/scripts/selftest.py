#!/usr/bin/env python3
"""
selftest.py — offline unit tests for code_plan.py.

Stdlib only. No network — the enhancement runs natively in the model that
executes the skill, so the only scripted surface is deterministic text
composition. Run:

    python3 skills/code-plan/scripts/selftest.py -v
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

# Make the script under test importable regardless of cwd.
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import code_plan  # noqa: E402  (after sys.path insert above)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class RenderTests(unittest.TestCase):

    def _run_render(self, template_text, instructions, tag=None, path="p",
                    plan_filename="f.md", lenses=None, lenses_file=None):
        # tag=None omits --tag entirely, exercising the ui-data default.
        # lenses="text" writes a lenses file; lenses_file overrides with a
        # raw path (for the missing-file case).
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_text(template_text, encoding="utf-8")
            ipath = Path(tmp) / "i.txt"
            ipath.write_text(instructions, encoding="utf-8")
            argv = [
                "render", "--template", str(tpath),
                "--path", path,
                "--plan-filename", plan_filename,
                "--instructions-file", str(ipath),
            ]
            if tag is not None:
                argv[3:3] = ["--tag", tag]
            if lenses is not None:
                lpath = Path(tmp) / "lenses.md"
                lpath.write_text(lenses, encoding="utf-8")
                argv += ["--lenses-file", str(lpath)]
            elif lenses_file is not None:
                argv += ["--lenses-file", lenses_file]
            out = io_capture(code_plan.main, argv)
            return out

    def test_render_substitutes_all(self):
        template = "TAG={{PROJECT_TAG}} PATH={{PATH}} FILE={{PLAN_FILENAME}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do the thing", tag="ui",
                               path="/x/y", plan_filename="z.md")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertNotIn("{{", out.stdout)
        self.assertIn("TAG=ui", out.stdout)
        self.assertIn("PATH=/x/y", out.stdout)
        self.assertIn("FILE=z.md", out.stdout)
        self.assertIn("do the thing", out.stdout)

    def test_render_default_tag_is_ui_data(self):
        """Omitting --tag must render ui-data, never an empty string.
        The skill no longer prompts for the tag; ui-data is the fixed
        default at both the SKILL.md layer and here in the script."""
        template = "TAG={{PROJECT_TAG}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do the thing", tag=None)
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("TAG=ui-data", out.stdout)

    def test_render_instructions_last(self):
        """Instructions containing the literal {{PATH}} must survive verbatim:
        never re-substituted into the real path value (instructions go in
        LAST) and never flagged by the leftover guard (the guard runs BEFORE
        instructions are inserted, so it only ever sees template tokens).
        Regression: ISSUE-002 — user prose containing {{TOKEN}}-shaped text
        used to hard-fail render with exit 3. Found by /qa on 2026-07-25."""
        template = "OUT={{PATH}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "see {{PATH}} here", tag="ui",
                               path="/REAL/PATH", plan_filename="f.md")
        self.assertEqual(out.code, 0, out.stderr)
        # Template token got the real value.
        self.assertIn("OUT=/REAL/PATH", out.stdout)
        # User prose kept its literal token — not substituted, not flagged.
        self.assertIn("see {{PATH}} here", out.stdout)

    def test_render_rejects_unsubstituted(self):
        template = "A {{FOO}} B {{PROJECT_TAG}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do thing", tag="ui", path="p",
                               plan_filename="f.md")
        self.assertEqual(out.code, 3, out.stderr)
        self.assertIn("FOO", out.stderr)

    def test_render_lenses_file_substituted(self):
        template = "LENS={{EXPERT_LENSES}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do thing",
                               lenses="## eng lens\n- test everything")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("## eng lens", out.stdout)
        self.assertNotIn("{{EXPERT_LENSES}}", out.stdout)

    def test_render_lenses_default_when_omitted(self):
        """{{EXPERT_LENSES}} without --lenses-file must render the generalist
        default, never trip the leftover guard, and never leak the token."""
        template = "LENS={{EXPERT_LENSES}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do thing")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("generalist", out.stdout)
        self.assertNotIn("{{EXPERT_LENSES}}", out.stdout)

    def test_render_lenses_missing_file_exits_1(self):
        template = "LENS={{EXPERT_LENSES}}\n{{INSTRUCTIONS}}\n"
        out = self._run_render(template, "do thing",
                               lenses_file="/nonexistent/lenses.md")
        self.assertEqual(out.code, 1, out.stderr)

    def test_render_requires_instructions_file(self):
        """render without --instructions-file must be an argparse error
        (exit 2), not a TypeError traceback."""
        out = io_capture(code_plan.main, [
            "render", "--tag", "ui", "--path", "p", "--plan-filename", "f.md",
        ])
        self.assertEqual(out.code, 2, out.stderr)


class EnhancePromptTests(unittest.TestCase):
    """Tests for `enhance-prompt` — the deterministic composition of the
    native rewrite prompt. There is no LLM call anywhere: the composed
    prompt is executed by the model already running the skill."""

    TEMPLATE = (
        "---\nid: enhance_instructions\nplaceholders:\n"
        "  - RAW_INSTRUCTIONS\n---\n\n"
        "<rules>rewrite only</rules>\n"
        "<raw_instructions>\n{{RAW_INSTRUCTIONS}}\n</raw_instructions>\n"
    )

    def _run(self, raw_text, template_text=None, instructions_file=True):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "enhance.md"
            tpath.write_text(template_text if template_text is not None
                             else self.TEMPLATE, encoding="utf-8")
            argv = ["enhance-prompt", "--prompt", str(tpath)]
            if instructions_file:
                ipath = Path(tmp) / "raw.txt"
                ipath.write_text(raw_text, encoding="utf-8")
                argv += ["--instructions-file", str(ipath)]
            return io_capture(code_plan.main, argv)

    def test_happy_path_substitutes_prose(self):
        out = self._run("MARKER_PROSE_XYZ\n")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("MARKER_PROSE_XYZ", out.stdout)
        self.assertNotIn("{{RAW_INSTRUCTIONS}}", out.stdout)

    def test_frontmatter_is_stripped(self):
        """The YAML frontmatter is metadata — it must never reach the
        composed prompt, and the prose lands exactly once (inside
        <raw_instructions>), never in a frontmatter placeholder listing."""
        out = self._run("MARKER_PROSE_XYZ\n")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertNotIn("id: enhance_instructions", out.stdout)
        self.assertNotIn("placeholders:", out.stdout)
        self.assertEqual(out.stdout.count("MARKER_PROSE_XYZ"), 1)

    def test_prose_with_literal_placeholder_not_resubstituted(self):
        """User prose containing a literal {{RAW_INSTRUCTIONS}} survives as
        text — a single replace pass never re-substitutes inserted prose."""
        out = self._run("see {{RAW_INSTRUCTIONS}} here\n")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("see {{RAW_INSTRUCTIONS}} here", out.stdout)

    def test_unreadable_instructions_file_exits_2(self):
        out = io_capture(code_plan.main, [
            "enhance-prompt",
            "--instructions-file", "/nonexistent/code-plan-selftest.txt",
        ])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertIn("WARN:", out.stderr)

    def test_empty_instructions_exit_2(self):
        out = self._run("   \n")
        self.assertEqual(out.code, 2, out.stderr)
        self.assertEqual(out.stdout, "")
        self.assertIn("WARN:", out.stderr)

    def test_unreadable_template_exits_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "raw.txt"
            ipath.write_text("some prose\n", encoding="utf-8")
            out = io_capture(code_plan.main, [
                "enhance-prompt", "--prompt", "/nonexistent/enhance.md",
                "--instructions-file", str(ipath),
            ])
        self.assertEqual(out.code, 1, out.stderr)
        self.assertIn("WARN:", out.stderr)

    def test_template_without_placeholder_exits_1(self):
        """A template missing {{RAW_INSTRUCTIONS}} would silently drop the
        user's prose — hard error instead."""
        out = self._run("some prose\n",
                        template_text="<rules>no placeholder here</rules>\n")
        self.assertEqual(out.code, 1, out.stderr)
        self.assertIn("RAW_INSTRUCTIONS", out.stderr)

    def test_real_template_composes_clean(self):
        """The shipped prompts/enhance-instructions.md composes without
        frontmatter leakage and with the placeholder substituted."""
        real = (Path(code_plan.__file__).resolve().parent.parent
                / "prompts" / "enhance-instructions.md")
        out = self._run("MARKER_PROSE_XYZ\n",
                        template_text=real.read_text(encoding="utf-8"))
        self.assertEqual(out.code, 0, out.stderr)
        self.assertNotIn("{{RAW_INSTRUCTIONS}}", out.stdout)
        self.assertNotIn("placeholders:", out.stdout)
        self.assertEqual(out.stdout.count("MARKER_PROSE_XYZ"), 1)


class PlanPathTests(unittest.TestCase):

    def test_plan_path_slug_and_collision(self):
        with tempfile.TemporaryDirectory() as tmp:
            # First call derives the slug.
            out1 = io_capture(code_plan.main, [
                "plan-path", "--path", tmp,
                "--objective", "Add a CSV export button to the reports page",
            ])
            self.assertEqual(out1.code, 0, out1.stderr)
            p1 = out1.stdout.strip()
            self.assertTrue(p1.endswith("-plan.md"))
            self.assertIn("add-a-csv-export-button", p1)
            # Create it so the next call must dodge.
            Path(p1).touch()
            # Second call collides -> -2 suffix.
            out2 = io_capture(code_plan.main, [
                "plan-path", "--path", tmp,
                "--objective", "Add a CSV export button to the reports page",
            ])
            self.assertEqual(out2.code, 0, out2.stderr)
            p2 = out2.stdout.strip()
            # Suffix inserts before .md and keeps the -plan marker.
            self.assertTrue(p2.endswith("-plan-2.md"), p2)
            self.assertNotEqual(p1, p2)


@contextmanager
def _chdir(path):
    prev = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


class PlanPathDefaultTests(unittest.TestCase):
    """No --path → <repo-root>/.plan, auto-created and git-ignored."""

    ARGV = ["plan-path", "--objective", "Add a CSV export button"]

    def test_default_no_git_uses_cwd_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            with _chdir(tmp):
                out = io_capture(code_plan.main, self.ARGV)
            self.assertEqual(out.code, 0, out.stderr)
            expected_dir = (Path(tmp) / ".plan").resolve()
            self.assertEqual(Path(out.stdout.strip()).parent, expected_dir)
            self.assertTrue(expected_dir.is_dir())
            # No .git → no .gitignore is invented.
            self.assertFalse((Path(tmp) / ".gitignore").exists())
            self.assertIn("NOTE: created", out.stderr)

    def test_default_walks_up_to_git_root_and_creates_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            sub = root / "src" / "deep"
            sub.mkdir(parents=True)
            with _chdir(sub):
                out = io_capture(code_plan.main, self.ARGV)
            self.assertEqual(out.code, 0, out.stderr)
            # .plan lands at the repo ROOT, not the cwd.
            self.assertEqual(Path(out.stdout.strip()).parent,
                             (root / ".plan").resolve())
            gi = root / ".gitignore"
            self.assertTrue(gi.exists())
            self.assertIn(".plan/", gi.read_text(encoding="utf-8"))

    def test_default_appends_to_existing_gitignore_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            gi = root / ".gitignore"
            gi.write_text("node_modules/\n", encoding="utf-8")
            with _chdir(root):
                out1 = io_capture(code_plan.main, self.ARGV)
                out2 = io_capture(code_plan.main, self.ARGV)
            self.assertEqual(out1.code, 0, out1.stderr)
            self.assertEqual(out2.code, 0, out2.stderr)
            text = gi.read_text(encoding="utf-8")
            self.assertIn("node_modules/", text)          # existing kept
            self.assertEqual(text.count(".plan/"), 1)     # appended ONCE
            self.assertIn("added '.plan/'", out1.stderr)
            self.assertNotIn("added", out2.stderr)        # second run silent

    def test_default_respects_preexisting_ignore_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            gi = root / ".gitignore"
            gi.write_text("/.plan/\n", encoding="utf-8")  # variant spelling
            with _chdir(root):
                out = io_capture(code_plan.main, self.ARGV)
            self.assertEqual(out.code, 0, out.stderr)
            self.assertEqual(gi.read_text(encoding="utf-8"), "/.plan/\n")

    def test_explicit_path_never_touches_gitignore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            dest = root / "plans"
            dest.mkdir()
            with _chdir(root):
                out = io_capture(code_plan.main, [
                    "plan-path", "--path", str(dest),
                    "--objective", "Add a CSV export button",
                ])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertFalse((root / ".gitignore").exists())
            self.assertFalse((root / ".plan").exists())


class RouteTests(unittest.TestCase):
    """Tests for the deterministic `route` subcommand (Step 8's floor)."""

    def _run_route(self, text, experts=None, json_out=True):
        """Run `route` with a temp instructions file. Returns _Captured."""
        with tempfile.TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "brief.txt"
            ipath.write_text(text, encoding="utf-8")
            argv = ["route", "--instructions-file", str(ipath)]
            if experts is not None:
                argv += ["--experts", experts]
            if json_out:
                argv += ["--json"]
            return io_capture(code_plan.main, argv)

    def _run_route_stdin(self, text, experts=None, json_out=True):
        """Run `route` reading from stdin (no --instructions-file)."""
        import io as _io
        argv = ["route"]
        if experts is not None:
            argv += ["--experts", experts]
        if json_out:
            argv += ["--json"]
        old_stdin = sys.stdin
        sys.stdin = _io.StringIO(text)
        try:
            return io_capture(code_plan.main, argv)
        finally:
            sys.stdin = old_stdin

    def test_ui_text_routes_to_design(self):
        out = self._run_route(
            "redesign the stock detail page cards and empty states")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("design", payload["lenses"])
        self.assertEqual(payload["recommended_skill"], "plan-design-review")

    def test_backend_api_routes_to_eng(self):
        out = self._run_route(
            "add a paginated /api/v1/quotes endpoint backed by a new sqlite schema")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["lenses"][0], "eng")
        self.assertEqual(payload["recommended_skill"], "plan-eng-review")

    def test_cli_skill_routes_to_devex(self):
        out = self._run_route(
            "add a new slash command and a CLI flag to the skill")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("devex", payload["lenses"])

    def test_auth_secrets_routes_to_security(self):
        out = self._run_route(
            "rotate the oauth token and add a password policy")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("security", payload["lenses"])

    def test_crash_timeout_routes_to_investigate(self):
        out = self._run_route(
            "the download step crashes with a timeout")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("investigate", payload["lenses"])

    def test_docs_text_routes_to_docs(self):
        out = self._run_route(
            "refresh the README and add a changelog entry")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("docs", payload["lenses"])
        self.assertEqual(payload["recommended_skill"], "docs-refresh")

    def test_swiftui_xcode_routes_to_ios(self):
        out = self._run_route(
            "update the SwiftUI settings view for Xcode 15")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("ios", payload["lenses"])

    def test_perf_text_routes_to_perf(self):
        out = self._run_route(
            "profile the slow dashboard query and optimize its latency")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("perf", payload["lenses"])

    def test_neutral_chore_yields_empty_lenses(self):
        out = self._run_route("rename a variable")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["lenses"], [])
        self.assertIsNone(payload["recommended_skill"])

    def test_routing_is_deterministic(self):
        text = "add a dark mode toggle to the settings page"
        out1 = self._run_route(text)
        out2 = self._run_route(text)
        self.assertEqual(out1.stdout, out2.stdout)

    def test_text_hitting_many_groups_caps_at_max_and_recommends_autoplan(self):
        # Hits design (page, css, ui), eng (api, schema, sql), security (auth),
        # qa (test), devex (cli), docs (readme) — well over MAX_LENSES groups.
        out = self._run_route(
            "redesign the settings page css and ui, add an api + sql schema, "
            "rotate the auth token, add a test suite, ship a cli flag, and "
            "update the readme docs")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(len(payload["lenses"]), code_plan.MAX_LENSES)
        self.assertEqual(payload["recommended_skill"], "autoplan")

    def test_experts_list_overrides_computed_set(self):
        out = self._run_route(
            "add a dark mode toggle to the settings page", experts="eng,design")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["lenses"], ["eng", "design"])

    def test_experts_none_yields_empty(self):
        out = self._run_route(
            "add a dark mode toggle to the settings page", experts="none")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["lenses"], [])

    def test_experts_unknown_exits_2_and_lists_valid_ids(self):
        out = self._run_route("whatever", experts="bogus")
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("unknown expert lens", out.stderr)
        # Every valid id appears in the error so the user knows the set.
        for lens in code_plan.SIGNALS:
            self.assertIn(lens, out.stderr)

    def test_word_boundary_no_false_positive_on_build_or_guide(self):
        """Text containing 'build' and 'guide' alone must NOT select design
        (no 'ui' false positive — word boundary, not substring)."""
        out = self._run_route("build the onboarding guide")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertNotIn("design", payload["lenses"])

    def test_human_output_format(self):
        """Non-JSON output prints two lines: lenses: a,b / skill: name
        (lenses: none / skill: none when empty)."""
        out = self._run_route(
            "add a dark mode toggle to the settings page", json_out=False)
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("lenses: design", out.stdout)
        self.assertIn("skill: plan-design-review", out.stdout)

    def test_unreadable_instructions_file_exits_2(self):
        out = io_capture(code_plan.main, [
            "route", "--instructions-file",
            "/nonexistent/code-plan-routetest.txt",
        ])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("instructions file", out.stderr)

    def test_stdin_input_works(self):
        out = self._run_route_stdin("add a dark mode toggle to the settings page")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertIn("design", payload["lenses"])


class RoutingTableConsistencyTests(unittest.TestCase):
    """Meta-test: the routing table, the distillate file, and the follow-up
    skill map stay in sync. Adding a lens without documenting it, or dropping a
    skill name, fails the suite offline instead of failing silently at the
    Step 13 hand-off.

    The distillate path is derived from the script location so the test works
    regardless of cwd (mirrors how SKILL_DIR resolves $SKILL_DIR).
    """

    @classmethod
    def setUpClass(cls):
        cls.distillate_path = (
            Path(code_plan.__file__).resolve().parent.parent
            / "prompts" / "expert-lenses.md"
        )
        cls.distillate = cls.distillate_path.read_text(encoding="utf-8")

    def test_signals_keys_have_distillate_headings(self):
        """Every SIGNALS lens id has a `## <lens> —` heading in the distillate
        file — so a lens added to the code without a distillate entry fails.
        Uses re.MULTILINE so `^` matches the start of any line, not just the
        start of the whole file (assertRegex's default search has no MULTILINE)."""
        for lens in code_plan.SIGNALS:
            with self.subTest(lens=lens):
                pattern = rf"^## {re.escape(lens)} —"
                self.assertTrue(
                    re.search(pattern, self.distillate, re.MULTILINE) is not None,
                    msg=f"lens '{lens}' in SIGNALS has no '## {lens} —' heading "
                        f"in {self.distillate_path}",
                )

    def test_three_collections_share_identical_keys(self):
        """SIGNALS, LENS_SKILL and LENS_PRIORITY must have identical key sets
        — the routing code sorts by LENS_PRIORITY.index(lens) and looks up
        LENS_SKILL[lens], so any drift is a latent crash or silent miss."""
        self.assertEqual(set(code_plan.SIGNALS), set(code_plan.LENS_SKILL))
        self.assertEqual(set(code_plan.SIGNALS), set(code_plan.LENS_PRIORITY))
        # And the order length matches (no duplicate ids in the priority list).
        self.assertEqual(
            len(code_plan.LENS_PRIORITY), len(set(code_plan.LENS_PRIORITY)),
            msg="LENS_PRIORITY contains duplicate lens ids",
        )

    def test_lens_skill_values_in_known_follow_up_skills_table(self):
        """Every LENS_SKILL value appears verbatim in the 'Known follow-up
        skills' table in the distillate, so a renamed gstack skill fails a
        test instead of failing silently at hand-off time. Scoped to the
        table section — skill names in lens headings do not count."""
        marker = "### Known follow-up skills"
        idx = self.distillate.find(marker)
        self.assertNotEqual(
            idx, -1,
            msg=f"'{marker}' section missing from {self.distillate_path}",
        )
        table = self.distillate[idx:]
        for lens, skill in code_plan.LENS_SKILL.items():
            with self.subTest(lens=lens, skill=skill):
                self.assertIn(
                    skill, table,
                    msg=f"LENS_SKILL[{lens}]={skill!r} not found in the "
                        f"'Known follow-up skills' table in "
                        f"{self.distillate_path}",
                )


# ---------------------------------------------------------------------------
# stdout/stderr capture helper
# ---------------------------------------------------------------------------

class _Captured:
    def __init__(self):
        self.code: int | None = None
        self.stdout = ""
        self.stderr = ""


def io_capture(fn, argv):
    """Run code_plan.main(argv) with stdout/stderr captured. main() returns
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
