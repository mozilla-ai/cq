#!/usr/bin/env bash
# migrate-v1_test.sh — Integration tests for the v1 migration script.
#
# All tests operate on temporary databases created under $TMPDIR.
# Real user data is never read or modified.
#
# Usage: ./scripts/migrate-v1_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
MIGRATE="${SCRIPT_DIR}/migrate-v1.sh"

PASS=0
FAIL=0
TEST_NAME=""

# --- Test framework -----------------------------------------------------------

run_test() {
    TEST_NAME="$1"
    local fn="$2"

    local tmpdir
    tmpdir=$(mktemp -d)

    if "$fn" "$tmpdir" 2>&1; then
        ((PASS++))
        echo "  PASS  ${TEST_NAME}"
    else
        ((FAIL++))
        echo "  FAIL  ${TEST_NAME}" >&2
    fi

    rm -rf "$tmpdir"
}

assert_eq() {
    local actual="$1" expected="$2" msg="${3:-}"
    if [[ "$actual" != "$expected" ]]; then
        echo "    assertion failed${msg:+: $msg}" >&2
        echo "      expected: ${expected}" >&2
        echo "      actual:   ${actual}" >&2
        return 1
    fi
}

assert_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" != *"$needle"* ]]; then
        echo "    assertion failed${msg:+: $msg}" >&2
        echo "      expected to contain: ${needle}" >&2
        echo "      actual:              ${haystack}" >&2
        return 1
    fi
}

assert_not_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then
        echo "    assertion failed${msg:+: $msg}" >&2
        echo "      expected NOT to contain: ${needle}" >&2
        echo "      actual:                  ${haystack}" >&2
        return 1
    fi
}

assert_file_exists() {
    local path="$1" msg="${2:-}"
    if [[ ! -f "$path" ]]; then
        echo "    assertion failed${msg:+: $msg}" >&2
        echo "      file not found: ${path}" >&2
        return 1
    fi
}

# --- Database helpers ---------------------------------------------------------

# The schema shared by both the Python and Go SDKs.
CQ_SCHEMA='
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
    PRIMARY KEY (unit_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);
CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_units_fts
    USING fts5(id UNINDEXED, summary, detail, action);
'

# Team-api schema: same tables but no FTS virtual table.
CQ_TEAM_SCHEMA='
CREATE TABLE IF NOT EXISTS knowledge_units (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    FOREIGN KEY (unit_id) REFERENCES knowledge_units(id) ON DELETE CASCADE,
    PRIMARY KEY (unit_id, domain)
);
CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);
'

# create_db sets up an empty cq database and prints its path.
create_db() {
    local dir="$1"
    local db_path="${dir}/test.db"

    sqlite3 "$db_path" "$CQ_SCHEMA"
    echo "$db_path"
}

# create_team_db sets up a database with the team-api schema (no FTS).
create_team_db() {
    local dir="$1"
    local db_path="${dir}/team.db"

    sqlite3 "$db_path" "$CQ_TEAM_SCHEMA"
    echo "$db_path"
}

# insert_ku inserts a raw KU row, its domain index entries, and FTS entry.
insert_ku() {
    local db_path="$1" id="$2" data="$3"
    shift 3
    local domains=("$@")

    sqlite3 "$db_path" "INSERT INTO knowledge_units (id, data) VALUES ('${id}', '${data}');"

    for d in "${domains[@]}"; do
        sqlite3 "$db_path" "INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES ('${id}', '${d}');"
    done

    # Only insert FTS entry if the table exists.
    local has_fts
    has_fts=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='knowledge_units_fts';")
    if [[ "$has_fts" -gt 0 ]]; then
        sqlite3 "$db_path" "
            INSERT INTO knowledge_units_fts (id, summary, detail, action)
            VALUES (
                '${id}',
                json_extract('${data}', '\$.insight.summary'),
                json_extract('${data}', '\$.insight.detail'),
                json_extract('${data}', '\$.insight.action')
            );
        "
    fi
}

# read_field extracts a JSON field from the data column of a KU row.
read_field() {
    local db_path="$1" id="$2" json_path="$3"
    sqlite3 "$db_path" "SELECT json_extract(data, '${json_path}') FROM knowledge_units WHERE id = '${id}';"
}

# row_id returns the id column value for a given row (by new or old id).
row_exists() {
    local db_path="$1" id="$2"
    local count
    count=$(sqlite3 "$db_path" "SELECT COUNT(*) FROM knowledge_units WHERE id = '${id}';")
    [[ "$count" -gt 0 ]]
}

# --- Tests --------------------------------------------------------------------

test_tier_local() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"TIER_LOCAL","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local tier
    tier=$(read_field "$db" "ku_00000000000000000000000000000001" '$.tier')
    assert_eq "$tier" "local" "TIER_LOCAL should become local"
}

test_tier_private() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000002" \
        '{"id":"ku_00000000000000000000000000000002","version":1,"domains":["api"],"tier":"TIER_PRIVATE","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local tier
    tier=$(read_field "$db" "ku_00000000000000000000000000000002" '$.tier')
    assert_eq "$tier" "private" "TIER_PRIVATE should become private"
}

test_tier_public() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000003" \
        '{"id":"ku_00000000000000000000000000000003","version":1,"domains":["api"],"tier":"TIER_PUBLIC","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local tier
    tier=$(read_field "$db" "ku_00000000000000000000000000000003" '$.tier')
    assert_eq "$tier" "public" "TIER_PUBLIC should become public"
}

test_tier_team() {
    local dir="$1"
    local db
    db=$(create_team_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"team","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local tier
    tier=$(read_field "$db" "ku_00000000000000000000000000000001" '$.tier')
    assert_eq "$tier" "private" "team should become private"
}

test_tier_global() {
    local dir="$1"
    local db
    db=$(create_team_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"global","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local tier
    tier=$(read_field "$db" "ku_00000000000000000000000000000001" '$.tier')
    assert_eq "$tier" "public" "global should become public"
}

test_flag_reason_stale() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_STALE"}]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_contains "$data" '"stale"' "FLAG_REASON_STALE should become stale"
    assert_not_contains "$data" 'FLAG_REASON_' "no legacy flag reasons should remain"
}

test_flag_reason_incorrect() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_INCORRECT"}]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_contains "$data" '"incorrect"' "FLAG_REASON_INCORRECT should become incorrect"
}

test_flag_reason_duplicate() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_DUPLICATE","duplicate_of":"ku_00000000000000000000000000000099"}]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_contains "$data" '"duplicate"' "FLAG_REASON_DUPLICATE should become duplicate"
}

test_domain_rename_array() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domain":["api","payments"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api" "payments"

    bash "$MIGRATE" "$db" >/dev/null

    local domains
    domains=$(read_field "$db" "ku_00000000000000000000000000000001" '$.domains')
    assert_eq "$domains" '["api","payments"]' "domain array should move to domains"

    local old_domain
    old_domain=$(read_field "$db" "ku_00000000000000000000000000000001" '$.domain')
    assert_eq "$old_domain" "" "singular domain key should be removed"
}

test_domain_rename_scalar() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domain":"api","tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local domains
    domains=$(read_field "$db" "ku_00000000000000000000000000000001" '$.domains')
    assert_eq "$domains" '["api"]' "scalar domain should become a single-element array"
}

test_id_normalization() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    local dashed_id="ku_01234567-89ab-cdef-0123-456789abcdef"
    local clean_id="ku_0123456789abcdef0123456789abcdef"

    insert_ku "$db" "$dashed_id" \
        '{"id":"ku_01234567-89ab-cdef-0123-456789abcdef","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    # Row should exist under the clean ID.
    assert_eq "$(row_exists "$db" "$clean_id" && echo yes || echo no)" "yes" "row should exist with clean ID"

    # Old dashed ID should be gone.
    assert_eq "$(row_exists "$db" "$dashed_id" && echo yes || echo no)" "no" "dashed ID row should be gone"

    # JSON id field should match.
    local json_id
    json_id=$(read_field "$db" "$clean_id" '$.id')
    assert_eq "$json_id" "$clean_id" "JSON id should match the normalised row ID"
}

test_id_updates_domain_index() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    local dashed_id="ku_01234567-89ab-cdef-0123-456789abcdef"
    local clean_id="ku_0123456789abcdef0123456789abcdef"

    insert_ku "$db" "$dashed_id" \
        '{"id":"ku_01234567-89ab-cdef-0123-456789abcdef","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local domain_unit_id
    domain_unit_id=$(sqlite3 "$db" "SELECT unit_id FROM knowledge_unit_domains WHERE domain = 'api';")
    assert_eq "$domain_unit_id" "$clean_id" "domain index should reference the clean ID"
}

test_id_rebuilds_fts() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    local dashed_id="ku_01234567-89ab-cdef-0123-456789abcdef"
    local clean_id="ku_0123456789abcdef0123456789abcdef"

    insert_ku "$db" "$dashed_id" \
        '{"id":"ku_01234567-89ab-cdef-0123-456789abcdef","version":1,"domains":["api"],"tier":"local","insight":{"summary":"uniqueftsterm","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local fts_id
    fts_id=$(sqlite3 "$db" "SELECT id FROM knowledge_units_fts WHERE knowledge_units_fts MATCH 'uniqueftsterm';")
    assert_eq "$fts_id" "$clean_id" "FTS index should reference the clean ID"
}

test_combined_all_legacy_formats() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    local dashed_id="ku_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    local clean_id="ku_aaaaaaaabbbbccccddddeeeeeeeeeeee"

    insert_ku "$db" "$dashed_id" \
        '{"id":"ku_aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","version":1,"domain":["api","payments"],"tier":"TIER_LOCAL","insight":{"summary":"combined test","detail":"d","action":"a"},"context":{"languages":["go"]},"evidence":{"confidence":0.7},"flags":[{"reason":"FLAG_REASON_STALE","timestamp":"2026-03-30T12:00:00Z"}]}' \
        "api" "payments"

    bash "$MIGRATE" "$db" >/dev/null

    assert_eq "$(row_exists "$db" "$clean_id" && echo yes || echo no)" "yes" "row should exist with clean ID"
    assert_eq "$(read_field "$db" "$clean_id" '$.id')" "$clean_id" "JSON id"
    assert_eq "$(read_field "$db" "$clean_id" '$.tier')" "local" "tier"
    assert_eq "$(read_field "$db" "$clean_id" '$.domains')" '["api","payments"]' "domains"
    assert_eq "$(read_field "$db" "$clean_id" '$.domain')" "" "singular domain removed"

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = '${clean_id}';")
    assert_contains "$data" '"stale"' "flag reason normalised"
    assert_not_contains "$data" 'FLAG_REASON_' "no legacy flag reasons"
}

test_idempotent() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"TIER_PUBLIC","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_INCORRECT"}]}' \
        "api"

    # First run migrates.
    local out1
    out1=$(bash "$MIGRATE" "$db")
    assert_contains "$out1" "All rows migrated" "first run should migrate"

    # Second run is a no-op.
    local out2
    out2=$(bash "$MIGRATE" "$db")
    assert_contains "$out2" "already in v1 format" "second run should be a no-op"

    # Data is correct after both runs.
    assert_eq "$(read_field "$db" "ku_00000000000000000000000000000001" '$.tier')" "public" "tier after idempotent run"
}

test_already_v1() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    local out
    out=$(bash "$MIGRATE" "$db")
    assert_contains "$out" "already in v1 format" "v1 database should be a no-op"
}

test_empty_database() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    local out
    out=$(bash "$MIGRATE" "$db")
    assert_contains "$out" "already in v1 format" "empty database should be a no-op"
    assert_contains "$out" "Total rows: 0" "should report zero rows"
}

test_backup_created() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"TIER_LOCAL","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    assert_file_exists "${db}.pre-v1-backup" "backup file should exist"

    # Backup should contain the original legacy data.
    local backup_tier
    backup_tier=$(sqlite3 "${db}.pre-v1-backup" "SELECT json_extract(data, '\$.tier') FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_eq "$backup_tier" "TIER_LOCAL" "backup should contain original data"
}

test_backup_not_overwritten() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"TIER_LOCAL","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "api"

    # First run creates backup.
    bash "$MIGRATE" "$db" >/dev/null

    # Manually insert another legacy row and re-run.
    insert_ku "$db" "ku_00000000000000000000000000000002" \
        '{"id":"ku_00000000000000000000000000000002","version":1,"domains":["db"],"tier":"TIER_PRIVATE","insight":{"summary":"s2","detail":"d2","action":"a2"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "db"

    bash "$MIGRATE" "$db" >/dev/null

    # Backup should still only have the original row (not overwritten).
    local backup_count
    backup_count=$(sqlite3 "${db}.pre-v1-backup" "SELECT COUNT(*) FROM knowledge_units;")
    assert_eq "$backup_count" "1" "backup should not be overwritten on subsequent runs"
}

test_preserves_v1_rows() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    # V1 row.
    insert_ku "$db" "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
        '{"id":"ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","version":1,"domains":["api"],"tier":"local","insight":{"summary":"v1 unit","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.9},"flags":[]}' \
        "api"

    # Legacy row.
    insert_ku "$db" "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" \
        '{"id":"ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","version":1,"domains":["db"],"tier":"TIER_LOCAL","insight":{"summary":"legacy unit","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[]}' \
        "db"

    bash "$MIGRATE" "$db" >/dev/null

    # V1 row should be untouched.
    assert_eq "$(read_field "$db" "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" '$.tier')" "local" "v1 row tier preserved"
    assert_eq "$(read_field "$db" "ku_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" '$.insight.summary')" "v1 unit" "v1 row summary preserved"

    # Legacy row should be migrated.
    assert_eq "$(read_field "$db" "ku_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" '$.tier')" "local" "legacy row tier migrated"
}

test_missing_database() {
    local dir="$1"

    local out
    if out=$(bash "$MIGRATE" "${dir}/nonexistent.db" 2>&1); then
        echo "    expected non-zero exit code" >&2
        return 1
    fi

    assert_contains "$out" "database not found" "should report missing database"
}

test_no_fts_table() {
    local dir="$1"
    local db
    db=$(create_team_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"TIER_LOCAL","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_STALE"}]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    assert_eq "$(read_field "$db" "ku_00000000000000000000000000000001" '$.tier')" "local" "tier migrated without FTS"

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_contains "$data" '"stale"' "flag reason migrated without FTS"
    assert_not_contains "$data" 'FLAG_REASON_' "no legacy flags remain"

    # Confirm FTS table still does not exist.
    local fts_count
    fts_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='knowledge_units_fts';")
    assert_eq "$fts_count" "0" "FTS table should not be created"
}

test_multiple_flags() {
    local dir="$1"
    local db
    db=$(create_db "$dir")

    insert_ku "$db" "ku_00000000000000000000000000000001" \
        '{"id":"ku_00000000000000000000000000000001","version":1,"domains":["api"],"tier":"local","insight":{"summary":"s","detail":"d","action":"a"},"context":{},"evidence":{"confidence":0.5},"flags":[{"reason":"FLAG_REASON_STALE"},{"reason":"FLAG_REASON_INCORRECT"}]}' \
        "api"

    bash "$MIGRATE" "$db" >/dev/null

    local data
    data=$(sqlite3 "$db" "SELECT data FROM knowledge_units WHERE id = 'ku_00000000000000000000000000000001';")
    assert_contains "$data" '"stale"' "first flag reason normalised"
    assert_contains "$data" '"incorrect"' "second flag reason normalised"
    assert_not_contains "$data" 'FLAG_REASON_' "no legacy flag reasons remain"
}

# --- Run all tests ------------------------------------------------------------

main() {
    echo "migrate-v1 integration tests"
    echo ""

    run_test "tier: TIER_LOCAL → local"                     test_tier_local
    run_test "tier: TIER_PRIVATE → private"                 test_tier_private
    run_test "tier: TIER_PUBLIC → public"                   test_tier_public
    run_test "tier: team → private"                         test_tier_team
    run_test "tier: global → public"                        test_tier_global
    run_test "flag: FLAG_REASON_STALE → stale"              test_flag_reason_stale
    run_test "flag: FLAG_REASON_INCORRECT → incorrect"      test_flag_reason_incorrect
    run_test "flag: FLAG_REASON_DUPLICATE → duplicate"      test_flag_reason_duplicate
    run_test "flag: multiple flags in one unit"             test_multiple_flags
    run_test "domain: array renamed to domains"             test_domain_rename_array
    run_test "domain: scalar wrapped in array"              test_domain_rename_scalar
    run_test "id: dashes stripped from UUID"                test_id_normalization
    run_test "id: domain index updated"                    test_id_updates_domain_index
    run_test "id: FTS index rebuilt"                        test_id_rebuilds_fts
    run_test "combined: all legacy formats at once"        test_combined_all_legacy_formats
    run_test "idempotent: second run is no-op"             test_idempotent
    run_test "already v1: no changes needed"               test_already_v1
    run_test "empty database: no-op"                       test_empty_database
    run_test "backup: created before migration"            test_backup_created
    run_test "backup: not overwritten on re-run"           test_backup_not_overwritten
    run_test "preserves existing v1 rows"                  test_preserves_v1_rows
    run_test "missing database: exits with error"          test_missing_database
    run_test "no FTS table: team-api schema works"         test_no_fts_table

    echo ""
    echo "Results: ${PASS} passed, ${FAIL} failed"
    [[ "$FAIL" -eq 0 ]]
}

main
