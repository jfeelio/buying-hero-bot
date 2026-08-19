#!/usr/bin/env bash
# Build, test, and publish the console to the n8n box.
#   bash deploy.sh
# Served by Caddy from /srv/dispo (bind-mounted from /opt/n8n/static/dispo)
# at https://automations.buyinghero.com/dispo/
set -euo pipefail
cd "$(dirname "$0")"

ZONE=us-east1-b
VM=n8n-vm
REMOTE=/opt/n8n/static/dispo/index.html

python build.py
node smoke.js
node contract-test.js

gcloud compute scp dist/index.html "$VM:/tmp/dispo-index.html" --zone="$ZONE"
gcloud compute ssh "$VM" --zone="$ZONE" --command="
  sudo cp $REMOTE $REMOTE.bak-\$(date +%Y%m%d-%H%M%S) 2>/dev/null || true
  sudo cp /tmp/dispo-index.html $REMOTE
  sudo chmod 644 $REMOTE
"
curl -sfo /dev/null -w 'live: HTTP %{http_code}, %{size_download} bytes\n' \
  https://automations.buyinghero.com/dispo/
