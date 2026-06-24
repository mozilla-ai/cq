package cq

import (
	"fmt"
	"math"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestConfidenceBucketBound(t *testing.T) {
	t.Parallel()

	tcs := []struct {
		name    string
		label   string
		want    float64
		wantErr string
	}{
		{
			name:  "lowest bucket",
			label: "0.0-0.3",
			want:  0.3,
		},
		{
			name:  "mid-low bucket",
			label: "0.3-0.5",
			want:  0.5,
		},
		{
			name:  "mid-high bucket",
			label: "0.5-0.7",
			want:  0.7,
		},
		{
			name:  "highest bucket is +Inf",
			label: "0.7-1.0",
		},
		{
			name:    "unknown label errors",
			label:   "invalid",
			wantErr: "unknown confidence bucket label",
		},
		{
			name:    "empty label errors",
			label:   "",
			wantErr: "unknown confidence bucket label",
		},
	}
	for _, tc := range tcs {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := ConfidenceBucketBound(tc.label)
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
				return
			}
			require.NoError(t, err)
			if tc.label == "0.7-1.0" {
				require.True(t, math.IsInf(got, 1), "expected +Inf for top bucket")
				return
			}
			require.InDelta(t, tc.want, got, 0.001)
		})
	}
}

func TestNormalizeDomains(t *testing.T) {
	t.Parallel()

	tcs := []struct {
		name   string
		input  []string
		expect []string
	}{
		{
			name:   "nil input",
			input:  nil,
			expect: []string{},
		},
		{
			name:   "empty input",
			input:  []string{},
			expect: []string{},
		},
		{
			name:   "lowercases",
			input:  []string{"API", "Cli"},
			expect: []string{"api", "cli"},
		},
		{
			name:   "trims whitespace",
			input:  []string{"  api  ", "cli"},
			expect: []string{"api", "cli"},
		},
		{
			name:   "drops empties",
			input:  []string{"", "  ", "api"},
			expect: []string{"api"},
		},
		{
			name:   "deduplicates preserving order",
			input:  []string{"api", "cli", "API"},
			expect: []string{"api", "cli"},
		},
		{
			name:   "all empty yields empty",
			input:  []string{"", " ", "  "},
			expect: []string{},
		},
	}
	for _, tc := range tcs {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got := NormalizeDomains(tc.input)
			require.Equal(t, tc.expect, got)
		})
	}
}

func TestNormalizeQueryParams(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		params      QueryParams
		expected    normalizedQuery
		expectedErr string
	}{
		{
			name:   "no params set defaults limit",
			params: QueryParams{},
			expected: normalizedQuery{
				domains:    []string{},
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:   "domain is normalized",
			params: QueryParams{Domains: []string{"Example.com"}},
			expected: normalizedQuery{
				domains:    []string{"example.com"},
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:   "language is normalized",
			params: QueryParams{Languages: []string{"Go"}},
			expected: normalizedQuery{
				domains:    []string{},
				languages:  []string{"go"},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:   "framework is normalized",
			params: QueryParams{Frameworks: []string{"Gin"}},
			expected: normalizedQuery{
				domains:    []string{},
				languages:  []string{},
				frameworks: []string{"gin"},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:   "explicit limit kept",
			params: QueryParams{Limit: 10},
			expected: normalizedQuery{
				domains:    []string{},
				languages:  []string{},
				frameworks: []string{},
				limit:      10,
			},
		},
		{
			name: "multiple params set",
			params: QueryParams{
				Domains:    []string{"Example.com"},
				Languages:  []string{"Go"},
				Frameworks: []string{"Gin"},
				Pattern:    "  Api-Client  ",
				Limit:      10,
			},
			expected: normalizedQuery{
				domains:    []string{"example.com"},
				languages:  []string{"go"},
				frameworks: []string{"gin"},
				pattern:    "api-client",
				limit:      10,
			},
		},
		{
			name: "empty string values are dropped",
			params: QueryParams{
				Domains:    []string{""},
				Languages:  []string{" "},
				Frameworks: []string{""},
			},
			expected: normalizedQuery{
				domains:    []string{},
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:        "negative limit is rejected",
			params:      QueryParams{Limit: -1},
			expectedErr: "limit must be greater than 0: -1",
		},
		{
			name:        "limit exceeds maximum",
			params:      QueryParams{Limit: 600},
			expectedErr: "limit must be less than max query limit: 600",
		},
		{
			name: "exactly max domains succeeds",
			params: QueryParams{Domains: func() []string {
				out := make([]string, 0, maxQueryDomains)
				for i := range maxQueryDomains {
					out = append(out, fmt.Sprintf("domain%d.com", i))
				}

				return out
			}()},
			expected: normalizedQuery{
				domains: func() []string {
					out := make([]string, 0, maxQueryDomains)
					for i := range maxQueryDomains {
						out = append(out, fmt.Sprintf("domain%d.com", i))
					}

					return out
				}(),
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name: "duplicate domains are deduplicated",
			params: QueryParams{Domains: func() []string {
				out := make([]string, 0, maxQueryDomains+1)
				for range maxQueryDomains + 1 {
					out = append(out, "same-domain")
				}

				return out
			}()},
			expected: normalizedQuery{
				domains:    []string{"same-domain"},
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name:   "case normalization deduplicates domains",
			params: QueryParams{Domains: []string{"API", "api", "Api"}},
			expected: normalizedQuery{
				domains:    []string{"api"},
				languages:  []string{},
				frameworks: []string{},
				limit:      defaultStoreQueryLimit,
			},
		},
		{
			name: "maximum domains reached",
			params: QueryParams{Domains: func() []string {
				out := make([]string, 0, maxQueryDomains+1)
				for i := range maxQueryDomains + 1 {
					out = append(out, fmt.Sprintf("domain%d.com", i))
				}

				return out
			}()},
			expectedErr: "maximum number of domains reached",
		},
		{
			name: "maximum languages reached",
			params: QueryParams{Languages: func() []string {
				out := make([]string, 0, maxQueryLanguages+1)
				for i := range maxQueryLanguages + 1 {
					out = append(out, fmt.Sprintf("lang%d", i))
				}

				return out
			}()},
			expectedErr: "maximum number of languages reached",
		},
		{
			name: "maximum frameworks reached",
			params: QueryParams{Frameworks: func() []string {
				out := make([]string, 0, maxQueryFrameworks+1)
				for i := range maxQueryFrameworks + 1 {
					out = append(out, fmt.Sprintf("fw%d", i))
				}

				return out
			}()},
			expectedErr: "maximum number of frameworks reached",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			got, err := normalizeQueryParams(tc.params)

			if tc.expectedErr != "" {
				require.Error(t, err)
				require.ErrorContains(t, err, tc.expectedErr)

				return
			}

			require.NoError(t, err)
			require.Equal(t, tc.expected, got)
		})
	}
}

func TestNormalizeQueryParamsPattern(t *testing.T) {
	t.Parallel()

	t.Run("lowercases and trims", func(t *testing.T) {
		t.Parallel()

		norm, err := normalizeQueryParams(QueryParams{Pattern: "  Api-Client  "})
		require.NoError(t, err)
		require.Equal(t, "api-client", norm.pattern)
	})

	t.Run("empty input yields empty pattern", func(t *testing.T) {
		t.Parallel()

		norm, err := normalizeQueryParams(QueryParams{Pattern: "   "})
		require.NoError(t, err)
		require.Empty(t, norm.pattern)
	})
}
