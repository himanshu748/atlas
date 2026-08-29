#!/usr/bin/env bash
# Create or reconcile the project-specific gross-spend alert. This is not a cap.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PROJECT="${1:-}"
BILLING_ACCOUNT="${2:-}"
AMOUNT="${3:-1}"
[[ -n "${PROJECT}" && -n "${BILLING_ACCOUNT}" ]] \
  || die "usage: cost_guard.sh ${EXPECTED_PROJECT} BILLING_ACCOUNT_ID [AMOUNT]"
require_dedicated_project "${PROJECT}"
require_billing_account "${BILLING_ACCOUNT}"
[[ "${AMOUNT}" =~ ^[0-9]+([.][0-9]+)?$ ]] && [[ "${AMOUNT}" != "0" ]] \
  || die "AMOUNT must be a positive number in the billing account currency"
require_gcloud
require_active_project "${PROJECT}"
require_open_billing_account "${BILLING_ACCOUNT}"
require_matching_billing_link "${PROJECT}" "${BILLING_ACCOUNT}"

EXISTING="$(gcloud billing budgets list \
  --billing-account="${BILLING_ACCOUNT}" \
  --filter="displayName='${BUDGET_DISPLAY_NAME}'" \
  --format='value(name)')"
if [[ "$(printf '%s\n' "${EXISTING}" | sed '/^$/d' | wc -l | tr -d ' ')" -gt 1 ]]; then
  die "multiple budgets match ${BUDGET_DISPLAY_NAME}; resolve them before continuing"
fi

if [[ -n "${EXISTING}" ]]; then
  gcloud billing budgets update "${EXISTING}" \
    --billing-account="${BILLING_ACCOUNT}" \
    --display-name "${BUDGET_DISPLAY_NAME}" \
    --budget-amount="${AMOUNT}" \
    --calendar-period=month \
    --filter-projects="projects/${PROJECT}" \
    --credit-types-treatment=exclude-all-credits \
    --clear-threshold-rules \
    --add-threshold-rule=percent=0.01 \
    --add-threshold-rule=percent=0.50 \
    --add-threshold-rule=percent=1.00 \
    --quiet >/dev/null
else
  gcloud billing budgets create \
    --billing-account="${BILLING_ACCOUNT}" \
    --display-name="${BUDGET_DISPLAY_NAME}" \
    --budget-amount="${AMOUNT}" \
    --calendar-period=month \
    --filter-projects="projects/${PROJECT}" \
    --credit-types-treatment=exclude-all-credits \
    --threshold-rule=percent=0.01 \
    --threshold-rule=percent=0.50 \
    --threshold-rule=percent=1.00 \
    --quiet >/dev/null
fi

echo "Gross-spend alert reconciled for ${PROJECT} at ${AMOUNT} in the billing account currency."
echo "This alert is not a hard cap and billing data can be delayed. Keep Scheduler paused until needed."
