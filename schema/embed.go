package cqschema

import (
	"bytes"
	_ "embed"
)

//go:embed knowledge_unit.json
var knowledgeUnitSchema []byte

//go:embed scoring.json
var scoringSchema []byte

//go:embed query.json
var querySchema []byte

//go:embed propose.json
var proposeSchema []byte

//go:embed confirm.json
var confirmSchema []byte

//go:embed flag.json
var flagSchema []byte

//go:embed review.json
var reviewSchema []byte

//go:embed health.json
var healthSchema []byte

//go:embed stats.json
var statsSchema []byte

//go:embed scoring.values.json
var scoringValuesRaw []byte

// ConfirmSchema returns the raw bytes of confirm.json.
func ConfirmSchema() []byte { return bytes.Clone(confirmSchema) }

// FlagSchema returns the raw bytes of flag.json.
func FlagSchema() []byte { return bytes.Clone(flagSchema) }

// HealthSchema returns the raw bytes of health.json.
func HealthSchema() []byte { return bytes.Clone(healthSchema) }

// KnowledgeUnitSchema returns the raw bytes of knowledge_unit.json.
func KnowledgeUnitSchema() []byte { return bytes.Clone(knowledgeUnitSchema) }

// ProposeSchema returns the raw bytes of propose.json.
func ProposeSchema() []byte { return bytes.Clone(proposeSchema) }

// QuerySchema returns the raw bytes of query.json.
func QuerySchema() []byte { return bytes.Clone(querySchema) }

// ReviewSchema returns the raw bytes of review.json.
func ReviewSchema() []byte { return bytes.Clone(reviewSchema) }

// ScoringSchema returns the raw bytes of scoring.json.
func ScoringSchema() []byte { return bytes.Clone(scoringSchema) }

// ScoringValues returns the raw bytes of scoring.values.json.
func ScoringValues() []byte { return bytes.Clone(scoringValuesRaw) }

// StatsSchema returns the raw bytes of stats.json.
func StatsSchema() []byte { return bytes.Clone(statsSchema) }
