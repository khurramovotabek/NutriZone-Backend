#!/usr/bin/env bash
# Daily host-level backup step (systemd timer nutrizone-offsite.timer, 05:30 Asia/Tashkent):
#   1. media archive  -- product / banner / store images live only in the media_volume; the db_backup service dumps
#      PostgreSQL but never the files. A tar.gz goes to /var/backups/nutrizone (kept MEDIA_KEEP days).
#   2. offsite copy   -- when /etc/nutrizone/offsite.env sets RCLONE_REMOTE (any rclone remote: S3, Backblaze B2,
#      Google Drive, ...), the latest DB dumps and media archives are copied there, older than REMOTE_KEEP_DAYS
#      removed. Without it the step is skipped (local copies still made) and the status says so.
#   3. status + alert -- /var/lib/nutrizone/offsite.status for /root/healthcheck.sh; a failure is sent to the
#      analytics bot chat (TELEGRAM_ANALYTICS_BOT_TOKEN / TELEGRAM_ANALYTICS_CHAT_IDS from the backend .env).
#
# Setup of a remote (once):  rclone config  -> name it e.g. "offsite", then in /etc/nutrizone/offsite.env:
#   RCLONE_REMOTE=offsite:nutrizone-backups
#   REMOTE_KEEP_DAYS=30
set -uo pipefail

ROOT=/opt/nutrizone/backend
LOCAL=/var/backups/nutrizone
STATUS_DIR=/var/lib/nutrizone
MEDIA_KEEP=${MEDIA_KEEP:-7}
mkdir -p "$LOCAL" "$STATUS_DIR"
[ -f /etc/nutrizone/offsite.env ] && . /etc/nutrizone/offsite.env
REMOTE_KEEP_DAYS=${REMOTE_KEEP_DAYS:-30}

envval() { grep -E "^$1=" "$ROOT/.env" | head -1 | cut -d= -f2-; }
alert() {
  local token chat
  token=$(envval TELEGRAM_ANALYTICS_BOT_TOKEN); chat=$(envval TELEGRAM_ANALYTICS_CHAT_IDS | cut -d, -f1 | tr -d ' ')
  [ -n "$token" ] && [ -n "$chat" ] && curl -fsS -m 15 -o /dev/null "https://api.telegram.org/bot${token}/sendMessage" \
    --data-urlencode "chat_id=${chat}" --data-urlencode "text=⚠️ NutriZone zaxira: $1" || true
}
status() { printf '%s %s %s\n' "$(date -u +%FT%TZ)" "$1" "$2" > "$STATUS_DIR/offsite.status"; echo "[offsite] $1 $2"; }

stamp=$(date -u +%Y%m%d-%H%M%S)
volume_path() { docker volume inspect -f '{{ .Mountpoint }}' "$1" 2>/dev/null; }
MEDIA=$(volume_path nutrizone-prod_media_volume)
DUMPS=$(volume_path nutrizone-prod_backups)

# 1) media archive
if [ -n "$MEDIA" ] && [ -d "$MEDIA" ]; then
  if tar -C "$MEDIA" -czf "$LOCAL/media-$stamp.tar.gz.part" . && mv "$LOCAL/media-$stamp.tar.gz.part" "$LOCAL/media-$stamp.tar.gz"; then
    echo "[offsite] media archive $(du -h "$LOCAL/media-$stamp.tar.gz" | cut -f1)"
  else
    rm -f "$LOCAL/media-$stamp.tar.gz.part"; status FAIL "media-archive"; alert "media arxivi yaratilmadi"; exit 1
  fi
  find "$LOCAL" -name 'media-*.tar.gz' -mtime +"$MEDIA_KEEP" -delete
fi

# 2) offsite copy
if [ -z "${RCLONE_REMOTE:-}" ]; then
  status SKIPPED "offsite-not-configured (local: $LOCAL)"; exit 0
fi
if ! command -v rclone >/dev/null; then
  status FAIL "rclone-missing"; alert "rclone o'rnatilmagan"; exit 1
fi
ok=1
[ -n "$DUMPS" ] && rclone copy "$DUMPS" "$RCLONE_REMOTE/db" --include '*.dump' --max-age 48h || ok=0
rclone copy "$LOCAL" "$RCLONE_REMOTE/media" --include 'media-*.tar.gz' --max-age 48h || ok=0
rclone delete "$RCLONE_REMOTE" --min-age "${REMOTE_KEEP_DAYS}d" || true
if [ "$ok" = 1 ]; then
  status OK "$RCLONE_REMOTE"
else
  status FAIL "rclone-copy"; alert "offsite nusxa ($RCLONE_REMOTE) yuborilmadi"; exit 1
fi
