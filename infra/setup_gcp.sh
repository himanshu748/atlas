#!/usr/bin/env bash
# Provision the bounded, disposable ATLAS Google Cloud runtime.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PROJECT="${1:-}"
BILLING_ACCOUNT="${2:-}"
[[ -n "${PROJECT}" && -n "${BILLING_ACCOUNT}" ]] \
  || die "usage: setup_gcp.sh ${EXPECTED_PROJECT} BILLING_ACCOUNT_ID"
require_dedicated_project "${PROJECT}"
require_billing_account "${BILLING_ACCOUNT}"
require_gcloud

ACCOUNT="$(active_account)"
DEPLOYER="$(principal_for_account "${ACCOUNT}")"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUILD_SA="${BUILD_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUCKET="${PROJECT}-atlas-evidence"

require_active_project "${PROJECT}"
require_open_billing_account "${BILLING_ACCOUNT}"
LINKED_BILLING="$(linked_billing_account "${PROJECT}")"
if [[ -z "${LINKED_BILLING}" ]]; then
  gcloud billing projects link "${PROJECT}" \
    --billing-account="${BILLING_ACCOUNT}" --quiet
elif [[ "${LINKED_BILLING}" != "billingAccounts/${BILLING_ACCOUNT}" ]]; then
  die "project is linked to ${LINKED_BILLING}, not billingAccounts/${BILLING_ACCOUNT}"
fi

echo "Provisioning ${PROJECT} in ${RUN_REGION}, with Gemini and Model Armor in ${APP_LOCATION}."
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  cloudtrace.googleapis.com \
  modelarmor.googleapis.com \
  cloudasset.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  billingbudgets.googleapis.com \
  iam.googleapis.com \
  --project="${PROJECT}" --quiet

ensure_service_account() {
  local name="$1"
  local display_name="$2"
  if gcloud iam service-accounts describe \
    "${name}@${PROJECT}.iam.gserviceaccount.com" \
    --project="${PROJECT}" >/dev/null 2>&1; then
    return
  fi
  gcloud iam service-accounts create "${name}" \
    --project="${PROJECT}" --display-name="${display_name}"
}

ensure_service_account "${RUNTIME_SA_NAME}" "ATLAS runtime"
ensure_service_account "${BUILD_SA_NAME}" "ATLAS source builder"

for role in \
  roles/aiplatform.user \
  roles/datastore.user \
  roles/cloudasset.viewer \
  roles/cloudtrace.agent \
  roles/modelarmor.user \
  roles/modelarmor.viewer \
  roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="serviceAccount:${RUNTIME_SA}" --role "${role}" \
    --condition=None --quiet >/dev/null
done
gcloud projects add-iam-policy-binding "${PROJECT}" \
  --member="serviceAccount:${BUILD_SA}" --role roles/run.builder \
  --condition=None --quiet >/dev/null
for role in roles/run.sourceDeveloper roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "${PROJECT}" \
    --member="${DEPLOYER}" --role "${role}" --condition=None --quiet >/dev/null
done
for service_account in "${RUNTIME_SA}" "${BUILD_SA}"; do
  gcloud iam service-accounts add-iam-policy-binding "${service_account}" \
    --project="${PROJECT}" --member="${DEPLOYER}" \
    --role roles/iam.serviceAccountUser --quiet >/dev/null
done

if gcloud firestore databases describe --database='(default)' \
  --project="${PROJECT}" >/dev/null 2>&1; then
  FIRESTORE_LOCATION="$(gcloud firestore databases describe --database='(default)' \
    --project="${PROJECT}" --format='value(locationId)')"
  [[ "${FIRESTORE_LOCATION}" == "${RUN_REGION}" ]] \
    || die "existing Firestore location ${FIRESTORE_LOCATION} does not match ${RUN_REGION}"
else
  gcloud firestore databases create --database='(default)' \
    --project="${PROJECT}" --location="${RUN_REGION}" --type=firestore-native --quiet
fi

if ! gcloud pubsub topics describe atlas-events \
  --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud pubsub topics create atlas-events --project="${PROJECT}"
fi
gcloud pubsub topics add-iam-policy-binding atlas-events \
  --project="${PROJECT}" --member="serviceAccount:${RUNTIME_SA}" \
  --role roles/pubsub.publisher --quiet >/dev/null

if ! gcloud storage buckets describe "gs://${BUCKET}" \
  --project="${PROJECT}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET}" \
    --project="${PROJECT}" --location="${RUN_REGION}" \
    --uniform-bucket-level-access --public-access-prevention \
    --soft-delete-duration=0
fi
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --project="${PROJECT}" --member="serviceAccount:${RUNTIME_SA}" \
  --role roles/storage.objectAdmin --quiet >/dev/null

if ! gcloud artifacts repositories describe "${ARTIFACT_REPOSITORY}" \
  --project="${PROJECT}" --location="${RUN_REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPOSITORY}" \
    --project="${PROJECT}" --location="${RUN_REGION}" \
    --repository-format=docker --description="Disposable ATLAS source builds"
fi

if ! model_armor_gcloud model-armor templates describe atlas-ingress-strict \
  --project="${PROJECT}" --location="${APP_LOCATION}" >/dev/null 2>&1; then
  model_armor_gcloud model-armor templates create atlas-ingress-strict \
    --project="${PROJECT}" --location="${APP_LOCATION}" \
    --pi-and-jailbreak-filter-settings-enforcement=enabled \
    --pi-and-jailbreak-filter-settings-confidence-level=low-and-above \
    --malicious-uri-filter-settings-enforcement=enabled
fi
if ! model_armor_gcloud model-armor templates describe atlas-egress-pii \
  --project="${PROJECT}" --location="${APP_LOCATION}" >/dev/null 2>&1; then
  model_armor_gcloud model-armor templates create atlas-egress-pii \
    --project="${PROJECT}" --location="${APP_LOCATION}" \
    --basic-config-filter-enforcement=enabled
fi

cat <<EOF
Setup complete. Create the alert and deploy next:
  ./infra/cost_guard.sh ${PROJECT} ${BILLING_ACCOUNT}
  ./infra/deploy.sh ${PROJECT}
EOF
