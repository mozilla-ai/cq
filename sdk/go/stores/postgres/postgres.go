// Package postgres provides a PostgreSQL-backed Store for the cq SDK.
//
// Construct with New and pass to the client via cq.WithStore:
//
//	store, err := postgres.New("postgres://localhost/cq")
//	client, err := cq.NewClient(cq.WithStore(store))
package postgres

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"runtime"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	cq "github.com/mozilla-ai/cq/sdk/go"
)

const (
	keyLastWriteAt = "last_write_at"
	keyLastWriter  = "last_writer"
	writerTagFmt   = "cq-go-sdk/postgres go/%s"
)

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
func New(connString string) (*Store, error) {
	if connString == "" {
		return nil, fmt.Errorf("connection string must not be empty")
	}
	cfg, err := pgxpool.ParseConfig(connString)
	if err != nil {
		return nil, fmt.Errorf("invalid connection string: %w", err)
	}
	pool, err := pgxpool.NewWithConfig(context.Background(), cfg)
	if err != nil {
		return nil, fmt.Errorf("creating connection pool: %w", err)
	}
	if err := pool.Ping(context.Background()); err != nil {
		pool.Close()
		return nil, fmt.Errorf("connecting to server: %w", err)
	}
	s := &Store{pool: pool}
	if err := s.ensureSchema(); err != nil {
		pool.Close()
		return nil, fmt.Errorf("ensuring schema: %w", err)
	}
	return s, nil
}

// All returns every knowledge unit in the store.
func (s *Store) All() ([]cq.KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, cq.ErrStoreClosed
	}
	return s.scanUnits(context.Background(), sqlSelectAll)
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
func (s *Store) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.ErrStoreClosed
	}
	ct, err := s.pool.Exec(context.Background(), sqlDeleteUnit, id)
	if err != nil {
		return err
	}
	if ct.RowsAffected() == 0 {
		return fmt.Errorf("unit %s not found", id)
	}
	return nil
}

// Insert stores a new knowledge unit.
// Domains are normalized before storage.
// Returns an error on duplicate ID or empty domains after normalization.
func (s *Store) Insert(ku cq.KnowledgeUnit) error {
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
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	// Rollback is a no-op after Commit; the returned error is not actionable.
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(ctx, sqlInsertUnit, ku.ID, data); err != nil {
		return fmt.Errorf("unit %s already exists", ku.ID)
	}
	if err := insertDomains(ctx, tx, ku.ID, domains); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

// Query returns knowledge units whose domain tags overlap with the query,
// ranked by relevance and confidence, truncated to the limit.
func (s *Store) Query(params cq.QueryParams) (cq.StoreQueryResult, error) {
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
	candidates, err := s.scanUnits(context.Background(), sqlQueryByDomains, nq.Domains)
	if err != nil {
		return cq.StoreQueryResult{}, err
	}
	ranked := cq.RankCandidates(candidates, params)
	return cq.StoreQueryResult{KUs: ranked}, nil
}

// Stats returns aggregated store statistics including unit counts per domain,
// the most recently inserted units, and confidence distribution across the
// canonical buckets.
func (s *Store) Stats(recentLimit int) (cq.StoreStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return cq.StoreStats{}, cq.ErrStoreClosed
	}
	if recentLimit < 0 {
		return cq.StoreStats{}, fmt.Errorf("recent limit must be non-negative: %d", recentLimit)
	}
	ctx := context.Background()
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
	}, nil
}

// Unit returns the knowledge unit with the given ID, or nil when absent.
func (s *Store) Unit(id string) (*cq.KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.closed {
		return nil, cq.ErrStoreClosed
	}
	var data []byte
	err := s.pool.QueryRow(context.Background(), sqlSelectByID, id).Scan(&data)
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
func (s *Store) Update(ku cq.KnowledgeUnit) error {
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
	ctx := context.Background()
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	// Rollback is a no-op after Commit; the returned error is not actionable.
	defer func() { _ = tx.Rollback(ctx) }()
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
	return tx.Commit(ctx)
}

// computeConfidenceBuckets loads all units and distributes them across the
// canonical confidence buckets shared with the server and other SDKs.
func (s *Store) computeConfidenceBuckets(ctx context.Context) (map[string]int, error) {
	units, err := s.scanUnits(ctx, sqlSelectAll)
	if err != nil {
		return nil, err
	}
	buckets := map[string]int{}
	for _, label := range cq.ConfidenceBucketLabels() {
		buckets[label] = 0
	}
	for _, ku := range units {
		for _, label := range cq.ConfidenceBucketLabels() {
			bound, err := cq.ConfidenceBucketBound(label)
			if err != nil {
				return nil, err
			}
			if ku.Evidence.Confidence >= bound {
				continue
			}
			buckets[label]++
			break
		}
	}
	return buckets, nil
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
func (s *Store) ensureSchema() error {
	ctx := context.Background()
	if _, err := s.pool.Exec(ctx, schemaDDL); err != nil {
		return err
	}
	return s.stampWriter()
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

// stampWriter records the SDK version and timestamp in the metadata table
// so operators can identify which SDK last modified the database.
func (s *Store) stampWriter() error {
	ctx := context.Background()
	tag := fmt.Sprintf(writerTagFmt, runtime.Version())
	now := time.Now().UTC().Format(time.RFC3339)
	batch := &pgx.Batch{}
	batch.Queue(sqlUpsertMetadata, keyLastWriter, tag)
	batch.Queue(sqlUpsertMetadata, keyLastWriteAt, now)
	return s.pool.SendBatch(ctx, batch).Close()
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
