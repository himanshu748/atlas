#!/usr/bin/env bash
# ATLAS — one-command Google Cloud setup.
# Enables APIs, creates per-agent service accounts with least-privilege roles,
# provisions Firestore, Pub/Sub, Storage and the Model Armor templates.
#
#   ./infra/setup_gcp.sh my-project-id us-central1
set -euo pipefail

PROJECT="${1:?usage: setup_gcp.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
BUCKET="${PROJECT}-atlas-evidence"

echo "▸ project=${PROJECT} region=${REGION}"
gcloud config set project "${PROJECT}" >/dev/null

echo "▸ enabling APIs"
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudtasks.googleapis.com \
  storage.googleapis.com \
  cloudtrace.googleapis.com \
  secretmanager.googleapis.com \
  apikeys.googleapis.com \
  generativelanguage.googleapis.com \
  billingbudgets.googleapis.com \
  modelarmor.googleapis.com \
  cloudasset.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com

echo "▸ firestore (native mode)"
gcloud firestore databases create --location="${REGION}" 2>/dev/null \
  || echo "  already exists"

echo "▸ pub/sub topics"
for t in atlas-work atlas-events; do
  gcloud pubsub topics create "$t" 2>/dev/null || echo "  $t exists"
done
gcloud pubsub topics create atlas-dlq 2>/dev/null || true
gcloud pubsub subscriptions create atlas-work-sub \
  --topic=atlas-work \
  --dead-letter-topic=atlas-dlq \
  --max-delivery-attempts=5 2>/dev/null || echo "  subscription exists"

echo "▸ evidence bucket"
gcloud storage buckets create "gs://${BUCKET}" --location="${REGION}" 2>/dev/null \
  || echo "  bucket exists"
gcloud storage buckets update "gs://${BUCKET}" --uniform-bucket-level-access

echo "▸ per-agent service accounts (zero-trust identities)"
# Each agent gets its own identity and only the roles its scopes require.
declare -A AGENT_ROLES=(
  ["atlas-orchestrator"]="roles/aiplatform.user roles/datastore.user roles/pubsub.publisher roles/cloudasset.viewer roles/storage.objectCreator roles/cloudtrace.agent roles/modelarmor.user roles/modelarmor.viewer"
  ["atlas-hunter-iam"]="roles/aiplatform.user roles/cloudasset.viewer roles/iam.securityReviewer"
  ["atlas-hunter-sdlc"]="roles/aiplatform.user roles/datastore.user"
  ["atlas-hunter-infra"]="roles/aiplatform.user roles/cloudasset.viewer roles/logging.viewer"
  ["atlas-hunter-hr"]="roles/aiplatform.user roles/datastore.user"
  ["atlas-hunter-vendor"]="roles/aiplatform.user roles/datastore.user"
  ["atlas-judge"]="roles/aiplatform.user roles/datastore.viewer"
  ["atlas-assembler"]="roles/aiplatform.user roles/storage.objectCreator"
)
for sa in "${!AGENT_ROLES[@]}"; do
  gcloud iam service-accounts create "$sa" --display-name="ATLAS ${sa}" 2>/dev/null \
    || echo "  $sa exists"
  for role in ${AGENT_ROLES[$sa]}; do
    gcloud projects add-iam-policy-binding "${PROJECT}" \
      --member="serviceAccount:${sa}@${PROJECT}.iam.gserviceaccount.com" \
      --role="$role" --condition=None >/dev/null
  done
  echo "  ✓ $sa"
done

echo "▸ model armor templates"
gcloud model-armor templates create atlas-ingress-strict \
  --location="${REGION}" \
  --pi-and-jailbreak-filter-settings-enforcement=enabled \
  --pi-and-jailbreak-filter-settings-confidence-level=LOW_AND_ABOVE \
  --malicious-uri-filter-settings-enforcement=enabled \
  2>/dev/null || echo "  ingress template exists"

gcloud model-armor templates create atlas-egress-pii \
  --location="${REGION}" \
  --basic-config-filter-enforcement=enabled \
  2>/dev/null || echo "  egress template exists"

cat <<EOF

✓ setup complete

  project : ${PROJECT}
  region  : ${REGION}
  bucket  : gs://${BUCKET}

next:
  ./infra/cost_guard.sh ${PROJECT} BILLING_ACCOUNT_ID
  ./infra/deploy.sh ${PROJECT} ${REGION}
EOF
