#!/usr/bin/env bash
# backup-db.sh — Snapshot the cq server database to a timestamped local directory.
#
# Usage:
#   ./server/scripts/backup-db.sh
#   make backup-db
#
# Uses sqlite3 .backup inside the container to produce a consistent snapshot,
# then copies it to $XDG_DATA_HOME/cq/backup/<timestamp>/.

set -euo pipefail

if [[ -n "${XDG_DATA_HOME:-}" && "$XDG_DATA_HOME" == /* ]]; then
    data_home="$XDG_DATA_HOME"
else
    data_home="$HOME/.local/share"
fi

ts=$(date -u +"%Y%m%dT%H%M%SZ")
dest="${data_home}/cq/backup/${ts}"
mkdir -p "$dest"

# Produce a consistent snapshot inside the container, then copy it out.
docker compose exec -T cq-server sqlite3 /data/cq.db ".backup /data/cq.db.backup"
docker compose cp cq-server:/data/cq.db.backup "$dest/cq.db"
docker compose exec -T cq-server rm /data/cq.db.backup

echo "Backed up to ${dest}"
