package install

import (
	"testing"

	"github.com/stretchr/testify/require"
)

func TestCheckProjectSupport(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		targets Targets
		wantErr []string
	}{
		{name: "all hosts support projects", targets: Targets{TargetClaude}},
		{
			name:    "names every unsupported host",
			targets: Targets{TargetClaude, TargetCodex, TargetCursor},
			wantErr: []string{
				"host codex does not support project installs",
				"host cursor does not support project installs",
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			err := CheckProjectSupport(SelectHosts(tc.targets))
			if len(tc.wantErr) == 0 {
				require.NoError(t, err)
				return
			}

			for _, want := range tc.wantErr {
				require.ErrorContains(t, err, want)
			}
			require.NotContains(t, err.Error(), "host claude")
		})
	}
}
