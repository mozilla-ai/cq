package cq

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestValidateExtensionKeys(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		key     string
		wantErr bool
	}{
		{
			name:    "simple namespaced key",
			key:     "impl:key",
			wantErr: false,
		},
		{
			name:    "cq namespace",
			key:     "cq:severity",
			wantErr: false,
		},
		{
			name:    "hyphenated namespace",
			key:     "my-impl:nested-key",
			wantErr: false,
		},
		{
			name:    "digit in namespace",
			key:     "x0:flag",
			wantErr: false,
		},
		{
			name:    "minimal single chars",
			key:     "a:b",
			wantErr: false,
		},
		{
			name:    "underscore in namespace",
			key:     "abc_def:ghi",
			wantErr: false,
		},
		{
			name:    "digits after first char",
			key:     "tool123:config",
			wantErr: false,
		},
		{
			name:    "dashes in value",
			key:     "impl:key-with-dashes",
			wantErr: false,
		},
		{
			name:    "underscores in value",
			key:     "impl:key_with_underscores",
			wantErr: false,
		},
		{
			name:    "dots in value",
			key:     "impl:key.with.dots",
			wantErr: false,
		},
		{
			name:    "slashes in value",
			key:     "impl:key/with/slashes",
			wantErr: false,
		},
		{
			name:    "numeric value",
			key:     "impl:123",
			wantErr: false,
		},
		{
			name:    "uppercase in value",
			key:     "ns:UPPER-value",
			wantErr: false,
		},
		{
			name:    "missing colon",
			key:     "no-namespace",
			wantErr: true,
		},
		{
			name:    "empty namespace",
			key:     ":missing-slug",
			wantErr: true,
		},
		{
			name:    "uppercase namespace",
			key:     "MixedCase:key",
			wantErr: true,
		},
		{
			name:    "empty string",
			key:     "",
			wantErr: true,
		},
		{
			name:    "all uppercase namespace",
			key:     "UPPER:key",
			wantErr: true,
		},
		{
			name:    "namespace starts with dash",
			key:     "-starts-with-dash:key",
			wantErr: true,
		},
		{
			name:    "namespace starts with underscore",
			key:     "_starts-with-underscore:key",
			wantErr: true,
		},
		{
			name:    "empty value after colon",
			key:     "impl:",
			wantErr: true,
		},
		{
			name:    "leading space in namespace",
			key:     " space:key",
			wantErr: true,
		},
		{
			name:    "leading space in value",
			key:     "impl: space-value",
			wantErr: true,
		},
		{
			name:    "embedded space in value",
			key:     "impl:has space",
			wantErr: true,
		},
		{
			name:    "tab in value",
			key:     "impl:\ttab-value",
			wantErr: true,
		},
		{
			name:    "newline in value",
			key:     "impl:new\nline",
			wantErr: true,
		},
		{
			name:    "space-only value",
			key:     "impl: ",
			wantErr: true,
		},
		{
			name:    "space in namespace",
			key:     "a b:key",
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := ValidateExtensionKeys(map[string]any{tc.key: "v"})
			if tc.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
			}
		})
	}
}

func TestValidateExtensionKeysNilMapIsValid(t *testing.T) {
	t.Parallel()
	require.NoError(t, ValidateExtensionKeys(nil))
}

func TestValidateExtensionKeysEmptyMapIsValid(t *testing.T) {
	t.Parallel()
	require.NoError(t, ValidateExtensionKeys(map[string]any{}))
}
