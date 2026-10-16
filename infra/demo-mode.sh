#!/usr/bin/env bash
# Keep web and api warm only for the demo window (min-instances=1 bills while idle).
#
# Usage: PROJECT_ID=my-project ./infra/demo-mode.sh on|off
set -euo pipefail

: "${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-us-central1}"
MODE="${1:-}"

case "$MODE" in
  on) MIN=1 ;;
  off) MIN=0 ;;
  *) echo "Usage: $0 on|off" >&2; exit 2 ;;
esac

for service in quotelens-web quotelens-api; do
  echo "==> $service: min-instances=$MIN"
  gcloud run services update "$service" --project="$PROJECT_ID" --region="$REGION" \
    --min-instances="$MIN" --quiet
done
[[ "$MIN" == 1 ]] && echo "Remember: run '$0 off' right after the demo."
exit 0
