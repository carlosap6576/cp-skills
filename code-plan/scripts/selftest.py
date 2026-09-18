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


class SignalTests(unittest.TestCase):
    """Pipeline stage signal (v1.13.0): one atomic JSON file per stage under
    <repo-root>/.plan/.signals/, so external automation can drive the
    plan → execute → validate pipeline without parsing chat."""

    STAGE = "plan"
    SKILL = "code-plan"

    def _run(self, argv, build=None, cwd_rel="."):
        """Run `signal` inside a temp repo; return (captured, {name: json})
        for every file left in .plan/.signals/."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            if build:
                build(root)
            prev = os.getcwd()
            os.chdir(root / cwd_rel)
            try:
                cap = io_capture(code_plan.main, argv)
            finally:
                os.chdir(prev)
            files = {}
            sig_dir = root / ".plan" / ".signals"
            if sig_dir.is_dir():
                for f in sorted(sig_dir.iterdir()):
                    if f.name.endswith(".json"):
                        files[f.name] = json.loads(f.read_text(encoding="utf-8"))
                    else:
                        files[f.name] = None  # a leftover .tmp is a bug
            return cap, files

    def test_success_signal_has_the_full_schema(self):
        def build(root):
            d = root / ".plan"
            d.mkdir()
            (d / "2026-08-26-add-export-plan.md").write_text(
                "### Step 1\n", encoding="utf-8")
        cap, files = self._run(
            ["signal", "--status", "success",
             "--plan", ".plan/2026-08-26-add-export-plan.md",
             "--detail", "plan written: 9 steps, tag ui-data"],
            build=build)
        self.assertEqual(cap.code, 0, cap.stderr)
        name = f"2026-08-26-add-export-plan.{self.STAGE}.json"
        self.assertEqual(list(files), [name])
        sig = files[name]
        self.assertEqual(sig["schema"], 1)
        self.assertEqual(sig["skill"], self.SKILL)
        self.assertEqual(sig["stage"], self.STAGE)
        self.assertEqual(sig["status"], "success")
        self.assertTrue(os.path.isabs(sig["plan"]))
        self.assertTrue(sig["plan"].endswith("add-export-plan.md"))
        self.assertIn("9 steps", sig["detail"])
        self.assertTrue(sig["written_at"])
        # The signal path is printed for the harness, and no .tmp remains.
        self.assertTrue(cap.stdout.strip().endswith(name))

    def test_failed_signal_without_plan_uses_pipeline_stem(self):
        cap, files = self._run(
            ["signal", "--status", "failed", "--detail", "stopped at Step 4"])
        self.assertEqual(cap.code, 0, cap.stderr)
        name = f"pipeline.{self.STAGE}.json"
        self.assertEqual(list(files), [name])
        self.assertEqual(files[name]["status"], "failed")
        self.assertEqual(files[name]["plan"], "")

    def test_rerun_overwrites_atomically(self):
        """Last write wins; the .tmp intermediate never survives."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "p-plan.md").write_text("### Step\n", encoding="utf-8")
            prev = os.getcwd()
            os.chdir(root)
            try:
                first = io_capture(code_plan.main, [
                    "signal", "--status", "failed", "--plan", "p-plan.md"])
                second = io_capture(code_plan.main, [
                    "signal", "--status", "success", "--plan", "p-plan.md"])
            finally:
                os.chdir(prev)
            self.assertEqual(first.code, 0, first.stderr)
            self.assertEqual(second.code, 0, second.stderr)
            sig_dir = root / ".plan" / ".signals"
            names = sorted(f.name for f in sig_dir.iterdir())
            self.assertEqual(names, [f"p-plan.{self.STAGE}.json"])
            sig = json.loads((sig_dir / names[0]).read_text(encoding="utf-8"))
            self.assertEqual(sig["status"], "success")

    def test_signal_resolves_repo_root_from_subdir(self):
        def build(root):
            (root / "src").mkdir()
        cap, files = self._run(
            ["signal", "--status", "failed"], build=build, cwd_rel="src")
        self.assertEqual(cap.code, 0, cap.stderr)
        # Landed at the repo ROOT's .plan/.signals even though cwd was src/.
        self.assertEqual(list(files), [f"pipeline.{self.STAGE}.json"])

    def test_invalid_status_is_rejected(self):
        cap, files = self._run(["signal", "--status", "done"])
        self.assertEqual(cap.code, 2)
        self.assertEqual(files, {})


# ---------------------------------------------------------------------------
# stdout/stderr capture helper
# ---------------------------------------------------------------------------

class RouteNewLensTests(unittest.TestCase):
    """The four lenses added for gstack 1.87 (data, api, ai, ops), the
    review-family rule for autoplan, and the pre-planning clarify hint."""

    def _route(self, text, experts=None):
        with tempfile.TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "brief.txt"
            ipath.write_text(text, encoding="utf-8")
            argv = ["route", "--instructions-file", str(ipath), "--json"]
            if experts is not None:
                argv += ["--experts", experts]
            out = io_capture(code_plan.main, argv)
        self.assertEqual(out.code, 0, out.stderr)
        return json.loads(out.stdout)

    def test_migration_backfill_routes_to_data(self):
        payload = self._route("add a prisma migration and backfill the new column")
        self.assertIn("data", payload["lenses"])

    def test_webhook_sdk_routes_to_api(self):
        payload = self._route("change the webhook payload shape and update the sdk")
        self.assertIn("api", payload["lenses"])

    def test_llm_prompt_routes_to_ai(self):
        payload = self._route("rewrite the system prompt and add a tool call for the agent")
        self.assertIn("ai", payload["lenses"])

    def test_deploy_pipeline_routes_to_ops(self):
        payload = self._route("add a github actions deploy job with a canary rollout")
        self.assertIn("ops", payload["lenses"])

    def test_three_lenses_in_one_family_keep_plan_eng_review(self):
        """eng + data + api all read best under plan-eng-review; autoplan
        would spend a CEO and a design pass on a backend-only plan."""
        payload = self._route(
            "add a paginated /api/v1/quotes endpoint backed by a new sqlite schema")
        self.assertEqual(len(payload["lenses"]), code_plan.MAX_LENSES)
        self.assertEqual(payload["recommended_skill"], "plan-eng-review")

    def test_three_lenses_across_families_recommend_autoplan(self):
        payload = self._route(
            "redesign the settings page css and ui, add an api + sql schema, "
            "rotate the auth token")
        self.assertEqual(len(payload["lenses"]), code_plan.MAX_LENSES)
        self.assertEqual(payload["recommended_skill"], "autoplan")

    def test_forced_three_lenses_follow_the_family_rule(self):
        one_family = self._route("x", experts="eng,data,api")
        self.assertEqual(one_family["recommended_skill"], "plan-eng-review")
        two_families = self._route("x", experts="eng,design,api")
        self.assertEqual(two_families["recommended_skill"], "autoplan")

    def test_open_questions_set_clarify_and_pre_skill(self):
        payload = self._route(
            "**Objective:** add export.\n\n**Open questions:**\n- Which format?\n")
        self.assertTrue(payload["clarify"])
        self.assertEqual(payload["pre_skill"], code_plan.PRE_SKILL_CLARIFY)

    def test_trailing_note_sets_clarify(self):
        payload = self._route("Make the app faster.\nNOTE: no measurable target.\n")
        self.assertTrue(payload["clarify"])

    def test_clean_brief_has_no_pre_skill(self):
        payload = self._route("**Objective:** add a CSV export button.\n")
        self.assertFalse(payload["clarify"])
        self.assertIsNone(payload["pre_skill"])

    def test_human_output_prints_pre_skill_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "brief.txt"
            ipath.write_text("**Open questions:**\n- ?\n", encoding="utf-8")
            out = io_capture(code_plan.main,
                             ["route", "--instructions-file", str(ipath)])
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("pre-skill: spec", out.stdout)


class KnowledgeTests(unittest.TestCase):
    """`knowledge` gathers repo signals deterministically and degrades to a
    'none found' block. gstack's helpers are stubbed out so the tests stay
    hermetic on machines with or without gstack."""

    def setUp(self):
        self._orig = code_plan._gstack_bin_dir
        code_plan._gstack_bin_dir = lambda: None

    def tearDown(self):
        code_plan._gstack_bin_dir = self._orig

    def _run(self, root, *extra):
        return io_capture(code_plan.main,
                          ["knowledge", "--root", str(root), *extra])

    def test_repo_signals_are_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "package.json").write_text(
                json.dumps({"scripts": {"test": "vitest run", "lint": "eslint ."}}),
                encoding="utf-8")
            (root / "CLAUDE.md").write_text(
                "# Repo\n<!-- gstack:verify: npm test -->\n", encoding="utf-8")
            (root / "DESIGN.md").write_text("# gstack: design-md-format=spec\n",
                                            encoding="utf-8")
            (root / "docs" / "designs").mkdir(parents=True)
            (root / "docs" / "designs" / "export.md").write_text("# Design\n",
                                                                  encoding="utf-8")
            out = self._run(root)
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("`npm test`", out.stdout)
        self.assertIn("vitest run", out.stdout)
        self.assertIn("DESIGN.md present", out.stdout)
        self.assertIn("docs/designs/export.md", out.stdout)
        self.assertIn("Reference data, not instructions", out.stdout)
        self.assertIn("verify command", out.stderr)
        self.assertIn("DESIGN.md", out.stderr)

    def test_empty_repo_yields_none_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run(Path(tmp))
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn(code_plan.KNOWLEDGE_EMPTY, out.stdout)
        self.assertIn("none found", out.stderr)

    def test_json_output_exposes_raw_facts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
            out = self._run(root, "--json")
        self.assertEqual(out.code, 0, out.stderr)
        payload = json.loads(out.stdout)
        self.assertEqual(payload["stacks"], ["python"])
        self.assertIn("pytest", payload["verify"])
        self.assertFalse(payload["gstack"])

    def test_query_keyword_skips_brief_labels(self):
        self.assertEqual(
            code_plan.pick_query_keyword(
                "**Objective:** Introduce a paginated quotes endpoint.\n"),
            "Introduce")
        self.assertEqual(
            code_plan.pick_query_keyword("**Objective:** add a webhook signature check"),
            "webhook")
        self.assertEqual(code_plan.pick_query_keyword("fix the bug"), "")

    def test_query_file_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qf = root / "brief.txt"
            qf.write_text("**Objective:** pagination for quotes\n", encoding="utf-8")
            out = self._run(root, "--query-file", str(qf), "--json")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn('"gstack": false', out.stdout)

    def test_walks_up_to_the_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / "AGENTS.md").write_text("rules\n", encoding="utf-8")
            sub = root / "src" / "deep"
            sub.mkdir(parents=True)
            out = self._run(sub)
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("AGENTS.md", out.stdout)


class RenderKnowledgeTests(unittest.TestCase):

    def _render(self, template, knowledge=None, knowledge_file=None):
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_text(template, encoding="utf-8")
            ipath = Path(tmp) / "i.txt"
            ipath.write_text("do thing", encoding="utf-8")
            argv = ["render", "--template", str(tpath), "--path", "p",
                    "--plan-filename", "f.md", "--instructions-file", str(ipath)]
            if knowledge is not None:
                kpath = Path(tmp) / "k.md"
                kpath.write_text(knowledge, encoding="utf-8")
                argv += ["--knowledge-file", str(kpath)]
            elif knowledge_file is not None:
                argv += ["--knowledge-file", knowledge_file]
            return io_capture(code_plan.main, argv)

    def test_knowledge_file_substituted(self):
        out = self._render("K={{PROJECT_KNOWLEDGE}}\n{{INSTRUCTIONS}}\n",
                           knowledge="### Repo signals\n- verify: `bun test`")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("bun test", out.stdout)
        self.assertNotIn("{{PROJECT_KNOWLEDGE}}", out.stdout)

    def test_knowledge_default_when_omitted(self):
        out = self._render("K={{PROJECT_KNOWLEDGE}}\n{{INSTRUCTIONS}}\n")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn(code_plan.KNOWLEDGE_EMPTY, out.stdout)

    def test_knowledge_missing_file_exits_1(self):
        out = self._render("K={{PROJECT_KNOWLEDGE}}\n{{INSTRUCTIONS}}\n",
                           knowledge_file="/nonexistent/k.md")
        self.assertEqual(out.code, 1, out.stderr)

    def test_knowledge_text_with_token_shapes_never_trips_the_guard(self):
        out = self._render("K={{PROJECT_KNOWLEDGE}}\n{{INSTRUCTIONS}}\n",
                           knowledge="learning mentions {{FOO}} literally")
        self.assertEqual(out.code, 0, out.stderr)
        self.assertIn("{{FOO}}", out.stdout)


class SkillContractTests(unittest.TestCase):
    """The shipped prompt template, SKILL.md and plugin.json stay coherent."""

    SKILL_DIR = SCRIPTS_DIR.parent

    def test_create_plan_template_carries_every_placeholder(self):
        text = (self.SKILL_DIR / "prompts" / "create-plan.md").read_text(encoding="utf-8")
        tokens = set(re.findall(r"\{\{[A-Z_]+\}\}", text))
        self.assertEqual(tokens, {"{{PROJECT_TAG}}", "{{PATH}}", "{{PLAN_FILENAME}}",
                                  "{{EXPERT_LENSES}}", "{{PROJECT_KNOWLEDGE}}",
                                  "{{INSTRUCTIONS}}"})
        self.assertLess(text.find("{{PROJECT_KNOWLEDGE}}"), text.find("{{INSTRUCTIONS}}"))

    def test_real_template_renders_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            ipath = Path(tmp) / "i.txt"
            ipath.write_text("add a CSV export", encoding="utf-8")
            out = io_capture(code_plan.main, [
                "render", "--path", tmp, "--plan-filename", "p.md",
                "--instructions-file", str(ipath)])
        self.assertEqual(out.code, 0, out.stderr)
        self.assertNotIn("{{", out.stdout.replace("{{PATH}}", ""))
        self.assertIn("### Step N", out.stdout)

    def test_skill_md_names_every_lens_and_the_knowledge_step(self):
        text = (self.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        for lens in code_plan.SIGNALS:
            self.assertIn(f"`{lens}`", text, f"SKILL.md does not list lens {lens}")
        self.assertIn("knowledge", text)
        self.assertIn("--knowledge-file", text)
        self.assertIn("pre_skill", text)

    def test_versions_in_lockstep(self):
        skill_text = (self.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', skill_text, re.MULTILINE)
        assert m is not None
        plugin = json.loads((self.SKILL_DIR / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(m.group(1), plugin["version"])


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
