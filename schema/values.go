package cqschema

import "encoding/json"

type scoringConstants struct {
	domainWeight      float64
	languageWeight    float64
	frameworkWeight   float64
	patternWeight     float64
	initialConfidence float64
	confirmationBoost float64
	flagPenalty       float64
	confidenceCeiling float64
	confidenceFloor   float64
}

var constants scoringConstants

// DomainWeight returns the domain relevance weight.
func DomainWeight() float64 { return constants.domainWeight }

// LanguageWeight returns the language relevance weight.
func LanguageWeight() float64 { return constants.languageWeight }

// FrameworkWeight returns the framework relevance weight.
func FrameworkWeight() float64 { return constants.frameworkWeight }

// PatternWeight returns the pattern relevance weight.
func PatternWeight() float64 { return constants.patternWeight }

// InitialConfidence returns the default confidence for new units.
func InitialConfidence() float64 { return constants.initialConfidence }

// ConfirmationBoost returns the confidence increase for a confirmation.
func ConfirmationBoost() float64 { return constants.confirmationBoost }

// FlagPenalty returns the confidence decrease for a flag.
func FlagPenalty() float64 { return constants.flagPenalty }

// ConfidenceCeiling returns the maximum allowed confidence.
func ConfidenceCeiling() float64 { return constants.confidenceCeiling }

// ConfidenceFloor returns the minimum allowed confidence.
func ConfidenceFloor() float64 { return constants.confidenceFloor }

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
	constants = scoringConstants{
		domainWeight:      values.RelevanceWeights.DomainWeight,
		languageWeight:    values.RelevanceWeights.LanguageWeight,
		frameworkWeight:   values.RelevanceWeights.FrameworkWeight,
		patternWeight:     values.RelevanceWeights.PatternWeight,
		initialConfidence: values.ConfidenceConstants.InitialConfidence,
		confirmationBoost: values.ConfidenceConstants.ConfirmationBoost,
		flagPenalty:       values.ConfidenceConstants.FlagPenalty,
		confidenceCeiling: values.ConfidenceConstants.Ceiling,
		confidenceFloor:   values.ConfidenceConstants.Floor,
	}
}
