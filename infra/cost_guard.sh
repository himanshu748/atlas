#!/usr/bin/env bash
# Create a gross-spend budget for this one demo project. This is an alert, not
# a hard cap. The teardown script unlinks billing for the actual spend stop.
set -euo pipefail

PROJECT="${1:?usage: cost_guard.sh PROJECT_ID BILLING_ACCOUNT_ID [AMOUNT]}"
BILLING_ACCOUNT="${2:?usage: cost_guard.sh PROJECT_ID BILLING_ACCOUNT_ID [AMOUNT]}"
AMOUNT="${3:-1INR}"
DISPLAY_NAME="ATLAS demo gross-spend guard"

echo "▸ checking ${DISPLAY_NAME}"
EXISTING="$(gcloud billing budgets list \
  --billing-account "${BILLING_ACCOUNT}" \
  --filter "displayName='${DISPLAY_NAME}'" \
  --limit 1 \
  --format='value(name)')"

if [[ -n "${EXISTING}" ]]; then
  echo "  budget already exists: ${EXISTING}"
  exit 0
fi

gcloud billing budgets create \
  --billing-account "${BILLING_ACCOUNT}" \
  --display-name "${DISPLAY_NAME}" \
  --budget-amount "${AMOUNT}" \
  --calendar-period month \
  --filter-projects "projects/${PROJECT}" \
  --credit-types-treatment exclude-all-credits \
  --threshold-rule percent=0.01 \
  --threshold-rule percent=0.50 \
  --threshold-rule percent=1.00 >/dev/null

echo "✓ ${AMOUNT} gross-spend alert created for ${PROJECT}"
echo "  Billing reports can be delayed. Run teardown immediately after recording."
