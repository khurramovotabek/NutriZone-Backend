#!/bin/sh
# Daily PostgreSQL backup for docker-compose.prod.yml's `db_backup` service.
# Writes a compressed custom-format dump (pg_restore-able) every BACKUP_INTERVAL_SECONDS and keeps
# BACKUP_KEEP_DAYS days of them in the `backups` volume. Restore:
#   docker compose exec db_backup sh -c 'pg_restore --clean --if-exists -d "$POSTGRES_DB" /backups/<file>.dump'
set -eu

: "${BACKUP_INTERVAL_SECONDS:=86400}"
: "${BACKUP_KEEP_DAYS:=14}"
export PGPASSWORD="$POSTGRES_PASSWORD" PGHOST="${POSTGRES_HOST:-db}" PGUSER="$POSTGRES_USER"

while true; do
    stamp=$(date -u +%Y%m%d-%H%M%S)
    target="/backups/${POSTGRES_DB}-${stamp}.dump"
    if pg_dump -Fc -d "$POSTGRES_DB" -f "${target}.part"; then
        mv "${target}.part" "$target"
        echo "[backup] $(date -u +%FT%TZ) wrote $target ($(du -h "$target" | cut -f1))"
    else
        rm -f "${target}.part"
        echo "[backup] $(date -u +%FT%TZ) pg_dump FAILED" >&2
    fi
    find /backups -name "*.dump" -mtime +"$BACKUP_KEEP_DAYS" -delete
    sleep "$BACKUP_INTERVAL_SECONDS"
done
