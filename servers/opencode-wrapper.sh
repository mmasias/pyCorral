#!/usr/bin/env bash
set -euo pipefail

export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
[ -s "$NVM_DIR/nvm.sh" ] && source "$NVM_DIR/nvm.sh"

MODEL="${CORRAL_OPENCODE_MODEL:-opencode/deepseek-v4-flash-free}"

PROMPT="$(cat "$1")"
rm -f "$1"

opencode --log-level ERROR -m "$MODEL" run "$PROMPT"
