# Test Fixtures

Cross-language test fixtures for verifying Go and Python SDK compatibility
against the same SQLite database.

All fixtures use the canonical JSON Schema format: snake_case field names
with clean enum values (`"local"`, `"private"`, `"stale"`).

## Python fixtures

- `python_unit.json` -- Local tier, one stale flag.
- `python_flagged_unit.json` -- Local tier, two flags (stale + incorrect), multiple languages.
- `python_real_unit.json` -- Real production unit from team API, private tier.
- `python_team_confirmed.json` -- Private tier, confirmed twice, no flags.
- `ku_*.json` -- Real KU backups from production, all private tier.

## Go fixtures

- `go_unit.json` -- Local tier, no flags.
- `go_flagged_unit.json` -- Local tier, one duplicate flag with duplicate_of reference.

Both formats must be readable by both SDKs.
