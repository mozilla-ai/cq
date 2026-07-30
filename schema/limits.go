package cqschema

import (
	"encoding/json"
	"sync"
)

// JSON keys used to navigate the embedded knowledge_unit.json.
const (
	keyContext    = "Context"
	keyDefs       = "$defs"
	keyFlag       = "Flag"
	keyInsight    = "Insight"
	keyItems      = "items"
	keyMaxItems   = "maxItems"
	keyMaxLength  = "maxLength"
	keyProperties = "properties"
)

// loadLimits parses the free-text ceilings from the embedded
// knowledge_unit.json, memoized so the document is parsed once on first use.
var loadLimits = sync.OnceValue(func() fieldLimits {
	var schema map[string]any
	if err := json.Unmarshal(knowledgeUnitSchema, &schema); err != nil {
		panic("cqschema: invalid knowledge_unit.json: " + err.Error())
	}
	props := objectField(schema, keyProperties)
	defs := objectField(schema, keyDefs)
	insightProps := objectField(objectField(defs, keyInsight), keyProperties)
	contextProps := objectField(objectField(defs, keyContext), keyProperties)
	flagProps := objectField(objectField(defs, keyFlag), keyProperties)

	domains := objectField(props, "domains")
	languages := objectField(contextProps, "languages")
	frameworks := objectField(contextProps, "frameworks")

	return fieldLimits{
		summaryMaxLength:    schemaInt(objectField(insightProps, "summary"), keyMaxLength),
		detailMaxLength:     schemaInt(objectField(insightProps, "detail"), keyMaxLength),
		actionMaxLength:     schemaInt(objectField(insightProps, "action"), keyMaxLength),
		domainMaxLength:     schemaInt(objectField(domains, keyItems), keyMaxLength),
		createdByMaxLength:  schemaInt(objectField(props, "created_by"), keyMaxLength),
		patternMaxLength:    schemaInt(objectField(contextProps, "pattern"), keyMaxLength),
		languageMaxLength:   schemaInt(objectField(languages, keyItems), keyMaxLength),
		frameworkMaxLength:  schemaInt(objectField(frameworks, keyItems), keyMaxLength),
		flagDetailMaxLength: schemaInt(objectField(flagProps, "detail"), keyMaxLength),
		domainsMaxItems:     schemaInt(domains, keyMaxItems),
		languagesMaxItems:   schemaInt(languages, keyMaxItems),
		frameworksMaxItems:  schemaInt(frameworks, keyMaxItems),
	}
})

// fieldLimits holds the length and cardinality ceilings declared on the
// free-text fields of knowledge_unit.json.
type fieldLimits struct {
	summaryMaxLength    int
	detailMaxLength     int
	actionMaxLength     int
	domainMaxLength     int
	createdByMaxLength  int
	patternMaxLength    int
	languageMaxLength   int
	frameworkMaxLength  int
	flagDetailMaxLength int
	domainsMaxItems     int
	languagesMaxItems   int
	frameworksMaxItems  int
}

// ActionMaxLength returns the maximum length, in characters, of insight.action.
func ActionMaxLength() int { return loadLimits().actionMaxLength }

// CreatedByMaxLength returns the maximum length, in characters, of created_by.
func CreatedByMaxLength() int { return loadLimits().createdByMaxLength }

// DetailMaxLength returns the maximum length, in characters, of insight.detail.
func DetailMaxLength() int { return loadLimits().detailMaxLength }

// DomainMaxLength returns the maximum length, in characters, of a single domain tag.
func DomainMaxLength() int { return loadLimits().domainMaxLength }

// DomainsMaxItems returns the maximum number of domain tags on a unit.
func DomainsMaxItems() int { return loadLimits().domainsMaxItems }

// FlagDetailMaxLength returns the maximum length, in characters, of a flag's detail.
func FlagDetailMaxLength() int { return loadLimits().flagDetailMaxLength }

// FrameworkMaxLength returns the maximum length, in characters, of a single framework tag.
func FrameworkMaxLength() int { return loadLimits().frameworkMaxLength }

// FrameworksMaxItems returns the maximum number of framework tags in context.
func FrameworksMaxItems() int { return loadLimits().frameworksMaxItems }

// LanguageMaxLength returns the maximum length, in characters, of a single language tag.
func LanguageMaxLength() int { return loadLimits().languageMaxLength }

// LanguagesMaxItems returns the maximum number of language tags in context.
func LanguagesMaxItems() int { return loadLimits().languagesMaxItems }

// PatternMaxLength returns the maximum length, in characters, of context.pattern.
func PatternMaxLength() int { return loadLimits().patternMaxLength }

// SummaryMaxLength returns the maximum length, in characters, of insight.summary.
func SummaryMaxLength() int { return loadLimits().summaryMaxLength }

// objectField returns the named child object of a parsed schema node,
// panicking if it is absent or not an object.
func objectField(node map[string]any, key string) map[string]any {
	child, ok := node[key].(map[string]any)
	if !ok {
		panic("cqschema: knowledge_unit.json missing object " + key)
	}
	return child
}

// schemaInt returns the named integer keyword (such as maxLength or
// maxItems) declared on a parsed schema node, panicking if it is absent.
func schemaInt(node map[string]any, keyword string) int {
	value, ok := node[keyword].(float64)
	if !ok {
		panic("cqschema: knowledge_unit.json missing " + keyword + " keyword")
	}
	return int(value)
}
