#!/usr/bin/env bash
# migrate-team-db.sh — Migrate team.db to cq.db inside the server data volume.
#
# Run from inside the container (via docker compose exec or run) or directly
# if the data directory is accessible on the host.
#
# Usage:
#   docker compose exec cq-server bash /app/scripts/migrate-team-db.sh
#   docker compose run --rm cq-server bash /app/scripts/migrate-team-db.sh
#   ./server/scripts/migrate-team-db.sh /path/to/data   # Direct host access.
#
# Uses sqlite3 .backup to produce a consistent cq.db from team.db.
# A copy of team.db is kept as team.db.pre-rename-backup.
#
# Idempotent: safe to run multiple times.

set -euo pipefail

DATA_DIR="${1:-/data}"

OLD_DB="${DATA_DIR}/team.db"
NEW_DB="${DATA_DIR}/cq.db"
BACKUP="${OLD_DB}.pre-rename-backup"

if [[ -f "$NEW_DB" ]]; then
    echo "cq.db already exists at ${NEW_DB} — nothing to do."
    exit 0
fi

if [[ ! -f "$OLD_DB" ]]; then
    echo "No team.db found at ${OLD_DB} — nothing to migrate."
    exit 0
fi

# Keep a backup of the original.
if [[ ! -f "$BACKUP" ]]; then
    cp "$OLD_DB" "$BACKUP"
    echo "Backup created at ${BACKUP}."
fi

# Produce a consistent snapshot as cq.db.
sqlite3 "$OLD_DB" ".backup '${NEW_DB}'"

# Clean up old WAL/SHM files.
rm -f "${OLD_DB}-wal" "${OLD_DB}-shm"

echo "Migrated ${OLD_DB} → ${NEW_DB}."
