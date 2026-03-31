package cq

import "time"

// Context describes the programming context where a knowledge unit applies.
type Context struct {
	Languages  []string `json:"languages"`
	Frameworks []string `json:"frameworks"`
	Pattern    string   `json:"pattern"`
}

// DrainResult holds the outcome of a drain operation.
type DrainResult struct {
	Pushed   int     `json:"pushed"`
	Warnings []error `json:"-"`
}

// Evidence tracks confidence metrics for a knowledge unit.
type Evidence struct {
	Confidence    float64    `json:"confidence"`
	Confirmations int32      `json:"confirmations"`
	FirstObserved *time.Time `json:"first_observed,omitempty"`
	LastConfirmed *time.Time `json:"last_confirmed,omitempty"`
}

// Flag records a problem report against a knowledge unit.
type Flag struct {
	Reason      FlagReason `json:"reason"`
	Timestamp   *time.Time `json:"timestamp,omitempty"`
	Detail      string     `json:"detail,omitempty"`
	DuplicateOf string     `json:"duplicate_of,omitempty"`
}

// FlagOption configures a Flag operation.
type FlagOption func(*flagConfig)

// Insight holds the core content of a knowledge unit.
type Insight struct {
	Summary string `json:"summary"`
	Detail  string `json:"detail"`
	Action  string `json:"action"`
}

// KnowledgeUnit is a single piece of agent knowledge.
type KnowledgeUnit struct {
	ID           string   `json:"id"`
	Version      int32    `json:"version"`
	Domains      []string `json:"domains"`
	Insight      Insight  `json:"insight"`
	Context      Context  `json:"context"`
	Evidence     Evidence `json:"evidence"`
	Tier         Tier     `json:"tier"`
	CreatedBy    string   `json:"created_by"`
	SupersededBy string   `json:"superseded_by,omitempty"`
	Flags        []Flag   `json:"flags"`
}

// ProposeParams describes a new knowledge unit to create.
type ProposeParams struct {
	Summary    string
	Detail     string
	Action     string
	Domains    []string
	Languages  []string // Optional.
	Frameworks []string // Optional.
	Pattern    string   // Optional.
	CreatedBy  string   // Optional.
}

// QueryParams configures a knowledge unit search.
type QueryParams struct {
	Domains    []string
	Languages  []string // Optional.
	Frameworks []string // Optional.
	Limit      int      // Default 5, max 50.
}

// QueryResult holds query results alongside metadata about the query.
type QueryResult struct {
	Units    []KnowledgeUnit `json:"units"`
	Source   string          `json:"source"`
	Warnings []error         `json:"-"`
}

// StoreStats holds aggregated statistics about the knowledge store.
type StoreStats struct {
	TotalCount             int             `json:"total_count"`
	DomainCounts           map[string]int  `json:"domain_counts"`
	Recent                 []KnowledgeUnit `json:"recent"`
	ConfidenceDistribution map[string]int  `json:"confidence_distribution"`
}

// flagConfig holds optional parameters for a flag operation.
type flagConfig struct {
	detail      string
	duplicateOf string
}

// WithDetail adds an explanation to the flag.
func WithDetail(detail string) FlagOption {
	return func(c *flagConfig) { c.detail = detail }
}

// WithDuplicateOf specifies the original unit this duplicates.
// Required when reason is Duplicate.
func WithDuplicateOf(id string) FlagOption {
	return func(c *flagConfig) { c.duplicateOf = id }
}

// resolveFlagConfig applies options and returns the resolved config.
func resolveFlagConfig(opts []FlagOption) flagConfig {
	var cfg flagConfig
	for _, opt := range opts {
		opt(&cfg)
	}
	return cfg
}
