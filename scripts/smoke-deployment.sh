#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "Usage: sh scripts/smoke-deployment.sh https://YOUR_HOSTNAME" >&2
    exit 1
fi
case "$1" in
    https://*) ;;
    *) echo "Deployment smoke requires HTTPS." >&2; exit 1 ;;
esac
origin=${1%/}
curl --fail --silent --show-error --max-time 15 "$origin/health" > /dev/null
curl --fail --silent --show-error --max-time 15 "$origin/ready" | grep -q '"status":"ready"'
curl --fail --silent --show-error --max-time 15 "$origin/" | grep -q '<div id="root">'
echo "HTTPS web, API liveness, and database readiness passed."
