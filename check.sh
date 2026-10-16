#!/usr/bin/env bash
# DevFoundry lab validation check (D3). Runs from the repository root.
set -euo pipefail
test -f README.md
if [ -e hello.txt ]; then
  [ "$(tr -d '[:space:]' < hello.txt | tr '[:upper:]' '[:lower:]')" = "hello" ]
fi
echo "lab checks passed"
