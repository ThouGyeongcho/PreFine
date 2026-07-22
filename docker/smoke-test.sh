#!/usr/bin/env bash
set -Eeuo pipefail

image="${1:?usage: smoke-test.sh IMAGE}"
container=""
smoke_dir=""
base_url=""
last_health_http_code="not attempted"
last_health_body="<empty>"
last_health_curl_error="<none>"

cleanup() {
  if [ -n "${container:-}" ]; then
    docker rm --force "$container" >/dev/null 2>&1 || true
  fi
  if [ -n "${smoke_dir:-}" ]; then
    rm -rf "$smoke_dir"
  fi
}

smoke_dir="$(mktemp -d "${RUNNER_TEMP:-/tmp}/prefine-smoke.XXXXXX")"
trap cleanup EXIT

container="prefine-smoke-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}"
cookie_jar="$smoke_dir/cookies.txt"
credentials_file="$smoke_dir/credentials.env"
admin_password="$(openssl rand -hex 24)"
session_secret="$(openssl rand -hex 32)"
umask 077
printf 'ADMIN_USERNAME=admin\nADMIN_PASSWORD=%s\nSESSION_SECRET=%s\n' \
  "$admin_password" "$session_secret" >"$credentials_file"

docker run --detach --name "$container" \
  --publish 127.0.0.1::8000 \
  --env PUID="$(id -u)" \
  --env PGID="$(id -g)" \
  --env-file "$credentials_file" \
  --env DATA_DIR=/data \
  --volume "$smoke_dir:/data" \
  "$image" >/dev/null

stage_marker() {
  printf 'prefine smoke: %s\n' "$1"
}

refresh_base_url() {
  local port
  port="$(docker port "$container" 8000/tcp | sed -n 's/.*://p')"
  test -n "$port"
  base_url="http://127.0.0.1:$port"
}

print_health_diagnostics() {
  local stage="${1:?health stage is required}"

  echo "prefine smoke health timeout: stage=$stage" >&2
  printf 'last HTTP code: %s\n' "$last_health_http_code" >&2
  printf 'last /api/health response body: %s\n' "$last_health_body" >&2
  printf 'last curl error: %s\n' "$last_health_curl_error" >&2
  docker inspect --format 'State={{json .State}} Health={{json .State.Health}}' \
    "$container" >&2 || true
  docker top "$container" >&2 || true
  docker port "$container" >&2 || true
  docker logs --timestamps "$container" >&2 || true
}

wait_for_health() {
  local stage="${1:?health stage is required}"
  local health_body_file="$smoke_dir/health-body-$stage.txt"
  local health_error_file="$smoke_dir/health-error-$stage.txt"
  local health_http_code

  for _ in $(seq 1 60); do
    : >"$health_body_file"
    : >"$health_error_file"
    health_http_code=""
    if health_http_code="$(curl --silent --show-error \
      --connect-timeout 2 \
      --max-time 5 \
      --output "$health_body_file" \
      --write-out '%{http_code}' \
      "$base_url/api/health" 2>"$health_error_file")"; then
      :
    fi
    last_health_http_code="${health_http_code:-000}"
    last_health_body="$(cat "$health_body_file")"
    last_health_curl_error="$(cat "$health_error_file")"
    if [ "$last_health_http_code" = "200" ] && \
      jq -e '.status == "ok"' "$health_body_file" >/dev/null 2>&1; then
      stage_marker "$stage healthy"
      return 0
    fi
    sleep 2
  done
  print_health_diagnostics "$stage"
  return 1
}

refresh_base_url
wait_for_health initial
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
stage_marker "settings saved"

stage_marker "restart beginning"
docker restart "$container" >/dev/null
refresh_base_url
stage_marker "restart completed"
wait_for_health restart
jq -nc --arg password "$admin_password" \
  '{username:"admin",password:$password}' | curl --fail --silent --cookie-jar "$cookie_jar" \
  --header 'Content-Type: application/json' \
  --data @- \
  "$base_url/api/auth/login" >/dev/null
curl --fail --silent --cookie "$cookie_jar" \
  "$base_url/api/tools/tax/settings" | jq -e '.reminder_days == [9,4]' >/dev/null
stage_marker "persistence verified"
