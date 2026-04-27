.DEFAULT_GOAL := validate

.PHONY: validate
validate: validate-fixtures validate-values

.PHONY: validate-fixtures
validate-fixtures:
	uvx check-jsonschema \
		--schemafile knowledge_unit.json \
		fixtures/valid-unit.json \
		fixtures/minimal-unit.json \
		fixtures/flagged-unit.json \
		fixtures/duplicate-flag.json

.PHONY: validate-values
validate-values:
	uvx check-jsonschema \
		--schemafile scoring.json \
		scoring.values.json
