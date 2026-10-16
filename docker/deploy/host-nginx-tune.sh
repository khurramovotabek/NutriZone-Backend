#!/usr/bin/env bash
# Host nginx (in front of nutrizone.uz and api.nutrizone.uz) performance tuning -- idempotent, safe to re-run.
#   * HTTP/2 on the TLS listeners (nginx 1.24 syntax: "listen 443 ssl http2"): the home page loads ~40 images and
#     a dozen scripts, which HTTP/1.1 fetches over a handful of connections one after another.
# The site file stays certbot-compatible. A copy is kept and nginx is reloaded only when `nginx -t` passes;
# otherwise the copy is restored.
set -euo pipefail

SITE=${1:-/etc/nginx/sites-available/nutrizone}
[ -f "$SITE" ] || SITE=$(readlink -f /etc/nginx/sites-enabled/nutrizone)
BACKUP="$SITE.bak-$(date +%Y%m%d%H%M%S)"

if grep -qE '^\s*listen 443 ssl;' "$SITE"; then
  cp -a "$SITE" "$BACKUP"
  sed -i -E 's/^(\s*)listen 443 ssl;/\1listen 443 ssl http2;/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "HTTP/2 enabled (backup: $BACKUP)"
  else
    cp -a "$BACKUP" "$SITE"
    nginx -t
    echo "nginx -t failed -- restored $BACKUP" >&2
    exit 1
  fi
else
  echo "HTTP/2 already enabled"
fi
