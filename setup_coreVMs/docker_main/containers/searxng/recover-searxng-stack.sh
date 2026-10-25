#!/usr/bin/env bash
set -euo pipefail

# Watchtower updates the images. This job repairs the shared network namespace
# after either container is replaced, and also recovers a failed health check.
PATH=/usr/local/bin:/usr/bin:/bin
export PATH
umask 077

compose_file=${SEARXNG_COMPOSE_FILE:-/home/fenkil/pcData/searxng/docker-compose.yml}
state_dir=${SEARXNG_STATE_DIR:-/var/lib/searxng-recovery}
lock_file=${SEARXNG_LOCK_FILE:-/run/lock/searxng-recovery.lock}
health_url=${SEARXNG_HEALTH_URL:-http://127.0.0.1:8888/}
state_file="$state_dir/container-ids"

log() { printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"; }
fail() { log "ERROR: $*" >&2; exit 1; }
compose() { docker-compose -f "$compose_file" "$@"; }
service_id() { compose ps -a -q "$1"; }
gluetun_healthy() {
  local id=$1
  [[ -n "$id" ]] &&
    [[ "$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}' "$id" 2>/dev/null)" == healthy ]]
}
search_responding() { curl --fail --silent --show-error --output /dev/null --max-time 8 "$health_url"; }

exec 9>"$lock_file"
flock -n 9 || exit 0
[[ -f "$compose_file" ]] || fail "Compose file missing: $compose_file"
mkdir -p "$state_dir"

# Let Watchtower finish a replacement before reading the container IDs.
previous_snapshot=''
for ((attempt = 0; attempt < 24; attempt++)); do
  gluetun_id=$(service_id gluetun)
  searxng_id=$(service_id searxng)
  snapshot="$gluetun_id:$searxng_id"
  if [[ -n "$gluetun_id" && -n "$searxng_id" && "$snapshot" == "$previous_snapshot" ]]; then
    break
  fi
  previous_snapshot=$snapshot
  sleep 5
done
[[ -n "$gluetun_id" && -n "$searxng_id" && "$snapshot" == "$previous_snapshot" ]] ||
  fail 'Both containers must exist and have stable IDs before recovery'

old_gluetun_id=''
old_searxng_id=''
if [[ -f "$state_file" ]]; then
  { read -r old_gluetun_id || true; read -r old_searxng_id || true; } < "$state_file"
fi

gluetun_changed=false
searxng_changed=false
if [[ -n "$old_gluetun_id" && "$gluetun_id" != "$old_gluetun_id" ]]; then gluetun_changed=true; fi
if [[ -n "$old_searxng_id" && "$searxng_id" != "$old_searxng_id" ]]; then searxng_changed=true; fi

vpn_healthy=false
search_healthy=false
if gluetun_healthy "$gluetun_id"; then vpn_healthy=true; fi
if search_responding; then search_healthy=true; fi

if [[ "$gluetun_changed" == true || "$searxng_changed" == true || "$vpn_healthy" == false || "$search_healthy" == false ]]; then
  log "Recovering SearXNG pair (gluetun changed=$gluetun_changed, searxng changed=$searxng_changed, VPN healthy=$vpn_healthy, search responding=$search_healthy)"

  # A SearXNG-only update can leave the VPN unhealthy. A new Gluetun
  # container has already restarted, so first give its tunnel time to settle.
  if [[ "$gluetun_changed" == true && "$vpn_healthy" == false ]]; then
    for ((attempt = 0; attempt < 6; attempt++)); do
      sleep 5
      if gluetun_healthy "$(service_id gluetun)"; then break; fi
    done
  fi
  if [[ "$gluetun_changed" == false ]] || ! gluetun_healthy "$(service_id gluetun)"; then
    compose restart gluetun || fail 'Could not restart Gluetun'
  fi

  for ((attempt = 0; attempt < 36; attempt++)); do
    gluetun_id=$(service_id gluetun)
    if gluetun_healthy "$gluetun_id"; then break; fi
    sleep 5
  done
  gluetun_healthy "$gluetun_id" || fail 'Gluetun did not become healthy within 180 seconds'

  # Recreate rather than merely restart so SearXNG joins the current
  # Gluetun network namespace even when Watchtower replaced Gluetun.
  compose up -d --no-deps --force-recreate searxng || fail 'Could not recreate SearXNG'
  for ((attempt = 0; attempt < 18; attempt++)); do
    if search_responding; then break; fi
    sleep 5
  done
  search_responding || fail 'SearXNG did not respond within 90 seconds'
  [[ "$(service_id gluetun)" == "$gluetun_id" ]] || fail 'Gluetun changed again during recovery'
  gluetun_healthy "$gluetun_id" || fail 'Gluetun became unhealthy during recovery'
  log 'SearXNG pair recovered'
fi

# Update state only after a successful check. An interrupted recovery will be
# retried on the next scheduled run.
gluetun_id=$(service_id gluetun)
searxng_id=$(service_id searxng)
[[ -n "$gluetun_id" && -n "$searxng_id" ]] || fail 'Container ID missing after recovery'
printf '%s\n%s\n' "$gluetun_id" "$searxng_id" > "$state_file.new"
mv -f "$state_file.new" "$state_file"
