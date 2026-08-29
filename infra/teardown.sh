#!/usr/bin/env bash
# Stop the live demo and disable project billing. Firestore and the evidence
# bucket are preserved, but billable services stop when billing is unlinked.
set -euo pipefail

PROJECT="${1:?usage: teardown.sh PROJECT_ID [REGION] --confirm}"
REGION="${2:-us-central1}"
CONFIRM="${3:-}"
SERVICE="atlas-console"
GEMINI_SECRET="atlas-gemini-api-key"
GEMINI_KEY_ID="atlas-gemini-demo"

if [[ "${CONFIRM}" != "--confirm" ]]; then
  cat <<EOF
This stops the public demo, deletes its scheduler and dedicated Gemini key,
then unlinks billing from ${PROJECT}. Firestore and the evidence bucket remain.

Run after recording:
  ./infra/teardown.sh ${PROJECT} ${REGION} --confirm
EOF
  exit 2
fi

echo "▸ deleting scheduled work"
gcloud scheduler jobs delete atlas-weekly-sweep \
  --project "${PROJECT}" --location "${REGION}" --quiet 2>/dev/null || true

echo "▸ deleting Cloud Run service"
gcloud run services delete "${SERVICE}" \
  --project "${PROJECT}" --region "${REGION}" --quiet 2>/dev/null || true

echo "▸ revoking the dedicated Gemini key and secret"
gcloud services api-keys delete "${GEMINI_KEY_ID}" \
  --project "${PROJECT}" --quiet 2>/dev/null || true
gcloud secrets delete "${GEMINI_SECRET}" \
  --project "${PROJECT}" --quiet 2>/dev/null || true

echo "▸ disabling project billing"
gcloud billing projects unlink "${PROJECT}" --quiet

gcloud billing projects describe "${PROJECT}" \
  --format='table(projectId,billingEnabled,billingAccountName.basename())'

echo "✓ demo stopped and billing disabled for ${PROJECT}"
