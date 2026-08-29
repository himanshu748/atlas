#!/usr/bin/env bash
# Shared safety contract for the disposable ATLAS Google Cloud deployment.

EXPECTED_PROJECT="atlas-agentic-hack-2026-v2"
RUN_REGION="us-central1"
APP_LOCATION="us"
SERVICE="atlas-console"
SCHEDULER_JOB="atlas-weekly-sweep"
RUNTIME_SA_NAME="atlas-orchestrator"
BUILD_SA_NAME="atlas-builder"
ARTIFACT_REPOSITORY="cloud-run-source-deploy"
BUDGET_DISPLAY_NAME="ATLAS ${EXPECTED_PROJECT} gross-spend guard"

die() {
  echo "error: $*" >&2
  exit 1
}

require_gcloud() {
  command -v gcloud >/dev/null 2>&1 || die "gcloud is required"
}

require_dedicated_project() {
  local project="$1"
  if [[ "${project}" != "${EXPECTED_PROJECT}" ]]; then
    die "refusing project '${project}'; this workflow only operates on dedicated project ${EXPECTED_PROJECT}"
  fi
}

require_billing_account() {
  local billing_account="$1"
  [[ -n "${billing_account}" ]] || die "BILLING_ACCOUNT_ID is required"
  [[ "${billing_account}" != "BILLING_ACCOUNT_ID" ]] \
    || die "replace BILLING_ACCOUNT_ID with the real billing account ID"
}

active_account() {
  local account
  account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' --limit=1)"
  [[ -n "${account}" ]] || die "no active gcloud account"
  printf '%s' "${account}"
}

principal_for_account() {
  local account="$1"
  if [[ "${account}" == *.gserviceaccount.com ]]; then
    printf 'serviceAccount:%s' "${account}"
  else
    printf 'user:%s' "${account}"
  fi
}

require_active_project() {
  local project="$1"
  local state
  state="$(gcloud projects describe "${project}" \
    --format='value(lifecycleState)')"
  [[ "${state}" == "ACTIVE" ]] \
    || die "project ${project} is not ACTIVE (state=${state:-unknown})"
}

require_open_billing_account() {
  local billing_account="$1"
  local is_open
  is_open="$(gcloud billing accounts describe "${billing_account}" \
    --format='value(open)')"
  [[ "${is_open}" == "True" || "${is_open}" == "true" ]] \
    || die "billing account ${billing_account} is not open"
}

linked_billing_account() {
  local project="$1"
  gcloud billing projects describe "${project}" \
    --format='value(billingAccountName)'
}

require_matching_billing_link() {
  local project="$1"
  local billing_account="$2"
  local linked
  linked="$(linked_billing_account "${project}")"
  [[ "${linked}" == "billingAccounts/${billing_account}" ]] \
    || die "project ${project} is linked to '${linked:-none}', not billingAccounts/${billing_account}"
}

model_armor_gcloud() {
  CLOUDSDK_API_ENDPOINT_OVERRIDES_MODELARMOR="https://modelarmor.${APP_LOCATION}.rep.googleapis.com/" \
    gcloud "$@"
}
