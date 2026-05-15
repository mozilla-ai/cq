package cqschema

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"
	"github.com/xeipuuv/gojsonschema"
)

func TestNodeDiscoverySchemaAcceptsValidFixtures(t *testing.T) {
	t.Parallel()

	schemaLoader := gojsonschema.NewBytesLoader(NodeDiscoverySchema())

	cases := []struct {
		name string
		path string
	}{
		{"minimal", "fixtures/node_discovery_minimal.json"},
		{"split", "fixtures/node_discovery_split.json"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			raw, err := os.ReadFile(tc.path)
			require.NoError(t, err)

			result, err := gojsonschema.Validate(schemaLoader, gojsonschema.NewBytesLoader(raw))
			require.NoError(t, err)
			require.Truef(t, result.Valid(), "fixture %s should validate, got errors: %v", tc.path, result.Errors())
		})
	}
}

func TestNodeDiscoverySchemaRejectsInvalidFixture(t *testing.T) {
	t.Parallel()

	schemaLoader := gojsonschema.NewBytesLoader(NodeDiscoverySchema())

	raw, err := os.ReadFile("fixtures/node_discovery_invalid_version.json")
	require.NoError(t, err)

	result, err := gojsonschema.Validate(schemaLoader, gojsonschema.NewBytesLoader(raw))
	require.NoError(t, err)
	require.False(t, result.Valid())
}
