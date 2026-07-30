package cqschema

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestFieldLimitsMatchSchema(t *testing.T) {
	t.Parallel()

	var schema map[string]any
	require.NoError(t, json.Unmarshal(KnowledgeUnitSchema(), &schema))

	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Insight", "properties", "summary", "maxLength"),
		SummaryMaxLength(),
	)
	require.Equal(t, schemaLimit(t, schema, "$defs", "Insight", "properties", "detail", "maxLength"), DetailMaxLength())
	require.Equal(t, schemaLimit(t, schema, "$defs", "Insight", "properties", "action", "maxLength"), ActionMaxLength())
	require.Equal(t, schemaLimit(t, schema, "properties", "domains", "items", "maxLength"), DomainMaxLength())
	require.Equal(t, schemaLimit(t, schema, "properties", "created_by", "maxLength"), CreatedByMaxLength())
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Context", "properties", "pattern", "maxLength"),
		PatternMaxLength(),
	)
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Context", "properties", "languages", "items", "maxLength"),
		LanguageMaxLength(),
	)
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Context", "properties", "frameworks", "items", "maxLength"),
		FrameworkMaxLength(),
	)
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Flag", "properties", "detail", "maxLength"),
		FlagDetailMaxLength(),
	)
	require.Equal(t, schemaLimit(t, schema, "properties", "domains", "maxItems"), DomainsMaxItems())
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Context", "properties", "languages", "maxItems"),
		LanguagesMaxItems(),
	)
	require.Equal(
		t,
		schemaLimit(t, schema, "$defs", "Context", "properties", "frameworks", "maxItems"),
		FrameworksMaxItems(),
	)
}

func TestFieldLimitsArePositive(t *testing.T) {
	t.Parallel()

	require.Positive(t, SummaryMaxLength())
	require.Positive(t, DetailMaxLength())
	require.Positive(t, ActionMaxLength())
	require.Positive(t, DomainMaxLength())
	require.Positive(t, CreatedByMaxLength())
	require.Positive(t, PatternMaxLength())
	require.Positive(t, LanguageMaxLength())
	require.Positive(t, FrameworkMaxLength())
	require.Positive(t, FlagDetailMaxLength())
	require.Positive(t, DomainsMaxItems())
	require.Positive(t, LanguagesMaxItems())
	require.Positive(t, FrameworksMaxItems())
}

// schemaLimit walks path through the parsed schema, treating every element
// but the last as an object key and the last as an integer keyword, and
// returns that integer.
func schemaLimit(t *testing.T, schema map[string]any, path ...string) int {
	t.Helper()

	node := schema
	for _, key := range path[:len(path)-1] {
		child, ok := node[key].(map[string]any)
		require.True(t, ok)
		node = child
	}
	value, ok := node[path[len(path)-1]].(float64)
	require.True(t, ok)
	return int(value)
}
