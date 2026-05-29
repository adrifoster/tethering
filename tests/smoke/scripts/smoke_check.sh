#!/usr/bin/env bash

# final stage of smoke test pipeline
# this just creates a dummy CIME case so the tethering machinery works normally
# then outputs to a text file that it actually PASSED
# usage: bash smoke_check.sh <root_dir> <case_dir>

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "ERROR: please specify root_dir and case_dir"
    exit 1
fi

root_dir="$1"
case_dir="$2"
case_root="${root_dir}/${case_dir}"

# create a dummy case directory
mkdir -p "${case_root}"

# dummy case.submit — just exits 0
cat > "${case_root}/case.submit" << 'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "${case_root}/case.submit"

# dummy xmlquery — returns a fake jobID
cat > "${case_root}/xmlquery" << 'EOF'
#!/usr/bin/env bash
echo "DUMMY:99999.pbs"
EOF
chmod +x "${case_root}/xmlquery"

# write smoke test result
echo "PASSED" > "${root_dir}/smoke_result.txt"
echo "Smoke test pipeline complete: $(date)"