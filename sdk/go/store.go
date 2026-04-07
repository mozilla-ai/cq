package cq

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"maps"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"slices"
	"sort"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"

	"github.com/mozilla-ai/cq/sdk/go/internal/version"
)

// Schema DDL applied on first open.
const schema = `
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
`

// metadataDDL creates the metadata table used to track writer identity and timestamps.
const metadataDDL = `
CREATE TABLE IF NOT EXISTS metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
`

// Metadata keys stored in the metadata table.
const (
	keyLastWriter  = "last_writer"
	keyLastWriteAt = "last_write_at"
)

// errClosed is returned when an operation is attempted on a closed store.
var errClosed = errors.New("store is closed")

// localStore is a SQLite-backed knowledge unit store.
type localStore struct {
	mu     sync.Mutex
	db     *sql.DB
	closed bool
}

// storeQueryResult holds query results alongside any non-fatal warnings.
type storeQueryResult struct {
	KUs      []KnowledgeUnit
	Warnings []error
}

// newLocalStore opens or creates a local store at the given path.
func newLocalStore(dbPath string) (*localStore, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0o755); err != nil {
		return nil, fmt.Errorf("creating store directory: %w", err)
	}

	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		return nil, fmt.Errorf("opening database: %w", err)
	}

	if err := applyPragmas(db); err != nil {
		_ = db.Close()
		return nil, err
	}

	if _, err := db.Exec(schema); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("applying schema: %w", err)
	}

	if err := ensureMetadata(db); err != nil {
		_ = db.Close()
		return nil, err
	}

	return &localStore{db: db}, nil
}

// all returns every knowledge unit in the store.
func (s *localStore) all() ([]KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil, errClosed
	}

	rows, err := s.db.Query("SELECT data FROM knowledge_units")
	if err != nil {
		return nil, fmt.Errorf("querying all units: %w", err)
	}
	defer func() { _ = rows.Close() }()

	var units []KnowledgeUnit
	for rows.Next() {
		var data string
		if err := rows.Scan(&data); err != nil {
			return nil, fmt.Errorf("scanning row: %w", err)
		}

		ku, err := unmarshalUnit([]byte(data))
		if err != nil {
			return nil, fmt.Errorf("unmarshalling unit: %w", err)
		}
		units = append(units, ku)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterating rows: %w", err)
	}

	return units, nil
}

// close releases the database connection. Safe to call multiple times.
func (s *localStore) close() {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return
	}

	s.closed = true
	_ = s.db.Close()
}

// delete removes a knowledge unit by ID.
func (s *localStore) delete(unitID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return errClosed
	}

	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("beginning transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	// Delete FTS entry first; virtual tables don't support CASCADE.
	if _, err := tx.Exec("DELETE FROM knowledge_units_fts WHERE id = ?", unitID); err != nil {
		return fmt.Errorf("deleting FTS entry: %w", err)
	}

	res, err := tx.Exec("DELETE FROM knowledge_units WHERE id = ?", unitID)
	if err != nil {
		return fmt.Errorf("deleting unit: %w", err)
	}

	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("checking rows affected: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("unit %q not found", unitID)
	}

	return tx.Commit()
}

// get retrieves a knowledge unit by ID. Returns nil, nil if not found.
func (s *localStore) get(id string) (*KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil, errClosed
	}

	var data string
	err := s.db.QueryRow("SELECT data FROM knowledge_units WHERE id = ?", id).Scan(&data)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("querying unit: %w", err)
	}

	ku, err := unmarshalUnit([]byte(data))
	if err != nil {
		return nil, fmt.Errorf("unmarshalling unit: %w", err)
	}

	return &ku, nil
}

// insert stores a knowledge unit. Error if ID exists or domains empty after normalization.
func (s *localStore) insert(ku KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return errClosed
	}

	domains := normalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return errors.New("knowledge unit must have at least one non-empty domain")
	}

	// Store normalized domains so the persisted data matches the domain index.
	stored := ku
	stored.Domains = domains

	data, err := marshalUnit(stored)
	if err != nil {
		return fmt.Errorf("marshalling unit: %w", err)
	}

	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("beginning transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	if _, err := tx.Exec("INSERT INTO knowledge_units (id, data) VALUES (?, ?)", ku.ID, string(data)); err != nil {
		return fmt.Errorf("inserting unit: %w", err)
	}

	if err := insertDomains(tx, ku.ID, domains); err != nil {
		return err
	}

	if err := insertFTS(tx, stored); err != nil {
		return err
	}

	return tx.Commit()
}

// update replaces an existing knowledge unit.
func (s *localStore) update(ku KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return errClosed
	}

	domains := normalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return errors.New("knowledge unit must have at least one non-empty domain")
	}

	stored := ku
	stored.Domains = domains

	data, err := marshalUnit(stored)
	if err != nil {
		return fmt.Errorf("marshalling unit: %w", err)
	}

	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("beginning transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	res, err := tx.Exec("UPDATE knowledge_units SET data = ? WHERE id = ?", string(data), ku.ID)
	if err != nil {
		return fmt.Errorf("updating unit: %w", err)
	}

	affected, err := res.RowsAffected()
	if err != nil {
		return fmt.Errorf("checking rows affected: %w", err)
	}
	if affected == 0 {
		return fmt.Errorf("unit %q not found", ku.ID)
	}

	// Replace domain rows.
	if _, err := tx.Exec("DELETE FROM knowledge_unit_domains WHERE unit_id = ?", ku.ID); err != nil {
		return fmt.Errorf("clearing domains: %w", err)
	}
	if err := insertDomains(tx, ku.ID, domains); err != nil {
		return err
	}

	// Replace FTS entry.
	if _, err := tx.Exec("DELETE FROM knowledge_units_fts WHERE id = ?", ku.ID); err != nil {
		return fmt.Errorf("clearing FTS entry: %w", err)
	}
	if err := insertFTS(tx, stored); err != nil {
		return err
	}

	return tx.Commit()
}

// query searches by domain with FTS and relevance ranking.
func (s *localStore) query(opt ...queryOption) (storeQueryResult, error) {
	opts, err := newQueryOptions(opt...)
	if err != nil {
		return storeQueryResult{}, err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return storeQueryResult{}, errClosed
	}

	// No domains means no results.
	if len(opts.domains) == 0 {
		return storeQueryResult{}, nil
	}

	candidates := make(map[string]KnowledgeUnit)

	// Collect candidates from domain table.
	domains := slices.Collect(maps.Keys(opts.domains))
	placeholders := make([]string, len(domains))
	args := make([]any, len(domains))
	for i, d := range domains {
		placeholders[i] = "?"
		args[i] = d
	}

	domainQuery := "SELECT DISTINCT k.data FROM knowledge_units k " +
		"JOIN knowledge_unit_domains d ON k.id = d.unit_id " +
		"WHERE d.domain IN (" + strings.Join(placeholders, ",") + ")"

	rows, err := s.db.Query(domainQuery, args...)
	if err != nil {
		return storeQueryResult{}, fmt.Errorf("querying by domain: %w", err)
	}
	defer func() { _ = rows.Close() }()

	for rows.Next() {
		var data string
		if err := rows.Scan(&data); err != nil {
			return storeQueryResult{}, fmt.Errorf("scanning domain row: %w", err)
		}
		ku, err := unmarshalUnit([]byte(data))
		if err != nil {
			return storeQueryResult{}, fmt.Errorf("unmarshalling domain result: %w", err)
		}
		candidates[ku.ID] = ku
	}
	if err := rows.Err(); err != nil {
		return storeQueryResult{}, fmt.Errorf("iterating domain rows: %w", err)
	}

	// Collect candidates from FTS (non-fatal errors become warnings).
	var warnings []error

	matchExpr := buildFTSMatchExpr(domains)
	if matchExpr != "" {
		ftsRows, ftsErr := s.db.Query(
			"SELECT k.data FROM knowledge_units k "+
				"JOIN knowledge_units_fts f ON k.id = f.id "+
				"WHERE knowledge_units_fts MATCH ?",
			matchExpr,
		)

		if ftsErr != nil {
			warnings = append(warnings, fmt.Errorf("FTS query: %w", ftsErr))
		} else {
			defer func() { _ = ftsRows.Close() }()

			for ftsRows.Next() {
				var data string
				if err := ftsRows.Scan(&data); err != nil {
					warnings = append(warnings, fmt.Errorf("FTS scan: %w", err))

					break
				}

				ku, err := unmarshalUnit([]byte(data))
				if err != nil {
					warnings = append(warnings, fmt.Errorf("FTS unmarshal: %w", err))

					continue
				}

				candidates[ku.ID] = ku
			}

			if err := ftsRows.Err(); err != nil {
				warnings = append(warnings, fmt.Errorf("FTS iteration: %w", err))
			}
		}
	}

	// Rank candidates.
	languages := slices.Sorted(maps.Keys(opts.languages))
	frameworks := slices.Sorted(maps.Keys(opts.frameworks))

	type ranked struct {
		ku    KnowledgeUnit
		score float64
	}

	results := make([]ranked, 0, len(candidates))
	for _, ku := range candidates {
		relevance := ku.relevance(domains, languages, frameworks)
		confidence := ku.Evidence.Confidence
		results = append(results, ranked{ku: ku, score: relevance * confidence})
	}

	sort.Slice(results, func(i, j int) bool {
		return results[i].score > results[j].score
	})

	if len(results) > opts.limit {
		results = results[:opts.limit]
	}

	units := make([]KnowledgeUnit, len(results))
	for i, r := range results {
		units[i] = r.ku
	}

	return storeQueryResult{KUs: units, Warnings: warnings}, nil
}

// stats returns aggregated store statistics.
func (s *localStore) stats(recentLimit int) (StoreStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return StoreStats{}, errClosed
	}

	if recentLimit < 0 {
		return StoreStats{}, errors.New("recentLimit must be non-negative")
	}

	var totalCount int
	if err := s.db.QueryRow("SELECT COUNT(*) FROM knowledge_units").Scan(&totalCount); err != nil {
		return StoreStats{}, fmt.Errorf("counting units: %w", err)
	}

	domainCounts := make(map[string]int)
	domainRows, err := s.db.Query("SELECT domain, COUNT(*) FROM knowledge_unit_domains GROUP BY domain")
	if err != nil {
		return StoreStats{}, fmt.Errorf("querying domain counts: %w", err)
	}
	defer func() { _ = domainRows.Close() }()

	for domainRows.Next() {
		var domain string
		var count int
		if err := domainRows.Scan(&domain, &count); err != nil {
			return StoreStats{}, fmt.Errorf("scanning domain count: %w", err)
		}
		domainCounts[domain] = count
	}
	if err := domainRows.Err(); err != nil {
		return StoreStats{}, fmt.Errorf("iterating domain counts: %w", err)
	}

	// Fetch recent units ordered by rowid descending (insertion order).
	recentRows, err := s.db.Query("SELECT data FROM knowledge_units ORDER BY rowid DESC LIMIT ?", recentLimit)
	if err != nil {
		return StoreStats{}, fmt.Errorf("querying recent units: %w", err)
	}
	defer func() { _ = recentRows.Close() }()

	var recent []KnowledgeUnit
	for recentRows.Next() {
		var data string
		if err := recentRows.Scan(&data); err != nil {
			return StoreStats{}, fmt.Errorf("scanning recent row: %w", err)
		}
		ku, err := unmarshalUnit([]byte(data))
		if err != nil {
			return StoreStats{}, fmt.Errorf("unmarshalling recent unit: %w", err)
		}
		recent = append(recent, ku)
	}
	if err := recentRows.Err(); err != nil {
		return StoreStats{}, fmt.Errorf("iterating recent rows: %w", err)
	}

	// Confidence distribution.
	buckets := map[string]int{
		"[0.0-0.3)": 0,
		"[0.3-0.5)": 0,
		"[0.5-0.7)": 0,
		"[0.7-1.0]": 0,
	}

	type bucket struct {
		label string
		upper float64
	}
	boundaries := []bucket{
		{"[0.0-0.3)", 0.3},
		{"[0.3-0.5)", 0.5},
		{"[0.5-0.7)", 0.7},
		{"[0.7-1.0]", math.Inf(1)},
	}

	allRows, err := s.db.Query("SELECT data FROM knowledge_units")
	if err != nil {
		return StoreStats{}, fmt.Errorf("querying for confidence distribution: %w", err)
	}
	defer func() { _ = allRows.Close() }()

	for allRows.Next() {
		var data string
		if err := allRows.Scan(&data); err != nil {
			return StoreStats{}, fmt.Errorf("scanning confidence row: %w", err)
		}
		ku, err := unmarshalUnit([]byte(data))
		if err != nil {
			return StoreStats{}, fmt.Errorf("unmarshalling confidence unit: %w", err)
		}
		conf := ku.Evidence.Confidence
		for _, b := range boundaries {
			if conf < b.upper {
				buckets[b.label]++
				break
			}
		}
	}
	if err := allRows.Err(); err != nil {
		return StoreStats{}, fmt.Errorf("iterating confidence rows: %w", err)
	}

	return StoreStats{
		TotalCount:             totalCount,
		DomainCounts:           domainCounts,
		Recent:                 recent,
		ConfidenceDistribution: buckets,
	}, nil
}

// applyPragmas configures SQLite connection pragmas.
func applyPragmas(db *sql.DB) error {
	pragmas := []string{
		"PRAGMA foreign_keys = ON",
		"PRAGMA journal_mode = WAL",
		"PRAGMA synchronous = NORMAL",
		"PRAGMA busy_timeout = 5000",
	}
	for _, p := range pragmas {
		if _, err := db.Exec(p); err != nil {
			return fmt.Errorf("executing %s: %w", p, err)
		}
	}

	var fk int
	if err := db.QueryRow("PRAGMA foreign_keys").Scan(&fk); err != nil {
		return fmt.Errorf("verifying foreign_keys pragma: %w", err)
	}
	if fk != 1 {
		return errors.New("foreign_keys pragma is not enabled")
	}

	return nil
}

// insertDomains writes domain rows for a unit within an existing transaction.
func insertDomains(tx *sql.Tx, unitID string, domains []string) error {
	stmt, err := tx.Prepare("INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES (?, ?)")
	if err != nil {
		return fmt.Errorf("preparing domain insert: %w", err)
	}
	defer func() { _ = stmt.Close() }()

	for _, d := range domains {
		if _, err := stmt.Exec(unitID, d); err != nil {
			return fmt.Errorf("inserting domain %q: %w", d, err)
		}
	}

	return nil
}

// insertFTS writes an FTS entry for a unit within an existing transaction.
func insertFTS(tx *sql.Tx, ku KnowledgeUnit) error {
	_, err := tx.Exec(
		"INSERT INTO knowledge_units_fts (id, summary, detail, action) VALUES (?, ?, ?, ?)",
		ku.ID,
		ku.Insight.Summary,
		ku.Insight.Detail,
		ku.Insight.Action,
	)
	if err != nil {
		return fmt.Errorf("inserting FTS entry: %w", err)
	}
	return nil
}

// normalizeDomains lowercases, trims whitespace, drops empties, and deduplicates preserving order.
func normalizeDomains(domains []string) []string {
	seen := make(map[string]struct{}, len(domains))
	result := make([]string, 0, len(domains))

	for _, d := range domains {
		normalized := strings.ToLower(strings.TrimSpace(d))
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		result = append(result, normalized)
	}

	return result
}

// marshalUnit serialises a KnowledgeUnit to JSON for SQLite storage.
func marshalUnit(ku KnowledgeUnit) ([]byte, error) {
	return json.Marshal(ku)
}

// unmarshalUnit deserialises a KnowledgeUnit from JSON.
func unmarshalUnit(data []byte) (KnowledgeUnit, error) {
	var ku KnowledgeUnit
	if err := json.Unmarshal(data, &ku); err != nil {
		return KnowledgeUnit{}, err
	}
	return ku, nil
}

// writerTag returns a User-Agent style identifier for this SDK.
func writerTag() string {
	goVer := strings.TrimPrefix(runtime.Version(), "go")
	return fmt.Sprintf("cq-go-sdk/%s go/%s", version.Version(), goVer)
}

// ensureMetadata creates the metadata table and stamps the writer.
func ensureMetadata(db *sql.DB) error {
	if _, err := db.Exec(metadataDDL); err != nil {
		return fmt.Errorf("creating metadata table: %w", err)
	}

	return stampWriter(db)
}

// stampWriter updates the last_writer and last_write_at metadata.
func stampWriter(db *sql.DB) error {
	now := time.Now().UTC().Format(time.RFC3339)
	tag := writerTag()
	for _, kv := range [][2]string{
		{keyLastWriter, tag},
		{keyLastWriteAt, now},
	} {
		if _, err := db.Exec(
			"INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
			kv[0], kv[1],
		); err != nil {
			return fmt.Errorf("writing metadata %s: %w", kv[0], err)
		}
	}
	return nil
}
