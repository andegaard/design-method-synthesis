#!/bin/bash
set -uo pipefail

mkdir -p /logs/verifier
cd /logs/verifier

pytest /tests/test_outputs.py --no-header -q \
  --ctrf /logs/verifier/ctrf.json \
  > /logs/verifier/test-console-output.txt 2>&1
rc=$?

if [ "$rc" -eq 0 ]; then
  printf '1\n' > /logs/verifier/reward.txt
else
  printf '0\n' > /logs/verifier/reward.txt
fi

exit 0
