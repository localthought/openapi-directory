# Moneybird readable record subset

The complete provider document remains at `../v2/openapi.yaml`. This compatible OpenAPI 3.0.3 subset preserves primary JSON list and detail operations and nested response data. `coverage.json` classifies every source GET operation, and records the source hash. `collections.json` is a generation inventory, not an OpenAPI extension or consumer execution policy.

Regenerate from the repository root with Python 3.9+ and PyYAML installed:

```sh
python APIs/moneybird.com/v2-readonly/generate.py
```

Validate conversion behavior with `openapi-schema-validator` installed:

```sh
python -m unittest discover -s APIs/moneybird.com/v2-readonly
```

The subset includes JSON download records; downloading attachment bytes and generated PDF/UBL payloads is separate. Duplicate lookup/filter/synchronization endpoints do not create additional record collections. Reports require their own period/aggregation selections and are identified separately in the coverage report. Nested records remain represented in the copied response schemas.

Publication of this document does not promote a catalog pin or prove that every collection has been synchronized. Pagination, authentication, relationships, and runtime coverage are validated separately before promotion.
