#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:?usage: smoke-test.sh IMAGE}"
smoke_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/prefine-smoke.XXXXXX")"
container="prefine-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
cookie_jar="$smoke_dir/cookies.txt"
credentials_file="$smoke_dir/credentials.env"
admin_password="$(openssl rand -hex 24)"
session_secret="$(openssl rand -hex 32)"
umask 077
printf 'ADMIN_USERNAME=admin\nADMIN_PASSWORD=%s\nSESSION_SECRET=%s\n' \
  "$admin_password" "$session_secret" >"$credentials_file"

cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
  rm -rf "$smoke_dir"
}
trap cleanup EXIT

docker run --detach --name "$container" \
  --publish 127.0.0.1::8000 \
  --env PUID="$(id -u)" \
  --env PGID="$(id -g)" \
  --env-file "$credentials_file" \
  --env DATA_DIR=/data \
  --volume "$smoke_dir:/data" \
  "$image" >/dev/null

port="$(docker port "$container" 8000/tcp | sed -n 's/.*://p')"
base_url="http://127.0.0.1:$port"

wait_for_health() {
  for _ in $(seq 1 60); do
    if curl --fail --silent "$base_url/api/health" | jq -e '.status == "ok"' >/dev/null; then
      return 0
    fi
    sleep 2
  done
  docker logs "$container"
  return 1
}

wait_for_health
test "$(docker exec "$container" awk '/^Uid:/{print $2}' /proc/1/status)" != "0"
test -s "$smoke_dir/prefine.db"

jq -nc --arg password "$admin_password" \
  '{username:"admin",password:$password}' | curl --fail --silent --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data @- \
  "$base_url/api/auth/login" >/dev/null

curl --fail --silent --cookie "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --header "Origin: $base_url" \
  --request PUT \
  --data '{"default_mode":"personalized","taxpayer_type":"general_taxpayer","selected_item_codes":["vat"],"default_region_code":"111000000","reminder_days":[9,4]}' \
  "$base_url/api/tools/tax/settings" | jq -e '.reminder_days == [9,4]' >/dev/null

docker restart "$container" >/dev/null
wait_for_health
jq -nc --arg password "$admin_password" \
  '{username:"admin",password:$password}' | curl --fail --silent --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data @- \
  "$base_url/api/auth/login" >/dev/null
curl --fail --silent --cookie "$cookie_jar" \
  "$base_url/api/tools/tax/settings" | jq -e '.reminder_days == [9,4]' >/dev/null
