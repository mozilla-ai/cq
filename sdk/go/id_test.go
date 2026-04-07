package cq

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestGenerateID(t *testing.T) {
	t.Parallel()

	id := GenerateID()
	require.Regexp(t, `^ku_[0-9a-f]{32}$`, id)
}

func TestGenerateIDUniqueness(t *testing.T) {
	t.Parallel()

	ids := make(map[string]struct{}, 100)
	for range 100 {
		id := GenerateID()
		_, exists := ids[id]
		require.False(t, exists, "duplicate ID generated: %s", id)
		ids[id] = struct{}{}
	}
}

func TestValidateID(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		id      string
		wantErr bool
	}{
		{name: "valid 32 hex", id: "ku_0123456789abcdef0123456789abcdef", wantErr: false},
		{name: "valid all zeros", id: "ku_00000000000000000000000000000000", wantErr: false},
		{name: "missing prefix", id: "0123456789abcdef0123456789abcdef", wantErr: true}, // pragma: allowlist secret
		{name: "wrong prefix", id: "xx_0123456789abcdef0123456789abcdef", wantErr: true},
		{name: "uuid with dashes", id: "ku_01234567-89ab-cdef-0123-456789abcdef", wantErr: true},
		{name: "too short", id: "ku_0123456789abcdef", wantErr: true},
		{name: "too long", id: "ku_0123456789abcdef0123456789abcdef00", wantErr: true},
		{name: "uppercase hex", id: "ku_0123456789ABCDEF0123456789ABCDEF", wantErr: true},
		{name: "empty", id: "", wantErr: true},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			err := ValidateID(tc.id)
			if tc.wantErr {
				require.Error(t, err)
			} else {
				require.NoError(t, err)
			}
		})
	}
}
