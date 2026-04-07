package cq

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestQueryOptions(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name        string
		options     []queryOption
		expected    queryOptions
		expectedErr string
	}{
		{
			name:    "no options set",
			options: []queryOption{},
			expected: queryOptions{
				domains:    make(map[string]struct{}),
				languages:  make(map[string]struct{}),
				frameworks: make(map[string]struct{}),
				limit:      100,
			},
			expectedErr: "",
		},
		{
			name: "withDomain option",
			options: []queryOption{
				withDomain("example.com"),
			},
			expected: queryOptions{
				domains: map[string]struct{}{
					"example.com": {},
				},
				languages:  make(map[string]struct{}),
				frameworks: make(map[string]struct{}),
				limit:      100,
			},
			expectedErr: "",
		},
		{
			name: "withLanguage option",
			options: []queryOption{
				withLanguage("Go"),
			},
			expected: queryOptions{
				domains:    make(map[string]struct{}),
				languages:  map[string]struct{}{"go": {}},
				frameworks: make(map[string]struct{}),
				limit:      100,
			},
			expectedErr: "",
		},
		{
			name: "withFramework option",
			options: []queryOption{
				withFramework("Gin"),
			},
			expected: queryOptions{
				domains:    make(map[string]struct{}),
				languages:  make(map[string]struct{}),
				frameworks: map[string]struct{}{"gin": {}},
				limit:      100,
			},
			expectedErr: "",
		},
		{
			name: "withLimit option",
			options: []queryOption{
				withLimit(10),
			},
			expected: queryOptions{
				domains:    make(map[string]struct{}),
				languages:  make(map[string]struct{}),
				frameworks: make(map[string]struct{}),
				limit:      10,
			},
			expectedErr: "",
		},
		{
			name: "multiple options set",
			options: []queryOption{
				withDomain("example.com"),
				withLanguage("Go"),
				withFramework("Gin"),
				withLimit(10),
			},
			expected: queryOptions{
				domains: map[string]struct{}{
					"example.com": {},
				},
				languages:  map[string]struct{}{"go": {}},
				frameworks: map[string]struct{}{"gin": {}},
				limit:      10,
			},
			expectedErr: "",
		},
		{
			name: "empty string values are ignored",
			options: []queryOption{
				withDomain(""),
				withLanguage(" "),
				withFramework(""),
			},
			expected: queryOptions{
				domains:    make(map[string]struct{}),
				languages:  make(map[string]struct{}),
				frameworks: make(map[string]struct{}),
				limit:      100,
			},
			expectedErr: "",
		},
		{
			name: "zero limit is rejected",
			options: []queryOption{
				withLimit(0),
			},
			expected:    queryOptions{},
			expectedErr: "limit must be greater than 0: 0",
		},
		{
			name: "limit exceeds maximum",
			options: []queryOption{
				withLimit(600),
			},
			expected:    queryOptions{},
			expectedErr: "limit must be less than max query limit: 600",
		},
		{
			name: "exactly max domains succeeds",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryDomains)
				for i := range maxQueryDomains {
					opts = append(opts, withDomain(fmt.Sprintf("domain%d.com", i)))
				}

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				for i := range maxQueryDomains {
					o.domains[fmt.Sprintf("domain%d.com", i)] = struct{}{}
				}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "duplicate domains are deduplicated",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryDomains+1)
				for range maxQueryDomains + 1 {
					opts = append(opts, withDomain("same-domain"))
				}

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				o.domains["same-domain"] = struct{}{}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "case normalization deduplicates domains",
			options: []queryOption{
				withDomain("API"),
				withDomain("api"),
				withDomain("Api"),
			},
			expected: func() queryOptions {
				o := defaultQueryOptions()
				o.domains["api"] = struct{}{}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "max domains plus blank succeeds",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryDomains+1)
				for i := range maxQueryDomains {
					opts = append(opts, withDomain(fmt.Sprintf("domain%d.com", i)))
				}

				opts = append(opts, withDomain(""))

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				for i := range maxQueryDomains {
					o.domains[fmt.Sprintf("domain%d.com", i)] = struct{}{}
				}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "max domains plus duplicate succeeds",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryDomains+1)
				for i := range maxQueryDomains {
					opts = append(opts, withDomain(fmt.Sprintf("domain%d.com", i)))
				}

				opts = append(opts, withDomain("domain0.com"))

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				for i := range maxQueryDomains {
					o.domains[fmt.Sprintf("domain%d.com", i)] = struct{}{}
				}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "duplicate languages are deduplicated",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryLanguages+1)
				for range maxQueryLanguages + 1 {
					opts = append(opts, withLanguage("go"))
				}

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				o.languages["go"] = struct{}{}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "duplicate frameworks are deduplicated",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryFrameworks+1)
				for range maxQueryFrameworks + 1 {
					opts = append(opts, withFramework("gin"))
				}

				return opts
			}(),
			expected: func() queryOptions {
				o := defaultQueryOptions()
				o.frameworks["gin"] = struct{}{}

				return o
			}(),
			expectedErr: "",
		},
		{
			name: "maximum domains reached",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryDomains+1)
				for i := range maxQueryDomains + 1 {
					opts = append(opts, withDomain(fmt.Sprintf("domain%d.com", i)))
				}

				return opts
			}(),
			expected:    queryOptions{},
			expectedErr: "maximum number of domains reached",
		},
		{
			name: "maximum languages reached",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryLanguages+1)
				for i := range maxQueryLanguages + 1 {
					opts = append(opts, withLanguage(fmt.Sprintf("lang%d", i)))
				}

				return opts
			}(),
			expected:    queryOptions{},
			expectedErr: "maximum number of languages reached",
		},
		{
			name: "maximum frameworks reached",
			options: func() []queryOption {
				opts := make([]queryOption, 0, maxQueryFrameworks+1)
				for i := range maxQueryFrameworks + 1 {
					opts = append(opts, withFramework(fmt.Sprintf("fw%d", i)))
				}

				return opts
			}(),
			expected:    queryOptions{},
			expectedErr: "maximum number of frameworks reached",
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			params, err := newQueryOptions(tc.options...)

			if tc.expectedErr != "" {
				require.Error(t, err)
				require.ErrorContains(t, err, tc.expectedErr)
			} else {
				require.NoError(t, err)
			}

			require.Equal(t, tc.expected, params)
		})
	}
}
