package cq

import (
	"encoding/json"
	"time"
)

// Context describes the programming context where a knowledge unit applies.
type Context struct {
	Languages  []string `json:"languages"`
	Frameworks []string `json:"frameworks"`
	Pattern    string   `json:"pattern"`
}

// DrainResult holds the outcome of a drain operation.
type DrainResult struct {
	Pushed   int      `json:"pushed"`
	Warnings Warnings `json:"warnings,omitempty"`
}

// Evidence tracks confidence metrics for a knowledge unit.
type Evidence struct {
	Confidence    float64    `json:"confidence"`
	Confirmations int32      `json:"confirmations"`
	FirstObserved *time.Time `json:"first_observed,omitempty"`
	LastConfirmed *time.Time `json:"last_confirmed,omitempty"`
}

// Facets counts how many units carry each tag value across a listing.
type Facets struct {
	// Domains counts the units carrying each subject tag.
	Domains map[string]int `json:"domains"`

	// Frameworks counts the units carrying each framework.
	Frameworks map[string]int `json:"frameworks"`

	// Languages counts the units carrying each language.
	Languages map[string]int `json:"languages"`
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
	ID           string         `json:"id"`
	Version      int32          `json:"version"`
	Domains      []string       `json:"domains"`
	Insight      Insight        `json:"insight"`
	Context      Context        `json:"context"`
	Evidence     Evidence       `json:"evidence"`
	Tier         Tier           `json:"tier"`
	CreatedBy    string         `json:"created_by"`
	SupersededBy string         `json:"superseded_by,omitempty"`
	Extensions   map[string]any `json:"extensions,omitempty"`
	Flags        []Flag         `json:"flags"`
}

// ListParams narrows a listing of the caller's own knowledge units.
type ListParams struct {
	// Cursor continues a listing from where an earlier page stopped. An
	// empty value starts at the newest unit.
	Cursor string

	// Domains limits the listing to units carrying any of these subject
	// tags. Values within an axis widen the selection; the axes narrow
	// against each other.
	Domains []string

	// Frameworks limits the listing to units carrying any of these
	// frameworks.
	Frameworks []string

	// Languages limits the listing to units carrying any of these
	// languages.
	Languages []string

	// Limit caps the number of units returned. A non-positive value leaves
	// the cap to the server.
	Limit int

	// Pattern limits the listing to units carrying this cross-cutting
	// concern. An empty value leaves the pattern unfiltered.
	Pattern string

	// Search limits the listing to units whose summary, detail or action
	// matches this text. An empty value leaves the text unfiltered.
	Search string

	// Status limits the listing to one review state. The zero value leaves
	// the selection to the server.
	Status ReviewStatus
}

// ListResult holds the caller's own knowledge units alongside metadata
// about the listing.
type ListResult struct {
	// Facets counts the tag values across the whole filtered listing, not
	// only the page returned.
	Facets Facets `json:"facets"`

	// NextCursor resumes the listing after the last unit returned. An empty
	// value means the listing reached its end.
	NextCursor string `json:"next_cursor,omitempty"`

	// Units contains the caller's own units, each carrying the review state
	// the server holds for it.
	Units []OwnUnit `json:"units"`

	// Warnings collects non-fatal issues encountered during the listing.
	Warnings Warnings `json:"warnings,omitempty"`
}

// OwnUnit is a knowledge unit the caller authored, paired with its review
// state.
//
// NOTE: review state exists only on a server. A unit held in the local
// store has never been reviewed and is therefore never an OwnUnit.
type OwnUnit struct {
	// KnowledgeUnit is the unit as the server holds it.
	KnowledgeUnit

	// Status is the review state the server reported for this unit.
	Status ReviewStatus `json:"status"`
}

// ProposeParams describes a new knowledge unit to create.
type ProposeParams struct {
	Summary    string
	Detail     string
	Action     string
	Domains    []string
	Languages  []string       // Optional.
	Frameworks []string       // Optional.
	Pattern    string         // Optional.
	CreatedBy  string         // Optional.
	Extensions map[string]any // Optional.
}

// QueryParams configures a knowledge unit search.
type QueryParams struct {
	Domains    []string
	Languages  []string // Optional.
	Frameworks []string // Optional.
	Pattern    string   // Optional.
	Limit      int      // Default 5, max 50.
}

// QueryResult holds query results alongside metadata about the query.
type QueryResult struct {
	// Units contains the matched knowledge units, potentially merged from
	// local and remote stores. Each unit's Tier field indicates its origin
	// and determines how subsequent operations (Confirm, Flag) are routed.
	Units []KnowledgeUnit `json:"units"`

	// Source indicates whether the query consulted only the local store
	// (SourceLocal) or was configured to also consult a remote API
	// (SourceRemote). This is metadata about the query itself, not about
	// individual units.
	Source QuerySource `json:"source"`

	// Warnings collects non-fatal issues encountered during the query.
	Warnings Warnings `json:"warnings,omitempty"`
}

// StoreStats holds aggregated statistics about the knowledge store.
type StoreStats struct {
	// TotalCount is the number of knowledge units across the local store
	// and any units a configured remote reports.
	TotalCount int `json:"total_count"`

	// DomainCounts is the per-domain unit count, summing the local store
	// with any units a configured remote reports.
	DomainCounts map[string]int `json:"domain_counts"`

	// Recent holds the most recently added units from the local store.
	Recent []KnowledgeUnit `json:"recent"`

	// ConfidenceDistribution covers the local store plus any private/org
	// units a configured remote reports; it excludes the public commons.
	// Keys are the canonical bucket labels (see confidenceBuckets).
	ConfidenceDistribution map[string]int `json:"confidence_distribution"`

	// TierCounts is the unit count per tier: the local total plus any
	// private/public totals a configured remote reports.
	TierCounts map[Tier]int `json:"tier_counts"`

	// Warnings collects non-fatal issues encountered while aggregating
	// stats, such as a remote API being unreachable. When present, the
	// reported counts reflect the local store only.
	Warnings Warnings `json:"warnings,omitempty"`
}

type Warnings []error

// flagConfig holds optional parameters for a flag operation.
type flagConfig struct {
	detail      string
	duplicateOf string
}

func (ws *Warnings) MarshalJSON() ([]byte, error) {
	v := make([]string, len(*ws))
	for i, w := range *ws {
		v[i] = w.Error()
	}
	return json.Marshal(v)
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
