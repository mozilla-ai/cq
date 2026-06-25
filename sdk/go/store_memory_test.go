package cq

import (
	"context"
	"testing"
)

// TestInMemoryStoreMatchesDomainsOnly verifies the in-memory store selects
// candidates by domain tag and does not consult full-text: a term that appears
// only in a unit's summary (and is not among its domains) does not surface.
// CRUD, ranking, stats, and error semantics are covered by the shared
// conformance suite (see store_conformance_test.go).
func TestInMemoryStoreMatchesDomainsOnly(t *testing.T) {
	t.Parallel()

	s := NewInMemoryStore()
	t.Cleanup(func() { _ = s.Close() })

	ku := KnowledgeUnit{
		ID:       "ku_000000000000000000000000000000a1",
		Version:  1,
		Domains:  []string{"api"},
		Insight:  Insight{Summary: "payments integration", Detail: "d", Action: "a"},
		Evidence: Evidence{Confidence: 0.7, Confirmations: 1},
		Tier:     Local,
	}
	if err := s.Insert(context.Background(), ku); err != nil {
		t.Fatalf("Insert: %s", err)
	}

	got, err := s.Query(context.Background(), QueryParams{Domains: []string{"api"}, Limit: 5})
	if err != nil {
		t.Fatalf("Query by domain: %s", err)
	}
	if len(got.KUs) != 1 {
		t.Fatalf("domain query returned %d units, want 1", len(got.KUs))
	}

	// "payments" appears only in the summary, never as a domain; the
	// full-text-free store must not surface it.
	none, err := s.Query(context.Background(), QueryParams{Domains: []string{"payments"}, Limit: 5})
	if err != nil {
		t.Fatalf("Query by summary term: %s", err)
	}
	if len(none.KUs) != 0 {
		t.Fatalf("summary-term query returned %d units, want 0 (no full-text)", len(none.KUs))
	}
}
