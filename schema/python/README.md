# cq-schema

Canonical JSON Schemas and parsed scoring values for [cq](https://github.com/mozilla-ai/cq).

This package ships:

- The JSON Schema documents that define the cq wire format (knowledge units, scoring, query/propose/confirm/flag/review payloads, health, stats).
- Parsed scoring constants (relevance weights, confidence bounds) drawn from `scoring.values.json`.

The package deliberately ships no JSON Schema validator. Consumers that need runtime validation can pass `load_schema_bytes(name)` (or `load_schema(name)`) to their preferred library (e.g. [`jsonschema`](https://pypi.org/project/jsonschema/)).

## Usage

```python
import json

import jsonschema

from cq_schema import (
    CONFIRMATION_BOOST,
    DOMAIN_WEIGHT,
    INITIAL_CONFIDENCE,
    load_schema,
    load_schema_bytes,
)

# Parsed constants (immutable; treat as read-only).
print(DOMAIN_WEIGHT, INITIAL_CONFIDENCE, CONFIRMATION_BOOST)

# Raw schema documents.
schema = load_schema("knowledge_unit")
jsonschema.validate(instance=my_unit, schema=schema)

# Or as bytes if your validator prefers.
raw = load_schema_bytes("scoring")
```
