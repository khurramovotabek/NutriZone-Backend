#!/usr/bin/env bash
# Host nginx (in front of nutrizone.uz and api.nutrizone.uz) performance tuning -- idempotent, safe to re-run.
#   * HTTP/2 on the TLS listeners (nginx 1.24 syntax: "listen 443 ssl http2"): the home page loads ~40 images and
#     a dozen scripts, which HTTP/1.1 fetches over a handful of connections one after another.
#   * www.nutrizone.uz → nutrizone.uz (301): one host, so search engines never index the same page twice.
#   * Upload size on the storefront host: uploads (avatar, review/chat media, store gallery, product-request photos)
#     go through Next's /api routes on nutrizone.uz, where nginx's 1 MB default answered 413 to ordinary photos.
#   * Paths with invalid UTF-8 %-escapes answer 400 (Next.js answered 500).
#   * Storefront upstream with a backup on :3001: deploy.sh runs a standby there while the live Next.js restarts.
#   * Disk cache for /_next/static and /_next/image (docker/nginx/host-assets-cache.conf): build assets and optimised
#     product photos come from nginx instead of Node.js on every request.
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

# Storefront upstream: the live Next.js on :3000, the deploy-time standby on :3001 as backup (idle otherwise).
cat > /etc/nginx/conf.d/nz-storefront-upstream.conf <<'CONF'
upstream nz_storefront {
    server 127.0.0.1:3000;
    server 127.0.0.1:3001 backup;
}
CONF
if ! grep -q 'nz-storefront-upstream' "$SITE"; then
  cp -a "$SITE" "$BACKUP.upstream"
  sed -i -E '0,/^(\s*)proxy_pass http:\/\/127\.0\.0\.1:3000;/s//\1proxy_pass http:\/\/nz_storefront;  # nz-storefront-upstream/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "storefront upstream with deploy standby (backup: $BACKUP.upstream)"
  else
    cp -a "$BACKUP.upstream" "$SITE"
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.upstream" >&2
    exit 1
  fi
else
  nginx -t 2>/dev/null && systemctl reload nginx
  echo "storefront upstream already in place"
fi

# Asset cache: cache zone + image-format key (http level), the two locations (server level, snippet refreshed each run).
mkdir -p /var/cache/nginx/nz_assets
chown www-data:www-data /var/cache/nginx/nz_assets 2>/dev/null || true
cat > /etc/nginx/conf.d/nz-assets-cache.conf <<'CONF'
proxy_cache_path /var/cache/nginx/nz_assets levels=1:2 keys_zone=nz_assets:20m max_size=3g inactive=30d use_temp_path=off;
map $http_accept $nz_img_fmt {
    ~*image/avif avif;
    ~*image/webp webp;
    default      other;
}
CONF
cp "$(dirname "$(readlink -f "$0")")/../nginx/host-assets-cache.conf" /etc/nginx/snippets/nz-assets-cache.conf
if ! grep -q 'nz-assets-cache' "$SITE"; then
  cp -a "$SITE" "$BACKUP.assets"
  sed -i -E '0,/^(\s*)include snippets\/nz-utf8-path\.conf;  # nz-utf8-path/s//\1include snippets\/nz-utf8-path.conf;  # nz-utf8-path\n\1include snippets\/nz-assets-cache.conf;  # nz-assets-cache/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "asset cache for /_next/static and /_next/image (backup: $BACKUP.assets)"
  else
    cp -a "$BACKUP.assets" "$SITE"
    rm -f /etc/nginx/conf.d/nz-assets-cache.conf
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.assets" >&2
    exit 1
  fi
else
  if nginx -t 2>/dev/null; then systemctl reload nginx; else nginx -t; exit 1; fi
  echo "asset cache already included (snippet refreshed)"
fi

# Page micro-cache: public storefront HTML for visitors without a session/cart cookie, ~20 s, refreshed in the
# background (docker/nginx/host-page-cache.conf explains what is never cached). Zone + skip rules at http level.
mkdir -p /var/cache/nginx/nz_pages
chown www-data:www-data /var/cache/nginx/nz_pages 2>/dev/null || true
cat > /etc/nginx/conf.d/nz-page-cache.conf <<'CONF'
proxy_cache_path /var/cache/nginx/nz_pages levels=1:2 keys_zone=nz_pages:20m max_size=1g inactive=10m use_temp_path=off;
# Any cookie the server reads to personalise a page -> straight to Next.js, never stored.
map $http_cookie $nz_page_cookie_skip {
    default 0;
    "~*(?:^|;\s*)(?:nz_access_token|nz_refresh_token|nz_cart_code|nz_cart_token|nz_embed|nz_ref)=" 1;
}
# The language a cookie picked (a /ru or /en address is already in $request_uri).
map $http_cookie $nz_page_locale {
    default uz;
    "~*(?:^|;\s*)nz_locale=(?<nz_l>[a-z]{2})" $nz_l;
}
# Only public catalogue/content pages; cart, checkout, account, profile, orders, wishlist, compare, login, /api ... never.
map $uri $nz_page_path_skip {
    default 1;
    "~^/(?:ru|en)?/?$" 0;
    "~^/(?:(?:ru|en)/)?(?:products|categories|brands|blog|guides|stores|store|about|contact|privacy|terms|loyalty)(?:/|$)" 0;
}
# RSC navigation/prefetch requests carry per-client router state -- only full HTML documents are cached.
map "$nz_page_cookie_skip$nz_page_path_skip:$http_rsc$http_next_router_prefetch:$request_method" $nz_page_skip {
    default 1;
    "00::GET" 0;
    "00::HEAD" 0;
}
CONF
cp "$(dirname "$(readlink -f "$0")")/../nginx/host-page-cache.conf" /etc/nginx/snippets/nz-page-cache.conf
if ! grep -q 'nz-page-cache' "$SITE"; then
  cp -a "$SITE" "$BACKUP.pages"
  sed -i -E '0,/^(\s*)include snippets\/nz-assets-cache\.conf;  # nz-assets-cache/s//\1include snippets\/nz-assets-cache.conf;  # nz-assets-cache\n\1include snippets\/nz-page-cache.conf;  # nz-page-cache/' "$SITE"
  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    echo "page micro-cache for public storefront pages (backup: $BACKUP.pages)"
  else
    cp -a "$BACKUP.pages" "$SITE"
    rm -f /etc/nginx/conf.d/nz-page-cache.conf
    nginx -t
    echo "nginx -t failed -- restored $BACKUP.pages" >&2
    exit 1
  fi
else
  if nginx -t 2>/dev/null; then systemctl reload nginx; else nginx -t; exit 1; fi
  echo "page micro-cache already included (snippet refreshed)"
fi
