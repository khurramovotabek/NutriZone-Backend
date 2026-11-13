#!/usr/bin/env bash
# Pre-encode product photos so no shopper waits for next/image: a cold AVIF encode is 0.6-1.2 s per photo and size
# (WebP 0.2-0.3 s), measured on the server 2026-11-13. Reads the product URLs from the sitemap, takes the exact
# /_next/image URLs each page's srcset asks for (the widths phones and desktops really pick: 640, 828, 1080) and
# requests them once per format through the public host, so both nginx's asset cache and Next's own cache fill.
# Low concurrency on purpose -- it runs beside live traffic. Usage: warm-images.sh [site] [parallel]
set -uo pipefail
SITE="${1:-https://nutrizone.uz}"
PAR="${2:-2}"
WIDTHS='w=(640|828|1080)&'
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsS "$SITE/sitemap.xml" | grep -o "<loc>[^<]*/products/[^<]*</loc>" | sed 's#</\?loc>##g' | sort -u | head -n "${LIMIT:-100000}" > "$TMP/pages"
echo "pages: $(wc -l < "$TMP/pages")"
while read -r page; do
  curl -fsS "$page" 2>/dev/null | grep -oE '/_next/image\?url=[^" ,]+' | sed 's/&amp;/\&/g' | grep -E "$WIDTHS" || true
done < "$TMP/pages" | sort -u > "$TMP/images"
echo "image urls: $(wc -l < "$TMP/images")"

warm() {
  local fmt="$1"
  xargs -P "$PAR" -I{} curl -s -o /dev/null -w "%{http_code} %{time_total}\n" -H "Accept: image/$fmt,image/*" "$SITE{}" < "$TMP/images" > "$TMP/out.$fmt"
  awk -v f="$fmt" '{n++; t+=$2; if ($1!=200) bad++} END {printf "%s: %d requests, %.0f s total, %d not 200\n", f, n, t, bad}' "$TMP/out.$fmt"
}
warm avif
warm webp
