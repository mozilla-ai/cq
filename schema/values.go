package cqschema

import "encoding/json"

// Scoring weights and confidence bounds parsed from scoring.values.json.
// Treat as immutable: mutating these breaks every downstream consumer
// running in the same process.
var (
	DomainWeight    float64
	LanguageWeight  float64
	FrameworkWeight float64
	PatternWeight   float64

	InitialConfidence float64
	ConfirmationBoost float64
	FlagPenalty       float64
	ConfidenceCeiling float64
	ConfidenceFloor   float64
)

func init() {
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
	if err := json.Unmarshal(scoringValuesRaw, &values); err != nil {
		panic("cqschema: invalid scoring.values.json: " + err.Error())
	}
	DomainWeight = values.RelevanceWeights.DomainWeight
	LanguageWeight = values.RelevanceWeights.LanguageWeight
	FrameworkWeight = values.RelevanceWeights.FrameworkWeight
	PatternWeight = values.RelevanceWeights.PatternWeight

	InitialConfidence = values.ConfidenceConstants.InitialConfidence
	ConfirmationBoost = values.ConfidenceConstants.ConfirmationBoost
	FlagPenalty = values.ConfidenceConstants.FlagPenalty
	ConfidenceCeiling = values.ConfidenceConstants.Ceiling
	ConfidenceFloor = values.ConfidenceConstants.Floor
}
