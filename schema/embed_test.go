package cqschema

import (
	"encoding/json"
	"maps"
	"slices"
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
		"node_discovery": NodeDiscoverySchema(),
		"propose":        ProposeSchema(),
		"query":          QuerySchema(),
		"review":         ReviewSchema(),
		"revoke":         RevokeSchema(),
		"scoring":        ScoringSchema(),
		"stats":          StatsSchema(),
	}
	for name, raw := range schemas {
		require.NotEmpty(t, raw, "schema %s should be embedded", name)
		var doc map[string]any
		require.NoError(t, json.Unmarshal(raw, &doc), "schema %s should be valid JSON", name)
		require.Equal(
			t,
			"https://json-schema.org/draft/2020-12/schema",
			doc["$schema"],
			"schema %s should declare draft 2020-12",
			name,
		)
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

func TestReviewStatusIncludesRevoked(t *testing.T) {
	t.Parallel()

	var doc map[string]any
	require.NoError(t, json.Unmarshal(ReviewSchema(), &doc))

	defs, ok := doc["$defs"].(map[string]any)
	require.True(t, ok, "review.json must declare $defs")
	status, ok := defs["ReviewStatus"].(map[string]any)
	require.True(t, ok, "review.json must define ReviewStatus")

	require.Equal(t, []any{"pending", "approved", "rejected", "revoked"}, status["enum"])
}

func TestRevokeSchemaRequiresOnlyUnitID(t *testing.T) {
	t.Parallel()

	var doc map[string]any
	require.NoError(t, json.Unmarshal(RevokeSchema(), &doc))

	require.Equal(t, []any{"unit_id"}, doc["required"])
	require.Equal(t, false, doc["additionalProperties"])

	props, ok := doc["properties"].(map[string]any)
	require.True(t, ok, "revoke.json must declare properties")
	require.Equal(t, []string{"unit_id"}, slices.Sorted(maps.Keys(props)))

	unitID, ok := props["unit_id"].(map[string]any)
	require.True(t, ok)
	require.Equal(t, "^ku_[0-9a-f]{32}$", unitID["pattern"])
}
