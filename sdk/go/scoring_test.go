package cq

import (
	"math"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func testTimePtr(t time.Time) *time.Time { return &t }

// newTestKU builds a KnowledgeUnit with the given domains, confidence, and confirmations.
func newTestKU(t *testing.T, domains []string, confidence float64, confirmations int32) KnowledgeUnit {
	t.Helper()

	return KnowledgeUnit{
		ID:      "ku_00000000000000000000000000000001",
		Domains: domains,
		Evidence: Evidence{
			Confidence:    confidence,
			Confirmations: confirmations,
			FirstObserved: testTimePtr(time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)),
			LastConfirmed: testTimePtr(time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)),
		},
		Context: Context{
			Languages:  []string{"go"},
			Frameworks: []string{"grpc"},
		},
		Tier: Local,
	}
}

func TestApplyConfirmation(t *testing.T) {
	t.Parallel()

	t.Run("increases confidence by 0.1", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		result := applyConfirmation(ku)

		require.InDelta(t, 0.6, result.Evidence.Confidence, 1e-9)
	})

	t.Run("caps confidence at 1.0", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.95, 1)
		result := applyConfirmation(ku)

		require.InDelta(t, 1.0, result.Evidence.Confidence, 1e-9)
	})

	t.Run("increments confirmation count", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 3)
		result := applyConfirmation(ku)

		require.Equal(t, int32(4), result.Evidence.Confirmations)
	})

	t.Run("updates last confirmed timestamp", func(t *testing.T) {
		t.Parallel()

		before := time.Now()
		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		result := applyConfirmation(ku)
		after := time.Now()

		lastConfirmed := *result.Evidence.LastConfirmed
		require.False(t, lastConfirmed.Before(before), "last_confirmed should be >= before")
		require.False(t, lastConfirmed.After(after), "last_confirmed should be <= after")
	})

	t.Run("does not mutate original", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		_ = applyConfirmation(ku)

		require.InDelta(t, 0.5, ku.Evidence.Confidence, 1e-9)
		require.Equal(t, int32(1), ku.Evidence.Confirmations)
	})
}

func TestApplyFlag(t *testing.T) {
	t.Parallel()

	t.Run("decreases confidence by 0.15", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		result := applyFlag(ku, Stale, flagConfig{})

		require.InDelta(t, 0.35, result.Evidence.Confidence, 1e-9)
	})

	t.Run("floors confidence at 0.0", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.05, 1)
		result := applyFlag(ku, Incorrect, flagConfig{})

		require.InDelta(t, 0.0, result.Evidence.Confidence, 1e-9)
	})

	t.Run("records flag with reason", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		result := applyFlag(ku, Stale, flagConfig{})

		require.Len(t, result.Flags, 1)
		require.Equal(t, Stale, result.Flags[0].Reason)
		require.NotNil(t, result.Flags[0].Timestamp)
	})

	t.Run("appends to existing flags", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.8, 1)
		now := time.Now()
		ku.Flags = []Flag{
			{Reason: Duplicate, Timestamp: &now},
		}

		result := applyFlag(ku, Incorrect, flagConfig{})

		require.Len(t, result.Flags, 2)
		require.Equal(t, Duplicate, result.Flags[0].Reason)
		require.Equal(t, Incorrect, result.Flags[1].Reason)
	})

	t.Run("does not mutate original", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		_ = applyFlag(ku, Stale, flagConfig{})

		require.InDelta(t, 0.5, ku.Evidence.Confidence, 1e-9)
		require.Empty(t, ku.Flags)
	})
}

func TestKnowledgeUnitRelevance(t *testing.T) {
	t.Parallel()

	t.Run("exact domain match scores higher than partial", func(t *testing.T) {
		t.Parallel()

		exact := newTestKU(t, []string{"go", "testing"}, 0.5, 1)
		partial := newTestKU(t, []string{"go", "python"}, 0.5, 1)

		exactScore := exact.relevance([]string{"go", "testing"}, nil, nil)
		partialScore := partial.relevance([]string{"go", "testing"}, nil, nil)

		require.Greater(t, exactScore, partialScore)
	})

	t.Run("no domain overlap returns zero", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"python"}, 0.5, 1)
		ku.Context = Context{}
		score := ku.relevance([]string{"rust"}, nil, nil)

		require.InDelta(t, 0.0, score, 1e-9)
	})

	t.Run("language match boosts score", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		ku.Context = Context{Languages: []string{"go"}}

		withLang := ku.relevance([]string{"testing"}, []string{"go"}, nil)
		withoutLang := ku.relevance([]string{"testing"}, nil, nil)

		require.Greater(t, withLang, withoutLang)
	})

	t.Run("framework match boosts score", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"testing"}, 0.5, 1)
		ku.Context = Context{Frameworks: []string{"grpc"}}

		withFw := ku.relevance([]string{"testing"}, nil, []string{"grpc"})
		withoutFw := ku.relevance([]string{"testing"}, nil, nil)

		require.Greater(t, withFw, withoutFw)
	})

	t.Run("full match returns 1.0", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"go", "testing"}, 0.5, 1)
		ku.Context = Context{
			Languages:  []string{"go"},
			Frameworks: []string{"grpc"},
		}

		score := ku.relevance([]string{"go", "testing"}, []string{"go"}, []string{"grpc"})

		require.InDelta(t, 1.0, score, 1e-9)
	})

	t.Run("score is bounded between 0 and 1", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{"go", "testing", "ci"}, 0.5, 1)
		ku.Context = Context{
			Languages:  []string{"go", "python", "rust"},
			Frameworks: []string{"grpc", "http"},
		}

		queries := []struct {
			domains    []string
			languages  []string
			frameworks []string
		}{
			{[]string{"go"}, []string{"go"}, []string{"grpc"}},
			{[]string{"rust", "wasm"}, []string{"python"}, []string{"django"}},
			{nil, nil, nil},
			{[]string{"go", "testing", "ci"}, []string{"go"}, []string{"grpc"}},
		}

		for _, q := range queries {
			score := ku.relevance(q.domains, q.languages, q.frameworks)
			require.True(t, score >= 0.0 && score <= 1.0,
				"score %f out of bounds for domains=%v languages=%v frameworks=%v",
				score, q.domains, q.languages, q.frameworks)
			require.False(t, math.IsNaN(score), "score must not be NaN")
		}
	})

	t.Run("empty KU domains and empty query domains returns zero", func(t *testing.T) {
		t.Parallel()

		ku := newTestKU(t, []string{}, 0.5, 1)
		ku.Context = Context{}
		score := ku.relevance([]string{}, nil, nil)

		require.InDelta(t, 0.0, score, 1e-9)
	})
}
