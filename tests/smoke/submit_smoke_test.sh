#!/usr/bin/env bash
#
# submit the tethering smoke test pipeline.
#
# Usage:
#   export TETHERING_REPO=/path/to/tethering
#   bash $TETHERING_REPO/tests/smoke/submit_smoke_test.sh
#
# Results:
#   Check with: python $TETHERING_REPO/tests/smoke/check_smoke_test.py <root>
#   where <root> is the root printed by this script.

set -euo pipefail

if [ -z "${TETHERING_REPO:-}" ]; then
  echo "ERROR: TETHERING_REPO environment variable must be set"
  echo "  export TETHERING_REPO=/path/to/tethering"
  exit 1
fi

CONFIG="${TETHERING_REPO}/tests/smoke/smoke_test.yaml"

echo "=== Tethering smoke test ==="
echo "Config: ${CONFIG}"
echo ""

clm-run --create --config "${CONFIG}"

# grab root from config
ROOT=$(python3 -c "import yaml; print(yaml.safe_load(open('${CONFIG}'))['root'])")
ROOT=$(echo $ROOT | envsubst)


clm-run --root "${ROOT}" --submit

echo ""
echo "Smoke test submitted. Check status with:"
echo "  clm-run --root ${ROOT} --print-status"
echo ""
echo "When complete, verify results with:"
echo "  python ${TETHERING_REPO}/tests/smoke/check_smoke_test.py ${ROOT}"