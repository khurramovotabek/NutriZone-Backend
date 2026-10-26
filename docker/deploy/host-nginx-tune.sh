#!/usr/bin/env bash
# Host nginx (in front of nutrizone.uz and api.nutrizone.uz) performance tuning -- idempotent, safe to re-run.
#   * HTTP/2 on the TLS listeners (nginx 1.24 syntax: "listen 443 ssl http2"): the home page loads ~40 images and
#     a dozen scripts, which HTTP/1.1 fetches over a handful of connections one after another.
#   * www.nutrizone.uz → nutrizone.uz (301): one host, so search engines never index the same page twice.
#   * Upload size on the storefront host: uploads (avatar, review/chat media, store gallery, product-request photos)
#     go through Next's /api routes on nutrizone.uz, where nginx's 1 MB default answered 413 to ordinary photos.
#   * Paths with invalid UTF-8 %-escapes answer 400 (Next.js answered 500).
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

# Storefront uploads pass through nutrizone.uz (Next /api routes) -- same ceiling as api.nutrizone.uz.
if ! grep -q 'nz-upload-size' "$SITE"; then
  cp -a "$SITE" "$BACKUP.upload"
  sed -i -E '0,/^(\s*)server_name nutrizone\.uz www\.nutrizone\.uz;/s//\1server_name nutrizone.uz www.nutrizone.uz;\n\1client_max_body_size 50M;  # nz-upload-size/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "storefront upload limit 50M (backup: $BACKUP.upload)"
  else
    cp -a "$BACKUP.upload" "$SITE"
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.upload" >&2
    exit 1
  fi
else
  echo "storefront upload limit already set"
fi

# A path whose %-escapes are not valid UTF-8 (/.env%A0 from scanners) crashes Next.js's 400 page into a 500;
# host nginx answers 400 itself (docker/nginx/host-utf8-path.conf). The snippet is refreshed on every run.
SNIPPET=/etc/nginx/snippets/nz-utf8-path.conf
mkdir -p /etc/nginx/snippets
cp "$(dirname "$(readlink -f "$0")")/../nginx/host-utf8-path.conf" "$SNIPPET"
if ! grep -q 'nz-utf8-path' "$SITE"; then
  cp -a "$SITE" "$BACKUP.utf8"
  sed -i -E '0,/^(\s*)server_name nutrizone\.uz www\.nutrizone\.uz;/s//\1server_name nutrizone.uz www.nutrizone.uz;\n\1include snippets\/nz-utf8-path.conf;  # nz-utf8-path/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "invalid UTF-8 paths answer 400 (backup: $BACKUP.utf8)"
  else
    cp -a "$BACKUP.utf8" "$SITE"
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.utf8" >&2
    exit 1
  fi
else
  nginx -t 2>/dev/null && systemctl reload nginx
  echo "invalid UTF-8 path rule already included (snippet refreshed)"
fi
