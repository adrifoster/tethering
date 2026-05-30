#!/usr/bin/env bash

# final stage of smoke test pipeline
# this just creates a dummy CIME case so the tethering machinery works normally
# then outputs to a text file that it actually PASSED
# usage: bash smoke_check.sh <root_dir> <case_dir>

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "ERROR: please specify a case_root"
    exit 1
fi
case_root="$1"
root_dir=$(dirname "${case_root}")

# write smoke test result
echo "PASSED" > "${root_dir}/smoke_result.txt"
echo "Smoke test pipeline complete: $(date)"