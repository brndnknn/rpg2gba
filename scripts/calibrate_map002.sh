#!/usr/bin/env bash
# Calibration re-run for Map002 under the current prompt + Opus.
# Run this, then bring the output back for the §9 #2 gate review.
#
# What it does:
#   1. Restores flag_state.json from the pristine baseline snapshot
#   2. Removes stale memo_manifest.json and unhandled.jsonl from the
#      confirmation runs (Map100/115) so this run starts clean
#   3. Clears the Map100/Map115 checkpoints (they're from the confirmation
#      run, not a real conversion; Map002 has no checkpoint to clear)
#   4. Runs: convert-map --map-id 2 --model claude-opus-4-8
#
# Expected outcome:
#   output/uranium-build/scripts/Map002.pory  — compiled through poryscript (rc 0)
#   output/uranium-build/unhandled.jsonl      — queued items (expect ~5)
#   output/uranium-build/flag_state.json      — updated with minted flags/vars
#   stdout                                    — per-event log lines

set -euo pipefail

OUT="output/uranium-build"

echo "==> Restoring baseline flag state..."
cp "$OUT/flag_state.baseline.json" "$OUT/flag_state.json"

echo "==> Clearing stale memo manifest..."
rm -f "$OUT/memo_manifest.json"

echo "==> Clearing stale unhandled log..."
rm -f "$OUT/unhandled.jsonl"

echo "==> Clearing confirmation-run checkpoints..."
rm -f "$OUT/checkpoints/Map100.done"
rm -f "$OUT/checkpoints/Map115.done"

echo "==> Running Map002 conversion (Opus, spends budget)..."
python -m rpg2gba.pipeline convert-map --map-id 2 --model claude-opus-4-8

echo ""
echo "==> Done. Bring back the following for gate review:"
echo "    cat $OUT/scripts/Map002.pory"
echo "    cat $OUT/unhandled.jsonl"
echo "    cat $OUT/flag_state.json"
