package cq

import (
	"slices"
	"time"
)

// Scoring weights and confidence bounds used to rank knowledge units.
const (
	confidenceCeiling = 1.0
	confidenceFloor   = 0.0

	confirmationBoost = 0.1
	flagPenalty       = 0.15

	domainWeight    = 0.7
	frameworkWeight = 0.15
	languageWeight  = 0.15
)

// relevance scores how relevant ku is to the given query parameters.
func (ku KnowledgeUnit) relevance(
	queryDomains []string,
	queryLanguages []string,
	queryFrameworks []string,
) float64 {
	domainScore := jaccardSimilarity(ku.Domains, queryDomains)
	var languageScore, frameworkScore float64
	if anyMatch(ku.Context.Languages, queryLanguages) {
		languageScore = 1.0
	}
	if anyMatch(ku.Context.Frameworks, queryFrameworks) {
		frameworkScore = 1.0
	}
	score := domainWeight*domainScore + languageWeight*languageScore + frameworkWeight*frameworkScore
	return min(max(score, confidenceFloor), confidenceCeiling)
}

// anyMatch reports whether any element in queries appears in items.
func anyMatch(items []string, queries []string) bool {
	if len(queries) == 0 {
		return false
	}
	set := make(map[string]struct{}, len(items))
	for _, item := range items {
		set[item] = struct{}{}
	}
	for _, q := range queries {
		if _, ok := set[q]; ok {
			return true
		}
	}
	return false
}

// applyConfirmation returns a copy of ku with boosted confidence and incremented confirmation count.
func applyConfirmation(ku KnowledgeUnit) KnowledgeUnit {
	out := ku
	out.Domains = slices.Clone(ku.Domains)
	out.Flags = slices.Clone(ku.Flags)
	out.Context.Languages = slices.Clone(ku.Context.Languages)
	out.Context.Frameworks = slices.Clone(ku.Context.Frameworks)
	out.Evidence.Confidence = min(out.Evidence.Confidence+confirmationBoost, confidenceCeiling)
	out.Evidence.Confirmations++
	now := time.Now()
	out.Evidence.LastConfirmed = &now
	return out
}

// applyFlag returns a copy of ku with reduced confidence and the given flag appended.
func applyFlag(ku KnowledgeUnit, reason FlagReason, cfg flagConfig) KnowledgeUnit {
	out := ku
	out.Domains = slices.Clone(ku.Domains)
	out.Context.Languages = slices.Clone(ku.Context.Languages)
	out.Context.Frameworks = slices.Clone(ku.Context.Frameworks)
	out.Evidence.Confidence = max(out.Evidence.Confidence-flagPenalty, confidenceFloor)
	now := time.Now()
	out.Flags = append(slices.Clone(ku.Flags), Flag{
		Reason:      reason,
		Timestamp:   &now,
		Detail:      cfg.detail,
		DuplicateOf: cfg.duplicateOf,
	})
	return out
}

// jaccardSimilarity computes the Jaccard index (intersection over union) of two string slices.
func jaccardSimilarity(a []string, b []string) float64 {
	if len(a) == 0 && len(b) == 0 {
		return 0.0
	}
	setA := make(map[string]struct{}, len(a))
	for _, v := range a {
		setA[v] = struct{}{}
	}
	setB := make(map[string]struct{}, len(b))
	for _, v := range b {
		setB[v] = struct{}{}
	}
	var intersection int
	for v := range setA {
		if _, ok := setB[v]; ok {
			intersection++
		}
	}
	union := len(setA) + len(setB) - intersection
	return float64(intersection) / float64(union)
}
