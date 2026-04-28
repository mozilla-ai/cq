package cqschema

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSchemaAccessorsReturnNonEmptyJSON(t *testing.T) {
	t.Parallel()

	schemas := map[string][]byte{
		"confirm":        ConfirmSchema(),
		"flag":           FlagSchema(),
		"health":         HealthSchema(),
		"knowledge_unit": KnowledgeUnitSchema(),
		"propose":        ProposeSchema(),
		"query":          QuerySchema(),
		"review":         ReviewSchema(),
		"scoring":        ScoringSchema(),
		"stats":          StatsSchema(),
	}
	for name, raw := range schemas {
		require.NotEmpty(t, raw, "schema %s should be embedded", name)
		var doc map[string]any
		require.NoError(t, json.Unmarshal(raw, &doc), "schema %s should be valid JSON", name)
		require.Equal(t, "https://json-schema.org/draft/2020-12/schema", doc["$schema"], "schema %s should declare draft 2020-12", name)
	}
}

func TestScoringValuesValidatesAgainstScoringSchema(t *testing.T) {
	t.Parallel()

	var schema map[string]any
	require.NoError(t, json.Unmarshal(ScoringSchema(), &schema))

	props, ok := schema["$defs"].(map[string]any)
	require.True(t, ok, "scoring.json must declare $defs")
	weights, ok := props["RelevanceWeights"].(map[string]any)
	require.True(t, ok)
	weightProps, ok := weights["properties"].(map[string]any)
	require.True(t, ok)

	require.Contains(t, weightProps, "domain_weight")
	require.Contains(t, weightProps, "language_weight")
	require.Contains(t, weightProps, "framework_weight")
	require.Contains(t, weightProps, "pattern_weight")
}

func TestSchemaAccessorsReturnDefensiveCopies(t *testing.T) {
	t.Parallel()

	first := KnowledgeUnitSchema()
	first[0] = byte('!')
	second := KnowledgeUnitSchema()

	require.NotEqual(t, first[0], second[0])
}
