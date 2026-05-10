#!/usr/bin/env bash
# Run all Phase 0 reconnaissance scripts in order.
# Set RPG2GBA_URANIUM_SRC before running.
#
# Usage:
#   export RPG2GBA_URANIUM_SRC=/path/to/uranium
#   bash scripts/phase0_run_all.sh

set -euo pipefail

if [[ -z "${RPG2GBA_URANIUM_SRC:-}" ]]; then
  echo "Error: RPG2GBA_URANIUM_SRC is not set" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV_PYTHON=".venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Error: venv not found. Run: python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
  exit 1
fi

echo "=== Phase 0 Reconnaissance ==="
echo "Uranium source: $RPG2GBA_URANIUM_SRC"
echo ""

echo "[0.1] Directory structure..."
"$VENV_PYTHON" scripts/recon_structure.py

echo "[0.2] PBS inventory..."
"$VENV_PYTHON" scripts/recon_pbs.py

echo "[0.3] Map inventory..."
ruby scripts/recon_maps.rb

echo "[0.4] Scripts dump (custom mechanic survey)..."
ruby scripts/recon_scripts.rb

echo "[0.5] Asset inventory..."
"$VENV_PYTHON" scripts/recon_assets.py

echo ""
echo "Done. Review reference/ for output:"
ls reference/*.md 2>/dev/null | sed 's/^/  /'
