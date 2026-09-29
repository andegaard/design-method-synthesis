#!/bin/bash
set -euo pipefail

SCRIPT=""
for p in "/app/solution/solve.py" "/solution/solve.py" "solution/solve.py" "solve.py"; do
  if [ -f "$p" ]; then
    SCRIPT="$p"
    break
  fi
done

if [ -z "$SCRIPT" ]; then
  echo "Error: solve.py not found" >&2
  exit 1
fi

python3 "$SCRIPT"
