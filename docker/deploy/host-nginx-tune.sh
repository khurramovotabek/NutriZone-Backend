#!/usr/bin/env bash
# Host nginx (in front of nutrizone.uz and api.nutrizone.uz) performance tuning -- idempotent, safe to re-run.
#   * HTTP/2 on the TLS listeners (nginx 1.24 syntax: "listen 443 ssl http2"): the home page loads ~40 images and
#     a dozen scripts, which HTTP/1.1 fetches over a handful of connections one after another.
#   * www.nutrizone.uz → nutrizone.uz (301): one host, so search engines never index the same page twice.
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

# One canonical host: www.nutrizone.uz answers with a permanent redirect to nutrizone.uz.
if ! grep -q 'nz-www-redirect' "$SITE"; then
  cp -a "$SITE" "$BACKUP.www"
  sed -i -E '0,/^(\s*)server_name nutrizone\.uz www\.nutrizone\.uz;/s//\1server_name nutrizone.uz www.nutrizone.uz;\n\1if ($host = www.nutrizone.uz) { return 301 https:\/\/nutrizone.uz$request_uri; }  # nz-www-redirect/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "www → apex redirect enabled (backup: $BACKUP.www)"
  else
    cp -a "$BACKUP.www" "$SITE"
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.www" >&2
    exit 1
  fi
else
  echo "www → apex redirect already enabled"
fi
