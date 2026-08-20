#!/usr/bin/env bash
# stock-eval installer — makes the skill discoverable by Claude Code and other
# SKILL.md-aware agents. Default: symlink into ~/.claude/skills/stock-eval.
#
#   ./install.sh            # symlink into ~/.claude/skills (default)
#   ./install.sh --copy     # copy instead of symlink
#   ./install.sh --dir DIR  # install into DIR/stock-eval instead of ~/.claude/skills
#   ./install.sh --uninstall
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST_ROOT="$HOME/.claude/skills"
MODE="symlink"
UNINSTALL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --copy) MODE="copy"; shift ;;
    --dir) DEST_ROOT="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

DEST="$DEST_ROOT/stock-eval"

if [ "$UNINSTALL" = "1" ]; then
  rm -rf "$DEST"
  echo "removed $DEST"
  exit 0
fi

# Verify a Python 3.12+ interpreter is reachable (engine requirement).
PY=""
for p in python3.14 python3.13 python3.12 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)' 2>/dev/null && { PY="$p"; break; }
done
if [ -z "$PY" ]; then
  echo "WARNING: no Python 3.12+ found on PATH. The skill needs Python 3.12+ to run." >&2
fi

mkdir -p "$DEST_ROOT"
rm -rf "$DEST"

if [ "$MODE" = "symlink" ]; then
  ln -s "$SRC" "$DEST"
  echo "symlinked $DEST -> $SRC"
else
  cp -R "$SRC" "$DEST"
  echo "copied $SRC -> $DEST"
fi

# First-run env (zero keys needed for the core sources).
mkdir -p "$HOME/.config/stock-eval"
ENV_FILE="$HOME/.config/stock-eval/.env"
if [ ! -f "$ENV_FILE" ]; then
  printf 'SETUP_COMPLETE=true\n' > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "wrote $ENV_FILE"
fi

echo "done. Invoke with: /stock-eval META"
