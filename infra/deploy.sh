#!/usr/bin/env bash
# Build and deploy QuoteLens to Cloud Run (free-credit settings). Run after bootstrap.sh.
#
#   PROJECT_ID=my-project ./infra/deploy.sh
#
# Options (environment variables):
#   REGION=us-central1            TAG=<git short sha>         SKIP_BUILD=1 (reuse TAG images)
#   CATALOG_BACKEND=seed|bigquery (bigquery after the catalog is loaded, see issue #3)
#   LLM_ENABLED=true|false
#   LLM_PROVIDER=openrouter|vertex   default openrouter: Google's Gemini models through OpenRouter,
#                                    paid from the OpenRouter balance (no Vertex AI spend on GCP).
#                                    Needs the openrouter-api-key secret (run secrets.sh first).
#                                    vertex: Gemini on Vertex AI, billed to the GCP project.
#   OPENROUTER_FLASH_MODEL / OPENROUTER_PRO_MODEL, or GEMINI_FLASH_MODEL / GEMINI_PRO_MODEL (vertex)
#
# Topology (all scale to zero; demo-mode.sh keeps web+api warm only during the demo):
#   web    public          → calls api with an ID token (web SA has run.invoker on api)
#   api    private         → publishes jobs to Pub/Sub; calls the LLM (OpenRouter or Vertex AI)
#   worker private         ← Pub/Sub push with OIDC (push SA has run.invoker on worker)
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
TAG="${TAG:-$(git rev-parse --short HEAD)}"
REPO="quotelens"
BUCKET="${BUCKET:-${PROJECT_ID}-quotelens}"
CATALOG_BACKEND="${CATALOG_BACKEND:-seed}"
LLM_ENABLED="${LLM_ENABLED:-true}"
LLM_PROVIDER="${LLM_PROVIDER:-openrouter}"
GEMINI_FLASH_MODEL="${GEMINI_FLASH_MODEL:-gemini-2.5-flash}"
GEMINI_PRO_MODEL="${GEMINI_PRO_MODEL:-gemini-2.5-pro}"
OPENROUTER_FLASH_MODEL="${OPENROUTER_FLASH_MODEL:-google/gemini-2.5-flash}"
OPENROUTER_PRO_MODEL="${OPENROUTER_PRO_MODEL:-google/gemini-2.5-pro}"
case "$LLM_PROVIDER" in
  openrouter | vertex) ;;
  *) echo "LLM_PROVIDER must be openrouter or vertex (got '$LLM_PROVIDER')"; exit 1 ;;
esac
TOPIC="analysis-jobs"
DLQ_TOPIC="analysis-jobs-dlq"
SUBSCRIPTION="analysis-jobs-push"
IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

sa() { echo "quotelens-$1@${PROJECT_ID}.iam.gserviceaccount.com"; }
log() { printf '\n==> %s\n' "$*"; }
url_of() { gcloud run services describe "$1" --region="$REGION" --project="$PROJECT_ID" --format='value(status.url)'; }
run() { gcloud "$@" --project="$PROJECT_ID" --quiet; }
secret_exists() { gcloud secrets describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1; }

# Fail before building anything if the copilot would be deployed without its key.
if [[ "$LLM_ENABLED" == "true" && "$LLM_PROVIDER" == "openrouter" ]] && ! secret_exists openrouter-api-key; then
  echo "No 'openrouter-api-key' secret in ${PROJECT_ID}. Put OPENROUTER_API_KEY in services/api/.env, then run:"
  echo "  PROJECT_ID=${PROJECT_ID} ./infra/secrets.sh"
  echo "or deploy without the LLM:  LLM_ENABLED=false PROJECT_ID=${PROJECT_ID} ./infra/deploy.sh"
  exit 1
fi

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  log "Building images (tag $TAG) with Cloud Build"
  gcloud builds submit --project="$PROJECT_ID" --config infra/cloudbuild.yaml \
    --substitutions "_TAG=${TAG},_REGION=${REGION}" .
fi

# Secrets that exist are mounted as env vars; missing ones are simply not configured.
SECRET_FLAGS=()
PAIRS=(DIGIKEY_CLIENT_ID=digikey-client-id DIGIKEY_CLIENT_SECRET=digikey-client-secret
       MOUSER_API_KEY=mouser-api-key ELEMENT14_API_KEY=element14-api-key)
if [[ "$LLM_PROVIDER" == "openrouter" ]]; then
  PAIRS+=(OPENROUTER_API_KEY=openrouter-api-key)
fi
for pair in "${PAIRS[@]}"; do
  secret="${pair#*=}"
  if secret_exists "$secret"; then
    SECRET_FLAGS+=("${pair%%=*}=${secret}:latest")
  fi
done
SECRETS_ARG=()
if ((${#SECRET_FLAGS[@]})); then
  SECRETS_ARG=(--set-secrets "$(IFS=,; echo "${SECRET_FLAGS[*]}")")
fi

COMMON_ENV="ENV=prod,GCP_PROJECT=${PROJECT_ID},GCP_REGION=${REGION},GCS_BUCKET=${BUCKET}"
COMMON_ENV+=",STORAGE_BACKEND=firestore,BLOB_BACKEND=gcs,CATALOG_BACKEND=${CATALOG_BACKEND}"
COMMON_ENV+=",JOB_BACKEND=pubsub,PUBSUB_TOPIC=${TOPIC}"
COMMON_ENV+=",LLM_ENABLED=${LLM_ENABLED},LLM_PROVIDER=${LLM_PROVIDER}"
COMMON_ENV+=",GEMINI_FLASH_MODEL=${GEMINI_FLASH_MODEL},GEMINI_PRO_MODEL=${GEMINI_PRO_MODEL}"
COMMON_ENV+=",OPENROUTER_FLASH_MODEL=${OPENROUTER_FLASH_MODEL},OPENROUTER_PRO_MODEL=${OPENROUTER_PRO_MODEL}"
COMMON_ENV+=",DATA_MODE=cache_first,LOG_LEVEL=INFO"

log "Deploying worker (private, Pub/Sub push target)"
run run deploy quotelens-worker --image "${IMAGE_BASE}/api:${TAG}" --region "$REGION" \
  --service-account "$(sa worker)" --no-allow-unauthenticated \
  --cpu 1 --memory 1Gi --min-instances 0 --max-instances 2 --concurrency 4 --timeout 600 \
  --set-env-vars "${COMMON_ENV},APP_MODULE=app.main_worker:app,PUBSUB_VERIFY_OIDC=true,PUBSUB_PUSH_SERVICE_ACCOUNT=$(sa pubsub-push)" \
  "${SECRETS_ARG[@]}"
WORKER_URL="$(url_of quotelens-worker)"
run run services update quotelens-worker --region "$REGION" --update-env-vars "PUBSUB_PUSH_AUDIENCE=${WORKER_URL}"
run run services add-iam-policy-binding quotelens-worker --region "$REGION" \
  --member "serviceAccount:$(sa pubsub-push)" --role roles/run.invoker >/dev/null

log "Pub/Sub push subscription → worker (OIDC, dead-letter after 5 attempts)"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
PUBSUB_AGENT="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com"
SUB_FLAGS=(--push-endpoint "${WORKER_URL}/internal/jobs/pubsub"
           --push-auth-service-account "$(sa pubsub-push)" --push-auth-token-audience "$WORKER_URL"
           --ack-deadline 600 --dead-letter-topic "$DLQ_TOPIC" --max-delivery-attempts 5
           --min-retry-delay 10s --max-retry-delay 120s)
if gcloud pubsub subscriptions describe "$SUBSCRIPTION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  run pubsub subscriptions update "$SUBSCRIPTION" "${SUB_FLAGS[@]}"
else
  run pubsub subscriptions create "$SUBSCRIPTION" --topic "$TOPIC" "${SUB_FLAGS[@]}"
fi
run pubsub topics add-iam-policy-binding "$DLQ_TOPIC" --member "$PUBSUB_AGENT" --role roles/pubsub.publisher >/dev/null
run pubsub subscriptions add-iam-policy-binding "$SUBSCRIPTION" --member "$PUBSUB_AGENT" --role roles/pubsub.subscriber >/dev/null

log "Deploying api (private)"
run run deploy quotelens-api --image "${IMAGE_BASE}/api:${TAG}" --region "$REGION" \
  --service-account "$(sa api)" --no-allow-unauthenticated \
  --cpu 1 --memory 1Gi --min-instances 0 --max-instances 3 --concurrency 40 --timeout 300 \
  --set-env-vars "${COMMON_ENV},APP_MODULE=app.main_api:app" "${SECRETS_ARG[@]}"
API_URL="$(url_of quotelens-api)"

log "Deploying web (public)"
run run deploy quotelens-web --image "${IMAGE_BASE}/web:${TAG}" --region "$REGION" \
  --service-account "$(sa web)" --allow-unauthenticated \
  --cpu 1 --memory 512Mi --min-instances 0 --max-instances 3 --concurrency 80 --timeout 300 \
  --set-env-vars "API_BASE_URL=${API_URL},API_AUDIENCE=${API_URL}"
run run services add-iam-policy-binding quotelens-api --region "$REGION" \
  --member "serviceAccount:$(sa web)" --role roles/run.invoker >/dev/null
# Organizations with domain-restricted sharing refuse the allUsers binding that
# --allow-unauthenticated relies on. Cloud Run's supported alternative for a public site
# is to switch off the invoker IAM check on that one service (api and worker stay private).
if ! gcloud run services get-iam-policy quotelens-web --region "$REGION" --project "$PROJECT_ID" \
     --format="value(bindings.members)" | grep -q allUsers; then
  log "Public access via allUsers was refused (organization policy); disabling the invoker check on web only"
  run run services update quotelens-web --region "$REGION" --no-invoker-iam-check >/dev/null
fi
WEB_URL="$(url_of quotelens-web)"

log "Smoke test"
curl -fsS "${WEB_URL}/" -o /dev/null && echo "web: OK"
curl -fsS "${WEB_URL}/api/v1/projects?limit=1" -o /dev/null && echo "web → api (ID token): OK"

echo
echo "Web:    ${WEB_URL}"
echo "API:    ${API_URL} (private)"
echo "Worker: ${WORKER_URL} (private)"
echo "Before the demo: PROJECT_ID=${PROJECT_ID} ./infra/demo-mode.sh on   (and 'off' afterwards)"
