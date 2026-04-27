package cqschema

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestScoringConstantsMatchValuesFile(t *testing.T) {
	t.Parallel()

	var values struct {
		RelevanceWeights struct {
			DomainWeight    float64 `json:"domain_weight"`
			LanguageWeight  float64 `json:"language_weight"`
			FrameworkWeight float64 `json:"framework_weight"`
			PatternWeight   float64 `json:"pattern_weight"`
		} `json:"relevance_weights"`
		ConfidenceConstants struct {
			InitialConfidence float64 `json:"initial_confidence"`
			ConfirmationBoost float64 `json:"confirmation_boost"`
			FlagPenalty       float64 `json:"flag_penalty"`
			Ceiling           float64 `json:"ceiling"`
			Floor             float64 `json:"floor"`
		} `json:"confidence_constants"`
	}
	require.NoError(t, json.Unmarshal(ScoringValues(), &values))

	require.Equal(t, values.RelevanceWeights.DomainWeight, DomainWeight())
	require.Equal(t, values.RelevanceWeights.LanguageWeight, LanguageWeight())
	require.Equal(t, values.RelevanceWeights.FrameworkWeight, FrameworkWeight())
	require.Equal(t, values.RelevanceWeights.PatternWeight, PatternWeight())

	require.Equal(t, values.ConfidenceConstants.InitialConfidence, InitialConfidence())
	require.Equal(t, values.ConfidenceConstants.ConfirmationBoost, ConfirmationBoost())
	require.Equal(t, values.ConfidenceConstants.FlagPenalty, FlagPenalty())
	require.Equal(t, values.ConfidenceConstants.Ceiling, ConfidenceCeiling())
	require.Equal(t, values.ConfidenceConstants.Floor, ConfidenceFloor())
}
