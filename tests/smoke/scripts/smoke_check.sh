#!/usr/bin/env bash

# final stage of smoke test pipeline
# just outputs to a text file that it actually PASSED

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "ERROR: please specify a case_root"
    exit 1
fi
case_root="$1"
root_dir=$(dirname "${case_root}")

# mkdir ${case_root}

# write smoke test result
echo "PASSED" > "${root_dir}/smoke_result.txt"
echo "Smoke test pipeline complete: $(date)"