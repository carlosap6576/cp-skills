#!/usr/bin/env python3
"""
selftest.py — offline unit tests for code_validation.py.

Stdlib only. No network, no LM Studio. Run:

    python3 skills/code-validation/scripts/selftest.py -v

Covers:
  render: substitutes {{PATH}} with the absolute path; exit 3 on an unknown
          {{FOO}} token in a custom --template; exit 1 on a missing/unreadable
          --template; exit 1 (no traceback) on a non-UTF-8 --template.
          With no --template flag, resolves the default to
          {skill_dir}/prompts/validate-code.md.
  plan-check: passes on a real stepped .md and prints an absolute path;
          exits 2 on a missing file, an empty file, a non-.md file, a .md
          with no "### " headings, an empty flag value, a directory, and a
          binary *.md (no traceback); the .md suffix gate runs before the read.
  SKILL.md: the shell blocks assign no zsh-reserved variable names (the
          `status=$?` regression) and stay POSIX-parseable.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Make the script under test importable regardless of cwd.
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import code_validation  # noqa: E402  (after sys.path insert above)


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
    """Run code_validation.main(argv) with stdout/stderr captured. main() returns
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
        template = "The plan to validate is at: {{PATH}}\n"
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "tmpl.md"
            tpath.write_text(template, encoding="utf-8")
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_validation.main, [
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
            out = io_capture(code_validation.main, [
                "render", "--template", str(tpath), "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 3, out.stderr)
            self.assertIn("FOO", out.stderr)

    def test_render_exits_1_on_missing_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_validation.main, [
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
            out = io_capture(code_validation.main, [
                "render", "--template", str(tpath), "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 1, out.stderr)
            self.assertIn("cannot read template", out.stderr)
            self.assertEqual(out.stdout, "")

    def test_render_default_template_resolves_to_validate_code_md(self):
        """With no --template flag, render resolves the default to
        prompts/validate-code.md under the skill dir. We point --skill-dir at a
        temp dir containing a prompts/validate-code.md with a {{PATH}} token and
        confirm it is used."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_root = Path(tmp) / "skill"
            prompts_dir = skill_root / "prompts"
            prompts_dir.mkdir(parents=True)
            (prompts_dir / "validate-code.md").write_text(
                "AUDIT PROMPT {{PATH}}\n", encoding="utf-8"
            )
            ppath = Path(tmp) / "plan.md"
            ppath.write_text("### Step 1\n", encoding="utf-8")
            # --skill-dir is a top-level flag (before the subcommand); --plan
            # belongs to the render subcommand (after). argparse enforces this
            # ordering for subparsers.
            out = io_capture(code_validation.main, [
                "--skill-dir", str(skill_root),
                "render",
                "--plan", str(ppath),
            ])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertIn("AUDIT PROMPT", out.stdout)
            self.assertIn(str(ppath.resolve()), out.stdout)
            self.assertNotIn("{{", out.stdout)


class PlanCheckTests(unittest.TestCase):

    def _write(self, tmp, name, body):
        p = Path(tmp) / name
        p.write_text(body, encoding="utf-8")
        return p

    def test_plan_check_passes_on_stepped_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "good.md", "# Title\n\n### Step 1\n\ndo thing\n")
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 0, out.stderr)
            # Prints the absolute path.
            printed = out.stdout.strip()
            self.assertTrue(printed.endswith("good.md"))
            self.assertTrue(os.path.isabs(printed), f"not absolute: {printed}")

    def test_plan_check_exits_2_on_missing_file(self):
        out = io_capture(code_validation.main, [
            "plan-check", "--plan", "/nonexistent/code-validation-selftest.md",
        ])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("does not exist", out.stderr)

    def test_plan_check_exits_2_on_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "empty.md", "")
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("empty", out.stderr)

    def test_plan_check_exits_2_on_non_md_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "plan.txt", "### Step 1\n\ndo thing\n")
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn(".md", out.stderr)

    def test_plan_check_exits_2_on_md_without_step_headings(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "readme.md", "# A README\n\nSome prose only.\n")
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("### ", out.stderr)

    def test_plan_check_exits_2_on_empty_flag_value(self):
        """`-p ""` counts as not provided (SKILL.md Step 1) — clean exit 2,
        not an argparse traceback."""
        out = io_capture(code_validation.main, ["plan-check", "--plan", ""])
        self.assertEqual(out.code, 2, out.stderr)
        self.assertIn("no plan file given", out.stderr)

    def test_plan_check_exits_2_on_directory(self):
        """A directory is not a plan file — is_file() gate, no traceback."""
        with tempfile.TemporaryDirectory() as tmp:
            out = io_capture(code_validation.main, ["plan-check", "--plan", tmp])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertEqual(out.stdout, "")

    def test_plan_check_exits_2_on_binary_md(self):
        """A binary file named *.md must exit 2 cleanly. Before the fix this
        raised UnicodeDecodeError and dumped a traceback at exit 1."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "binary.md"
            p.write_bytes(b"### Step 1\n\xd8\xff\x00\x80not utf8\n")
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn("not UTF-8", out.stderr)
            self.assertEqual(out.stdout, "")

    def test_plan_check_suffix_gate_precedes_read(self):
        """A non-.md binary is rejected on the cheap suffix gate — we never
        slurp it. Guards the check-ordering fix."""
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "blob.bin"
            p.write_bytes(b"\x00\xff" * 32)
            out = io_capture(code_validation.main, ["plan-check", "--plan", str(p)])
            self.assertEqual(out.code, 2, out.stderr)
            self.assertIn(".md", out.stderr)
            self.assertNotIn("UTF-8", out.stderr)


class DefaultPlanTests(unittest.TestCase):
    """Auto-discovery for an omitted -p: exactly one *.md in <repo-root>/.plan
    resolves with zero prompts; missing/empty/ambiguous all exit 2 so the
    SKILL.md falls back to its path question. A regression that guesses here
    would validate the wrong plan; one that exits 2 on a single plan would
    resurrect the needless confirmation prompt."""

    def _in_tmp(self, build, cwd_rel="."):
        """Create a temp tree via build(root), chdir to root/cwd_rel, run
        default-plan, restore cwd. Returns the captured result."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build(root)
            prev = os.getcwd()
            os.chdir(root / cwd_rel)
            try:
                return io_capture(code_validation.main, ["default-plan"]), root
            finally:
                os.chdir(prev)

    def test_single_plan_resolves_with_zero_prompts(self):
        def build(root):
            (root / ".git").mkdir()
            d = root / ".plan"
            d.mkdir()
            (d / "only-plan.md").write_text("### Step 1\n", encoding="utf-8")
        out, _ = self._in_tmp(build)
        self.assertEqual(out.code, 0)
        self.assertTrue(out.stdout.strip().endswith("only-plan.md"))

    def test_single_plan_resolves_from_a_subdirectory(self):
        def build(root):
            (root / ".git").mkdir()
            (root / "src").mkdir()
            d = root / ".plan"
            d.mkdir()
            (d / "only-plan.md").write_text("### Step 1\n", encoding="utf-8")
        out, _ = self._in_tmp(build, cwd_rel="src")
        self.assertEqual(out.code, 0)
        self.assertTrue(out.stdout.strip().endswith("only-plan.md"))

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
            (d / "a-plan.md").write_text("### Step 1\n", encoding="utf-8")
            (d / "b-plan.md").write_text("### Step 1\n", encoding="utf-8")
        out, _ = self._in_tmp(build)
        self.assertEqual(out.code, 2)
        self.assertIn("2 plans", out.stderr)
        self.assertIn("a-plan.md", out.stderr)
        self.assertIn("b-plan.md", out.stderr)

    def test_skill_md_pins_the_zero_prompt_contract(self):
        raw = (SCRIPTS_DIR.parent / "SKILL.md").read_text(encoding="utf-8")
        # Collapse the markdown line wrapping so the pinned phrases match
        # regardless of where the prose happens to break.
        flat = re.sub(r"\s+", " ", raw)
        self.assertIn("default-plan", flat)
        self.assertIn("Do NOT ask for confirmation", flat,
                      "a single discovered plan must run without a prompt")


class SkillMdShellTests(unittest.TestCase):
    """The SKILL.md bash blocks are copy-pasted verbatim into a live shell by the
    agent running the skill. That shell is whatever the user runs — commonly zsh.
    These guard the contract those blocks must honor."""

    SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"

    # zsh makes these read-only specials (or ties them to another variable), so
    # assigning to one aborts the block mid-gate. `status` is the one that bit:
    # `status=$?` errored, `$status` then read the FAILED assignment's code, and
    # a perfectly valid plan was falsely rejected before Step 3 ever ran.
    ZSH_RESERVED = {
        "status", "pipestatus", "path", "argv",
        "LINENO", "PPID", "ZSH_VERSION", "ZSH_NAME",
    }

    _FENCE = re.compile(r"```(?:bash|sh)\n(.*?)```", re.DOTALL)
    _ASSIGN = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)=", re.MULTILINE)

    def _blocks(self):
        self.assertTrue(self.SKILL_MD.is_file(), f"missing {self.SKILL_MD}")
        blocks = self._FENCE.findall(self.SKILL_MD.read_text(encoding="utf-8"))
        self.assertTrue(blocks, "SKILL.md has no bash blocks — contract changed?")
        return blocks

    def test_skill_md_assigns_no_zsh_reserved_names(self):
        offenders = []
        for block in self._blocks():
            for name in self._ASSIGN.findall(block):
                if name in self.ZSH_RESERVED:
                    offenders.append(name)
        self.assertEqual(
            offenders, [],
            f"SKILL.md assigns zsh-reserved name(s) {sorted(set(offenders))}; "
            "the block breaks under zsh. Use `rc` for exit codes.",
        )

    def test_skill_md_blocks_parse_under_sh(self):
        """Every block must at least be syntactically valid POSIX shell."""
        for i, block in enumerate(self._blocks()):
            with self.subTest(block=i):
                proc = subprocess.run(
                    ["sh", "-n"], input=block, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)


class ProductionCleanupContractTests(unittest.TestCase):
    """Tripwires for LAW 5 (production cleanup). The sweep lives in prose —
    the template and SKILL.md — so a hand-edit that drops it would fail
    silently at audit time. These pin the load-bearing phrases offline."""

    SKILL_DIR = Path(__file__).resolve().parent.parent

    @classmethod
    def setUpClass(cls):
        cls.template = (cls.SKILL_DIR / "prompts" / "validate-code.md").read_text(
            encoding="utf-8")
        cls.skill_md = (cls.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_template_has_cleanup_phase_before_final_report(self):
        cleanup = self.template.find("## Phase 5 — Production Cleanup Sweep")
        report = self.template.find("## Phase 6 — Final Report")
        self.assertNotEqual(cleanup, -1, "cleanup phase heading missing")
        self.assertNotEqual(report, -1, "final report is no longer Phase 6")
        self.assertLess(cleanup, report, "cleanup must precede the report")

    def test_template_names_the_debris_classes(self):
        for marker in ("console.log", "debugger", "TODO/FIXME",
                       "commented-out code", "Unused code", "imports"):
            self.assertIn(marker, self.template,
                          f"debris class {marker!r} dropped from the sweep")

    def test_template_reverifies_after_sweep_and_bans_git(self):
        self.assertIn("re-run the Phase 4 verification", self.template)
        self.assertIn("no commits, no branches", self.template)

    def test_template_nonnegotiable_pins_the_sweep(self):
        self.assertIn("Never leave developer debris", self.template)

    def test_skill_md_carries_law_5_and_the_c_counter(self):
        self.assertIn("LAW 5", self.skill_md)
        self.assertIn("{C} files production-cleaned", self.skill_md)

    def test_template_keeps_the_single_path_placeholder(self):
        tokens = set(re.findall(r"\{\{[A-Z_]+\}\}", self.template))
        self.assertEqual(tokens, {"{{PATH}}"},
                         "render substitutes exactly one token — {{PATH}}")


class PrCleanContractTests(unittest.TestCase):
    """Tripwires for the v1.6 PR-clean rules: the Phase 5a scaffolding
    teardown (generated tests/mocks/stubs are deleted after proving the
    work), the 5b zero-comment production polish, and the 5c .gitignore/.plan
    repo hygiene gate. All three live in prose, so a hand-edit that drops one
    would fail silently at audit time."""

    SKILL_DIR = Path(__file__).resolve().parent.parent

    @classmethod
    def setUpClass(cls):
        cls.template = (cls.SKILL_DIR / "prompts" / "validate-code.md").read_text(
            encoding="utf-8")
        cls.skill_md = (cls.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (cls.SKILL_DIR / "README.md").read_text(encoding="utf-8")

    def test_phase5_has_three_ordered_passes_before_the_report(self):
        teardown = self.template.find("### 5a — Test scaffolding teardown")
        polish = self.template.find("### 5b — Production polish")
        hygiene = self.template.find("### 5c — Repo hygiene gate")
        report = self.template.find("## Phase 6 — Final Report")
        for pos, name in ((teardown, "5a teardown"), (polish, "5b polish"),
                          (hygiene, "5c hygiene"), (report, "Phase 6")):
            self.assertNotEqual(pos, -1, f"{name} heading missing")
        self.assertLess(teardown, polish, "teardown must precede polish")
        self.assertLess(polish, hygiene, "polish must precede the hygiene gate")
        self.assertLess(hygiene, report, "the sweep must precede the report")

    def test_teardown_is_strict_and_names_the_scaffolding_classes(self):
        for marker in ("mock", "stub", "fixture", "harness", "DELETED"):
            self.assertIn(marker, self.template,
                          f"scaffolding class {marker!r} dropped from 5a")
        self.assertIn("zero tolerance", self.template)
        self.assertIn("pre-date this change", self.template,
                      "the pre-existing-tests survivor rule is load-bearing")
        self.assertIn("explicitly names as a deliverable", self.template,
                      "the plan-named-deliverable survivor rule is load-bearing")

    def test_template_encourages_test_creation_before_teardown(self):
        self.assertIn("encouraged", self.template,
                      "creating proof tests must stay encouraged — the rule "
                      "is teardown-after-proof, not no-tests")

    def test_zero_comment_policy_pinned(self):
        self.assertIn("zero-comment policy", self.template)
        self.assertIn("AI-generated notes", self.template)
        self.assertIn("User-facing output is NOT debris", self.template,
                      "CLI/interface informational output must stay exempt")

    def test_repo_hygiene_gate_pinned(self):
        for marker in (".plan", ".gitignore", "git rm -r --cached",
                       "read-only inspection"):
            self.assertIn(marker, self.template,
                          f"hygiene-gate marker {marker!r} dropped from 5c")

    def test_skill_md_and_readme_carry_the_s_counter(self):
        self.assertIn("{S} scaffolding files removed", self.skill_md)
        self.assertIn("{S} scaffolding files removed", self.readme)
        self.assertIn("Scaffolding teardown", self.skill_md)
        self.assertIn("Repo hygiene gate", self.readme)


class PlanDeletionContractTests(unittest.TestCase):
    """Tripwires for LAW 6 (end-of-run plan deletion). The close-out lives in
    SKILL.md prose, so a hand-edit that drops it would fail silently — the
    plan would linger and the user would never see the ready signal."""

    SKILL_DIR = Path(__file__).resolve().parent.parent

    @classmethod
    def setUpClass(cls):
        cls.skill_md = (cls.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        cls.readme = (cls.SKILL_DIR / "README.md").read_text(encoding="utf-8")

    def test_skill_md_carries_law_6_and_the_deletion_line(self):
        self.assertIn("LAW 6", self.skill_md)
        self.assertIn("PLAN DELETED —", self.skill_md)
        self.assertIn("same session", self.skill_md,
                      "the same-session continuation note is part of the contract")

    def test_integrity_check_precedes_the_deletion_step(self):
        check = self.skill_md.find("## Step 5")
        close_out = self.skill_md.find("## Step 7")
        self.assertNotEqual(check, -1, "Step 5 integrity check heading missing")
        self.assertNotEqual(close_out, -1, "Step 7 close-out heading missing")
        self.assertLess(check, close_out,
                        "the mtime check must run before the plan is deleted")

    def test_failed_audits_keep_the_plan(self):
        self.assertIn("NEVER deletes the plan", self.skill_md,
                      "a failed/aborted audit must keep its plan for the re-run")

    def test_readme_documents_the_close_out(self):
        self.assertIn("PLAN DELETED —", self.readme)

    def test_skill_md_routes_the_deletion_through_close_out(self):
        """The prose must call the subcommand, not hand-roll `rm`.

        The regression this pins: Step 7 used to be a `rm -f` the model had to
        remember plus a sentence it wrote itself. Those are uncoupled, so the
        sentence got emitted without the deletion. The line must now come from
        close-out's stdout.
        """
        self.assertIn("close-out", self.skill_md,
                      "Step 7 must invoke the close-out subcommand")
        self.assertNotIn('rm -f "$PLAN_ABS"', self.skill_md,
                         "the hand-rolled rm is what let the claim outrun the act")
        self.assertIn("verbatim", self.skill_md,
                      "the closing line must be relayed, not composed")
        self.assertIn("Never type the `PLAN DELETED` line yourself", self.skill_md)


class CloseOutTests(unittest.TestCase):
    """Behavioural coverage for `close-out` — the subcommand that makes the
    LAW 6 announcement a consequence of the deletion instead of a claim about
    it. Prose tripwires cannot catch 'announced but never deleted'; these can,
    because the line only ever reaches stdout when the file is really gone."""

    def test_deletes_the_plan_and_prints_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.md"
            plan.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_validation.main, ["close-out", "--plan", str(plan)])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertFalse(plan.exists(), "the plan file must actually be gone")
            self.assertIn("PLAN DELETED —", out.stdout)
            self.assertIn(str(plan.resolve()), out.stdout)
            self.assertIn("same session", out.stdout,
                          "the continuation note is part of the contract")

    def test_stdout_is_the_whole_announcement_on_one_line(self):
        """The model relays stdout verbatim as its final line, so stdout must
        be exactly that line — nothing to trim, nothing to reassemble."""
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "plan.md"
            plan.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_validation.main, ["close-out", "--plan", str(plan)])
            lines = [ln for ln in out.stdout.splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1, f"expected one line, got {lines!r}")
            self.assertTrue(lines[0].startswith("PLAN DELETED — "))
            self.assertTrue(lines[0].endswith("continue right here."))

    def test_undeletable_plan_prints_no_success_line(self):
        """The load-bearing property: a failed deletion yields EMPTY stdout, so
        there is no line to relay and the run cannot claim a deletion."""
        with tempfile.TemporaryDirectory() as tmp:
            holder = Path(tmp) / "locked"
            holder.mkdir()
            plan = holder / "plan.md"
            plan.write_text("### Step 1\n", encoding="utf-8")
            os.chmod(holder, 0o500)  # read+execute: cannot unlink children
            try:
                out = io_capture(code_validation.main, ["close-out", "--plan", str(plan)])
                if out.code == 0:
                    self.skipTest("filesystem/user ignores directory write perms (root?)")
                self.assertEqual(out.code, 1)
                self.assertEqual(out.stdout.strip(), "",
                                 "a failed deletion must print NOTHING to stdout")
                self.assertIn("WARN: could not delete", out.stderr)
                self.assertTrue(plan.exists())
            finally:
                os.chmod(holder, 0o700)

    def test_already_absent_is_idempotent_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = Path(tmp) / "gone.md"
            out = io_capture(code_validation.main, ["close-out", "--plan", str(plan)])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertIn("PLAN DELETED —", out.stdout)
            self.assertIn("already absent", out.stderr,
                          "stderr must be honest that we did not do the removing")

    def test_refuses_a_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "dot-plan.md"
            target.mkdir()
            out = io_capture(code_validation.main, ["close-out", "--plan", str(target)])
            self.assertEqual(out.code, 2)
            self.assertEqual(out.stdout.strip(), "")
            self.assertIn("refusing to delete a directory", out.stderr)
            self.assertTrue(target.is_dir(), "the directory must survive")

    def test_refuses_a_non_md_file(self):
        """A mis-set PLAN_ABS must not be able to delete arbitrary files."""
        with tempfile.TemporaryDirectory() as tmp:
            victim = Path(tmp) / "important.db"
            victim.write_text("payload", encoding="utf-8")
            out = io_capture(code_validation.main, ["close-out", "--plan", str(victim)])
            self.assertEqual(out.code, 2)
            self.assertEqual(out.stdout.strip(), "")
            self.assertIn("refusing to delete a non-.md file", out.stderr)
            self.assertTrue(victim.exists(), "a non-plan file must survive")

    def test_only_the_named_file_is_touched(self):
        """Sibling plans and the containing folder must survive the close-out."""
        with tempfile.TemporaryDirectory() as tmp:
            plan_dir = Path(tmp) / ".plan"
            plan_dir.mkdir()
            target = plan_dir / "a.md"
            sibling = plan_dir / "b.md"
            target.write_text("### Step 1\n", encoding="utf-8")
            sibling.write_text("### Step 1\n", encoding="utf-8")
            out = io_capture(code_validation.main, ["close-out", "--plan", str(target)])
            self.assertEqual(out.code, 0, out.stderr)
            self.assertFalse(target.exists())
            self.assertTrue(sibling.exists(), "sibling plans must survive")
            self.assertTrue(plan_dir.is_dir(), "the .plan folder must survive")


class DocsContractTests(unittest.TestCase):
    """Pins the expert-awareness contract added in v1.5.0: the gstack expert
    roster ships with the skill, carries a verifiable gstack version pin
    (install.sh's doctor greps it for drift detection), SKILL.md actually
    routes to it, and the two version declarations stay in lockstep."""

    SKILL_DIR = SCRIPTS_DIR.parent

    def test_gstack_experts_file_exists_with_version_pin(self):
        experts = self.SKILL_DIR / "prompts" / "gstack-experts.md"
        self.assertTrue(experts.is_file(), "prompts/gstack-experts.md missing")
        text = experts.read_text(encoding="utf-8")
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
        the force-flag advisory in SKILL.md Step 6 depends on it."""
        text = (self.SKILL_DIR / "prompts" / "gstack-experts.md").read_text(
            encoding="utf-8")
        for specialist in ("testing", "maintainability", "security",
                           "performance", "data-migration", "api-contract",
                           "red-team", "--all-specialists"):
            self.assertIn(specialist, text, f"missing specialist: {specialist}")

    def test_versions_in_lockstep(self):
        import json
        skill_text = (self.SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
        m = re.search(r'^version:\s*"([^"]+)"', skill_text, re.MULTILINE)
        assert m is not None, "no version in SKILL.md frontmatter"
        plugin = json.loads(
            (self.SKILL_DIR / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(m.group(1), plugin["version"],
                         "SKILL.md and plugin.json versions drifted")

    def test_residual_risk_evidence_rule_in_template(self):
        """Phase 6's Residual-risks item must keep the evidence requirement
        (gstack ≥ 1.65: a claimed limitation needs the verbatim probe)."""
        text = (self.SKILL_DIR / "prompts" / "validate-code.md").read_text(
            encoding="utf-8")
        self.assertIn("verbatim probe output", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
