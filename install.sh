#!/usr/bin/env bash
# cp-skills installer & doctor — installs EVERY skill in this repo into every
# skills root your agent harnesses scan (Claude Code, Codex, Gemini CLI,
# Cursor, Copilot, OpenCode, Hermes, OpenClaw, and the shared ~/.agents
# root). Same doctor contract as the per-skill installers: every check prints
# a verdict, every problem it can safely fix is fixed on the spot, and the
# summary states exactly what was installed, upgraded, or repaired and at
# which version.
#
# A skill is any top-level folder of this repo that carries a SKILL.md, so a
# new skill folder is picked up automatically — no edits to this file needed.
# Versions come from each skill's SKILL.md frontmatter (cross-checked against
# its plugin.json); symlink installs always track the checkout, copy installs
# are upgraded in place when the source version moves.
#
#   ./install.sh                        # install/upgrade all skills everywhere + full checkup
#   ./install.sh --doctor               # checkup only: diagnose, change nothing
#   ./install.sh --copy                 # copy instead of symlink
#   ./install.sh --dir DIR              # operate on DIR/<skill> only (one root)
#   ./install.sh --root DIR             # add DIR to the candidate roots (repeatable)
#   ./install.sh --only a,b             # limit to these skills
#   ./install.sh --skip a,b             # exclude these skills
#   ./install.sh --list                 # list discovered skills + versions and exit
#   ./install.sh --no-gstack            # skip the gstack install/upgrade + contract sync
#   ./install.sh --no-sync              # upgrade gstack but leave the skills' contract snapshot alone
#   ./install.sh --gstack-dir DIR       # gstack checkout to manage (default ~/.claude/skills/gstack)
#   ./install.sh --uninstall            # remove every skill from every candidate root (gstack is left alone)
#   ./install.sh --dir DIR --uninstall  # remove from DIR/<skill> only
#
# gstack: the code-* skills chain into gstack (/review, /qa, /cso, /ship, the
# plan reviews). Every run installs gstack if missing, fast-forwards an
# existing git checkout to origin/main and reruns its ./setup, then re-verifies
# the hand-off contract against what is actually installed — /review's
# specialist roster and force flags, its diff thresholds, autoplan's phase
# order, the plan-review scope gates, and the presence of every gstack skill
# the roster names. The verified facts are written to each code-* skill's
# prompts/gstack-contract.md, its "verified against gstack X" pins are bumped,
# and its patch version is bumped when the snapshot changed. --doctor reports
# the drift without touching anything.
#
# Env: CP_SKILLS_ROOTS="dir1:dir2" replaces the built-in candidate roots.
#      GSTACK_DIR overrides the gstack checkout location (same as --gstack-dir).
#      NO_COLOR=1 disables colour.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="symlink"
UNINSTALL=0
DOCTOR=0
LIST=0
EXPLICIT_DIR=""
ONLY=""
SKIP=""
EXTRA_ROOTS=()
DO_GSTACK=1
DO_SYNC=1
GSTACK_DIR="${GSTACK_DIR:-$HOME/.claude/skills/gstack}"
GSTACK_REPO_URL="https://github.com/garrytan/gstack.git"
MANIFEST_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/cp-skills"
MANIFEST="$MANIFEST_DIR/installed.tsv"

# Every harness we know of, keyed on the parent dir the harness itself
# creates. A root is only targeted when that parent already exists, so a
# machine without e.g. Codex never grows an orphan ~/.codex.
CANDIDATE_ROOTS=(
  "$HOME/.claude/skills"           # Claude Code
  "$HOME/.codex/skills"            # OpenAI Codex CLI
  "$HOME/.gemini/skills"           # Gemini CLI
  "$HOME/.cursor/skills"           # Cursor
  "$HOME/.copilot/skills"          # GitHub Copilot CLI
  "$HOME/.config/opencode/skills"  # OpenCode
  "$HOME/.hermes/skills"           # Hermes
  "$HOME/.config/hermes/skills"    # Hermes (XDG layout)
  "$HOME/.openclaw/skills"         # OpenClaw
  "$HOME/.agents/skills"           # shared cross-harness root (agentskills.io)
)

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE="copy"; shift ;;
    --dir)
      [ $# -ge 2 ] || { echo "ERROR: --dir needs a directory argument" >&2; exit 2; }
      EXPLICIT_DIR="$2"; shift 2 ;;
    --root)
      [ $# -ge 2 ] || { echo "ERROR: --root needs a directory argument" >&2; exit 2; }
      EXTRA_ROOTS+=("$2"); shift 2 ;;
    --only)
      [ $# -ge 2 ] || { echo "ERROR: --only needs a comma-separated skill list" >&2; exit 2; }
      ONLY="$2"; shift 2 ;;
    --skip)
      [ $# -ge 2 ] || { echo "ERROR: --skip needs a comma-separated skill list" >&2; exit 2; }
      SKIP="$2"; shift 2 ;;
    --no-gstack) DO_GSTACK=0; shift ;;
    --no-sync) DO_SYNC=0; shift ;;
    --gstack-dir)
      [ $# -ge 2 ] || { echo "ERROR: --gstack-dir needs a directory argument" >&2; exit 2; }
      GSTACK_DIR="$2"; shift 2 ;;
    --doctor) DOCTOR=1; shift ;;
    --list) LIST=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown arg: $1 (see --help)" >&2; exit 2 ;;
  esac
done

# ---- Doctor console ---------------------------------------------------------

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_OK=$'\033[32m'; C_FIX=$'\033[36m'; C_WARN=$'\033[33m'
  C_FAIL=$'\033[31m'; C_BOLD=$'\033[1m'; C_DIM=$'\033[2m'; C_END=$'\033[0m'
else
  C_OK=""; C_FIX=""; C_WARN=""; C_FAIL=""; C_BOLD=""; C_DIM=""; C_END=""
fi

WARNS=0
FAILS=0
CHANGES=()   # every install/upgrade/repair, replayed verbatim in the summary

ok()      { printf '  %s[ OK ]%s %s\n' "$C_OK"   "$C_END" "$1"; }
note()    { printf '  %s[ -- ]%s %s\n' "$C_DIM"  "$C_END" "$1"; }
fixed()   { printf '  %s[FIX ]%s %s\n' "$C_FIX"  "$C_END" "$1"; CHANGES+=("$1"); }
warn()    { printf '  %s[WARN]%s %s\n' "$C_WARN" "$C_END" "$1"; WARNS=$((WARNS+1)); }
fail()    { printf '  %s[FAIL]%s %s\n' "$C_FAIL" "$C_END" "$1"; FAILS=$((FAILS+1)); }
section() { printf '\n%s%s%s\n' "$C_BOLD" "$1" "$C_END"; }

# ---- Small helpers ----------------------------------------------------------

skill_version() {  # $1 = a skill dir; prints the SKILL.md frontmatter version
  sed -n 's/^version:[[:space:]]*"\{0,1\}\([0-9][0-9A-Za-z.-]*\)"\{0,1\}.*$/\1/p' \
    "$1/SKILL.md" 2>/dev/null | head -n 1
}

plugin_version() {  # $1 = a skill dir; prints the plugin.json version
  sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
    "$1/plugin.json" 2>/dev/null | head -n 1
}

skill_python_min() {  # $1 = a skill dir; prints the highest "Python 3.N+" it documents (default 3.9)
  local v
  v="$(grep -rhoE 'Python 3\.[0-9]+\+' "$1/SKILL.md" "$1/README.md" "$1/requirements.txt" 2>/dev/null \
    | sed 's/^Python //; s/+$//' | sort -t. -k2,2n | tail -n 1 || true)"
  printf '%s' "${v:-3.9}"
}

resolve_path() {  # canonical absolute path; echoes nothing if unresolvable
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1" 2>/dev/null || true
  else
    (cd "$1" 2>/dev/null && pwd) || true
  fi
}

in_list() {  # $1 = needle, $2 = comma-separated list
  case ",$2," in *",$1,"*) return 0 ;; esac
  return 1
}

install_into() {  # $1 = src, $2 = dest path; assumes dest does not exist
  if [ "$MODE" = "symlink" ]; then
    ln -s "$1" "$2"
  else
    cp -R "$1" "$2"
  fi
}

record_manifest() {  # $1 skill $2 version $3 root $4 mode — one line per (skill, root), latest wins
  [ "$DOCTOR" = "1" ] && return 0
  mkdir -p "$MANIFEST_DIR"
  local tmp
  tmp="$(mktemp "$MANIFEST_DIR/.installed.XXXXXX")"
  { [ -f "$MANIFEST" ] && grep -v "^$1	.*	$3	" "$MANIFEST" || true; } > "$tmp"
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$REPO" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$tmp"
  mv "$tmp" "$MANIFEST"
}

forget_manifest() {  # $1 skill $2 root
  [ "$DOCTOR" = "1" ] && return 0
  [ -f "$MANIFEST" ] || return 0
  local tmp
  tmp="$(mktemp "$MANIFEST_DIR/.installed.XXXXXX")"
  grep -v "^$1	.*	$2	" "$MANIFEST" > "$tmp" || true
  mv "$tmp" "$MANIFEST"
}

# ---- Discover skills --------------------------------------------------------

SKILLS=()
for d in "$REPO"/*/; do
  d="${d%/}"
  name="$(basename "$d")"
  [ -f "$d/SKILL.md" ] || continue
  if [ -n "$ONLY" ] && ! in_list "$name" "$ONLY"; then continue; fi
  if [ -n "$SKIP" ] && in_list "$name" "$SKIP"; then continue; fi
  SKILLS+=("$name")
done

if [ -n "$ONLY" ]; then
  IFS=',' read -r -a _want <<< "$ONLY"
  for w in "${_want[@]}"; do
    [ -f "$REPO/$w/SKILL.md" ] || { echo "ERROR: --only names '$w' but $REPO/$w/SKILL.md does not exist" >&2; exit 2; }
  done
fi

if [ "${#SKILLS[@]}" -eq 0 ]; then
  echo "ERROR: no skills found under $REPO (a skill is a folder with a SKILL.md)" >&2
  exit 1
fi

if [ "$LIST" = "1" ]; then
  printf '%-18s %-12s %s\n' "SKILL" "VERSION" "SOURCE"
  for s in "${SKILLS[@]}"; do
    v="$(skill_version "$REPO/$s")"
    printf '%-18s %-12s %s\n' "$s" "${v:-unversioned}" "$REPO/$s"
  done
  exit 0
fi

# ---- Select targets ---------------------------------------------------------

if [ -n "$EXPLICIT_DIR" ]; then
  TARGETS=("$EXPLICIT_DIR")
else
  TARGETS=()
  if [ -n "${CP_SKILLS_ROOTS:-}" ]; then
    IFS=':' read -r -a CANDIDATE_ROOTS <<< "$CP_SKILLS_ROOTS"
  fi
  for root in "${CANDIDATE_ROOTS[@]}" ${EXTRA_ROOTS[@]+"${EXTRA_ROOTS[@]}"}; do
    [ -n "$root" ] || continue
    parent="$(dirname "$root")"
    [ -d "$parent" ] && TARGETS+=("$root")
  done
  if [ "${#TARGETS[@]}" -eq 0 ]; then
    TARGETS=("$HOME/.claude/skills")
  fi
fi

# ---- Uninstall path ---------------------------------------------------------

if [ "$UNINSTALL" = "1" ]; then
  section "── cp-skills doctor ── uninstall (${#SKILLS[@]} skill(s), ${#TARGETS[@]} root(s))"
  for root in "${TARGETS[@]}"; do
    for skill in "${SKILLS[@]}"; do
      src="$REPO/$skill"
      dest="$root/$skill"
      if [ -L "$dest" ]; then
        rm -f "$dest"
        fixed "removed symlink $dest"
        forget_manifest "$skill" "$root"
      elif [ -d "$dest" ]; then
        if [ "$(resolve_path "$dest")" = "$src" ]; then
          fail "$dest IS this source checkout — refusing to delete it"
        elif [ -f "$dest/SKILL.md" ]; then
          rm -rf "$dest"
          fixed "removed copy install $dest"
          forget_manifest "$skill" "$root"
        else
          fail "$dest exists but is not a $skill install (no SKILL.md) — refusing to delete foreign content; remove it manually"
        fi
      elif [ -e "$dest" ]; then
        fail "$dest exists but is not a skill install — refusing to delete; remove it manually"
      else
        note "$skill not installed at $root"
      fi
    done
  done
  section "summary"
  if [ "${#CHANGES[@]}" -gt 0 ]; then
    for c in ${CHANGES[@]+"${CHANGES[@]}"}; do printf '    • %s\n' "$c"; done
  else
    printf '    nothing to remove.\n'
  fi
  [ "$FAILS" -eq 0 ] || { printf '  %sRESULT: %d item(s) need manual removal.%s\n' "$C_FAIL" "$FAILS" "$C_END"; exit 1; }
  printf '  %sRESULT: uninstall complete.%s\n' "$C_OK" "$C_END"
  exit 0
fi

# ---- Phase 1: source checkup (every skill) ----------------------------------

section "── cp-skills doctor ── source checkup ($REPO)"

SRC_VERSIONS=()   # parallel to SKILLS
PY_MIN="3.9"
for skill in "${SKILLS[@]}"; do
  src="$REPO/$skill"
  v="$(skill_version "$src")"
  if [ -z "$v" ]; then
    v="unversioned"
    warn "$skill: SKILL.md carries no parseable version — treating the source as unversioned"
  else
    ok "$skill: SKILL.md present — source version $v"
  fi
  SRC_VERSIONS+=("$v")

  pv="$(plugin_version "$src")"
  if [ -n "$pv" ] && [ "$pv" != "$v" ]; then
    warn "$skill: version drift in the source: plugin.json says $pv, SKILL.md says $v — align them"
  fi

  for d in prompts scripts; do
    if [ -d "$src/$d" ] && [ -z "$(ls -A "$src/$d" 2>/dev/null)" ]; then
      fail "$skill: $d/ exists but is empty — the skill cannot run; restore it from the repo"
    fi
  done

  # highest Python floor across the selected skills drives the dependency check
  m="$(skill_python_min "$src")"
  if [ "${m#3.}" -gt "${PY_MIN#3.}" ]; then PY_MIN="$m"; fi
done

# ---- Phase 2: dependency & tools checkup (once) -----------------------------

section "dependency & tools checkup"

if [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
  ok "✓ bash $BASH_VERSION"
else
  warn "✗ bash ${BASH_VERSION:-unknown} is old — 4.x+ recommended (the installer copes, but upgrade when you can)"
fi

MISSING_TOOLS=""
for t in sed grep stat mktemp ln cp dirname readlink; do
  command -v "$t" >/dev/null 2>&1 || MISSING_TOOLS="$MISSING_TOOLS $t"
done
if [ -z "$MISSING_TOOLS" ]; then
  ok "✓ core tools: sed grep stat mktemp ln cp dirname readlink"
else
  fail "✗ missing core tool(s):$MISSING_TOOLS — install coreutils (Debian/Ubuntu: 'sudo apt install coreutils'; macOS: 'brew install coreutils') and rerun"
fi

# Python: find the newest interpreter, then judge it against each skill's floor.
PY=""
PY_VER=""
for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  PY="$p"
  PY_VER="$("$p" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))' 2>/dev/null || true)"
  [ -n "$PY_VER" ] && break
done
if [ -z "$PY" ]; then
  fail "✗ Python not found — every skill needs it at run time. Install it (Debian/Ubuntu: 'sudo apt install python3'; macOS: 'brew install python3') and rerun"
else
  py_minor="$(printf '%s' "$PY_VER" | cut -d. -f2)"
  i=0
  for skill in "${SKILLS[@]}"; do
    m="$(skill_python_min "$REPO/$skill")"
    if [ "$py_minor" -ge "${m#3.}" ]; then
      ok "✓ $skill: python $PY_VER satisfies its $m+ floor (stdlib only)"
    else
      warn "✗ $skill: needs Python $m+ but only $PY_VER is on PATH — the skill installs, but will not run until you upgrade Python"
    fi
    i=$((i+1))
  done
fi

if command -v git >/dev/null 2>&1; then
  ok "✓ git $(git --version 2>/dev/null | sed 's/^git version //') — repo-root resolution available"
else
  warn "✗ git not found — the code-* skills fall back to the plan's own directory; install git for full repo-root behavior"
fi

# optional: gstack (powers --skill chaining into /review, /qa, /cso, /ship).
# Presence only here — install/upgrade and the contract re-sync are phases 2b/2c.
if [ -f "$GSTACK_DIR/VERSION" ]; then
  ok "✓ gstack $(head -n 1 "$GSTACK_DIR/VERSION" | tr -d '[:space:]') present at $GSTACK_DIR"
elif [ "$DO_GSTACK" = "1" ]; then
  note "◦ gstack not installed — phase 2b will install it (or skip with --no-gstack)"
else
  warn "◦ gstack not installed (optional) — skills run fine, but --skill chaining into /review, /qa, /cso, /ship is unavailable until gstack is installed"
fi

# self integrity: each skill's own test suite as a health probe
if [ -n "$PY" ]; then
  for skill in "${SKILLS[@]}"; do
    st="$REPO/$skill/scripts/selftest.py"
    [ -f "$st" ] || continue
    if "$PY" "$st" >/dev/null 2>&1; then
      ok "✓ $skill: selftest suite passes"
    else
      warn "✗ $skill: selftest reported failures — install continues, but run '$PY $st' for the details"
    fi
  done
fi

if [ "$FAILS" -gt 0 ] && [ "$DOCTOR" = "0" ]; then
  section "summary"
  printf '  %sRESULT: %d failure(s) above must be resolved before installing — nothing was changed.%s\n' "$C_FAIL" "$FAILS" "$C_END"
  exit 1
fi

# ---- Phase 2b: gstack install & upgrade -------------------------------------

GSTACK_VER=""          # version installed after this phase (empty = none)
gstack_version() { head -n 1 "$GSTACK_DIR/VERSION" 2>/dev/null | tr -d '[:space:]'; }

gstack_setup() {  # reruns gstack's own ./setup; $1 = label for the log line
  local log="$MANIFEST_DIR/gstack-setup.log"
  mkdir -p "$MANIFEST_DIR"
  if (cd "$GSTACK_DIR" && ./setup -q </dev/null) >"$log" 2>&1; then
    return 0
  fi
  fail "gstack ./setup failed after $1 — see $log (gstack itself is at $(gstack_version); its skills may be partially rendered until setup succeeds)"
  return 1
}

if [ "$DO_GSTACK" = "1" ]; then
  section "gstack install & upgrade ($GSTACK_DIR)"

  if [ ! -f "$GSTACK_DIR/VERSION" ]; then
    if [ -e "$GSTACK_DIR" ]; then
      fail "$GSTACK_DIR exists but is not a gstack checkout (no VERSION) — move it aside or pass --gstack-dir"
    elif ! command -v git >/dev/null 2>&1 || ! command -v bun >/dev/null 2>&1; then
      warn "◦ gstack needs git and bun (https://bun.sh) to install — install them and rerun, or use --no-gstack"
    elif [ "$DOCTOR" = "1" ]; then
      warn "◦ gstack not installed — an install run will clone $GSTACK_REPO_URL into $GSTACK_DIR and run ./setup"
    else
      note "cloning gstack…"
      if git clone --quiet --single-branch --depth 1 "$GSTACK_REPO_URL" "$GSTACK_DIR" 2>/dev/null; then
        if gstack_setup "fresh install"; then
          fixed "installed gstack $(gstack_version) at $GSTACK_DIR"
        fi
      else
        warn "✗ could not clone gstack (offline, or GitHub unreachable) — skipping; rerun when online"
      fi
    fi
  elif [ ! -d "$GSTACK_DIR/.git" ]; then
    ok "✓ gstack $(gstack_version) present (vendored copy, not a git checkout) — upgrade it with /gstack-upgrade; this installer only fast-forwards git checkouts"
  elif ! command -v git >/dev/null 2>&1; then
    warn "✗ gstack $(gstack_version) present but git is missing — cannot check for upgrades"
  else
    old_ver="$(gstack_version)"
    # Never fetch with --depth here: on the shallow clone gstack's README
    # prescribes, a depth-limited fetch records a second, disconnected shallow
    # root and git can no longer prove HEAD is an ancestor of origin/main —
    # the fast-forward is refused for a checkout that is perfectly clean. A
    # plain fetch connects the new commits to the existing shallow tip; if an
    # earlier tool already left a disconnected root behind, deepen to reconnect.
    if git -C "$GSTACK_DIR" fetch --quiet origin main 2>/dev/null; then
      local_head="$(git -C "$GSTACK_DIR" rev-parse HEAD 2>/dev/null || true)"
      remote_head="$(git -C "$GSTACK_DIR" rev-parse FETCH_HEAD 2>/dev/null || true)"
      remote_ver="$(git -C "$GSTACK_DIR" show FETCH_HEAD:VERSION 2>/dev/null | head -n 1 | tr -d '[:space:]' || true)"
      if [ -n "$local_head" ] && [ "$local_head" != "$remote_head" ] \
         && ! git -C "$GSTACK_DIR" merge-base --is-ancestor HEAD FETCH_HEAD 2>/dev/null; then
        git -C "$GSTACK_DIR" fetch --quiet --deepen=500 origin main 2>/dev/null || true
      fi
      if [ -n "$local_head" ] && [ "$local_head" = "$remote_head" ]; then
        ok "✓ gstack $old_ver is the latest on origin/main"
      elif [ "$DOCTOR" = "1" ]; then
        warn "gstack upgrade available: $old_ver → ${remote_ver:-?} — an install run will fast-forward and rerun ./setup"
      elif ! command -v bun >/dev/null 2>&1; then
        warn "✗ gstack upgrade available ($old_ver → ${remote_ver:-?}) but bun is missing — ./setup needs it; install bun (https://bun.sh) and rerun"
      else
        pre_commit="$local_head"
        if git -C "$GSTACK_DIR" pull --quiet --ff-only --autostash origin main >/dev/null 2>&1; then
          if gstack_setup "upgrading $old_ver → $(gstack_version)"; then
            fixed "upgraded gstack $old_ver → $(gstack_version) (setup rerun, migrations applied by setup)"
            # a browse daemon started before the upgrade keeps serving the old binary
            if [ -x "$GSTACK_DIR/browse/dist/browse" ]; then
              "$GSTACK_DIR/browse/dist/browse" stop >/dev/null 2>&1 && note "stopped the pre-upgrade browse daemon (next browse command starts the new binary)"
            fi
          else
            note "pre-upgrade commit was $pre_commit — gstack's /gstack-upgrade skill documents recovery; no reset was attempted"
          fi
        else
          dirty_n="$(git -C "$GSTACK_DIR" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
          fail "gstack checkout at $GSTACK_DIR cannot fast-forward to origin/main ($dirty_n dirty file(s); local commits or a rewritten upstream) — resolve with /gstack-upgrade, which gates the reset on what would be lost; no reset was attempted"
        fi
      fi
    else
      warn "◦ could not reach GitHub to check gstack for upgrades — keeping $old_ver"
    fi
  fi

  GSTACK_VER="$(gstack_version)"
else
  GSTACK_VER="$(gstack_version)"
fi

# ---- Phase 2c: gstack contract sync -----------------------------------------
#
# Deterministic facts read from the installed gstack, rendered into each
# code-* skill's prompts/gstack-contract.md. The skills' hand-written prompts
# treat that file as the live roster: "pick the installed expert that best
# suits the task", so new gstack experts become usable the moment this runs.

CONTRACT_FILE="prompts/gstack-contract.md"
CONTRACT_SKILLS=()
for skill in "${SKILLS[@]}"; do
  case "$skill" in code-*) CONTRACT_SKILLS+=("$skill") ;; esac
done

gs_frontmatter_desc() {  # $1 = SKILL.md; prints the frontmatter description, one line, trimmed
  awk 'NR==1 && $0!="---"{exit} NR>1 && $0=="---"{exit} NR>1' "$1" 2>/dev/null \
    | sed -n 's/^description:[[:space:]]*"\{0,1\}\(.*\)$/\1/p' | head -n 1 \
    | sed 's/"[[:space:]]*$//; s/[[:space:]]*$//' | cut -c1-180
}

gs_skill_names_in() {  # $1.. = files; prints the /skill names our roster tables and headings recommend
  grep -hE '^(\||##)' "$@" 2>/dev/null | grep -oE '`/[a-z][a-z0-9-]*`' | tr -d '`/' | sort -u
}

installed_anywhere() {  # $1 = skill name; true if any candidate skills root has it
  local r
  for r in "${CANDIDATE_ROOTS[@]}"; do [ -f "$r/$1/SKILL.md" ] && return 0; done
  return 1
}

render_contract() {  # prints the snapshot for the installed gstack
  local army="$GSTACK_DIR/review/sections/review-army.md" d name desc
  printf '# gstack hand-off contract — live snapshot\n\n'
  printf '<!-- GENERATED by cp-skills/install.sh (gstack contract sync). Do not edit by\n'
  printf '     hand: rerun ./install.sh from the cp-skills checkout to refresh. -->\n\n'
  printf 'verified_against: gstack %s\n\n' "$GSTACK_VER"
  printf 'This file is the authoritative list of what is installed. The hand-written\n'
  printf 'rosters and routing tables in the sibling prompt files are worked examples;\n'
  printf 'when they disagree with this file, this file wins. Choose the installed\n'
  printf 'expert that best suits the work at hand — including experts that were added\n'
  printf 'to gstack after those examples were written.\n\n'

  printf '## Installed gstack experts\n\n| Skill | What it does |\n|---|---|\n'
  for d in "$GSTACK_DIR"/*/; do
    d="${d%/}"; name="$(basename "$d")"
    [ -f "$d/SKILL.md" ] || continue
    case "$name" in node_modules|test|docs|scripts|lib|bin|hosts|patches|licenses|contrib|supabase|extension|agents|agents-digest|model-overlays|browser-skills|gstack|claude|codex|openclaw|design) continue ;; esac
    desc="$(gs_frontmatter_desc "$d/SKILL.md")"
    printf '| `/%s` | %s |\n' "$name" "${desc:-—}"
  done

  printf '\n## `/review` specialists\n\n'
  if [ -f "$army" ]; then
    printf 'Specialist checklists installed: '
    ls "$GSTACK_DIR/review/specialists"/*.md 2>/dev/null | sed 's|.*/||; s|\.md$||' | tr '\n' ' ' ; printf '\n'
    [ -f "$GSTACK_DIR/review/design-checklist.md" ] && printf 'Design specialist: checklist-driven (`review/design-checklist.md`).\n'
    printf 'Force flags: %s\n' "$(grep -m1 -F '**Force flags:**' "$army" | grep -oE -- '`--[a-z-]+`' | tr -d '`' | tr '\n' ' ')"
    printf 'Always-on threshold: %s\n' "$(grep -oE -m1 'every review with [0-9]+\+ changed lines' "$army" || echo 'not stated')"
    printf 'Small-diff skip: %s → all specialists skipped\n' "$(grep -oE -m1 'DIFF_LINES < [0-9]+' "$army" || echo 'not stated')"
    printf 'Security (backend scope): %s\n' "$(grep -m1 -F '**Security**' "$army" | grep -oE 'DIFF_LINES > [0-9]+' || echo 'not stated')"
    printf 'Simplification: %s (advisory only)\n' "$(grep -m1 -F '**Simplification**' "$army" | grep -oE 'DIFF_LINES > [0-9]+' || echo 'not installed')"
    printf 'Red team: %s\n' "$(grep -m1 -F '**Activation:**' "$army" | sed 's/^\*\*Activation:\*\*[[:space:]]*//' || echo 'not stated')"
    grep -q 'NEVER_GATE' "$army" && printf 'Adaptive gating: conditional specialists with 0 findings in 10+ dispatches are auto-gated off; NEVER_GATE specialists (security, data-migration) always run.\n'
  else
    printf 'review-army section not found in this gstack — specialist mechanics unknown.\n'
  fi

  printf '\n## `/autoplan` phase order\n\n'
  tr '\n' ' ' < "$GSTACK_DIR/autoplan/SKILL.md" 2>/dev/null | grep -oE 'Phases MUST execute in strict order: [^.]*\.' | head -n 1 || printf 'not stated\n'
  printf '\n\n## Plan-review scope gates\n\n'
  for name in plan-eng-review plan-design-review plan-ceo-review plan-devex-review autoplan; do
    if [ ! -f "$GSTACK_DIR/$name/SKILL.md" ]; then printf -- '- `/%s`: NOT INSTALLED\n' "$name"
    elif grep -q '^## Scope gate' "$GSTACK_DIR/$name/SKILL.md"; then printf -- '- `/%s`: scope gate (auto-resolves when the target is named in args or in plan mode)\n' "$name"
    elif grep -q 'Scope gate' "$GSTACK_DIR/$name/SKILL.md"; then printf -- '- `/%s`: no gate question — the plan under review is already the target\n' "$name"
    else printf -- '- `/%s`: no scope gate\n' "$name"; fi
  done

  printf '\n## Roster check\n\nEvery gstack skill named in the hand-written prompts, verified present:\n\n'
  local missing=0
  for name in $(gs_skill_names_in "$REPO"/code-*/prompts/gstack-experts.md "$REPO"/code-*/prompts/expert-lenses.md); do
    case "$name" in code-plan|code-execute|code-validation) continue ;; esac
    if [ -f "$GSTACK_DIR/$name/SKILL.md" ]; then printf -- '- `/%s` ✓\n' "$name"
    elif installed_anywhere "$name"; then printf -- '- `/%s` ✓ (not a gstack skill; installed separately)\n' "$name"
    else printf -- '- `/%s` ✗ MISSING from this gstack — do not recommend it\n' "$name"; missing=$((missing+1)); fi
  done
  [ "$missing" -eq 0 ] && printf '\nAll named skills present.\n'
  return 0
}

bump_patch() {  # $1 = skill dir; bumps SKILL.md + plugin.json patch version; prints new version
  local cur="$(skill_version "$1")" maj min pat new
  maj="${cur%%.*}"; pat="${cur##*.}"; min="${cur#*.}"; min="${min%.*}"
  new="$maj.$min.$((pat+1))"
  sed -i.bak "s/^version:[[:space:]]*\"\{0,1\}$cur\"\{0,1\}/version: \"$new\"/" "$1/SKILL.md" && rm -f "$1/SKILL.md.bak"
  [ -f "$1/plugin.json" ] && sed -i.bak "s/\"version\"[[:space:]]*:[[:space:]]*\"$cur\"/\"version\": \"$new\"/" "$1/plugin.json" && rm -f "$1/plugin.json.bak"
  printf '%s' "$new"
}

if [ "$DO_GSTACK" = "1" ] && [ "$DO_SYNC" = "1" ] && [ "${#CONTRACT_SKILLS[@]}" -gt 0 ]; then
  section "gstack contract sync"
  if [ -z "$GSTACK_VER" ]; then
    warn "◦ gstack not installed — contract snapshot left as is (skills fall back to their hand-written rosters)"
  else
    tmp_contract="$(mktemp)"
    sync_changes_before="${#CHANGES[@]}"
    render_contract > "$tmp_contract"
    missing_n="$(grep -c 'MISSING from this gstack' "$tmp_contract" || true)"
    if [ "$missing_n" -gt 0 ]; then
      warn "✗ $missing_n skill(s) named in the hand-written prompts are missing from gstack $GSTACK_VER — recorded in the snapshot; update the prompts"
    fi
    for skill in "${CONTRACT_SKILLS[@]}"; do
      src="$REPO/$skill"; dest="$src/$CONTRACT_FILE"; changed=0
      if [ -f "$dest" ] && cmp -s "$dest" "$tmp_contract"; then
        ok "$skill: contract snapshot current (gstack $GSTACK_VER)"
      else
        changed=1
        if [ "$DOCTOR" = "1" ]; then
          if [ -f "$dest" ]; then
            old_pin="$(sed -n 's/^verified_against: gstack //p' "$dest" | head -n 1)"
            warn "$skill: contract drift — snapshot verified against gstack ${old_pin:-?}, installed is $GSTACK_VER ($(diff "$dest" "$tmp_contract" 2>/dev/null | grep -c '^[<>]' || echo '?') line(s) differ); an install run will re-sync and bump the patch version"
          else
            warn "$skill: no contract snapshot yet — an install run will write $CONTRACT_FILE"
          fi
        else
          mkdir -p "$src/prompts"; cp "$tmp_contract" "$dest"
          fixed "$skill: wrote $CONTRACT_FILE (verified against gstack $GSTACK_VER)"
        fi
      fi
      # hand-written pins: "verified against gstack X" / "Verified against gstack X" / "verified X)"
      stale="$(grep -rhoE '[Vv]erified against gstack [0-9][0-9.]*' "$src/SKILL.md" "$src"/prompts/*.md 2>/dev/null | sed 's/.*gstack //' | grep -vx "$GSTACK_VER" | sort -u | tr '\n' ' ' || true)"
      if [ -n "$stale" ]; then
        if [ "$DOCTOR" = "1" ]; then
          warn "$skill: stale pin(s) → ${stale}— an install run will bump them to $GSTACK_VER"
        else
          for f in "$src/SKILL.md" "$src"/prompts/*.md; do
            [ "$f" = "$dest" ] && continue
            sed -i.bak -E "s/([Vv]erified against gstack )[0-9][0-9.]*/\1$GSTACK_VER/g; s/(verified )[0-9][0-9.]+\)/\1$GSTACK_VER)/g" "$f" && rm -f "$f.bak"
          done
          fixed "$skill: bumped hand-written pins to gstack $GSTACK_VER"
          changed=1
        fi
      fi
      if [ "$changed" = "1" ] && [ "$DOCTOR" = "0" ]; then
        old_v="$(skill_version "$src")"
        new_v="$(bump_patch "$src")"
        fixed "$skill: version $old_v → $new_v (gstack contract re-synced to $GSTACK_VER)"
      fi
    done
    rm -f "$tmp_contract"
    if [ "$DOCTOR" = "0" ] && [ "${#CHANGES[@]}" -gt "$sync_changes_before" ]; then
      note "source checkout updated — review with 'git diff' and commit"
    fi
  fi
  # versions may have moved: refresh the table phase 3 reports
  SRC_VERSIONS=()
  for skill in "${SKILLS[@]}"; do
    v="$(skill_version "$REPO/$skill")"; SRC_VERSIONS+=("${v:-unversioned}")
  done
fi

# ---- Phase 3: per-target checkup & self-heal --------------------------------

section "install targets ($MODE mode) — ${#TARGETS[@]} root(s)"

heal_root() {  # $1 = root; creates it (or reports) once per run
  local root="$1"
  if [ ! -d "$root" ]; then
    if [ "$DOCTOR" = "1" ]; then
      warn "$root does not exist — an install run will create it"
      return 1
    fi
    mkdir -p "$root"
    fixed "created skills root $root"
  fi
  return 0
}

heal_target() {  # $1 = root, $2 = skill name, $3 = source version
  local root="$1" skill="$2" ver="$3" src dest link_target resolved inst_v
  src="$REPO/$skill"
  dest="$root/$skill"

  if [ -L "$dest" ]; then
    link_target="$(readlink "$dest")"
    resolved="$(resolve_path "$dest")"
    if [ "$resolved" = "$src" ]; then
      if [ "$MODE" = "copy" ]; then
        if [ "$DOCTOR" = "1" ]; then
          note "$dest is a symlink; an install run with --copy will convert it to a copy"
        else
          rm -f "$dest"; cp -R "$src" "$dest"
          fixed "converted $dest from symlink to copy (v$ver)"
          record_manifest "$skill" "$ver" "$root" "copy"
        fi
      else
        ok "$dest → symlink tracks this checkout (v$ver) — up to date"
        record_manifest "$skill" "$ver" "$root" "symlink"
      fi
    elif [ -z "$resolved" ] || [ ! -e "$dest" ]; then
      if [ "$DOCTOR" = "1" ]; then
        warn "$dest is a BROKEN symlink (→ $link_target) — an install run will repair it"
      else
        rm -f "$dest"; install_into "$src" "$dest"
        fixed "repaired broken symlink $dest (was → $link_target; now v$ver, $MODE)"
        record_manifest "$skill" "$ver" "$root" "$MODE"
      fi
    else
      if [ "$DOCTOR" = "1" ]; then
        warn "$dest points at a DIFFERENT checkout ($link_target) — an install run will repoint it here"
      else
        rm -f "$dest"; install_into "$src" "$dest"
        fixed "repointed $dest (was → $link_target; now v$ver, $MODE)"
        record_manifest "$skill" "$ver" "$root" "$MODE"
      fi
    fi
    return 0
  fi

  if [ -d "$dest" ]; then
    if [ "$(resolve_path "$dest")" = "$src" ]; then
      fail "$dest IS this source checkout — refusing to touch it (pick another --dir)"
      return 0
    fi
    if [ ! -f "$dest/SKILL.md" ]; then
      fail "$dest exists but is not a $skill install (no SKILL.md) — refusing to overwrite foreign content; remove it manually and rerun"
      return 0
    fi
    inst_v="$(skill_version "$dest")"
    [ -n "$inst_v" ] || inst_v="unknown"
    if [ "$DOCTOR" = "1" ]; then
      if [ "$inst_v" = "$ver" ]; then
        note "$dest is a copy install at v$inst_v (current); an install run will refresh it as a $MODE"
      else
        warn "$dest is a copy install at v$inst_v — OUT OF DATE (source is v$ver); an install run will upgrade it"
      fi
      return 0
    fi
    rm -rf "$dest"; install_into "$src" "$dest"
    if [ "$inst_v" = "$ver" ]; then
      fixed "refreshed $dest at v$ver ($MODE)"
    else
      fixed "upgraded $dest: v$inst_v → v$ver ($MODE)"
    fi
    record_manifest "$skill" "$ver" "$root" "$MODE"
    return 0
  fi

  if [ -e "$dest" ]; then
    fail "$dest exists but is not a skill install — refusing to overwrite; remove it manually and rerun"
    return 0
  fi

  if [ "$DOCTOR" = "1" ]; then
    warn "$skill not installed at $root — an install run will add v$ver ($MODE)"
  else
    install_into "$src" "$dest"
    fixed "installed $dest (v$ver, $MODE)"
    record_manifest "$skill" "$ver" "$root" "$MODE"
  fi
}

# Skill-specific first-run steps that the per-skill installers perform beyond
# linking. Runs once per skill (not per root), never in --doctor mode.
post_install() {  # $1 = skill name
  case "$1" in
    stock-eval)
      local env_dir="$HOME/.config/stock-eval" env_file
      env_file="$env_dir/.env"
      if [ ! -f "$env_file" ]; then
        mkdir -p "$env_dir"
        printf 'SETUP_COMPLETE=true\n' > "$env_file"
        chmod 600 "$env_file"
        fixed "wrote first-run config $env_file (chmod 600)"
      elif [ "$(stat -c '%a' "$env_file" 2>/dev/null || stat -f '%Lp' "$env_file" 2>/dev/null)" != "600" ]; then
        chmod 600 "$env_file"
        fixed "tightened $env_file permissions to 600"
      fi
      ;;
  esac
}

for root in "${TARGETS[@]}"; do
  printf '\n  %s%s%s\n' "$C_DIM" "$root" "$C_END"
  heal_root "$root" || continue
  i=0
  for skill in "${SKILLS[@]}"; do
    heal_target "$root" "$skill" "${SRC_VERSIONS[$i]}"
    i=$((i+1))
  done
done

if [ "$DOCTOR" = "0" ]; then
  section "first-run configuration"
  before="${#CHANGES[@]}"
  for skill in "${SKILLS[@]}"; do post_install "$skill"; done
  [ "${#CHANGES[@]}" -gt "$before" ] || note "nothing to configure — existing config left untouched"
fi

# ---- Phase 4: summary -------------------------------------------------------

section "summary"

printf '  %-18s %-12s %s\n' "SKILL" "VERSION" "INVOKE"
i=0
for skill in "${SKILLS[@]}"; do
  printf '  %-18s %-12s /%s\n' "$skill" "${SRC_VERSIONS[$i]}" "$skill"
  i=$((i+1))
done
printf '\n'

if [ "${#CHANGES[@]}" -gt 0 ]; then
  printf '  %d change(s) made:\n' "${#CHANGES[@]}"
  for c in ${CHANGES[@]+"${CHANGES[@]}"}; do
    printf '    • %s\n' "$c"
  done
else
  if [ "$DOCTOR" = "1" ]; then
    printf '    no changes made (checkup only).\n'
  else
    printf '    no changes were needed — every install is already current.\n'
  fi
fi
[ "$WARNS" -gt 0 ] && printf '  %d warning(s) above.\n' "$WARNS"
[ "$DOCTOR" = "1" ] || printf '  manifest: %s\n' "$MANIFEST"

if [ "$FAILS" -gt 0 ]; then
  printf '  %sRESULT: attention required — %d failure(s) above need a manual fix.%s\n' "$C_FAIL" "$FAILS" "$C_END"
  exit 1
elif [ "$DOCTOR" = "1" ]; then
  if [ "$WARNS" -gt 0 ]; then
    printf '  %sRESULT: checkup complete — run ./install.sh to apply the pending fixes.%s\n' "$C_WARN" "$C_END"
  else
    printf '  %sRESULT: healthy — %d skill(s) current in %d root(s), nothing to do.%s\n' "$C_OK" "${#SKILLS[@]}" "${#TARGETS[@]}" "$C_END"
  fi
else
  printf '  %sRESULT: healthy — %d skill(s) ready in %d root(s).%s\n' "$C_OK" "${#SKILLS[@]}" "${#TARGETS[@]}" "$C_END"
fi
