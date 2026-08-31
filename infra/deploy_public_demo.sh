#!/usr/bin/env bash
# Deploy an isolated, read-only judge demo with no direct project IAM role bindings or production secrets.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PUBLIC_SERVICE="atlas-public-demo"
PUBLIC_RUNTIME_SA_NAME="atlas-public-demo"

PROJECT="${1:-}"
[[ -n "${PROJECT}" ]] || die "usage: deploy_public_demo.sh ${EXPECTED_PROJECT}"
[[ $# -eq 1 ]] || die "usage: deploy_public_demo.sh ${EXPECTED_PROJECT}"
require_dedicated_project "${PROJECT}"
require_gcloud
require_active_project "${PROJECT}"
[[ -f "${PROJECT_ROOT}/Dockerfile" && -f "${PROJECT_ROOT}/app/main.py" ]] \
  || die "deployment source is incomplete at ${PROJECT_ROOT}"

PUBLIC_RUNTIME_SA="${PUBLIC_RUNTIME_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUILD_SA="${BUILD_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${PUBLIC_RUNTIME_SA}" \
  --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${PUBLIC_RUNTIME_SA_NAME}" \
    --project="${PROJECT}" \
    --display-name="ATLAS public read-only demo"
fi

PROJECT_ROLES="$(gcloud projects get-iam-policy "${PROJECT}" \
  --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:${PUBLIC_RUNTIME_SA}" \
  --format='value(bindings.role)')"
[[ -z "${PROJECT_ROLES}" ]] \
  || die "refusing public runtime identity with project IAM roles: ${PROJECT_ROLES//$'\n'/, }"

# Limit act-as permission to this one identity. The runtime itself receives no
# direct project IAM role bindings, credentials, secrets, production data or
# cloud connectors.
ACCOUNT="$(active_account)"
DEPLOYER="$(principal_for_account "${ACCOUNT}")"
gcloud iam service-accounts add-iam-policy-binding "${PUBLIC_RUNTIME_SA}" \
  --project="${PROJECT}" \
  --member="${DEPLOYER}" \
  --role=roles/iam.serviceAccountUser \
  --quiet >/dev/null

ENV_VARS="ATLAS_MODE=local,ATLAS_PUBLIC_DEMO=true,GOOGLE_GENAI_USE_VERTEXAI=false,ATLAS_USE_MANAGED_ARMOR=false,ATLAS_ENABLE_TTS=false,ATLAS_RUN_BUDGET_USD=0,ATLAS_COST_PER_CONTROL_USD=0"

gcloud run deploy "${PUBLIC_SERVICE}" \
  --source="${PROJECT_ROOT}" \
  --project="${PROJECT}" \
  --region="${RUN_REGION}" \
  --service-account="${PUBLIC_RUNTIME_SA}" \
  --build-service-account="projects/${PROJECT}/serviceAccounts/${BUILD_SA}" \
  --allow-unauthenticated \
  --ingress=all \
  --memory=512Mi \
  --cpu=1 \
  --cpu-throttling \
  --no-cpu-boost \
  --min-instances=0 \
  --max-instances=1 \
  --concurrency=8 \
  --timeout=30 \
  --clear-secrets \
  --clear-volumes \
  --clear-volume-mounts \
  --clear-cloudsql-instances \
  --clear-vpc-connector \
  --clear-network \
  --set-env-vars="${ENV_VARS}" \
  --labels="atlas-surface=public-demo,atlas-data=fixtures" \
  --quiet

URL="$(gcloud run services describe "${PUBLIC_SERVICE}" \
  --project="${PROJECT}" --region="${RUN_REGION}" \
  --format='value(status.url)')"
[[ -n "${URL}" ]] || die "Cloud Run did not return a public demo URL"

cat <<EOF
Public judge demo deployed.
  Cloud Run: ${URL} (public, fixture-only, read-only)
  Runtime:   ${PUBLIC_RUNTIME_SA} (no direct project IAM role bindings)
  Capacity:  min 0, max 1, concurrency 8, 30 second timeout

The private atlas-console service and its Scheduler were not changed.
EOF
