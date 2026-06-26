// Package postgres provides a PostgreSQL-backed Store for the cq SDK.
//
// Construct with New and pass to the client via cq.WithStore:
//
//	store, err := postgres.New(ctx, "postgres://localhost/cq")
//	client, err := cq.NewClient(cq.WithStore(store))
package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

const (
	keyLastWriteAt = "last_write_at"
	keyLastWriter  = "last_writer"
	writerTagFmt   = "cq-go-sdk/postgres go/%s"
)

// rollbackTimeout bounds the deferred rollback cleanup so it cannot block
// indefinitely on an unresponsive server.
const rollbackTimeout = 5 * time.Second

const schemaDDL = `
CREATE TABLE IF NOT EXISTS knowledge_units (
    rowid BIGINT GENERATED ALWAYS AS IDENTITY,
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_unit_domains (
    unit_id TEXT NOT NULL REFERENCES knowledge_units(id) ON DELETE CASCADE,
    domain TEXT NOT NULL,
    PRIMARY KEY (unit_id, domain)
);

CREATE INDEX IF NOT EXISTS idx_domains_domain
    ON knowledge_unit_domains(domain);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
`

const (
	sqlDeleteDomains = `DELETE FROM knowledge_unit_domains WHERE unit_id = $1`
	sqlDeleteUnit    = `DELETE FROM knowledge_units WHERE id = $1`
	sqlDomainCounts  = `SELECT domain, COUNT(*) FROM knowledge_unit_domains GROUP BY domain`
	sqlInsertDomain  = `INSERT INTO knowledge_unit_domains (unit_id, domain) VALUES ($1, $2)`
	sqlInsertUnit    = `INSERT INTO knowledge_units (id, data) VALUES ($1, $2)`

	sqlQueryByDomains = `
		SELECT DISTINCT k.data
		FROM knowledge_units k
		JOIN knowledge_unit_domains d ON k.id = d.unit_id
		WHERE d.domain = ANY($1)`

	sqlSelectAll    = `SELECT data FROM knowledge_units`
	sqlSelectByID   = `SELECT data FROM knowledge_units WHERE id = $1`
	sqlSelectCount  = `SELECT COUNT(*) FROM knowledge_units`
	sqlSelectRecent = `SELECT data FROM knowledge_units ORDER BY rowid DESC LIMIT $1`
	sqlUpdateUnit   = `UPDATE knowledge_units SET data = $1 WHERE id = $2`

	sqlUpsertMetadata = `
		INSERT INTO metadata (key, value) VALUES ($1, $2)
		ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value`
)

// execer runs a single SQL statement, whether against the connection pool
// directly or within an open transaction.
type execer interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
}

// Store is a PostgreSQL-backed implementation of cq.Store.
// All methods are safe for concurrent use.
type Store struct {
	mu     sync.Mutex
	pool   *pgxpool.Pool
	closed bool
}

// New creates a PostgreSQL-backed Store.
// The connection string must be a valid PostgreSQL URL or DSN.
// New validates the string, connects, pings the server, and ensures the
// schema exists before returning.
func New(ctx context.Context, connString string) (*Store, error) {
	if connString == "" {
		return nil, fmt.Errorf("connection string must not be empty")
	}
	cfg, err := pgxpool.ParseConfig(connString)
	if err != nil {
		return nil, fmt.Errorf("invalid connection string: %w", err)
	}
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("creating connection pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("connecting to server: %w", err)
	}
	s := &Store{pool: pool}
	if err := s.ensureSchema(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ensuring schema: %w", err)
	}
	return s, nil
}

// All returns every knowledge unit in the store.
func (s *Store) All(ctx context.Context) ([]cq.KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, cq.ErrStoreClosed
	}
	return s.scanUnits(ctx, sqlSelectAll)
}

// Close releases the connection pool. Safe to call more than once.
func (s *Store) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil
	}
	s.closed = true
	s.pool.Close()
	return nil
}

// Delete removes the knowledge unit with the given ID.
// Returns an error if no unit with that ID exists.
func (s *Store) Delete(ctx context.Context, id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.ErrStoreClosed
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("beginning transaction: %w", err)
	}
	defer rollback(tx)
	ct, err := tx.Exec(ctx, sqlDeleteUnit, id)
	if err != nil {
		return fmt.Errorf("deleting unit: %w", err)
	}
	if ct.RowsAffected() == 0 {
		return fmt.Errorf("unit %s not found", id)
	}
	if err := stampWriter(ctx, tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Insert stores a new knowledge unit.
// Domains are normalized before storage.
// Returns an error on duplicate ID or empty domains after normalization.
func (s *Store) Insert(ctx context.Context, ku cq.KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.ErrStoreClosed
	}
	domains := cq.NormalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return fmt.Errorf("at least one non-empty domain is required")
	}
	ku.Domains = domains
	data, err := marshal(ku)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer rollback(tx)
	if _, err := tx.Exec(ctx, sqlInsertUnit, ku.ID, data); err != nil {
		return fmt.Errorf("inserting unit %s: %w", ku.ID, err)
	}
	if err := insertDomains(ctx, tx, ku.ID, domains); err != nil {
		return err
	}
	if err := stampWriter(ctx, tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Query returns knowledge units whose domain tags overlap with the query,
// ranked by relevance and confidence, truncated to the limit.
func (s *Store) Query(ctx context.Context, params cq.QueryParams) (cq.StoreQueryResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.StoreQueryResult{}, cq.ErrStoreClosed
	}
	nq, err := cq.NormalizeQueryParams(params)
	if err != nil {
		return cq.StoreQueryResult{}, err
	}
	if len(nq.Domains) == 0 {
		return cq.StoreQueryResult{}, nil
	}
	candidates, err := s.scanUnits(ctx, sqlQueryByDomains, nq.Domains)
	if err != nil {
		return cq.StoreQueryResult{}, err
	}
	ranked := cq.RankCandidates(candidates, params)
	return cq.StoreQueryResult{KUs: ranked}, nil
}

// Stats returns aggregated store statistics including unit counts per domain,
// the most recently inserted units, and confidence distribution across the
// canonical buckets.
func (s *Store) Stats(ctx context.Context, recentLimit int) (cq.StoreStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.StoreStats{}, cq.ErrStoreClosed
	}
	if recentLimit < 0 {
		return cq.StoreStats{}, fmt.Errorf("recent limit must be non-negative: %d", recentLimit)
	}
	totalCount, err := s.countUnits(ctx)
	if err != nil {
		return cq.StoreStats{}, err
	}
	domainCounts, err := s.queryDomainCounts(ctx)
	if err != nil {
		return cq.StoreStats{}, err
	}
	recent, err := s.scanUnits(ctx, sqlSelectRecent, recentLimit)
	if err != nil {
		return cq.StoreStats{}, err
	}
	buckets, err := s.computeConfidenceBuckets(ctx)
	if err != nil {
		return cq.StoreStats{}, err
	}
	return cq.StoreStats{
		TotalCount:             totalCount,
		DomainCounts:           domainCounts,
		Recent:                 recent,
		ConfidenceDistribution: buckets,
		TierCounts:             map[cq.Tier]int{cq.Local: totalCount},
	}, nil
}

// Unit returns the knowledge unit with the given ID, or nil when absent.
func (s *Store) Unit(ctx context.Context, id string) (*cq.KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, cq.ErrStoreClosed
	}
	var data []byte
	err := s.pool.QueryRow(ctx, sqlSelectByID, id).Scan(&data)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	ku, err := unmarshal(data)
	if err != nil {
		return nil, err
	}
	return &ku, nil
}

// Update replaces an existing knowledge unit.
// Domains are re-normalized and the domain index is rebuilt.
// Returns an error if no unit with that ID exists.
func (s *Store) Update(ctx context.Context, ku cq.KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.ErrStoreClosed
	}
	domains := cq.NormalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return fmt.Errorf("at least one non-empty domain is required")
	}
	ku.Domains = domains
	data, err := marshal(ku)
	if err != nil {
		return err
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer rollback(tx)
	ct, err := tx.Exec(ctx, sqlUpdateUnit, data, ku.ID)
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return fmt.Errorf("unit %s not found", ku.ID)
	}
	if _, err := tx.Exec(ctx, sqlDeleteDomains, ku.ID); err != nil {
		return err
	}
	if err := insertDomains(ctx, tx, ku.ID, domains); err != nil {
		return err
	}
	if err := stampWriter(ctx, tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// computeConfidenceBuckets returns the count of units in each canonical
// confidence bucket.
func (s *Store) computeConfidenceBuckets(ctx context.Context) (map[string]int, error) {
	buckets := map[string]int{}
	for _, label := range cq.ConfidenceBucketLabels() {
		buckets[label] = 0
	}
	rows, err := s.pool.Query(ctx, buildConfidenceSQL())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	for rows.Next() {
		var bucket string
		var cnt int
		if err := rows.Scan(&bucket, &cnt); err != nil {
			return nil, err
		}
		buckets[bucket] = cnt
	}
	return buckets, rows.Err()
}

// countUnits returns the total number of knowledge units in the store.
func (s *Store) countUnits(ctx context.Context) (int, error) {
	var n int
	if err := s.pool.QueryRow(ctx, sqlSelectCount).Scan(&n); err != nil {
		return 0, err
	}
	return n, nil
}

// ensureSchema creates the tables and indexes if they do not exist, then
// stamps the writer metadata so cross-SDK diagnostics can identify the
// last SDK that wrote to the database.
func (s *Store) ensureSchema(ctx context.Context) error {
	if _, err := s.pool.Exec(ctx, schemaDDL); err != nil {
		return err
	}
	return stampWriter(ctx, s.pool)
}

// queryDomainCounts returns the number of knowledge units per domain tag.
func (s *Store) queryDomainCounts(ctx context.Context) (map[string]int, error) {
	rows, err := s.pool.Query(ctx, sqlDomainCounts)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	counts := map[string]int{}
	for rows.Next() {
		var domain string
		var count int
		if err := rows.Scan(&domain, &count); err != nil {
			return nil, err
		}
		counts[domain] = count
	}
	return counts, rows.Err()
}

// scanUnits executes a query returning a single JSONB data column and
// deserializes each row into a KnowledgeUnit.
func (s *Store) scanUnits(ctx context.Context, sql string, args ...any) ([]cq.KnowledgeUnit, error) {
	rows, err := s.pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var units []cq.KnowledgeUnit
	for rows.Next() {
		var data []byte
		if err := rows.Scan(&data); err != nil {
			return nil, err
		}
		ku, err := unmarshal(data)
		if err != nil {
			return nil, err
		}
		units = append(units, ku)
	}
	return units, rows.Err()
}

// buildConfidenceSQL renders the bucketing query from the canonical bucket
// definitions so the CASE thresholds stay in lockstep with the SDK constants.
// Exactly one label carries an infinite upper bound; it becomes the ELSE arm.
func buildConfidenceSQL() string {
	labels := cq.ConfidenceBucketLabels()
	var whens []string
	for _, label := range labels {
		bound, err := cq.ConfidenceBucketBound(label)
		if err != nil {
			panic(fmt.Sprintf("confidence bucket %q has no upper bound: %v", label, err))
		}
		if math.IsInf(bound, 1) {
			whens = append(whens, fmt.Sprintf("ELSE '%s'", label))
		} else {
			whens = append(whens, fmt.Sprintf("WHEN confidence < %g THEN '%s'", bound, label))
		}
	}
	return "SELECT CASE " + strings.Join(whens, " ") + " END AS bucket, COUNT(*) AS cnt " +
		"FROM (SELECT COALESCE((data->'evidence'->>'confidence')::float, 0.5) " +
		"AS confidence FROM knowledge_units) sub " +
		"GROUP BY bucket"
}

// stampWriter records the SDK version and timestamp in the metadata table
// so operators can identify which SDK last modified the database.
func stampWriter(ctx context.Context, e execer) error {
	tag := fmt.Sprintf(writerTagFmt, runtime.Version())
	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := e.Exec(ctx, sqlUpsertMetadata, keyLastWriter, tag); err != nil {
		return fmt.Errorf("writing writer metadata: %w", err)
	}
	if _, err := e.Exec(ctx, sqlUpsertMetadata, keyLastWriteAt, now); err != nil {
		return fmt.Errorf("writing timestamp metadata: %w", err)
	}
	return nil
}

// insertDomains writes domain tag rows for a unit within an existing transaction.
func insertDomains(ctx context.Context, tx pgx.Tx, unitID string, domains []string) error {
	for _, d := range domains {
		if _, err := tx.Exec(ctx, sqlInsertDomain, unitID, d); err != nil {
			return err
		}
	}
	return nil
}

// rollback discards tx using a context independent of the caller's, so cleanup
// runs even after the caller cancels — otherwise a cancelled rollback churns
// the pooled connection instead of releasing it. No-op after a successful
// Commit; the returned error is not actionable.
func rollback(tx pgx.Tx) {
	ctx, cancel := context.WithTimeout(context.Background(), rollbackTimeout)
	defer cancel()
	_ = tx.Rollback(ctx)
}

// marshal serializes a KnowledgeUnit to JSON for JSONB storage.
func marshal(ku cq.KnowledgeUnit) ([]byte, error) {
	return json.Marshal(ku)
}

// unmarshal deserializes a JSONB byte slice into a KnowledgeUnit.
func unmarshal(data []byte) (cq.KnowledgeUnit, error) {
	var ku cq.KnowledgeUnit
	if err := json.Unmarshal(data, &ku); err != nil {
		return cq.KnowledgeUnit{}, err
	}
	return ku, nil
}
