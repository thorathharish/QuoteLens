#!/usr/bin/env bash
# Remove QuoteLens resources after judging so nothing keeps drawing on the credits.
#
# Usage:
#   PROJECT_ID=my-project ./infra/teardown.sh            # delete QuoteLens resources only
#   PROJECT_ID=my-project ./infra/teardown.sh --project  # delete the whole project
#
# Irreversible: asks you to type the project id before doing anything.
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
BUCKET="${BUCKET:-${PROJECT_ID}-quotelens}"

read -r -p "This permanently deletes QuoteLens resources in '$PROJECT_ID'. Type the project id to confirm: " answer
[[ "$answer" == "$PROJECT_ID" ]] || { echo "Aborted."; exit 1; }

if [[ "${1:-}" == "--project" ]]; then
  gcloud projects delete "$PROJECT_ID" --quiet
  exit 0
fi

run() { "$@" --quiet 2>/dev/null || echo "   (skipped: not found) $*"; }

echo "==> Cloud Run services"
for service in quotelens-web quotelens-api quotelens-worker; do
  run gcloud run services delete "$service" --project="$PROJECT_ID" --region="$REGION"
done

echo "==> Pub/Sub"
run gcloud pubsub subscriptions delete analysis-jobs-push --project="$PROJECT_ID"
for topic in analysis-jobs analysis-jobs-dlq; do
  run gcloud pubsub topics delete "$topic" --project="$PROJECT_ID"
done

echo "==> Cloud Storage"
run gcloud storage rm --recursive "gs://$BUCKET"

echo "==> BigQuery"
for ds in catalog analytics; do
  bq --project_id="$PROJECT_ID" rm -r -f -d "$PROJECT_ID:$ds" 2>/dev/null || echo "   (skipped) $ds"
done

echo "==> Artifact Registry"
run gcloud artifacts repositories delete quotelens --project="$PROJECT_ID" --location="$REGION"

echo "Done. Firestore data remains (delete via console or --project). Billing budget remains."
