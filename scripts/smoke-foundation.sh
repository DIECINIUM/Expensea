#!/bin/sh
set -eu

api_host="${API_HOST:-127.0.0.1}"
api_port="${API_PORT:-8000}"
web_host="${WEB_HOST:-127.0.0.1}"
web_port="${WEB_PORT:-5173}"
api_log="$(mktemp)"
web_log="$(mktemp)"
api_pid=""
web_pid=""

cleanup() {
    if [ -n "$web_pid" ]; then
        kill "$web_pid" 2>/dev/null || true
        wait "$web_pid" 2>/dev/null || true
    fi
    if [ -n "$api_pid" ]; then
        kill "$api_pid" 2>/dev/null || true
        wait "$api_pid" 2>/dev/null || true
    fi
    rm -f "$api_log" "$web_log"
}
trap cleanup EXIT INT TERM

wait_for_url() {
    url="$1"
    log_file="$2"
    attempts=0
    until curl --fail --silent --show-error "$url" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 30 ]; then
            echo "Timed out waiting for $url" >&2
            sed -n '1,160p' "$log_file" >&2
            return 1
        fi
        sleep 1
    done
}

.venv/bin/uvicorn app.main:app \
    --app-dir apps/api \
    --host "$api_host" \
    --port "$api_port" >"$api_log" 2>&1 &
api_pid="$!"

API_PORT="$api_port" npm --prefix apps/web run dev -- \
    --host "$web_host" \
    --port "$web_port" >"$web_log" 2>&1 &
web_pid="$!"

wait_for_url "http://$api_host:$api_port/health" "$api_log"
wait_for_url "http://$web_host:$web_port/" "$web_log"

graphql_response="$(
    curl --fail --silent --show-error \
        -H "content-type: application/json" \
        --data '{"query":"query FoundationStatus { health appInfo { name version environment } }"}' \
        "http://$web_host:$web_port/graphql"
)"

printf '%s' "$graphql_response" | .venv/bin/python -c '
import json
import os
import sys

payload = json.load(sys.stdin)
assert payload["data"]["health"] == "ok", payload
expected_name = os.environ.get("APP_NAME", "SpendGraph AI API")
assert payload["data"]["appInfo"]["name"] == expected_name, payload
'

echo "Foundation smoke passed: web /graphql proxy reached the API."
