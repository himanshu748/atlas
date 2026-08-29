#!/usr/bin/env bash
# Delete the dedicated project, which removes every ATLAS resource as one unit.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PROJECT="${1:-}"
BILLING_ACCOUNT="${2:-}"
CONFIRM="${3:-}"
[[ -n "${PROJECT}" && -n "${BILLING_ACCOUNT}" ]] \
  || die "usage: teardown.sh ${EXPECTED_PROJECT} BILLING_ACCOUNT_ID [--confirm-delete-project]"
require_dedicated_project "${PROJECT}"
require_billing_account "${BILLING_ACCOUNT}"

if [[ "${CONFIRM}" != "--confirm-delete-project" ]]; then
  cat <<EOF
This permanently schedules deletion of the dedicated project ${PROJECT}, including all ATLAS data and services.
Run only after recording and exporting anything you need:
  ./infra/teardown.sh ${PROJECT} ${BILLING_ACCOUNT} --confirm-delete-project
EOF
  exit 2
fi
[[ $# -eq 3 ]] || die "usage: teardown.sh ${EXPECTED_PROJECT} BILLING_ACCOUNT_ID --confirm-delete-project"

require_gcloud
require_active_project "${PROJECT}"
require_open_billing_account "${BILLING_ACCOUNT}"
require_matching_billing_link "${PROJECT}" "${BILLING_ACCOUNT}"

BUDGETS="$(gcloud billing budgets list \
  --billing-account="${BILLING_ACCOUNT}" \
  --filter="displayName='${BUDGET_DISPLAY_NAME}'" \
  --format='value(name)')"
if [[ -n "${BUDGETS}" ]]; then
  while IFS= read -r budget; do
    [[ -n "${budget}" ]] || continue
    gcloud billing budgets delete "${budget}" \
      --billing-account="${BILLING_ACCOUNT}" --quiet
  done <<< "${BUDGETS}"
fi

gcloud projects delete "${PROJECT}" --quiet
echo "Project ${PROJECT} is scheduled for deletion. Google Cloud provides a limited recovery window before final deletion."
