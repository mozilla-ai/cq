#!/usr/bin/env bash
# migrate-team-db.sh — Create cq.db from an existing team.db.
#
# For users upgrading from the old team-server layout where the database was
# named team.db. Uses sqlite3 .backup to produce a consistent cq.db snapshot.
# The original team.db is left in place; a copy is also kept at
# team.db.pre-rename-backup for safety.
#
# Run from inside the container or directly on the host:
#   docker compose exec cq-server bash /app/scripts/migrate-team-db.sh
#   docker compose run --rm cq-server bash /app/scripts/migrate-team-db.sh
#   ./server/scripts/migrate-team-db.sh /path/to/data
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

echo "Created ${NEW_DB} from ${OLD_DB}."
