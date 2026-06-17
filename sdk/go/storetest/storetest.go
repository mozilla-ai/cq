// Package storetest provides a backend-agnostic conformance suite for the
// cq Store SPI. Any Store implementation, in-tree or out-of-tree, can run
// RunConformance to assert it exhibits the observable behavior the Client
// depends on.
//
// NOTE: this package is imported by non-test code paths (it is a shippable
// helper, not a _test.go file), so it deliberately depends only on the
// standard library testing package and avoids third-party assertion
// libraries that would enter the module's distributable dependency surface.
package storetest

import (
	"testing"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// RunConformance exercises a Store implementation against the behavior the
// Client depends on: CRUD round-trips, query ranking and limits, stats
// aggregation, idempotent close, and error semantics on missing IDs and
// empty domains. newStore must return a fresh, empty Store on each call.
func RunConformance(t *testing.T, newStore func() cq.Store) {
	t.Helper()

	t.Run("insert and get round-trip", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000001", []string{"api"}, 0.8)
		noErr(t, s.Insert(ku))

		got, err := s.Unit(ku.ID)
		noErr(t, err)
		if got == nil {
			t.Fatal("Get returned nil for an inserted unit")
		}
		if got.ID != ku.ID {
			t.Fatalf("Get ID = %s, want %s", got.ID, ku.ID)
		}
		if got.Insight.Summary != ku.Insight.Summary {
			t.Fatalf("Get summary = %s, want %s", got.Insight.Summary, ku.Insight.Summary)
		}
	})

	t.Run("get missing returns nil without error", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		got, err := s.Unit("ku_0000000000000000000000000000dead")
		noErr(t, err)
		if got != nil {
			t.Fatalf("Get for a missing ID = %+v, want nil", got)
		}
	})

	t.Run("duplicate insert errors", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000002", []string{"api"}, 0.5)
		noErr(t, s.Insert(ku))
		wantErr(t, s.Insert(ku), "duplicate Insert")
	})

	t.Run("insert rejects empty domains", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000003", []string{"  ", ""}, 0.5)
		wantErr(t, s.Insert(ku), "Insert with empty domains")
	})

	t.Run("update existing persists", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000004", []string{"api"}, 0.5)
		noErr(t, s.Insert(ku))

		ku.Insight.Summary = "updated summary"
		noErr(t, s.Update(ku))

		got, err := s.Unit(ku.ID)
		noErr(t, err)
		if got.Insight.Summary != "updated summary" {
			t.Fatalf("summary after Update = %s, want updated summary", got.Insight.Summary)
		}
	})

	t.Run("update missing errors", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000005", []string{"api"}, 0.5)
		wantErr(t, s.Update(ku), "Update of a missing unit")
	})

	t.Run("delete existing then missing", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000006", []string{"api"}, 0.5)
		noErr(t, s.Insert(ku))

		noErr(t, s.Delete(ku.ID))

		got, err := s.Unit(ku.ID)
		noErr(t, err)
		if got != nil {
			t.Fatalf("Get after Delete = %+v, want nil", got)
		}

		wantErr(t, s.Delete(ku.ID), "Delete of a missing unit")
	})

	t.Run("all returns inserted units", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku1 := newKU("ku_00000000000000000000000000000007", []string{"api"}, 0.5)
		ku2 := newKU("ku_00000000000000000000000000000008", []string{"db"}, 0.5)
		noErr(t, s.Insert(ku1))
		noErr(t, s.Insert(ku2))

		all, err := s.All()
		noErr(t, err)
		if len(all) != 2 {
			t.Fatalf("All returned %d units, want 2", len(all))
		}

		ids := map[string]bool{}
		for _, ku := range all {
			ids[ku.ID] = true
		}
		if !ids[ku1.ID] || !ids[ku2.ID] {
			t.Fatalf("All missing an inserted unit: got IDs %v", ids)
		}
	})

	t.Run("query ranks by relevance and confidence", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		// Two matching domains and high confidence ranks first.
		better := newKU("ku_00000000000000000000000000000009", []string{"api", "payments"}, 0.9)
		noErr(t, s.Insert(better))

		worse := newKU("ku_0000000000000000000000000000000a", []string{"api"}, 0.3)
		noErr(t, s.Insert(worse))

		res, err := s.Query(cq.QueryParams{Domains: []string{"api", "payments"}, Limit: 10})
		noErr(t, err)
		if len(res.KUs) != 2 {
			t.Fatalf("Query returned %d units, want 2", len(res.KUs))
		}
		if res.KUs[0].ID != better.ID {
			t.Fatalf("top-ranked ID = %s, want %s", res.KUs[0].ID, better.ID)
		}
	})

	t.Run("query respects limit", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		for i, id := range []string{
			"ku_0000000000000000000000000000000b",
			"ku_0000000000000000000000000000000c",
			"ku_0000000000000000000000000000000d",
		} {
			ku := newKU(id, []string{"api"}, 0.5+float64(i)*0.1)
			noErr(t, s.Insert(ku))
		}

		res, err := s.Query(cq.QueryParams{Domains: []string{"api"}, Limit: 2})
		noErr(t, err)
		if len(res.KUs) != 2 {
			t.Fatalf("Query with Limit 2 returned %d units, want 2", len(res.KUs))
		}
	})

	t.Run("query returns domain matches", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_0000000000000000000000000000000e", []string{"unique-domain"}, 0.5)
		noErr(t, s.Insert(ku))

		res, err := s.Query(cq.QueryParams{Domains: []string{"unique-domain"}, Limit: 10})
		noErr(t, err)
		if len(res.KUs) != 1 {
			t.Fatalf("Query returned %d units, want 1", len(res.KUs))
		}
		if res.KUs[0].ID != ku.ID {
			t.Fatalf("matched ID = %s, want %s", res.KUs[0].ID, ku.ID)
		}

		none, err := s.Query(cq.QueryParams{Domains: []string{"no-such-domain"}, Limit: 10})
		noErr(t, err)
		if len(none.KUs) != 0 {
			t.Fatalf("Query for an absent domain returned %d units, want 0", len(none.KUs))
		}
	})

	t.Run("query limit zero defaults and negative errors", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		ku := newKU("ku_00000000000000000000000000000030", []string{"api"}, 0.5)
		noErr(t, s.Insert(ku))

		// A zero limit means "unset": the store falls back to its default.
		res, err := s.Query(cq.QueryParams{Domains: []string{"api"}, Limit: 0})
		noErr(t, err)
		if len(res.KUs) == 0 {
			t.Fatal("Query with Limit 0 should fall back to the default, got no results")
		}

		_, err = s.Query(cq.QueryParams{Domains: []string{"api"}, Limit: -1})
		wantErr(t, err, "Query with a negative limit")
	})

	t.Run("stats aggregates totals, domains, recent, buckets", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		confidences := []float64{0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.95}
		ids := []string{
			"ku_00000000000000000000000000000010",
			"ku_00000000000000000000000000000011",
			"ku_00000000000000000000000000000012",
			"ku_00000000000000000000000000000013",
			"ku_00000000000000000000000000000014",
			"ku_00000000000000000000000000000015",
			"ku_00000000000000000000000000000016",
			"ku_00000000000000000000000000000017",
			"ku_00000000000000000000000000000018",
		}
		for i, conf := range confidences {
			ku := newKU(ids[i], []string{"api"}, conf)
			noErr(t, s.Insert(ku))
		}

		stats, err := s.Stats(3)
		noErr(t, err)
		if stats.TotalCount != len(confidences) {
			t.Fatalf("TotalCount = %d, want %d", stats.TotalCount, len(confidences))
		}
		if stats.DomainCounts["api"] != len(confidences) {
			t.Fatalf("DomainCounts[api] = %d, want %d", stats.DomainCounts["api"], len(confidences))
		}
		if len(stats.Recent) != 3 {
			t.Fatalf("Recent length = %d, want 3", len(stats.Recent))
		}
		wantBuckets := map[string]int{"0.0-0.3": 2, "0.3-0.5": 2, "0.5-0.7": 2, "0.7-1.0": 3}
		for label, want := range wantBuckets {
			if stats.ConfidenceDistribution[label] != want {
				t.Fatalf("ConfidenceDistribution[%s] = %d, want %d", label, stats.ConfidenceDistribution[label], want)
			}
		}
	})

	t.Run("stats rejects negative recent limit", func(t *testing.T) {
		s := newStore()
		t.Cleanup(func() { _ = s.Close() })

		_, err := s.Stats(-1)
		wantErr(t, err, "Stats with a negative recent limit")
	})

	t.Run("close is idempotent and post-close ops error", func(t *testing.T) {
		s := newStore()

		noErr(t, s.Close())
		noErr(t, s.Close())

		ku := newKU("ku_00000000000000000000000000000020", []string{"api"}, 0.5)
		wantErr(t, s.Insert(ku), "Insert after Close")
		wantErr(t, s.Update(ku), "Update after Close")
		wantErr(t, s.Delete(ku.ID), "Delete after Close")

		_, err := s.Unit(ku.ID)
		wantErr(t, err, "Get after Close")

		_, err = s.All()
		wantErr(t, err, "All after Close")

		_, err = s.Query(cq.QueryParams{Domains: []string{"api"}, Limit: 10})
		wantErr(t, err, "Query after Close")

		_, err = s.Stats(5)
		wantErr(t, err, "Stats after Close")
	})
}

// noErr fails the test immediately when err is non-nil.
func noErr(t *testing.T, err error) {
	t.Helper()
	if err != nil {
		t.Fatalf("unexpected error: %s", err)
	}
}

// wantErr fails the test immediately when err is nil; op names the operation
// that was expected to fail, so the failure message identifies the case.
func wantErr(t *testing.T, err error, op string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s: expected an error, got nil", op)
	}
}

// newKU builds a knowledge unit for conformance assertions.
func newKU(id string, domains []string, confidence float64) cq.KnowledgeUnit {
	return cq.KnowledgeUnit{
		ID:      id,
		Version: 1,
		Domains: domains,
		Insight: cq.Insight{Summary: "summary " + id, Detail: "detail", Action: "action"},
		Context: cq.Context{Languages: []string{"go"}, Frameworks: []string{"grpc"}},
		Evidence: cq.Evidence{
			Confidence:    confidence,
			Confirmations: 1,
		},
		Tier: cq.Local,
	}
}
