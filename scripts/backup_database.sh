#!/usr/bin/env bash
# ============================================================================
# NutriZone PostgreSQL backup script -- Phase 15B.
#
# Usage:
#   POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_DB=... POSTGRES_USER=... \
#   PGPASSWORD=... ./backup_database.sh [output_dir]
#
# Credentials are read from the standard PostgreSQL environment variables
# (PGPASSWORD, or a .pgpass file) -- never hardcoded, never accepted as a
# command-line argument (which would leak into shell history / process
# listings), and never echoed or logged by this script.
# ============================================================================
set -euo pipefail

OUTPUT_DIR="${1:-./backups}"
POSTGRES_HOST="${POSTGRES_HOST:?POSTGRES_HOST must be set}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:?POSTGRES_DB must be set}"
POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER must be set}"

mkdir -p "$OUTPUT_DIR"

TIMESTAMP="$(date -u +%Y-%m-%d_%H-%M-%S)"
# Filename contains only the DB name and a timestamp -- never the host,
# user, or any credential material.
BACKUP_FILE="${OUTPUT_DIR}/nutrizone_${TIMESTAMP}.dump"

if [ -e "$BACKUP_FILE" ]; then
    echo "[backup] ERROR: ${BACKUP_FILE} already exists -- refusing to overwrite." >&2
    exit 1
fi

echo "[backup] Starting backup of database '${POSTGRES_DB}' to ${BACKUP_FILE}..."

# Custom format (-Fc): compressed, supports selective restore and
# pg_restore --list inspection, and correctly captures PostGIS extension
# objects (the extension itself is recreated via CREATE EXTENSION on
# restore into a postgis/postgis-based target, not dumped as raw rows).
if ! pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --format=custom \
    --no-password \
    --file="$BACKUP_FILE" \
    "$POSTGRES_DB"; then
    echo "[backup] ERROR: pg_dump failed. Removing any partial output file." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

if [ ! -s "$BACKUP_FILE" ]; then
    echo "[backup] ERROR: backup file was created but is empty." >&2
    rm -f "$BACKUP_FILE"
    exit 1
fi

# Verify the archive is genuinely readable by PostgreSQL's own tooling --
# a non-empty file alone does not prove a valid backup.
if ! pg_restore --list "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "[backup] ERROR: backup file exists but pg_restore cannot read its table of contents." >&2
    exit 1
fi

SIZE="$(du -h "$BACKUP_FILE" | cut -f1)"
echo "[backup] SUCCESS: ${BACKUP_FILE} (${SIZE}), verified readable by pg_restore."
