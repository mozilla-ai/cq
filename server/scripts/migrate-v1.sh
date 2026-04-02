#!/usr/bin/env bash
# migrate-v1.sh — Migrate pre-v1 cq local databases to v1 format.
#
# Handles databases created by both the Python SDK and Go SDK (cq-go).
#
# Usage:
#   ./server/scripts/migrate-v1.sh [DB_PATH]    # Local SDK database.
#   docker compose exec cq-server \
#     bash /app/scripts/migrate-v1.sh            # Server database.
#
# DB_PATH resolution order:
#   1. Explicit argument
#   2. CQ_LOCAL_DB_PATH environment variable
#   3. CQ_DB_PATH environment variable (set in the cq-server container)
#   4. ${XDG_DATA_HOME:-$HOME/.local/share}/cq/local.db
#
# Transformations applied:
#   - Tier values:   TIER_LOCAL → local, TIER_PRIVATE → private, TIER_PUBLIC → public,
#                    team → private, global → public (server legacy values)
#   - Flag reasons:  FLAG_REASON_STALE → stale, FLAG_REASON_INCORRECT → incorrect,
#                    FLAG_REASON_DUPLICATE → duplicate
#   - Field rename:  "domain" (singular) → "domains" (plural) in JSON data
#   - KU ID format:  ku_<uuid-with-dashes> → ku_<32hex> (Go SDK only; no-op otherwise)
#
# Creates a backup at DB_PATH.pre-v1-backup before modifying.
# Idempotent: safe to run multiple times on the same database.
#
# Requires: sqlite3 with JSON1 support (3.38.0+).
#
# Closes: https://github.com/mozilla-ai/cq/issues/175
# Closes: https://github.com/mozilla-ai/cq/issues/178
set -euo pipefail

default_db_path() {
    if [[ -n "${CQ_LOCAL_DB_PATH:-}" ]]; then
        echo "$CQ_LOCAL_DB_PATH"
        return
    fi
    if [[ -n "${CQ_DB_PATH:-}" ]]; then
        echo "$CQ_DB_PATH"
        return
    fi
    local data_home="${XDG_DATA_HOME:-${HOME}/.local/share}"
    echo "${data_home}/cq/local.db"
}

check_prerequisites() {
    if ! command -v sqlite3 &>/dev/null; then
        echo "Error: sqlite3 is required but not found in PATH." >&2
        exit 1
    fi

    if ! sqlite3 :memory: "SELECT json_extract('{\"a\": 1}', '\$.a');" &>/dev/null; then
        echo "Error: sqlite3 does not support JSON functions (requires 3.38.0+)." >&2
        exit 1
    fi
}

count_legacy_rows() {
    local db_path="$1"
    sqlite3 "$db_path" <<'SQL'
SELECT
    (SELECT COUNT(*) FROM knowledge_units
     WHERE json_extract(data, '$.tier') IN ('TIER_LOCAL','TIER_PRIVATE','TIER_PUBLIC','team','global'))
    || '|' ||
    (SELECT COUNT(*) FROM knowledge_units
     WHERE data LIKE '%FLAG_REASON_%')
    || '|' ||
    (SELECT COUNT(*) FROM knowledge_units
     WHERE json_type(data, '$.domain') IS NOT NULL)
    || '|' ||
    (SELECT COUNT(*) FROM knowledge_units
     WHERE id LIKE 'ku_%-%')
    || '|' ||
    (SELECT COUNT(*) FROM knowledge_units);
SQL
}

check_id_collisions() {
    local db_path="$1"
    local collisions
    collisions=$(sqlite3 "$db_path" <<'SQL'
SELECT COUNT(*) FROM knowledge_units
WHERE id LIKE 'ku_%-%'
  AND 'ku_' || REPLACE(SUBSTR(id, 4), '-', '') IN (
    SELECT id FROM knowledge_units WHERE id NOT LIKE 'ku_%-%'
  );
SQL
    )

    if [[ "$collisions" -gt 0 ]]; then
        echo "Error: ${collisions} ID collision(s) detected." >&2
        echo "The database contains both legacy (dashed) and v1 (undashed) entries" >&2
        echo "that would map to the same ID. Manual resolution is required." >&2
        exit 1
    fi
}

create_backup() {
    local db_path="$1"
    local backup_path="${db_path}.pre-v1-backup"

    if [[ -f "$backup_path" ]]; then
        echo "Backup already exists at ${backup_path} (skipping)."
        return
    fi

    # Checkpoint WAL to ensure the backup is self-contained.
    sqlite3 "$db_path" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true

    cp "$db_path" "$backup_path"
    for ext in "-wal" "-shm"; do
        if [[ -f "${db_path}${ext}" ]]; then
            cp "${db_path}${ext}" "${backup_path}${ext}"
        fi
    done

    echo "Backup created at ${backup_path}."
}

has_fts_table() {
    local db_path="$1"
    local count
    count=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='knowledge_units_fts';")
    [[ "$count" -gt 0 ]]
}

run_migration() {
    local db_path="$1"

    sqlite3 -bail "$db_path" <<'SQL'
PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

-- Normalise tier enum values using targeted JSON path replacement.
-- Handles both Go SDK prefixed values and server legacy values.
UPDATE knowledge_units
SET data = json_set(data, '$.tier',
    CASE json_extract(data, '$.tier')
        WHEN 'TIER_LOCAL'   THEN 'local'
        WHEN 'TIER_PRIVATE' THEN 'private'
        WHEN 'TIER_PUBLIC'  THEN 'public'
        WHEN 'team'         THEN 'private'
        WHEN 'global'       THEN 'public'
    END
)
WHERE json_extract(data, '$.tier') IN ('TIER_LOCAL', 'TIER_PRIVATE', 'TIER_PUBLIC', 'team', 'global');

-- Normalise flag reason enum values.
-- Uses string replacement because SQLite lacks ergonomic JSON array-element
-- mutation.  The quoted patterns (e.g. "FLAG_REASON_STALE") only ever appear
-- as standalone JSON string values, never as substrings of longer strings.
UPDATE knowledge_units
SET data = REPLACE(REPLACE(REPLACE(data,
    '"FLAG_REASON_STALE"',     '"stale"'),
    '"FLAG_REASON_INCORRECT"', '"incorrect"'),
    '"FLAG_REASON_DUPLICATE"', '"duplicate"')
WHERE data LIKE '%FLAG_REASON_%';

-- Rename "domain" (singular) to "domains" (plural) in JSON data.
-- Handles both array and scalar values; always writes an array.
UPDATE knowledge_units
SET data = json_remove(
    json_set(data, '$.domains',
        CASE json_type(data, '$.domain')
            WHEN 'array' THEN json(json_extract(data, '$.domain'))
            ELSE json_array(json_extract(data, '$.domain'))
        END
    ),
    '$.domain'
)
WHERE json_type(data, '$.domain') IS NOT NULL
  AND json_type(data, '$.domains') IS NULL;

-- Remove orphaned "domain" key when "domains" already exists.
UPDATE knowledge_units
SET data = json_remove(data, '$.domain')
WHERE json_type(data, '$.domain') IS NOT NULL
  AND json_type(data, '$.domains') IS NOT NULL;

-- Normalise KU IDs: strip dashes from the UUID portion.
-- Update the domain index first (before the PK changes).
UPDATE knowledge_unit_domains
SET unit_id = 'ku_' || REPLACE(SUBSTR(unit_id, 4), '-', '')
WHERE unit_id LIKE 'ku_%-%';

-- Update the primary key.
UPDATE knowledge_units
SET id = 'ku_' || REPLACE(SUBSTR(id, 4), '-', '')
WHERE id LIKE 'ku_%-%';

-- Sync the ID inside JSON data with the row ID.
UPDATE knowledge_units
SET data = json_set(data, '$.id', id)
WHERE json_extract(data, '$.id') != id;

COMMIT;

PRAGMA foreign_keys = ON;
SQL

    # Rebuild FTS index only if the table exists (local SDK databases have it;
    # team-api databases do not).
    if has_fts_table "$db_path"; then
        sqlite3 -bail "$db_path" <<'SQL'
DELETE FROM knowledge_units_fts;
INSERT INTO knowledge_units_fts (id, summary, detail, action)
SELECT id,
       json_extract(data, '$.insight.summary'),
       json_extract(data, '$.insight.detail'),
       json_extract(data, '$.insight.action')
FROM knowledge_units;
SQL
    fi
}

verify_migration() {
    local db_path="$1"
    local remaining
    remaining=$(sqlite3 "$db_path" <<'SQL'
SELECT
    (SELECT COUNT(*) FROM knowledge_units
     WHERE json_extract(data, '$.tier') IN ('TIER_LOCAL','TIER_PRIVATE','TIER_PUBLIC','team','global'))
    +
    (SELECT COUNT(*) FROM knowledge_units
     WHERE data LIKE '%FLAG_REASON_%')
    +
    (SELECT COUNT(*) FROM knowledge_units
     WHERE json_type(data, '$.domain') IS NOT NULL)
    +
    (SELECT COUNT(*) FROM knowledge_units
     WHERE id LIKE 'ku_%-%');
SQL
    )

    if [[ "$remaining" -gt 0 ]]; then
        echo "Error: ${remaining} row(s) still contain legacy data after migration." >&2
        exit 1
    fi

    echo "All rows migrated to v1 format."
}

main() {
    local db_path="${1:-$(default_db_path)}"

    check_prerequisites

    if [[ ! -f "$db_path" ]]; then
        echo "Error: database not found at ${db_path}" >&2
        exit 1
    fi

    local counts
    counts=$(count_legacy_rows "$db_path")

    local legacy_tiers legacy_flags legacy_domains legacy_ids total_rows
    IFS='|' read -r legacy_tiers legacy_flags legacy_domains legacy_ids total_rows <<< "$counts"

    if [[ "$legacy_tiers" -eq 0 && "$legacy_flags" -eq 0 && "$legacy_domains" -eq 0 && "$legacy_ids" -eq 0 ]]; then
        echo "Database is already in v1 format. Nothing to migrate."
        echo "  Total rows: ${total_rows}"
        exit 0
    fi

    echo "Found legacy data in ${db_path}:"
    echo "  Total rows:          ${total_rows}"
    echo "  Legacy tier values:  ${legacy_tiers}"
    echo "  Legacy flag reasons: ${legacy_flags}"
    echo "  Legacy domain field: ${legacy_domains}"
    echo "  Legacy KU IDs:       ${legacy_ids}"
    echo ""

    check_id_collisions "$db_path"
    create_backup "$db_path"
    run_migration "$db_path"
    verify_migration "$db_path"
}

main "$@"
