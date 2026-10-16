#!/usr/bin/env bash
# Copy distributor API keys from services/api/.env into Secret Manager (values never printed).
# Free tier: 6 active secret versions; this uses at most 4 (old versions are disabled).
#
# Usage: PROJECT_ID=my-project ./infra/secrets.sh
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
ENV_FILE="${ENV_FILE:-services/api/.env}"
[[ -f "$ENV_FILE" ]] || { echo "No $ENV_FILE found"; exit 1; }

value_of() {
  # Last assignment wins; strips surrounding quotes. Never echoes the value.
  grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//"
}

store() {
  local env_name="$1" secret="$2" value
  value="$(value_of "$env_name")"
  if [[ -z "${value// }" ]]; then
    echo "skip    $secret ($env_name is empty)"
    return
  fi
  if ! gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets create "$secret" --project="$PROJECT_ID" --replication-policy=automatic >/dev/null
  fi
  printf '%s' "$value" | gcloud secrets versions add "$secret" --project="$PROJECT_ID" --data-file=- >/dev/null
  # Keep only the newest version enabled (free tier counts active versions).
  gcloud secrets versions list "$secret" --project="$PROJECT_ID" --filter="state=ENABLED" \
      --format="value(name)" --sort-by="~createTime" | tail -n +2 | while read -r old; do
    gcloud secrets versions disable "$old" --secret="$secret" --project="$PROJECT_ID" --quiet >/dev/null
  done
  echo "stored  $secret"
}

store DIGIKEY_CLIENT_ID digikey-client-id
store DIGIKEY_CLIENT_SECRET digikey-client-secret
store MOUSER_API_KEY mouser-api-key
store ELEMENT14_API_KEY element14-api-key
