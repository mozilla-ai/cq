package postgres

import (
	"fmt"
	"math"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	cq "github.com/mozilla-ai/cq/sdk/go"
)

// TestBuildConfidenceSQLGolden pins the exact query so any change to the
// canonical bucket definitions that alters the generated SQL trips this test.
func TestBuildConfidenceSQLGolden(t *testing.T) {
	t.Parallel()
	want := "SELECT CASE " +
		"WHEN confidence < 0.3 THEN '0.0-0.3' " +
		"WHEN confidence < 0.5 THEN '0.3-0.5' " +
		"WHEN confidence < 0.7 THEN '0.5-0.7' " +
		"ELSE '0.7-1.0' " +
		"END AS bucket, COUNT(*) AS cnt " +
		"FROM (SELECT COALESCE((data->'evidence'->>'confidence')::float, 0.5) " +
		"AS confidence FROM knowledge_units) sub " +
		"GROUP BY bucket"
	require.Equal(t, want, buildConfidenceSQL())
}

// TestBuildConfidenceSQLTracksBuckets proves the SQL stays single-sourced: every
// canonical label gets exactly one arm, finite bounds become WHEN clauses, and
// the single infinite bound becomes the ELSE fallback.
func TestBuildConfidenceSQLTracksBuckets(t *testing.T) {
	t.Parallel()
	sql := buildConfidenceSQL()

	for _, label := range cq.ConfidenceBucketLabels() {
		bound, err := cq.ConfidenceBucketBound(label)
		require.NoError(t, err)
		if math.IsInf(bound, 1) {
			require.Contains(t, sql, fmt.Sprintf("ELSE '%s'", label))
		} else {
			require.Contains(t, sql, fmt.Sprintf("WHEN confidence < %g THEN '%s'", bound, label))
		}
	}

	require.Equal(t, len(cq.ConfidenceBucketLabels()), strings.Count(sql, "THEN ")+strings.Count(sql, "ELSE "))
	require.Equal(t, 1, strings.Count(sql, "ELSE "))
}
