// Package cqschema embeds the canonical cq JSON Schemas and the parsed
// scoring values that all language SDKs share. Consumers receive raw
// schema documents (as []byte) and parsed scoring constants. The package
// deliberately ships no JSON Schema validator; Go has no stdlib option
// and forcing a third-party validator dependency on every consumer is
// heavier than the package itself. Callers that need validation can
// pass the documents to their preferred library.
package cqschema
