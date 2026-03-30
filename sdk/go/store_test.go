package cq

import (
	"database/sql"
	"fmt"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	_ "modernc.org/sqlite"
)

func newTestStore(t *testing.T) *localStore {
	t.Helper()

	dbPath := filepath.Join(t.TempDir(), "sub", "dir", "test.db")
	s, err := newLocalStore(dbPath)
	require.NoError(t, err)
	t.Cleanup(func() { s.close() })
	return s
}

func newFakeKU(t *testing.T, domains []string) KnowledgeUnit {
	t.Helper()

	now := time.Now()
	return KnowledgeUnit{
		ID:      GenerateID(),
		Domains: domains,
		Insight: Insight{Summary: "test summary", Detail: "test detail", Action: "test action"},
		Context: Context{Languages: []string{"go"}, Frameworks: []string{"grpc"}},
		Evidence: Evidence{
			Confidence:    0.8,
			Confirmations: 1,
			FirstObserved: testTimePtr(now),
			LastConfirmed: testTimePtr(now),
		},
		Tier: Local,
	}
}

func TestNewStore(t *testing.T) {
	t.Parallel()

	t.Run("creates DB file in nested directory", func(t *testing.T) {
		t.Parallel()
		dbPath := filepath.Join(t.TempDir(), "sub", "dir", "test.db")
		s, err := newLocalStore(dbPath)
		require.NoError(t, err)
		s.close()

		require.FileExists(t, dbPath)
	})

	t.Run("idempotent schema creation", func(t *testing.T) {
		t.Parallel()
		dbPath := filepath.Join(t.TempDir(), "test.db")

		s1, err := newLocalStore(dbPath)
		require.NoError(t, err)
		s1.close()

		s2, err := newLocalStore(dbPath)
		require.NoError(t, err)
		s2.close()
	})
}

func TestClose(t *testing.T) {
	t.Parallel()

	t.Run("idempotent", func(t *testing.T) {
		t.Parallel()
		dbPath := filepath.Join(t.TempDir(), "test.db")
		s, err := newLocalStore(dbPath)
		require.NoError(t, err)

		s.close()
		s.close()
	})

	t.Run("operations after close error", func(t *testing.T) {
		t.Parallel()
		dbPath := filepath.Join(t.TempDir(), "test.db")
		s, err := newLocalStore(dbPath)
		require.NoError(t, err)
		s.close()

		ku := newFakeKU(t, []string{"testing"})
		require.ErrorIs(t, s.insert(ku), errClosed)

		_, err = s.get("any")
		require.ErrorIs(t, err, errClosed)

		_, err = s.all()
		require.ErrorIs(t, err, errClosed)

		require.ErrorIs(t, s.delete("any"), errClosed)
		require.ErrorIs(t, s.update(ku), errClosed)

		_, err = s.query(withDomain("testing"), withLimit(10))
		require.ErrorIs(t, err, errClosed)

		_, err = s.stats(5)
		require.ErrorIs(t, err, errClosed)
	})
}

func TestInsert(t *testing.T) {
	t.Parallel()

	t.Run("insert and retrieve", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"databases"})
		require.NoError(t, s.insert(ku))

		got, err := s.get(ku.ID)
		require.NoError(t, err)
		require.NotNil(t, got)
		require.Equal(t, ku.ID, got.ID)
	})

	t.Run("duplicate ID error", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"databases"})
		require.NoError(t, s.insert(ku))
		require.Error(t, s.insert(ku))
	})

	t.Run("rejects empty domains", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, nil)
		require.Error(t, s.insert(ku))
	})

	t.Run("rejects whitespace-only domains", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"  ", "\t", ""})
		require.Error(t, s.insert(ku))
	})
}

func TestGet(t *testing.T) {
	t.Parallel()

	t.Run("nil for missing ID", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		got, err := s.get("ku_nonexistent")
		require.NoError(t, err)
		require.Nil(t, got)
	})

	t.Run("roundtrip preserves all fields", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		now := time.Now()
		ku := KnowledgeUnit{
			ID:      GenerateID(),
			Domains: []string{"api", "payments"},
			Insight: Insight{
				Summary: "Use retries for flaky APIs",
				Detail:  "Exponential backoff with jitter prevents thundering herd.",
				Action:  "Wrap HTTP calls in a retry loop.",
			},
			Context: Context{
				Languages:  []string{"go", "python"},
				Frameworks: []string{"grpc", "http"},
				Pattern:    "retry",
			},
			Evidence: Evidence{
				Confidence:    0.75,
				Confirmations: 3,
				FirstObserved: testTimePtr(now),
				LastConfirmed: testTimePtr(now),
			},
			Tier:      Public,
			CreatedBy: "agent-007",
			Flags: []Flag{
				{Reason: Stale, Timestamp: testTimePtr(now)},
			},
		}

		require.NoError(t, s.insert(ku))

		got, err := s.get(ku.ID)
		require.NoError(t, err)
		require.Equal(t, ku.ID, got.ID)
		require.Equal(t, ku.Domains, got.Domains)
		require.Equal(t, ku.Insight.Summary, got.Insight.Summary)
		require.Equal(t, ku.Insight.Detail, got.Insight.Detail)
		require.Equal(t, ku.Insight.Action, got.Insight.Action)
		require.Equal(t, ku.Context.Languages, got.Context.Languages)
		require.Equal(t, ku.Context.Frameworks, got.Context.Frameworks)
		require.Equal(t, ku.Context.Pattern, got.Context.Pattern)
		require.InDelta(t, ku.Evidence.Confidence, got.Evidence.Confidence, 1e-9)
		require.Equal(t, ku.Evidence.Confirmations, got.Evidence.Confirmations)
		require.Equal(t, ku.Tier, got.Tier)
		require.Equal(t, ku.CreatedBy, got.CreatedBy)
		require.Len(t, got.Flags, 1)
		require.Equal(t, Stale, got.Flags[0].Reason)
	})
}

func TestAll(t *testing.T) {
	t.Parallel()

	t.Run("empty returns empty", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		all, err := s.all()
		require.NoError(t, err)
		require.Empty(t, all)
	})

	t.Run("returns all inserted", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku1 := newFakeKU(t, []string{"api"})
		ku2 := newFakeKU(t, []string{"databases"})
		require.NoError(t, s.insert(ku1))
		require.NoError(t, s.insert(ku2))

		all, err := s.all()
		require.NoError(t, err)
		require.Len(t, all, 2)

		ids := map[string]bool{all[0].ID: true, all[1].ID: true}
		require.True(t, ids[ku1.ID])
		require.True(t, ids[ku2.ID])
	})
}

func TestDelete(t *testing.T) {
	t.Parallel()

	t.Run("removes unit", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		require.NoError(t, s.delete(ku.ID))

		got, err := s.get(ku.ID)
		require.NoError(t, err)
		require.Nil(t, got)
	})

	t.Run("missing returns error", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		require.Error(t, s.delete("ku_nonexistent"))
	})

	t.Run("domain rows cascaded", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"unique-domain-for-cascade"})
		require.NoError(t, s.insert(ku))
		require.NoError(t, s.delete(ku.ID))

		// Verify domain is no longer queryable.
		results, err := s.query(withDomain("unique-domain-for-cascade"), withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)
	})
}

func TestUpdate(t *testing.T) {
	t.Parallel()

	t.Run("persists changes", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		ku.Insight = Insight{
			Summary: "updated summary",
			Detail:  "updated detail",
			Action:  "updated action",
		}
		require.NoError(t, s.update(ku))

		got, err := s.get(ku.ID)
		require.NoError(t, err)
		require.Equal(t, "updated summary", got.Insight.Summary)
	})

	t.Run("missing error", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.Error(t, s.update(ku))
	})

	t.Run("rejects empty domains", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		ku.Domains = nil
		require.Error(t, s.update(ku))
	})

	t.Run("refreshes domain tags", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"old-domain"})
		require.NoError(t, s.insert(ku))

		ku.Domains = []string{"new-domain"}
		require.NoError(t, s.update(ku))

		// Old domain should no longer match.
		results, err := s.query(withDomain("old-domain"), withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)

		// New domain should match.
		results, err = s.query(withDomain("new-domain"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)
	})
}

func TestDomainNormalization(t *testing.T) {
	t.Parallel()

	t.Run("lowercase", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"API", "Databases"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain("api"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
	})

	t.Run("case insensitive query", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain("API"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
	})

	t.Run("deduplicates", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api", "API", "Api"})
		require.NoError(t, s.insert(ku))

		stats, err := s.stats(0)
		require.NoError(t, err)
		// Only one domain "api" should exist.
		require.Equal(t, 1, stats.DomainCounts["api"])
	})
}

func TestQuery(t *testing.T) {
	t.Parallel()

	t.Run("matching domain", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain("api"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)
	})

	t.Run("no match empty", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain("databases"), withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)
	})

	t.Run("empty domains empty", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		results, err := s.query(withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)
	})

	t.Run("rejects non-positive limit", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		_, err := s.query(withDomain("api"), withLimit(0))
		require.Error(t, err)

		_, err = s.query(withDomain("api"), withLimit(-1))
		require.Error(t, err)
	})

	t.Run("rejects excessive domain count", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		oversized := maxQueryDomains + 1

		opts := make([]queryOption, 0, oversized)
		for i := range oversized {
			opts = append(opts, withDomain(fmt.Sprintf("domain%d", i)))
		}

		opts = append(opts, withLimit(10))

		_, err := s.query(opts...)
		require.Error(t, err)
		require.Contains(t, err.Error(), "maximum number of domains")
	})

	t.Run("respects limit", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		for i := 0; i < 5; i++ {
			ku := newFakeKU(t, []string{"api"})
			require.NoError(t, s.insert(ku))
		}

		results, err := s.query(withDomain("api"), withLimit(3))
		require.NoError(t, err)
		require.Len(t, results.KUs, 3)
	})

	t.Run("ranks by domain overlap", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		// Unit with two matching domains should rank higher.
		kuBetter := newFakeKU(t, []string{"api", "payments"})
		kuBetter.Evidence.Confidence = 0.8
		require.NoError(t, s.insert(kuBetter))

		kuWorse := newFakeKU(t, []string{"api"})
		kuWorse.Evidence.Confidence = 0.8
		require.NoError(t, s.insert(kuWorse))

		results, err := s.query(withDomain("api"), withDomain("payments"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 2)
		require.Equal(t, kuBetter.ID, results.KUs[0].ID)
	})

	t.Run("language boosts", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		kuGo := newFakeKU(t, []string{"api"})
		kuGo.Context = Context{Languages: []string{"go"}}
		kuGo.Evidence.Confidence = 0.8
		require.NoError(t, s.insert(kuGo))

		kuPython := newFakeKU(t, []string{"api"})
		kuPython.Context = Context{Languages: []string{"python"}}
		kuPython.Evidence.Confidence = 0.8
		require.NoError(t, s.insert(kuPython))

		results, err := s.query(withDomain("api"), withLanguage("go"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 2)
		require.Equal(t, kuGo.ID, results.KUs[0].ID)
	})

	t.Run("higher confidence ranks higher", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		kuHigh := newFakeKU(t, []string{"api"})
		kuHigh.Evidence.Confidence = 0.9
		require.NoError(t, s.insert(kuHigh))

		kuLow := newFakeKU(t, []string{"api"})
		kuLow.Evidence.Confidence = 0.3
		require.NoError(t, s.insert(kuLow))

		results, err := s.query(withDomain("api"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 2)
		require.Equal(t, kuHigh.ID, results.KUs[0].ID)
	})
}

func TestFTS(t *testing.T) {
	t.Parallel()

	t.Run("finds by summary text", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"unrelated-domain"})
		ku.Insight = Insight{
			Summary: "Always use retries for flaky network calls",
			Detail:  "some detail",
			Action:  "some action",
		}
		require.NoError(t, s.insert(ku))

		// Query with a domain that matches the summary text via FTS.
		results, err := s.query(withDomain("retries"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)
	})

	t.Run("finds by detail text", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"unrelated-domain"})
		ku.Insight = Insight{
			Summary: "some summary",
			Detail:  "Exponential backoff prevents thundering herd problems",
			Action:  "some action",
		}
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain("exponential"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)
	})

	t.Run("deduplicates with domain matches", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"retries"})
		ku.Insight = Insight{
			Summary: "Use retries for network calls",
			Detail:  "detail",
			Action:  "action",
		}
		require.NoError(t, s.insert(ku))

		// "retries" matches both domain and FTS but should appear only once.
		results, err := s.query(withDomain("retries"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
	})

	t.Run("updated after unit update", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		ku.Insight = Insight{
			Summary: "original summary",
			Detail:  "original detail",
			Action:  "original action",
		}
		require.NoError(t, s.insert(ku))

		ku.Insight = Insight{
			Summary: "completely new unique-fts-keyword summary",
			Detail:  "updated detail",
			Action:  "updated action",
		}
		require.NoError(t, s.update(ku))

		// FTS should find the updated text.
		results, err := s.query(withDomain("unique-fts-keyword"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)

		// FTS should not find the old text.
		results, err = s.query(withDomain("original"), withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)
	})

	t.Run("double quote in domain does not poison", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"safe-domain"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain(`bad"domain`), withDomain("safe-domain"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
	})

	t.Run("malicious domains do not break search", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"safe-domain"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain(`") OR (id:`), withDomain("safe-domain"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
	})

	t.Run("empty match expr does not crash", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s.insert(ku))

		results, err := s.query(withDomain(""), withLimit(10))
		require.NoError(t, err)
		require.Empty(t, results.KUs)
	})
}

func TestStats(t *testing.T) {
	t.Parallel()

	t.Run("empty store zero counts", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		stats, err := s.stats(5)
		require.NoError(t, err)
		require.Equal(t, 0, stats.TotalCount)
		require.Empty(t, stats.DomainCounts)
		require.Empty(t, stats.Recent)
	})

	t.Run("total count", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		require.NoError(t, s.insert(newFakeKU(t, []string{"api"})))
		require.NoError(t, s.insert(newFakeKU(t, []string{"databases"})))

		stats, err := s.stats(10)
		require.NoError(t, err)
		require.Equal(t, 2, stats.TotalCount)
	})

	t.Run("domain counts", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		require.NoError(t, s.insert(newFakeKU(t, []string{"api", "payments"})))
		require.NoError(t, s.insert(newFakeKU(t, []string{"api", "databases"})))

		stats, err := s.stats(10)
		require.NoError(t, err)
		require.Equal(t, 2, stats.DomainCounts["api"])
		require.Equal(t, 1, stats.DomainCounts["payments"])
		require.Equal(t, 1, stats.DomainCounts["databases"])
	})

	t.Run("recent respects limit", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		for i := 0; i < 5; i++ {
			require.NoError(t, s.insert(newFakeKU(t, []string{"api"})))
		}

		stats, err := s.stats(3)
		require.NoError(t, err)
		require.Len(t, stats.Recent, 3)
	})

	t.Run("rejects negative", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		_, err := s.stats(-1)
		require.Error(t, err)
	})

	t.Run("confidence distribution buckets", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		for _, conf := range []float64{0.1, 0.2, 0.4, 0.6, 0.8, 0.95} {
			ku := newFakeKU(t, []string{"api"})
			ku.Evidence.Confidence = conf
			require.NoError(t, s.insert(ku))
		}

		stats, err := s.stats(10)
		require.NoError(t, err)
		require.Equal(t, 2, stats.ConfidenceDistribution["[0.0-0.3)"])
		require.Equal(t, 1, stats.ConfidenceDistribution["[0.3-0.5)"])
		require.Equal(t, 1, stats.ConfidenceDistribution["[0.5-0.7)"])
		require.Equal(t, 2, stats.ConfidenceDistribution["[0.7-1.0]"])
	})
}

func TestEndToEnd(t *testing.T) {
	t.Parallel()

	t.Run("insert confirm query flag lifecycle", func(t *testing.T) {
		t.Parallel()
		s := newTestStore(t)

		ku := newFakeKU(t, []string{"api", "payments"})
		ku.Evidence.Confidence = 0.6
		require.NoError(t, s.insert(ku))

		// Confirm the unit.
		confirmed := applyConfirmation(ku)
		require.NoError(t, s.update(confirmed))

		// Verify confidence increased.
		got, err := s.get(ku.ID)
		require.NoError(t, err)
		require.Greater(t, got.Evidence.Confidence, 0.6)

		// Query should find it.
		results, err := s.query(withDomain("api"), withDomain("payments"), withLimit(10))
		require.NoError(t, err)
		require.Len(t, results.KUs, 1)
		require.Equal(t, ku.ID, results.KUs[0].ID)

		// Flag the unit.
		flagged := applyFlag(*got, Stale, flagConfig{})
		require.NoError(t, s.update(flagged))

		got, err = s.get(ku.ID)
		require.NoError(t, err)
		require.Len(t, got.Flags, 1)
		require.Equal(t, Stale, got.Flags[0].Reason)
	})

	t.Run("persistence across re-open", func(t *testing.T) {
		t.Parallel()
		dbPath := filepath.Join(t.TempDir(), "persist", "test.db")

		s1, err := newLocalStore(dbPath)
		require.NoError(t, err)

		ku := newFakeKU(t, []string{"api"})
		require.NoError(t, s1.insert(ku))
		s1.close()

		s2, err := newLocalStore(dbPath)
		require.NoError(t, err)
		t.Cleanup(func() { s2.close() })

		got, err := s2.get(ku.ID)
		require.NoError(t, err)
		require.NotNil(t, got)
		require.Equal(t, ku.ID, got.ID)
		require.Equal(t, ku.Insight.Summary, got.Insight.Summary)
	})
}

func TestWriterStamp(t *testing.T) {
	t.Parallel()

	dbPath := filepath.Join(t.TempDir(), "test.db")
	s, err := newLocalStore(dbPath)
	require.NoError(t, err)
	defer s.close()

	db, err := sql.Open("sqlite", dbPath)
	require.NoError(t, err)
	defer func() { _ = db.Close() }()

	var lastWriter string
	require.NoError(t, db.QueryRow("SELECT value FROM metadata WHERE key = ?", keyLastWriter).Scan(&lastWriter))
	require.Contains(t, lastWriter, "cq-go-sdk/")
	require.Contains(t, lastWriter, "go/")

	var lastWriteAt string
	require.NoError(t, db.QueryRow("SELECT value FROM metadata WHERE key = ?", keyLastWriteAt).Scan(&lastWriteAt))
	require.NotEmpty(t, lastWriteAt)
}
