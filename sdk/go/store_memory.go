package cq

import (
	"errors"
	"fmt"
	"slices"
	"sync"
)

// inMemoryStore is a map-backed Store that keeps knowledge units in memory.
// It performs domain-tag candidate matching only (no full-text search),
// demonstrating that the Store contract degrades gracefully without full-text.
// It doubles as the fastest conformance fixture and as a worked example for
// authors of out-of-tree stores.
type inMemoryStore struct {
	mu     sync.Mutex
	units  map[string]KnowledgeUnit
	order  []string
	closed bool
}

// NewInMemoryStore returns a Store that holds knowledge units in memory.
// It matches the error semantics of the default SQLite store and ranks with
// the shared ranker, but does no full-text search.
func NewInMemoryStore() Store {
	return &inMemoryStore{units: make(map[string]KnowledgeUnit)}
}

// All returns every knowledge unit in insertion order.
func (s *inMemoryStore) All() ([]KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil, ErrStoreClosed
	}

	units := make([]KnowledgeUnit, 0, len(s.order))
	for _, id := range s.order {
		units = append(units, cloneUnit(s.units[id]))
	}

	return units, nil
}

// Close marks the store closed. Safe to call more than once; subsequent calls
// return nil.
func (s *inMemoryStore) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.closed = true

	return nil
}

// Delete removes a knowledge unit by ID.
func (s *inMemoryStore) Delete(id string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return ErrStoreClosed
	}

	if _, ok := s.units[id]; !ok {
		return fmt.Errorf("unit %s not found", id)
	}

	delete(s.units, id)
	s.order = slices.DeleteFunc(s.order, func(existing string) bool {
		return existing == id
	})

	return nil
}

// Insert stores a new knowledge unit. Error if ID exists or domains empty after normalization.
func (s *inMemoryStore) Insert(ku KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return ErrStoreClosed
	}

	domains := NormalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return errors.New("knowledge unit must have at least one non-empty domain")
	}

	if _, ok := s.units[ku.ID]; ok {
		return fmt.Errorf("unit %s already exists", ku.ID)
	}

	stored := cloneUnit(ku)
	stored.Domains = domains

	s.units[ku.ID] = stored
	s.order = append(s.order, ku.ID)

	return nil
}

// Query returns units matching any of the requested domains, ranked by the
// shared ranker. It does not run full-text search.
func (s *inMemoryStore) Query(params QueryParams) (StoreQueryResult, error) {
	norm, err := normalizeQueryParams(params)
	if err != nil {
		return StoreQueryResult{}, err
	}

	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return StoreQueryResult{}, ErrStoreClosed
	}

	if len(norm.domains) == 0 {
		return StoreQueryResult{}, nil
	}

	wanted := make(map[string]struct{}, len(norm.domains))
	for _, d := range norm.domains {
		wanted[d] = struct{}{}
	}

	var candidates []KnowledgeUnit
	for _, id := range s.order {
		ku := s.units[id]
		for _, d := range ku.Domains {
			if _, ok := wanted[d]; ok {
				candidates = append(candidates, cloneUnit(ku))

				break
			}
		}
	}

	return StoreQueryResult{KUs: RankCandidates(candidates, params)}, nil
}

// Stats returns aggregated statistics, including up to recentLimit most-recently-inserted units.
func (s *inMemoryStore) Stats(recentLimit int) (StoreStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return StoreStats{}, ErrStoreClosed
	}

	if recentLimit < 0 {
		return StoreStats{}, errors.New("recentLimit must be non-negative")
	}

	domainCounts := make(map[string]int)
	buckets := make(map[string]int, len(confidenceBuckets))
	for label := range confidenceBuckets {
		buckets[label] = 0
	}
	orderedLabels := ConfidenceBucketLabels()

	for _, id := range s.order {
		ku := s.units[id]
		for _, d := range ku.Domains {
			domainCounts[d]++
		}
		for _, label := range orderedLabels {
			if ku.Evidence.Confidence < confidenceBuckets[label] {
				buckets[label]++

				break
			}
		}
	}

	// Recent units in reverse insertion order, newest first.
	var recent []KnowledgeUnit
	for i := len(s.order) - 1; i >= 0 && len(recent) < recentLimit; i-- {
		recent = append(recent, cloneUnit(s.units[s.order[i]]))
	}

	return StoreStats{
		TotalCount:             len(s.order),
		DomainCounts:           domainCounts,
		Recent:                 recent,
		ConfidenceDistribution: buckets,
	}, nil
}

// Unit retrieves a knowledge unit by ID. Returns nil, nil if not found.
func (s *inMemoryStore) Unit(id string) (*KnowledgeUnit, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return nil, ErrStoreClosed
	}

	ku, ok := s.units[id]
	if !ok {
		return nil, nil
	}

	out := cloneUnit(ku)

	return &out, nil
}

// Update replaces an existing knowledge unit.
func (s *inMemoryStore) Update(ku KnowledgeUnit) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.closed {
		return ErrStoreClosed
	}

	domains := NormalizeDomains(ku.Domains)
	if len(domains) == 0 {
		return errors.New("knowledge unit must have at least one non-empty domain")
	}

	if _, ok := s.units[ku.ID]; !ok {
		return fmt.Errorf("unit %s not found", ku.ID)
	}

	stored := cloneUnit(ku)
	stored.Domains = domains
	s.units[ku.ID] = stored

	return nil
}

// cloneUnit returns a deep-enough copy of ku so callers cannot mutate stored slices.
func cloneUnit(ku KnowledgeUnit) KnowledgeUnit {
	out := ku
	out.Domains = slices.Clone(ku.Domains)
	out.Flags = slices.Clone(ku.Flags)
	out.Context.Languages = slices.Clone(ku.Context.Languages)
	out.Context.Frameworks = slices.Clone(ku.Context.Frameworks)

	return out
}
