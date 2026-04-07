.DEFAULT_GOAL := validate

.PHONY: validate
validate:
	uvx check-jsonschema \
		--schemafile knowledge_unit.json \
		fixtures/valid-unit.json \
		fixtures/minimal-unit.json \
		fixtures/flagged-unit.json \
		fixtures/duplicate-flag.json
