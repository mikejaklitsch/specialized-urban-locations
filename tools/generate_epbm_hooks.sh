#!/usr/bin/env bash
# Wrapper: generate EPBM building maintenance hooks for SUL mod.
# Pre-fills --prefix, --vanilla, --mod, --output, --exclude for this mod.
#
# Usage:
#   ./tools/generate_epbm_hooks.sh         # generate hooks (in-place for mod, INJECT/REPLACE for vanilla)
#   ./tools/generate_epbm_hooks.sh --strip # strip all hooks from mod building files
#
# Extra args are forwarded to generate_building_hooks.py.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VANILLA="/mnt/d/Program Files (x86)/Steam/steamapps/common/Europa Universalis V/game/in_game"

exec python3 "$SCRIPT_DIR/generate_building_hooks.py" \
    --prefix sul_epbm \
    --vanilla "$VANILLA" \
    --mod "$MOD_ROOT/in_game" \
    --output "$MOD_ROOT" \
    --exclude "$SCRIPT_DIR/exclusions.txt" \
    "$@"
