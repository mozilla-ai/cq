package cq

import (
	"cmp"
	"errors"
	"fmt"
	"math"
	"net/url"
	"slices"
	"strings"
)

// Store-level query limits and filter bounds.
const (
	// defaultStoreQueryLimit is used when QueryParams.Limit is non-positive.
	defaultStoreQueryLimit = 5

	// maxQueryDomains is the maximum number of domain tags in a single query.
	maxQueryDomains = 50

	// maxQueryFrameworks is the maximum number of framework filters in a single query.
	maxQueryFrameworks = 50

	// maxQueryLanguages is the maximum number of language filters in a single query.
	maxQueryLanguages = 50

	// maxQueryLimit is the maximum number of results a query can return.
	maxQueryLimit = 500
)

// confidenceBuckets maps each canonical confidence-distribution label to its
// exclusive upper bound. The unbracketed labels are the wire contract shared
// with the server and the other SDKs; keep them aligned so a remote
// distribution merges without drift. Use ConfidenceBucketLabels() for the
// labels in ascending order.
var confidenceBuckets = map[string]float64{
	"0.0-0.3": 0.3,
	"0.3-0.5": 0.5,
	"0.5-0.7": 0.7,
	"0.7-1.0": math.Inf(1),
}

// errClosed is returned when an operation is attempted on a closed store.
var errClosed = errors.New("store is closed")

// Store is the local persistence provider interface for the cq SDK.
// Implementations own all storage concerns (full-text search, dialect SQL,
// connection pooling, ranking strategy); the Client depends only on these
// methods and never learns how a store ranks or whether it does full-text.
// NOTE: implementations must be safe for concurrent use.
type Store interface {
	// Unit returns the knowledge unit with the given ID, or nil when absent.
	Unit(id string) (*KnowledgeUnit, error)

	// All returns every knowledge unit in the store.
	All() ([]KnowledgeUnit, error)

	// Insert stores a new knowledge unit.
	// NOTE: implementations must reject a duplicate ID and a unit whose
	// domains are empty after normalization.
	Insert(ku KnowledgeUnit) error

	// Update replaces an existing knowledge unit.
	// NOTE: implementations must error when the ID is absent and reject a
	// unit whose domains are empty after normalization.
	Update(ku KnowledgeUnit) error

	// Delete removes the knowledge unit with the given ID.
	// NOTE: implementations must error when the ID is absent.
	Delete(id string) error

	// Query returns knowledge units matching the parameters, ranked by
	// relevance and confidence and truncated to the limit.
	Query(params QueryParams) (StoreQueryResult, error)

	// Stats returns aggregated store statistics, including up to recentLimit
	// most-recently-inserted units.
	Stats(recentLimit int) (StoreStats, error)

	// Close releases the resources held by the store.
	// NOTE: implementations must be safe to call more than once.
	Close() error
}

// StoreQueryResult holds the ranked units a Store query produced alongside any
// non-fatal warnings (for example a backend that could not run full-text for a
// given query).
type StoreQueryResult struct {
	// KUs holds the matched knowledge units in ranked order.
	KUs []KnowledgeUnit

	// Warnings collects non-fatal issues encountered during the query.
	Warnings []error
}

// normalizedQuery holds query parameters after normalization and bounds
// checks, ready for candidate gathering and ranking. Tags are lowercased,
// trimmed, deduplicated, and order-stable.
type normalizedQuery struct {
	// domains are the normalized domain tags to match.
	domains []string

	// languages are the normalized language filters.
	languages []string

	// frameworks are the normalized framework filters.
	frameworks []string

	// pattern is the normalized pattern filter, empty when unset.
	pattern string

	// limit is the maximum number of ranked results to return.
	limit int
}

// ConfidenceBucketLabels returns the canonical confidence-distribution bucket
// labels in ascending order by upper bound. Display and bucketing code should
// use this rather than hardcoding labels, so order and spelling stay tied to
// StoreStats output.
func ConfidenceBucketLabels() []string {
	labels := make([]string, 0, len(confidenceBuckets))
	for label := range confidenceBuckets {
		labels = append(labels, label)
	}
	slices.SortFunc(labels, func(a, b string) int {
		return cmp.Compare(confidenceBuckets[a], confidenceBuckets[b])
	})

	return labels
}

// StoreFromURL resolves a connection string to a Store.
// A sqlite:///<path> or sqlite:<path> URL selects the built-in SQLite store.
// A postgresql:// or postgres:// URL is not handled by the core SDK and
// returns an error naming the optional Postgres adapter module to install.
// Any other scheme returns an error.
//
// NOTE: it returns the Store interface rather than a concrete type because the
// resolved implementation varies by scheme (and the SQLite implementation is
// deliberately unexported), so the interface is the only stable contract a
// caller can hold.
func StoreFromURL(connURL string) (Store, error) {
	parsed, err := url.Parse(connURL)
	if err != nil {
		return nil, fmt.Errorf("parsing store URL: %w", err)
	}

	switch parsed.Scheme {
	case "sqlite":
		path := sqlitePathFromURL(parsed)
		if path == "" {
			return nil, fmt.Errorf("sqlite store URL must include a file path")
		}

		return newSQLiteStore(path)
	case "postgresql", "postgres":
		return nil, fmt.Errorf(
			"postgres store requires the optional adapter module github.com/mozilla-ai/cq/sdk/go/stores/postgres, which is not yet available",
		)
	case "":
		return nil, fmt.Errorf("store URL must include a scheme, for example sqlite:///path/to/local.db")
	default:
		return nil, fmt.Errorf("unsupported store URL scheme %s", parsed.Scheme)
	}
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

// normalizeQueryParams validates and normalizes query parameters against the
// store-level bounds, returning an error when a bound is exceeded.
// Tags are lowercased, trimmed, deduplicated, and order-stable; a zero limit
// defaults to defaultStoreQueryLimit; a negative limit errors.
func normalizeQueryParams(params QueryParams) (normalizedQuery, error) {
	domains := normalizeDomains(params.Domains)
	if len(domains) > maxQueryDomains {
		return normalizedQuery{}, fmt.Errorf("maximum number of domains reached")
	}

	languages := normalizeDomains(params.Languages)
	if len(languages) > maxQueryLanguages {
		return normalizedQuery{}, fmt.Errorf("maximum number of languages reached")
	}

	frameworks := normalizeDomains(params.Frameworks)
	if len(frameworks) > maxQueryFrameworks {
		return normalizedQuery{}, fmt.Errorf("maximum number of frameworks reached")
	}

	limit := params.Limit
	if limit == 0 {
		limit = defaultStoreQueryLimit
	}
	if limit < 0 {
		return normalizedQuery{}, fmt.Errorf("limit must be greater than 0: %d", limit)
	}
	if limit > maxQueryLimit {
		return normalizedQuery{}, fmt.Errorf("limit must be less than max query limit: %d", limit)
	}

	return normalizedQuery{
		domains:    domains,
		languages:  languages,
		frameworks: frameworks,
		pattern:    strings.ToLower(strings.TrimSpace(params.Pattern)),
		limit:      limit,
	}, nil
}

// sqlitePathFromURL extracts the filesystem path from a parsed sqlite: URL.
// It accepts both the sqlite:///abs/path host-less form and the sqlite:path
// opaque form.
func sqlitePathFromURL(parsed *url.URL) string {
	if parsed.Opaque != "" {
		return parsed.Opaque
	}

	return parsed.Path
}
