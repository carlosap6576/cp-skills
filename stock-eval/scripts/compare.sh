#!/bin/bash
# A/B test runner: public release vs private beta
# Usage: bash skills/stock-eval/scripts/compare.sh "Kanye West"
#
# Runs /stock-eval (public release) and /stock-eval-beta (private beta)
# sequentially with a 30s gap, saves raw results with distinct suffixes,
# prints file paths for comparison.

set -e

if [ $# -eq 0 ]; then
  echo "Usage: bash skills/stock-eval/scripts/compare.sh <topic>"
  echo "  Example: bash skills/stock-eval/scripts/compare.sh Kevin Rose"
  exit 1
fi
TOPIC="$*"
SLUG=$(echo "$TOPIC" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/--*/-/g' | sed 's/^-//' | sed 's/-$//')
STOCK_EVAL_MEMORY_DIR="${STOCK_EVAL_MEMORY_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/outputs}"
DIR="$STOCK_EVAL_MEMORY_DIR"
DATE=$(date +%Y-%m-%d)

echo "=============================================="
echo " A/B Test: $TOPIC"
echo " Date: $DATE"
echo "=============================================="
echo ""

# Run 1: public release
echo "[1/2] Running /stock-eval (public release)..."
echo "  This takes 2-4 minutes..."
claude -p --dangerously-skip-permissions "/stock-eval $TOPIC" > /dev/null 2>&1 || true
RELEASE_FILE="$DIR/${SLUG}-raw.md"
[ -f "$RELEASE_FILE" ] && echo "  Done: $RELEASE_FILE" || echo "  FAILED: no output file"
echo ""

echo "  Waiting 30s for API rate limits..."
sleep 30

# Run 2: private beta
echo "[2/2] Running /stock-eval-beta (private beta)..."
echo "  This takes 2-4 minutes..."
claude -p --dangerously-skip-permissions "/stock-eval-beta $TOPIC" > /dev/null 2>&1 || true
BETA_FILE="$DIR/${SLUG}-raw-beta.md"
[ -f "$BETA_FILE" ] && echo "  Done: $BETA_FILE" || echo "  FAILED: no output file"
echo ""

echo "=============================================="
echo " Both complete. Raw files:"
echo "=============================================="
echo ""
ls -la "$DIR/${SLUG}-raw"*.md 2>/dev/null || echo "  (no files found - check if skills saved correctly)"
echo ""
echo "To compare, run in Claude Code:"
echo "  Read and compare these raw research files, produce a detailed report:"
echo "  $RELEASE_FILE"
echo "  $BETA_FILE"
echo ""
echo "Beta output should start with a line like:"
echo "  🧪 stock-eval-beta · branch <name> · synced $DATE"
echo "If that line is missing, the beta badge regressed. See docs/plans/2026-04-17-005-*-plan.md."
echo ""
