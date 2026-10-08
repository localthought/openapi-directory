# ClickUp v2 read-only subset source

The maintained full ClickUp v2 OpenAPI document is preserved at
[`../../v2/2.0/openapi.yaml`](../../v2/2.0/openapi.yaml). It was last changed in Git commit
`f3b0d16b015e11f98aaa78aebfb7d5c954436dbe` and has SHA-256
`91786855cf012ef7472ba15f86c2e164d69e994a5faae1b584c5338adabbf9de`. It is derived
from the current official source at
<https://developer.clickup.com/openapi/clickup-api-v2-reference.json>; the document
records its source SHA-256 as `a0a72ec97ddb4e4859b9ed89b997bb784ba5828412ff35119f41e87103069662`.
The exact downloaded official JSON currently has that same SHA-256.

Run `python3 generate_subset.py` with PyYAML installed to reproduce
`../openapi.yaml`. The generator checks the maintained full source hash before reading
it, selects only `GET /v2/team`, `GET /v2/team/{team_Id}/task`, and
`GET /v2/task/{task_id}`, and resolves schema references into components. Referenced
schemas that originally pointed into other operations are extracted as schemas; no
other operation paths are included.

The full source is OpenAPI 3.1. The subset is OpenAPI 3.0.3: source `type` unions of a
single non-null type and `null` become the equivalent OAS 3.0 `type` plus `nullable: true`;
numeric `contentEncoding` values (`int32`, `int64`, `double`) become their corresponding
`format`; schema `examples` retain the first value as `example` and, when there are
multiple, retain the complete list in `x-json-schema-examples`. Unsupported unions or
conflicting conversion constraints stop generation.

The official [Get Authorized Workspaces reference](https://developer.clickup.com/reference/getauthorizedteams)
returns Workspaces available to the authenticated user. The [Get Filtered Team Tasks
reference](https://developer.clickup.com/reference/getfilteredteamtasks) accepts a
zero-based `page` and limits responses to 100 tasks per page. The [Get Task reference](https://developer.clickup.com/reference/gettask)
retrieves one task accessible to the current user. The source's `Authorization` header
scheme covers both personal API tokens and OAuth bearer tokens. OAuth has no declared
read scope in the source; this subset invents none.

The pinned official task response examples contain values that violate their own
response schemas. This subset retains both the source schemas and examples; strict
response validation may reject those examples. Validation fixtures were adjusted only
for conversion smoke checks and are not presented as captured API responses.
