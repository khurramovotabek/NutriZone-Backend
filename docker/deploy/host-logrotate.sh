#!/usr/bin/env bash
# Host logrotate for the Django log files on the `app_logs` volume (errors.log, api.log, audit.log ...).
# In production the app only appends (WatchedFileHandler, LOG_ROTATION=external) -- every gunicorn worker, web replica
# and Celery process writes the same files, so rotating from inside Python would race. Idempotent; deploy.sh runs it.
set -euo pipefail

CONF=/etc/logrotate.d/nutrizone
DIR=/var/lib/docker/volumes/nutrizone-prod_app_logs/_data
WANT=$(cat <<CFG
# managed by /opt/nutrizone/backend/docker/deploy/host-logrotate.sh -- edit there
$DIR/*.log {
    daily
    maxsize 50M
    rotate 30
    dateext
    compress
    delaycompress
    missingok
    notifempty
    create 0644 1000 1000
}
CFG
)

if [ "$(cat "$CONF" 2>/dev/null || true)" != "$WANT" ]; then
  printf '%s\n' "$WANT" > "$CONF"
  echo "logrotate: wrote $CONF"
fi
logrotate --debug "$CONF" >/dev/null 2>&1 || { echo "logrotate: $CONF does not parse" >&2; logrotate --debug "$CONF" >&2; exit 1; }
echo "logrotate: $CONF ok"
