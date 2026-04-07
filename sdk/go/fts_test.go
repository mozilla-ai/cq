package cq

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestBuildFTSMatchExpr(t *testing.T) {
	t.Parallel()

	t.Run("unit", func(t *testing.T) {
		t.Parallel()

		unitCases := []struct {
			name string
			in   []string
			want string
		}{
			{
				name: "single clean term",
				in:   []string{"databases"},
				want: `"databases"`,
			},
			{
				name: "multiple terms joined with OR",
				in:   []string{"api", "payments"},
				want: `"api" OR "payments"`,
			},
			{
				name: "hyphens preserved",
				in:   []string{"setup-uv"},
				want: `"setup-uv"`,
			},
			{
				name: "slashes preserved",
				in:   []string{"path/to/file"},
				want: `"path/to/file"`,
			},
			{
				name: "backslashes preserved",
				in:   []string{`back\slash`},
				want: `"back\slash"`,
			},
			{
				name: "double quotes stripped",
				in:   []string{`bad"term`},
				want: `"badterm"`,
			},
			{
				name: "only quotes yields empty",
				in:   []string{`"""`},
				want: "",
			},
			{
				name: "interspersed quotes stripped",
				in:   []string{`a"b"c`},
				want: `"abc"`,
			},
			{
				name: "whitespace stripped",
				in:   []string{"  spaced  "},
				want: `"spaced"`,
			},
			{
				name: "empty list yields empty",
				in:   []string{},
				want: "",
			},
			{
				name: "all terms empty after cleaning",
				in:   []string{`""`, `"`, "  "},
				want: "",
			},
			{
				name: "mixed clean and dirty",
				in:   []string{"api", `"""`, "payments"},
				want: `"api" OR "payments"`,
			},
			{
				name: "wildcards preserved",
				in:   []string{"term*"},
				want: `"term*"`,
			},
			{
				name: "braces preserved",
				in:   []string{"{near}"},
				want: `"{near}"`,
			},
			{
				name: "colons preserved",
				in:   []string{"col:filter"},
				want: `"col:filter"`,
			},
		}

		for _, tc := range unitCases {
			t.Run(tc.name, func(t *testing.T) {
				t.Parallel()
				got := buildFTSMatchExpr(tc.in)
				require.Equal(t, tc.want, got)
			})
		}
	})

	t.Run("injection", func(t *testing.T) {
		t.Parallel()

		injectionCases := []struct {
			name string
			in   []string
			want string
		}{
			{
				name: "OR injection via quotes",
				in:   []string{`term"OR"1"OR"`},
				want: `"termOR1OR"`,
			},
			{
				name: "parenthesis injection",
				in:   []string{`") OR (id:`},
				want: `") OR (id:"`,
			},
			{
				name: "OR with surrounding quotes",
				in:   []string{`" OR ""`},
				want: `"OR"`,
			},
		}

		for _, tc := range injectionCases {
			t.Run(tc.name, func(t *testing.T) {
				t.Parallel()
				got := buildFTSMatchExpr(tc.in)
				require.Equal(t, tc.want, got)
				requireBalancedQuotes(t, got)
				require.True(t, strings.HasPrefix(got, `"`), "output must start with double quote")
				require.True(t, strings.HasSuffix(got, `"`), "output must end with double quote")
			})
		}
	})

	t.Run("guardrails", func(t *testing.T) {
		t.Parallel()

		t.Run("excess terms capped at ftsMaxTerms", func(t *testing.T) {
			t.Parallel()

			terms := make([]string, 30)
			for i := range terms {
				terms[i] = "term"
			}
			got := buildFTSMatchExpr(terms)
			orCount := strings.Count(got, " OR ")
			require.Equal(t, ftsMaxTerms-1, orCount)
		})

		t.Run("long term truncated to ftsMaxTermLength", func(t *testing.T) {
			t.Parallel()

			long := strings.Repeat("x", 250)
			got := buildFTSMatchExpr([]string{long})
			// 200 chars + opening quote + closing quote = 202.
			require.Len(t, got, ftsMaxTermLength+2)
		})
	})
}

// requireBalancedQuotes asserts that the string contains an even number of double quotes.
func requireBalancedQuotes(t *testing.T, s string) {
	t.Helper()
	count := strings.Count(s, `"`)
	require.Equal(t, 0, count%2, "unbalanced double quotes in %q", s)
}
