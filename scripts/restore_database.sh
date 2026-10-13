#!/usr/bin/env bash
# ============================================================================
# NutriZone PostgreSQL restore script -- Phase 15B.
#
# CRITICAL SAFETY RULE: this script restores into TARGET_DB, which must be
# explicitly named by the caller and must NEVER be the production database.
# It does not infer a target from POSTGRES_DB or any other "default"
# variable, specifically to prevent an accidental production overwrite.
#
# Usage:
#   POSTGRES_HOST=... POSTGRES_PORT=... POSTGRES_USER=... PGPASSWORD=... \
#   ./restore_database.sh <backup_file> <target_db>
# ============================================================================
set -euo pipefail

BACKUP_FILE="${1:?Usage: restore_database.sh <backup_file> <target_db>}"
TARGET_DB="${2:?Usage: restore_database.sh <backup_file> <target_db>}"
POSTGRES_HOST="${POSTGRES_HOST:?POSTGRES_HOST must be set}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:?POSTGRES_USER must be set}"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "[restore] ERROR: backup file '${BACKUP_FILE}' does not exist." >&2
    exit 1
fi

echo "[restore] Restoring ${BACKUP_FILE} into database '${TARGET_DB}' at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
echo "[restore] (TARGET_DB must already exist and be empty -- this script does not create or drop databases.)"

if ! pg_restore \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --no-password \
    --dbname="$TARGET_DB" \
    --no-owner \
    --no-privileges \
    "$BACKUP_FILE"; then
    echo "[restore] WARNING: pg_restore reported errors -- inspect output above (some are expected for extension-owned objects; verify actual data below)." >&2
fi

echo "[restore] Restore command completed. Run application-level verification against '${TARGET_DB}' next."
