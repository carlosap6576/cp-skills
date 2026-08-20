#!/usr/bin/env bash
# code-validation installer & doctor — makes the skill discoverable by Claude
# Code, Hermes, and other SKILL.md-aware agents. Runs like a doctor CLI:
# every check prints a verdict, every problem it can safely fix is fixed on
# the spot, and the summary states exactly what was repaired and which
# version was installed or upgraded.
#
#   ./install.sh                        # install/upgrade everywhere + full checkup
#   ./install.sh --doctor               # checkup only: diagnose, change nothing
#   ./install.sh --copy                 # copy instead of symlink
#   ./install.sh --dir DIR              # operate on DIR/code-validation only
#   ./install.sh --uninstall            # remove from every candidate root
#   ./install.sh --dir DIR --uninstall  # remove from DIR/code-validation only
set -euo pipefail

SKILL_NAME="code-validation"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="symlink"
UNINSTALL=0
DOCTOR=0
EXPLICIT_DIR=""

CANDIDATE_ROOTS=(
  "$HOME/.claude/skills"
  "$HOME/.hermes/skills"
  "$HOME/.config/hermes/skills"
  "$HOME/.openclaw/skills"
)

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE="copy"; shift ;;
    --dir)
      [ $# -ge 2 ] || { echo "ERROR: --dir needs a directory argument" >&2; exit 2; }
      EXPLICIT_DIR="$2"; shift 2 ;;
    --doctor) DOCTOR=1; shift ;;
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

resolve_path() {  # canonical absolute path; echoes nothing if unresolvable
  if command -v realpath >/dev/null 2>&1; then
    realpath "$1" 2>/dev/null || true
  else
    (cd "$1" 2>/dev/null && pwd) || true
  fi
}

install_into() {  # $1 = dest path; assumes dest does not exist
  if [ "$MODE" = "symlink" ]; then
    ln -s "$SRC" "$1"
  else
    cp -R "$SRC" "$1"
  fi
}

# ---- Select targets ---------------------------------------------------------

if [ -n "$EXPLICIT_DIR" ]; then
  TARGETS=("$EXPLICIT_DIR")
else
  TARGETS=()
  for root in "${CANDIDATE_ROOTS[@]}"; do
    parent="$(dirname "$root")"
    [ -d "$parent" ] && TARGETS+=("$root")
  done
  if [ "${#TARGETS[@]}" -eq 0 ]; then
    TARGETS=("$HOME/.claude/skills")
  fi
fi

SRC_VERSION="$(skill_version "$SRC")"
[ -n "$SRC_VERSION" ] || SRC_VERSION="unversioned"

# ---- Uninstall path ---------------------------------------------------------

if [ "$UNINSTALL" = "1" ]; then
  section "── $SKILL_NAME doctor ── uninstall"
  for root in "${TARGETS[@]}"; do
    dest="$root/$SKILL_NAME"
    if [ -L "$dest" ]; then
      rm -f "$dest"
      fixed "removed symlink $dest"
    elif [ -d "$dest" ]; then
      if [ "$(resolve_path "$dest")" = "$SRC" ]; then
        fail "$dest IS this source checkout — refusing to delete it"
      elif [ -f "$dest/SKILL.md" ]; then
        rm -rf "$dest"
        fixed "removed copy install $dest"
      else
        fail "$dest exists but is not a $SKILL_NAME install (no SKILL.md) — refusing to delete foreign content; remove it manually"
      fi
    elif [ -e "$dest" ]; then
      fail "$dest exists but is not a skill install — refusing to delete; remove it manually"
    else
      note "not installed at $root"
    fi
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

# ---- Phase 1: source checkup ------------------------------------------------

section "── $SKILL_NAME doctor ── source checkup ($SRC)"

if [ -f "$SRC/SKILL.md" ]; then
  if [ "$SRC_VERSION" = "unversioned" ]; then
    warn "SKILL.md carries no parseable version — treating the source as unversioned"
  else
    ok "SKILL.md present — source version $SRC_VERSION"
  fi
else
  fail "SKILL.md missing — this checkout is broken; restore it from the repo before installing"
fi

for d in prompts scripts; do
  if [ -d "$SRC/$d" ] && [ -n "$(ls -A "$SRC/$d" 2>/dev/null)" ]; then
    ok "$d/ present"
  else
    fail "$d/ missing or empty — the skill cannot run; restore it from the repo"
  fi
done

PLUGIN_VERSION="$(plugin_version "$SRC")"
if [ -n "$PLUGIN_VERSION" ]; then
  if [ "$PLUGIN_VERSION" = "$SRC_VERSION" ]; then
    ok "plugin.json version matches SKILL.md ($PLUGIN_VERSION)"
  else
    warn "version drift in the source: plugin.json says $PLUGIN_VERSION, SKILL.md says $SRC_VERSION — align them"
  fi
fi

# ---- Phase 2: dependency & tools checkup ------------------------------------

section "dependency & tools checkup"

# -- required: bash
if [ "${BASH_VERSINFO[0]:-0}" -ge 4 ]; then
  ok "✓ bash $BASH_VERSION"
else
  warn "✗ bash ${BASH_VERSION:-unknown} is old — 4.x+ recommended (the installer copes, but upgrade when you can)"
fi

# -- required: core tools (coreutils + friends the skill contract shells out to)
MISSING_TOOLS=""
for t in sed grep stat mktemp ln cp dirname readlink; do
  command -v "$t" >/dev/null 2>&1 || MISSING_TOOLS="$MISSING_TOOLS $t"
done
if [ -z "$MISSING_TOOLS" ]; then
  ok "✓ core tools: sed grep stat mktemp ln cp dirname readlink"
else
  fail "✗ missing core tool(s):$MISSING_TOOLS — install coreutils (Debian/Ubuntu: 'sudo apt install coreutils'; macOS: 'brew install coreutils') and rerun"
fi

# -- required: Python 3.9+ (stdlib only — no pip packages needed)
PY=""
for p in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  if "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$p"; break
  fi
done
if [ -n "$PY" ]; then
  ok "✓ python: $PY ($("$PY" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')) — 3.9+ required, stdlib only"
else
  fail "✗ Python 3.9+ not found — the skill needs it at run time. Install it (Debian/Ubuntu: 'sudo apt install python3'; macOS: 'brew install python3') and rerun"
fi

# -- recommended: git (repo-root resolution; degrades to the plan's directory)
if command -v git >/dev/null 2>&1; then
  ok "✓ git $(git --version 2>/dev/null | sed 's/^git version //') — repo-root resolution available"
else
  warn "✗ git not found — EXEC_ROOT falls back to the plan's own directory; install git for full repo-root behavior"
fi

# -- optional: gstack (powers --skill chaining into /review, /qa, /cso, /ship)
GSTACK_VER=""
for vf in "$HOME/.claude/skills/gstack/VERSION" "$HOME/.gstack/VERSION"; do
  if [ -f "$vf" ]; then
    GSTACK_VER="$(head -n 1 "$vf" | tr -d '[:space:]')"
    [ -n "$GSTACK_VER" ] && break
  fi
done
if [ -n "$GSTACK_VER" ]; then
  ok "✓ gstack $GSTACK_VER installed — --skill chaining (/review /qa /cso /ship) available"
  # pin cross-check: the highest gstack version this skill's docs were verified
  # against; a drifted install can silently invalidate the hand-off contract
  # `|| true` is load-bearing: with pipefail, a docs set with no version
  # reference would otherwise abort the whole checkup via set -e
  GSTACK_PIN="$(grep -rhoE 'gstack [0-9]+\.[0-9]+(\.[0-9]+)*' "$SRC/SKILL.md" "$SRC"/prompts/*.md 2>/dev/null \
    | sort -V | tail -n 1 | sed 's/^gstack //' || true)"
  if [ -n "$GSTACK_PIN" ]; then
    pin_mm="$(printf '%s' "$GSTACK_PIN" | cut -d. -f1-2)"
    inst_mm="$(printf '%s' "$GSTACK_VER" | cut -d. -f1-2)"
    if [ "$pin_mm" = "$inst_mm" ]; then
      ok "✓ gstack contract pin ($GSTACK_PIN) matches the installed line ($inst_mm.x)"
    else
      warn "✗ this skill was verified against gstack $GSTACK_PIN but $GSTACK_VER is installed — the hand-off contract may have drifted; run the gstack re-sync procedure and bump the pins"
    fi
  fi
else
  warn "◦ gstack not installed (optional) — the skill runs fine, but --skill chaining into /review, /qa, /cso, /ship will be unavailable until gstack is installed"
fi

# -- self integrity: the skill's own test suite as a health probe
if [ -n "$PY" ] && [ -f "$SRC/scripts/selftest.py" ]; then
  if "$PY" "$SRC/scripts/selftest.py" >/dev/null 2>&1; then
    ok "✓ selftest suite passes"
  else
    warn "✗ selftest reported failures — install continues, but run '$PY scripts/selftest.py' from $SRC for the details"
  fi
fi

if [ "$FAILS" -gt 0 ] && [ "$DOCTOR" = "0" ]; then
  section "summary"
  printf '  %sRESULT: %d failure(s) above must be resolved before installing — nothing was changed.%s\n' "$C_FAIL" "$FAILS" "$C_END"
  exit 1
fi

# ---- Phase 3: per-target checkup & self-heal --------------------------------

section "install targets ($MODE mode)"

heal_target() {
  local root="$1" dest link_target resolved inst_v
  dest="$root/$SKILL_NAME"

  if [ ! -d "$root" ]; then
    if [ "$DOCTOR" = "1" ]; then
      warn "$root does not exist — an install run will create it"
      return 0
    fi
    mkdir -p "$root"
    fixed "created skills root $root"
  fi

  if [ -L "$dest" ]; then
    link_target="$(readlink "$dest")"
    resolved="$(resolve_path "$dest")"
    if [ "$resolved" = "$SRC" ]; then
      if [ "$MODE" = "copy" ]; then
        if [ "$DOCTOR" = "1" ]; then
          note "$dest is a symlink; an install run with --copy will convert it to a copy"
        else
          rm -f "$dest"; cp -R "$SRC" "$dest"
          fixed "converted $dest from symlink to copy (v$SRC_VERSION)"
        fi
      else
        ok "$dest → symlink tracks this checkout (v$SRC_VERSION) — up to date"
      fi
    elif [ -z "$resolved" ] || [ ! -e "$dest" ]; then
      if [ "$DOCTOR" = "1" ]; then
        warn "$dest is a BROKEN symlink (→ $link_target) — an install run will repair it"
      else
        rm -f "$dest"; install_into "$dest"
        fixed "repaired broken symlink $dest (was → $link_target; now v$SRC_VERSION, $MODE)"
      fi
    else
      if [ "$DOCTOR" = "1" ]; then
        warn "$dest points at a DIFFERENT checkout ($link_target) — an install run will repoint it here"
      else
        rm -f "$dest"; install_into "$dest"
        fixed "repointed $dest (was → $link_target; now v$SRC_VERSION, $MODE)"
      fi
    fi
    return 0
  fi

  if [ -d "$dest" ]; then
    if [ "$(resolve_path "$dest")" = "$SRC" ]; then
      fail "$dest IS this source checkout — refusing to touch it (pick another --dir)"
      return 0
    fi
    if [ ! -f "$dest/SKILL.md" ]; then
      fail "$dest exists but is not a $SKILL_NAME install (no SKILL.md) — refusing to overwrite foreign content; remove it manually and rerun"
      return 0
    fi
    inst_v="$(skill_version "$dest")"
    [ -n "$inst_v" ] || inst_v="unknown"
    if [ "$DOCTOR" = "1" ]; then
      if [ "$inst_v" = "$SRC_VERSION" ]; then
        note "$dest is a copy install at v$inst_v (current); an install run will refresh it as a $MODE"
      else
        warn "$dest is a copy install at v$inst_v — OUT OF DATE (source is v$SRC_VERSION); an install run will upgrade it"
      fi
      return 0
    fi
    rm -rf "$dest"; install_into "$dest"
    if [ "$inst_v" = "$SRC_VERSION" ]; then
      fixed "refreshed $dest at v$SRC_VERSION ($MODE)"
    else
      fixed "upgraded $dest: v$inst_v → v$SRC_VERSION ($MODE)"
    fi
    return 0
  fi

  if [ -e "$dest" ]; then
    fail "$dest exists but is not a skill install — refusing to overwrite; remove it manually and rerun"
    return 0
  fi

  if [ "$DOCTOR" = "1" ]; then
    warn "not installed at $root — an install run will add v$SRC_VERSION ($MODE)"
  else
    install_into "$dest"
    fixed "installed $dest (v$SRC_VERSION, $MODE)"
  fi
}

# The three skills form one lifecycle (plan → execute → validate); a root
# missing a sibling gets it installed from the checkout sitting next to this
# one. Existing sibling installs are never touched — upgrading those is the
# sibling's own installer's job.
LIFECYCLE_SKILLS="code-plan code-execute code-validation"

heal_siblings() {
  local root="$1" sib sib_src sib_dest sib_v present=""
  for sib in $LIFECYCLE_SKILLS; do
    [ "$sib" = "$SKILL_NAME" ] && continue
    sib_dest="$root/$sib"
    if [ -e "$sib_dest" ] || [ -L "$sib_dest" ]; then
      present="$present /$sib"
      continue
    fi
    sib_src="$(dirname "$SRC")/$sib"
    if [ -f "$sib_src/SKILL.md" ]; then
      if [ "$DOCTOR" = "1" ]; then
        warn "◦ lifecycle sibling /$sib is not installed at $root — an install run will add it from $sib_src"
      else
        sib_v="$(skill_version "$sib_src")"
        [ -n "$sib_v" ] || sib_v="unversioned"
        if [ "$MODE" = "symlink" ]; then
          ln -s "$sib_src" "$sib_dest"
        else
          cp -R "$sib_src" "$sib_dest"
        fi
        fixed "installed lifecycle sibling $sib_dest (v$sib_v, $MODE)"
      fi
    else
      warn "◦ lifecycle sibling /$sib is not installed at $root and no checkout sits next to this one — install it separately for the full plan → execute → validate flow"
    fi
  done
  [ -n "$present" ] && ok "✓ lifecycle sibling(s) present at $root:$present"
  return 0
}

for root in "${TARGETS[@]}"; do
  heal_target "$root"
  if [ -d "$root" ]; then
    heal_siblings "$root"
  fi
done

# ---- Phase 4: summary -------------------------------------------------------

section "summary"

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

if [ "$FAILS" -gt 0 ]; then
  printf '  %sRESULT: attention required — %d failure(s) above need a manual fix.%s\n' "$C_FAIL" "$FAILS" "$C_END"
  exit 1
elif [ "$DOCTOR" = "1" ]; then
  if [ "$WARNS" -gt 0 ]; then
    printf '  %sRESULT: checkup complete — run ./install.sh to apply the pending fixes.%s\n' "$C_WARN" "$C_END"
  else
    printf '  %sRESULT: healthy — %s v%s, nothing to do.%s\n' "$C_OK" "$SKILL_NAME" "$SRC_VERSION" "$C_END"
  fi
else
  printf '  %sRESULT: healthy — %s v%s ready. Invoke with: /%s%s\n' "$C_OK" "$SKILL_NAME" "$SRC_VERSION" "$SKILL_NAME" "$C_END"
fi
