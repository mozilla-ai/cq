package cq

import (
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestKnowledgeUnitJSONRoundTrip(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 3, 30, 12, 0, 0, 0, time.UTC)
	original := KnowledgeUnit{
		ID:      "ku_0123456789abcdef0123456789abcdef",
		Version: 1,
		Domains: []string{"api", "stripe"},
		Insight: Insight{
			Summary: "Stripe returns 402 for expired cards",
			Detail:  "Check error.code, not error.type.",
			Action:  "Handle card_declined explicitly.",
		},
		Context: Context{
			Languages:  []string{"go"},
			Frameworks: []string{"net/http"},
			Pattern:    "api-client",
		},
		Evidence: Evidence{
			Confidence:    0.8,
			Confirmations: 4,
			FirstObserved: &now,
			LastConfirmed: &now,
		},
		Tier:      Local,
		CreatedBy: "test-agent",
		Flags: []Flag{
			{Reason: Stale, Timestamp: &now},
		},
	}

	data, err := json.Marshal(original)
	require.NoError(t, err)

	var result KnowledgeUnit
	require.NoError(t, json.Unmarshal(data, &result))

	require.Equal(t, original.ID, result.ID)
	require.Equal(t, original.Domains, result.Domains)
	require.Equal(t, original.Insight, result.Insight)
	require.Equal(t, original.Context, result.Context)
	require.InDelta(t, original.Evidence.Confidence, result.Evidence.Confidence, 0.001)
	require.Equal(t, original.Evidence.Confirmations, result.Evidence.Confirmations)
	require.Equal(t, original.Tier, result.Tier)
	require.Equal(t, original.CreatedBy, result.CreatedBy)
	require.Len(t, result.Flags, 1)
	require.Equal(t, Stale, result.Flags[0].Reason)
}

func TestKnowledgeUnitJSONUsesDomainsPlural(t *testing.T) {
	t.Parallel()

	ku := KnowledgeUnit{
		ID:      "ku_0123456789abcdef0123456789abcdef",
		Domains: []string{"api"},
	}
	data, err := json.Marshal(ku)
	require.NoError(t, err)

	require.Contains(t, string(data), `"domains"`)
	require.NotContains(t, string(data), `"domain"`)
}

func TestKnowledgeUnitJSONUsesLowercaseEnums(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	ku := KnowledgeUnit{
		ID:      "ku_0123456789abcdef0123456789abcdef",
		Domains: []string{"test"},
		Tier:    Local,
		Flags: []Flag{
			{Reason: Stale, Timestamp: &now},
		},
	}
	data, err := json.Marshal(ku)
	require.NoError(t, err)

	text := string(data)
	require.Contains(t, text, `"tier":"local"`)
	require.Contains(t, text, `"reason":"stale"`)
	require.NotContains(t, text, "TIER_")
	require.NotContains(t, text, "FLAG_REASON_")
}

func TestKnowledgeUnitJSONSchemaFieldCoverage(t *testing.T) {
	t.Parallel()

	schemaData, err := os.ReadFile("../../schema/knowledge_unit.json")
	require.NoError(t, err)

	var schema map[string]any
	require.NoError(t, json.Unmarshal(schemaData, &schema))

	props, ok := schema["properties"].(map[string]any)
	require.True(t, ok)

	now := time.Now().UTC()
	ku := KnowledgeUnit{
		ID:           "ku_0123456789abcdef0123456789abcdef",
		Version:      1,
		Domains:      []string{"test"},
		Insight:      Insight{Summary: "s", Detail: "d", Action: "a"},
		Context:      Context{Languages: []string{"go"}, Frameworks: []string{"f"}, Pattern: "p"},
		Evidence:     Evidence{Confidence: 0.5, Confirmations: 1, FirstObserved: &now, LastConfirmed: &now},
		Tier:         Local,
		CreatedBy:    "agent",
		SupersededBy: "ku_abcdef01234567890123456789abcdef",
		Flags:        []Flag{{Reason: Stale, Timestamp: &now}},
	}

	data, err := json.Marshal(ku)
	require.NoError(t, err)

	var kuMap map[string]any
	require.NoError(t, json.Unmarshal(data, &kuMap))

	for field := range props {
		require.Contains(t, kuMap, field, "Go KnowledgeUnit missing JSON Schema field %q", field)
	}
}

func TestTierEnumMatchesSchema(t *testing.T) {
	t.Parallel()

	schema := readTestSchema(t)
	defs, ok := schema["$defs"].(map[string]any)
	require.True(t, ok)
	tierDef, ok := defs["Tier"].(map[string]any)
	require.True(t, ok)
	schemaValues, ok := tierDef["enum"].([]any)
	require.True(t, ok)

	goValues := []Tier{Local, Private, Public}
	require.Len(t, goValues, len(schemaValues))
	for i, v := range schemaValues {
		require.Equal(t, v.(string), string(goValues[i]))
	}
}

func TestFlagReasonEnumMatchesSchema(t *testing.T) {
	t.Parallel()

	schema := readTestSchema(t)
	defs, ok := schema["$defs"].(map[string]any)
	require.True(t, ok)
	reasonDef, ok := defs["FlagReason"].(map[string]any)
	require.True(t, ok)
	schemaValues, ok := reasonDef["enum"].([]any)
	require.True(t, ok)

	goValues := []FlagReason{Stale, Incorrect, Duplicate}
	require.Len(t, goValues, len(schemaValues))
	for i, v := range schemaValues {
		require.Equal(t, v.(string), string(goValues[i]))
	}
}

func TestGenerateIDMatchesSchemaPattern(t *testing.T) {
	t.Parallel()

	schema := readTestSchema(t)
	props := schema["properties"].(map[string]any)
	idProp := props["id"].(map[string]any)
	pattern := idProp["pattern"].(string)

	require.Regexp(t, pattern, GenerateID())
}

func TestQueryParamsFieldsMatchSchema(t *testing.T) {
	t.Parallel()

	schemaData, err := os.ReadFile("../../schema/query.json")
	require.NoError(t, err)

	var schema map[string]any
	require.NoError(t, json.Unmarshal(schemaData, &schema))

	props, ok := schema["properties"].(map[string]any)
	require.True(t, ok)

	qp := QueryParams{
		Domains:    []string{"test"},
		Languages:  []string{"go"},
		Frameworks: []string{"grpc"},
		Limit:      5,
	}

	// Verify that each schema field name maps to a QueryParams field.
	fieldMap := map[string]any{
		"domains":    qp.Domains,
		"languages":  qp.Languages,
		"frameworks": qp.Frameworks,
		"limit":      qp.Limit,
	}

	for field := range props {
		_, exists := fieldMap[field]
		require.True(t, exists, "QueryParams missing field for schema property %q", field)
	}

	// Verify no extra fields in fieldMap beyond what the schema declares.
	for field := range fieldMap {
		_, exists := props[field]
		require.True(t, exists, "QueryParams has field %q not in schema", field)
	}
}

func readTestSchema(t *testing.T) map[string]any {
	t.Helper()

	schemaData, err := os.ReadFile("../../schema/knowledge_unit.json")
	require.NoError(t, err)

	var schema map[string]any
	require.NoError(t, json.Unmarshal(schemaData, &schema))

	return schema
}
