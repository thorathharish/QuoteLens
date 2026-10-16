#!/usr/bin/env bash
# One-time (idempotent) GCP setup for QuoteLens, sized for free-trial credits.
#
# Usage:
#   PROJECT_ID=my-hackathon-project \
#   BILLING_ACCOUNT=XXXXXX-XXXXXX-XXXXXX BUDGET_AMOUNT=300 BUDGET_CURRENCY=USD \
#   ./infra/bootstrap.sh
#
# BILLING_ACCOUNT is optional (only used to create the budget alert). BUDGET_CURRENCY must
# match the billing account's currency (e.g. INR for many accounts in India).
# Cloud Run services and the Pub/Sub push subscription are created by deploy.sh (Phase 9a).
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"            # free GCS tier + broad Gemini availability
BUCKET="${BUCKET:-${PROJECT_ID}-quotelens}"
TOPIC="analysis-jobs"
DLQ_TOPIC="analysis-jobs-dlq"
AR_REPO="quotelens"
BUDGET_AMOUNT="${BUDGET_AMOUNT:-300}"
BUDGET_CURRENCY="${BUDGET_CURRENCY:-USD}"
BUDGET_NAME="quotelens-hackathon"

SA_API="quotelens-api"
SA_WORKER="quotelens-worker"
SA_WEB="quotelens-web"
SA_PUSH="quotelens-pubsub-push"

sa_email() { echo "$1@${PROJECT_ID}.iam.gserviceaccount.com"; }
log() { printf '\n==> %s\n' "$*"; }
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

gcloud config set project "$PROJECT_ID" >/dev/null

log "Enabling APIs"
gcloud services enable \
  run.googleapis.com firestore.googleapis.com bigquery.googleapis.com \
  pubsub.googleapis.com storage.googleapis.com aiplatform.googleapis.com \
  secretmanager.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  iamcredentials.googleapis.com billingbudgets.googleapis.com

log "Service accounts"
for sa in "$SA_API" "$SA_WORKER" "$SA_WEB" "$SA_PUSH"; do
  if ! gcloud iam service-accounts describe "$(sa_email "$sa")" >/dev/null 2>&1; then
    gcloud iam service-accounts create "$sa" --display-name="QuoteLens ${sa#quotelens-}"
  fi
done

grant_project() {
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$1" --role="$2" --condition=None --quiet >/dev/null
}

log "Project roles (least privilege)"
for role in roles/datastore.user roles/bigquery.dataViewer roles/bigquery.jobUser \
            roles/aiplatform.user roles/secretmanager.secretAccessor; do
  grant_project "$(sa_email "$SA_API")" "$role"
done
for role in roles/datastore.user roles/bigquery.dataEditor roles/bigquery.jobUser \
            roles/aiplatform.user roles/secretmanager.secretAccessor; do
  grant_project "$(sa_email "$SA_WORKER")" "$role"
done
# The api signs GCS download URLs via IAM signBlob (no key files).
gcloud iam service-accounts add-iam-policy-binding "$(sa_email "$SA_API")" \
  --member="serviceAccount:$(sa_email "$SA_API")" \
  --role=roles/iam.serviceAccountTokenCreator --quiet >/dev/null

log "Firestore (native, default database = free tier)"
if ! gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  gcloud firestore databases create --location="$REGION" --type=firestore-native
fi

log "Cloud Storage bucket gs://$BUCKET"
if ! gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
    --uniform-bucket-level-access --public-access-prevention
fi
cat >"$tmp_dir/lifecycle.json" <<'JSON'
{"rule": [{"action": {"type": "Delete"}, "condition": {"age": 7, "matchesPrefix": ["exports/"]}}]}
JSON
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file="$tmp_dir/lifecycle.json" >/dev/null
for sa in "$SA_API" "$SA_WORKER"; do
  gcloud storage buckets add-iam-policy-binding "gs://$BUCKET" \
    --member="serviceAccount:$(sa_email "$sa")" --role=roles/storage.objectAdmin >/dev/null
done

log "BigQuery datasets"
for ds in catalog analytics; do
  if ! bq --project_id="$PROJECT_ID" show --dataset "$PROJECT_ID:$ds" >/dev/null 2>&1; then
    bq --project_id="$PROJECT_ID" --location="$REGION" mk --dataset \
      --description="QuoteLens $ds" "$PROJECT_ID:$ds"
  fi
done

log "Pub/Sub topics"
for topic in "$TOPIC" "$DLQ_TOPIC"; do
  if ! gcloud pubsub topics describe "$topic" >/dev/null 2>&1; then
    gcloud pubsub topics create "$topic"
  fi
done
gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="serviceAccount:$(sa_email "$SA_API")" --role=roles/pubsub.publisher >/dev/null

log "Artifact Registry ($AR_REPO) with cleanup policy (keep 2 most recent: free tier is 0.5 GB)"
if ! gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" >/dev/null 2>&1; then
  gcloud artifacts repositories create "$AR_REPO" --repository-format=docker \
    --location="$REGION" --description="QuoteLens images"
fi
cat >"$tmp_dir/cleanup.json" <<'JSON'
[
  {"name": "keep-2-recent", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
  {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"tagState": "ANY", "olderThan": "1d"}}
]
JSON
gcloud artifacts repositories set-cleanup-policies "$AR_REPO" --location="$REGION" \
  --policy="$tmp_dir/cleanup.json" --no-dry-run >/dev/null

if [[ -n "${BILLING_ACCOUNT:-}" ]]; then
  log "Budget alert ($BUDGET_AMOUNT $BUDGET_CURRENCY; alerts at 25/50/75/90/100%)"
  if gcloud billing budgets list --billing-account="$BILLING_ACCOUNT" \
       --format="value(displayName)" | grep -qx "$BUDGET_NAME"; then
    echo "Budget '$BUDGET_NAME' already exists"
  else
    gcloud billing budgets create --billing-account="$BILLING_ACCOUNT" \
      --display-name="$BUDGET_NAME" \
      --budget-amount="${BUDGET_AMOUNT}${BUDGET_CURRENCY}" \
      --filter-projects="projects/$PROJECT_ID" \
      --threshold-rule=percent=0.25 --threshold-rule=percent=0.5 \
      --threshold-rule=percent=0.75 --threshold-rule=percent=0.9 \
      --threshold-rule=percent=1.0
  fi
else
  log "BILLING_ACCOUNT not set: skipping budget alert (create it in the console: Billing > Budgets)"
fi

log "Done. Next: deploy services with infra/deploy.sh (Phase 9a)."
echo "Bucket: gs://$BUCKET   Region: $REGION   Registry: $REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO"
echo "Note: budgets only alert; they do not cap spend. Check infra/cost-check.md daily."
