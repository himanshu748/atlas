#!/usr/bin/env bash
# ATLAS build and deploy to Cloud Run, then wire the weekly sweep.
#
# Vertex AI backend:
#   ./infra/deploy.sh my-project-id us-central1 vertex
#
# Zero-cost Gemini Developer API backend. If GEMINI_API_KEY is unset, the
# script creates a dedicated key restricted to the Gemini API and stores it
# directly in Secret Manager without printing it:
#   ./infra/deploy.sh my-project-id us-central1 ai-studio
set -euo pipefail

PROJECT="${1:?usage: deploy.sh PROJECT_ID [REGION]}"
REGION="${2:-us-central1}"
MODEL_BACKEND="${3:-vertex}"
SERVICE="atlas-console"
BUCKET="${PROJECT}-atlas-evidence"
SA="atlas-orchestrator@${PROJECT}.iam.gserviceaccount.com"
GEMINI_SECRET="atlas-gemini-api-key"
GEMINI_KEY_ID="atlas-gemini-demo"

case "${MODEL_BACKEND}" in
  vertex|ai-studio) ;;
  *)
    echo "MODEL_BACKEND must be 'vertex' or 'ai-studio'" >&2
    exit 2
    ;;
esac

ENV_VARS="ATLAS_MODE=cloud,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},ATLAS_BUCKET=${BUCKET},ATLAS_MODEL_FAST=gemini-3.5-flash,ATLAS_MODEL_JUDGE=gemini-3.5-flash,ATLAS_ENABLE_TTS=false"
SECRET_ARGS=()

if [[ "${MODEL_BACKEND}" == "ai-studio" ]]; then
  echo "▸ configuring a Gemini API key through Secret Manager"
  if ! gcloud secrets describe "${GEMINI_SECRET}" --project "${PROJECT}" >/dev/null 2>&1; then
    gcloud secrets create "${GEMINI_SECRET}" \
      --project "${PROJECT}" \
      --replication-policy automatic
  fi

  SECRET_VERSION="$(gcloud secrets versions list "${GEMINI_SECRET}" \
    --project "${PROJECT}" \
    --filter='state=ENABLED' \
    --limit 1 \
    --format='value(name)')"
  if [[ -z "${SECRET_VERSION}" ]]; then
    if [[ -n "${GEMINI_API_KEY:-}" ]]; then
      printf '%s' "${GEMINI_API_KEY}" | gcloud secrets versions add "${GEMINI_SECRET}" \
        --project "${PROJECT}" \
        --data-file=-
    else
      echo "  creating dedicated API-restricted key"
      if ! gcloud services api-keys describe "${GEMINI_KEY_ID}" \
        --project "${PROJECT}" >/dev/null 2>&1; then
        gcloud services api-keys create \
          --project "${PROJECT}" \
          --key-id "${GEMINI_KEY_ID}" \
          --display-name "ATLAS Gemini demo key" \
          --api-target service=generativelanguage.googleapis.com >/dev/null
      fi
      gcloud services api-keys get-key-string "${GEMINI_KEY_ID}" \
        --project "${PROJECT}" \
        --format='value(keyString)' | gcloud secrets versions add "${GEMINI_SECRET}" \
          --project "${PROJECT}" \
          --data-file=- >/dev/null
    fi
  else
    echo "  reusing enabled ${GEMINI_SECRET} version"
  fi

  gcloud secrets add-iam-policy-binding "${GEMINI_SECRET}" \
    --project "${PROJECT}" \
    --member "serviceAccount:${SA}" \
    --role roles/secretmanager.secretAccessor >/dev/null

  ENV_VARS="${ENV_VARS},GOOGLE_GENAI_USE_VERTEXAI=false,ATLAS_RUN_BUDGET_USD=0,ATLAS_COST_PER_CONTROL_USD=0"
  SECRET_ARGS=(--set-secrets "GEMINI_API_KEY=${GEMINI_SECRET}:latest")
else
  ENV_VARS="${ENV_VARS},GOOGLE_GENAI_USE_VERTEXAI=true"
fi

echo "▸ building and deploying ${SERVICE}"
gcloud run deploy "${SERVICE}" \
  --source . \
  --project "${PROJECT}" \
  --region "${REGION}" \
  --service-account "${SA}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 1 \
  --timeout 900 \
  --set-env-vars "${ENV_VARS}" \
  "${SECRET_ARGS[@]}"

URL=$(gcloud run services describe "${SERVICE}" \
  --project "${PROJECT}" --region "${REGION}" --format='value(status.url)')

echo "▸ scheduling the weekly drift sweep"
gcloud scheduler jobs create http atlas-weekly-sweep \
  --project "${PROJECT}" \
  --location "${REGION}" \
  --schedule "0 7 * * 1" \
  --time-zone "Etc/UTC" \
  --uri "${URL}/internal/sweep" \
  --http-method POST \
  --oidc-service-account-email "${SA}" \
  2>/dev/null || gcloud scheduler jobs update http atlas-weekly-sweep \
  --project "${PROJECT}" --location "${REGION}" --uri "${URL}/internal/sweep"

cat <<EOF

✓ deployed

  console : ${URL}
  health  : ${URL}/healthz
  api docs: ${URL}/docs
  model   : ${MODEL_BACKEND}
  sweep   : ${URL}/internal/sweep  (Cloud Scheduler, Mondays 07:00 UTC)

Record this URL in the demo video — it is the proof the backend runs on Google Cloud.
Tear down after recording:
  ./infra/teardown.sh ${PROJECT} ${REGION} --confirm
EOF
