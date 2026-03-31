package cq

import (
	"fmt"
	"strings"
)

// Store-level query limits and filter bounds.
const (
	// defaultStoreQueryLimit is used when no explicit limit option is provided.
	defaultStoreQueryLimit = 100

	// maxQueryDomains is the maximum number of domain tags in a single query.
	maxQueryDomains = 50

	// maxQueryFrameworks is the maximum number of framework filters in a single query.
	maxQueryFrameworks = 50

	// maxQueryLanguages is the maximum number of language filters in a single query.
	maxQueryLanguages = 50

	// maxQueryLimit is the maximum number of results a query can return.
	maxQueryLimit = 500
)

// queryOptions configures a store query.
type queryOptions struct {
	domains    map[string]struct{}
	languages  map[string]struct{}
	frameworks map[string]struct{}
	limit      int
}

// queryOption configures a store query.
type queryOption func(*queryOptions) error

// defaultQueryOptions returns queryOptions populated with compile-time defaults.
func defaultQueryOptions() queryOptions {
	return queryOptions{
		domains:    make(map[string]struct{}),
		languages:  make(map[string]struct{}),
		frameworks: make(map[string]struct{}),
		limit:      defaultStoreQueryLimit,
	}
}

// newQueryOptions applies the given options over defaults and returns the resolved queryOptions.
func newQueryOptions(opt ...queryOption) (queryOptions, error) {
	opts := defaultQueryOptions()

	for _, o := range opt {
		if o == nil {
			continue
		}

		if err := o(&opts); err != nil {
			return queryOptions{}, err
		}
	}

	return opts, nil
}

// withDomain adds a domain tag to the query. Call multiple times for multiple domains.
func withDomain(domain string) queryOption {
	return func(p *queryOptions) error {
		d := strings.ToLower(strings.TrimSpace(domain))

		if d == "" {
			return nil
		}

		if _, exists := p.domains[d]; exists {
			return nil
		}

		if len(p.domains) >= maxQueryDomains {
			return fmt.Errorf("maximum number of domains reached")
		}

		p.domains[d] = struct{}{}

		return nil
	}
}

// withLanguage adds a language filter to the query. Call multiple times for multiple languages.
func withLanguage(language string) queryOption {
	return func(p *queryOptions) error {
		l := strings.ToLower(strings.TrimSpace(language))

		if l == "" {
			return nil
		}

		if _, exists := p.languages[l]; exists {
			return nil
		}

		if len(p.languages) >= maxQueryLanguages {
			return fmt.Errorf("maximum number of languages reached")
		}

		p.languages[l] = struct{}{}

		return nil
	}
}

// withFramework adds a framework filter to the query. Call multiple times for multiple frameworks.
func withFramework(framework string) queryOption {
	return func(p *queryOptions) error {
		f := strings.ToLower(strings.TrimSpace(framework))

		if f == "" {
			return nil
		}

		if _, exists := p.frameworks[f]; exists {
			return nil
		}

		if len(p.frameworks) >= maxQueryFrameworks {
			return fmt.Errorf("maximum number of frameworks reached")
		}

		p.frameworks[f] = struct{}{}

		return nil
	}
}

// withLimit sets the maximum number of results.
func withLimit(limit int) queryOption {
	return func(p *queryOptions) error {
		if limit <= 0 {
			return fmt.Errorf("limit must be greater than 0: %d", limit)
		}

		if limit > maxQueryLimit {
			return fmt.Errorf("limit must be less than max query limit: %d", limit)
		}

		p.limit = limit

		return nil
	}
}
