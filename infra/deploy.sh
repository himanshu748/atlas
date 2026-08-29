#!/usr/bin/env bash
# Build a private, scale-to-zero Cloud Run service and a paused weekly proof job.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=common.sh
source "${SCRIPT_DIR}/common.sh"

PROJECT="${1:-}"
SCHEDULER_MODE="${2:-}"
[[ -n "${PROJECT}" ]] || die "usage: deploy.sh ${EXPECTED_PROJECT} [--resume-scheduler]"
require_dedicated_project "${PROJECT}"
[[ -z "${SCHEDULER_MODE}" || "${SCHEDULER_MODE}" == "--resume-scheduler" ]] \
  || die "unknown option ${SCHEDULER_MODE}; expected --resume-scheduler"
[[ $# -le 2 ]] || die "usage: deploy.sh ${EXPECTED_PROJECT} [--resume-scheduler]"
require_gcloud
require_active_project "${PROJECT}"
[[ -f "${PROJECT_ROOT}/Dockerfile" && -f "${PROJECT_ROOT}/app/main.py" ]] \
  || die "deployment source is incomplete at ${PROJECT_ROOT}"

RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUILD_SA="${BUILD_SA_NAME}@${PROJECT}.iam.gserviceaccount.com"
BUCKET="${PROJECT}-atlas-evidence"
ENV_VARS="ATLAS_MODE=cloud,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${APP_LOCATION},GOOGLE_GENAI_USE_VERTEXAI=true,ATLAS_BUCKET=${BUCKET},ATLAS_MODEL_FAST=gemini-3.5-flash,ATLAS_MODEL_JUDGE=gemini-3.5-flash,ATLAS_ENABLE_TTS=false,ATLAS_RUN_BUDGET_USD=5,ATLAS_COST_PER_CONTROL_USD=0.0031"

gcloud run deploy "${SERVICE}" \
  --source="${PROJECT_ROOT}" \
  --project="${PROJECT}" \
  --region="${RUN_REGION}" \
  --service-account="${RUNTIME_SA}" \
  --build-service-account="projects/${PROJECT}/serviceAccounts/${BUILD_SA}" \
  --no-allow-unauthenticated \
  --ingress=all \
  --memory=1Gi \
  --cpu=1 \
  --cpu-throttling \
  --no-cpu-boost \
  --min-instances=0 \
  --max-instances=1 \
  --concurrency=1 \
  --timeout=900 \
  --set-env-vars="${ENV_VARS}" \
  --quiet

URL="$(gcloud run services describe "${SERVICE}" \
  --project="${PROJECT}" --region="${RUN_REGION}" \
  --format='value(status.url)')"
[[ -n "${URL}" ]] || die "Cloud Run did not return a service URL"

gcloud run services add-iam-policy-binding "${SERVICE}" \
  --project="${PROJECT}" --region="${RUN_REGION}" \
  --member="serviceAccount:${RUNTIME_SA}" --role roles/run.invoker \
  --quiet >/dev/null

SCHEDULER_ARGS=(
  --project="${PROJECT}"
  --location="${RUN_REGION}"
  --schedule="0 7 * * 1"
  --time-zone="Etc/UTC"
  --uri="${URL}/internal/sweep"
  --http-method=POST
  --oidc-service-account-email="${RUNTIME_SA}"
  --oidc-token-audience="${URL}"
  --attempt-deadline=900s
  --max-retry-attempts=0
  --quiet
)
if gcloud scheduler jobs describe "${SCHEDULER_JOB}" \
  --project="${PROJECT}" --location="${RUN_REGION}" >/dev/null 2>&1; then
  gcloud scheduler jobs update http "${SCHEDULER_JOB}" "${SCHEDULER_ARGS[@]}"
else
  gcloud scheduler jobs create http "${SCHEDULER_JOB}" "${SCHEDULER_ARGS[@]}"
fi

# Reconciliation is deliberately safe: every deploy leaves the job paused unless
# the caller opts in on this invocation.
gcloud scheduler jobs pause "${SCHEDULER_JOB}" \
  --project="${PROJECT}" --location="${RUN_REGION}" --quiet
if [[ "${SCHEDULER_MODE}" == "--resume-scheduler" ]]; then
  gcloud scheduler jobs resume "${SCHEDULER_JOB}" \
    --project="${PROJECT}" --location="${RUN_REGION}" --quiet
  SCHEDULER_STATUS="enabled by explicit opt-in"
else
  SCHEDULER_STATUS="paused (use ./infra/deploy.sh ${PROJECT} --resume-scheduler to enable)"
fi

cat <<EOF
Deployment complete.
  Cloud Run: ${URL} (private, min 0, max 1, concurrency 1)
  Scheduler: ${SCHEDULER_STATUS}

Authenticate the private demo locally:
  gcloud run services proxy ${SERVICE} --project=${PROJECT} --region=${RUN_REGION}

Delete the disposable project after recording:
  ./infra/teardown.sh ${PROJECT} BILLING_ACCOUNT_ID --confirm-delete-project
EOF
