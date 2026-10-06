# Official-source maintenance

This updater checks only the service artifacts configured in `sources.json`,
including both public GitHub REST descriptions. It does not claim coverage of the
entire directory or discover every vendor release. Bounded monthly discovery and an
explicit per-API draft generator are implemented separately below. Scheduled PR
publication and deliberate updates to existing pending PRs remain follow-up work in
AGENTS.md §9. There is no merge command. Blocked services remain visible in reports.

Use Python 3.10+, Node.js 22.12+ (CI uses Node 24), and the pinned dependencies:

```sh
python3 -m venv /tmp/openapi-maintenance-venv
/tmp/openapi-maintenance-venv/bin/pip install -r maintenance/requirements.txt
npm ci --prefix maintenance --ignore-scripts --no-audit --no-fund
/tmp/openapi-maintenance-venv/bin/python -m unittest discover -s maintenance -v
git fetch origin main
/tmp/openapi-maintenance-venv/bin/python maintenance/update.py check
```

`requirements.in` records the direct dependencies; `requirements.txt` pins their
transitive dependencies too. `package-lock.json` pins the Redocly bundler package and its
integrity; that release includes its runtime dependencies. Update and test both locks
deliberately. GitHub Actions are
pinned to verified release commit SHAs.

The audit step uses Actions' built-in `GITHUB_TOKEN` with the workflow's existing
`contents: read` permission. Locally, an optional `GITHUB_TOKEN` environment variable
authenticates GitHub API requests; otherwise they remain anonymous and can exhaust the
shared anonymous IP quota. See GitHub's [REST authentication guide](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api).
Authentication is limited to HTTPS `api.github.com` on the default/443 port, without
URL user information. Raw files, archives and other vendor hosts receive no token.
The authorization header is dropped on every redirect, even within the same origin;
use canonical API URLs rather than relying on authenticated redirects. Request headers
are not recorded in fetch metadata or reports. A 403 fails without retrying or falling
back to anonymous access; review the report and token permissions/quota before rerunning.

`check` reads committed specs from `origin/main`, so sparse checkouts and stale feature
branches cannot hide existing providers. It resolves GitHub sources to a commit before
fetching, stores the exact original bytes and fetch metadata under `cache/maintenance/`,
and compares paths, operations, schemas, security, and other vendor content. Versions
alone are insufficient. An unchanged source is reported as `matches_source`; it is not
a guarantee that the vendor still maintains that source or that it covers the current API.

Security requirement names must resolve to `components.securitySchemes`, as required by
the [OpenAPI specification](https://spec.openapis.org/oas/v3.0.1.html#security-requirement-object).
The additional semantic check covers document security, operations, referenced path items,
callbacks and OpenAPI 3.1 webhooks, with guards for recursive callback graphs. It ignores
example payloads and extensions, accepts anonymous alternatives and explicit empty security,
and aggregates undefined names rather than flooding the report with repeated errors.
This check complements structural validation; it does not invent schemes or infer scopes.

The JSON report records check times, successes, validation errors, separate additions and
removals, source revisions/hashes, and import blockers. A failed check preserves previous
success timestamps. A check of selected sources keeps other report rows and their old
timestamps. The command exits nonzero for fetch/parse failures, validation errors, and
explicit blockers, including failed or adverse source-health checks; valid content drift
itself is an actionable finding, not a failed check.
Each row records its comparison base revision; retained older rows keep their old revision
or show it as unrecorded. A readable Markdown report is written beside the JSON report
(by default `cache/maintenance/report.md`). It distinguishes blocked matches from valid
source matches, reports added and removed paths/operations separately, and shows per-service
attempt/success dates, provenance and errors. Vendor text is escaped for Markdown display.
The ignored cache is local state, not durable publication. CI uploads both reports and
source snapshots as an artifact, and publishes the readable report in the audit job summary
even when individual services cause the check command to fail.
If a custom JSON report filename already ends in `.md`, the readable companion uses
`.summary.md` to avoid overwriting the machine-readable report.

Each run also reads GitHub's [repository metadata endpoint](https://docs.github.com/en/rest/repos/repos#get-a-repository)
for registered GitHub sources. It records the returned repository/owner identity, archived
and disabled flags, default branch, fork status, repository activity dates, retrieval time
and response hash. Exact response bytes and retrieval metadata are cached under
`cache/maintenance/source-health/` and uploaded with the audit artifact. Services sharing
a repository reuse one observation within a run, including failures; the next run checks
again. No credentials or additional repository permissions are required for public metadata.

`repository_available` means the configured public repository still resolves to the same
name (case insensitive) and is neither archived nor disabled. It does not establish vendor
ownership, description maintenance, stable releases or current API coverage. Repository
`pushed_at` and `updated_at` dates can change for unrelated files. Hosted sources are
explicitly `not_assessed` by this repository check; a successful description download alone
does not assess their ongoing maintenance. Manual manifest source-health notes and existing
import blockers remain visible independently of these live observations.

Archived/disabled repositories and changed repository identities block imports. Failed or
malformed metadata checks also block imports and make `check` exit nonzero. Content fetching,
comparison and validation continue independently, so an archived source can still be shown
to match without being counted as a valid update candidate. The report retains each attempt
and the last successful source-health check; failed attempts preserve that successful date.
An observed archive is a successful health check with an adverse finding. Previous successful
dates never stand in for a failed current observation. Import commands repeat the health check
before fetching or writing an artifact. These checks do not edit spec timestamps or remove APIs.

Validation pins `openapi-spec-validator` and `openapi-schema-validator` 0.9.0 with
`regress` 2026.9.1, using the schema validator's [official ECMAScript regex extra](https://github.com/python-openapi/openapi-schema-validator/blob/0.9.0/README.rst).
Pattern syntax and default-value matching use ECMAScript semantics with no flags,
including named captures and legacy identity escapes. No Unicode flag is inferred;
that would change matching and reject some vendor patterns. Regression cases compare
these semantics with Node's `new RegExp(pattern)`. A missing backend or changed reviewed
validator/engine pin fails validation rather than falling back to Python regex.

`validation.py` selects the Python jsonschema document backend explicitly and subclasses
the pinned spec validators' schema keyword. Its only traversal change makes upstream
property collection iterative with a visited-object guard over the same edges
(`allOf`, `anyOf`, `oneOf`, `items`, `not`). This avoids infinite cycles while retaining
required-property, schema/default, reference and document checks. It does not rewrite
schemas, raise recursion limits, disable formats or modify global validator classes.
Both OpenAPI 3.0 and 3.1 are covered by regressions; boolean schemas remain supported in
3.1, and its discriminator remains an annotation. Imports record the validation profile
in provenance; reports show it alongside actual success/error observations. Review the
adapter and tests whenever upgrading its pinned upstream APIs. OpenAPI 3.2 import support
remains outside the current updater scope.

The stricter 3.1 schema checks expose Cohere's existing invalid
`components.schemas.TruncationStrategy.oneOf: []` (official source commit
`734aafbe1fe2ca5c7356609009ec0d9b74e6ac57`). It still matches its source, but validation
blocks another import. No union alternatives are invented and no validation is waived.
Look for a vendor correction; other existing source-specific defects remain reported.

Import one service on its own branch, widening the sparse cone first if necessary:

```sh
git switch -c codex/refresh-plaid origin/main
git sparse-checkout add APIs/plaid.com
/tmp/openapi-maintenance-venv/bin/python maintenance/update.py import --source plaid
git diff --check
```

The importer re-fetches and validates the official artifact, records provenance in its
`info` block, preserves existing curation, creates a new directory for a new declared
version, and refuses to overwrite local changes. If that version already exists, it is
the comparison baseline; otherwise the manifest target is the reviewed current baseline.
A successful import advances that target to the imported version. Commit the manifest
change with that API's new file, retaining historical directories. Version ordering is
never guessed across vendor schemes. The report names the actual comparison baseline.
An unchanged import writes no spec; it only repairs a lagging manifest target if needed.
Manifest changes are checked before writing, preserving unrelated configuration and its
formatting. Versions must be safe directory names.
Empty versions and snapshot policies require an explicit future recipe, not an invented
vendor version. Existing curation tags are merged by name, with vendor fields taking
precedence and curated tags preserved.

Run `check --source plaid` to select one service, or repeat `--source` for several. Use
`--report PATH` and `--cache PATH` to retain state in an appropriate location. Add sources
to `sources.json` only after verifying ownership, service scope, stable-release selection,
and absence from the full main tree. Known upstream defects need documented patches or
reviewed exceptions before import; this tool has no validation bypass.

Twilio's classic REST artifact follows the exact `spec/json/twilio_api_v2010.json`
source cited by the stored `api/1.55.0` description. The [official repository](https://github.com/twilio/twilio-oai)
labels the specification project GA and actively maintained (checked 2026-10-03).
The vendor's [June 2024 MVR release](https://github.com/twilio/twilio-oai/pull/111)
reset this artifact's declared version from `1.56.1` to `1.0.0`; the repository's
`2.8.3` release number is a different version. Preserve the old directory and use the
actual source `info.version` for imports, without assuming numeric version ordering.
This source monitors classic `api.twilio.com` REST routes only. Other Twilio service
artifacts, preview APIs and TwiML need separate review. Keep vendor lifecycle annotations;
the repository's GA label is not a guarantee that every included operation is GA.
The latest source omits `/healthcheck`, which the stored vendor metadata already labelled
private; report that removal without claiming the runtime endpoint was retired.

Twilio Messaging is registered separately from classic REST, following
`spec/json/twilio_messaging_v1.json` and monitoring `messaging.twilio.com` v1 resource
management only. Its [DestinationAlphaSenders](https://www.twilio.com/docs/messaging/api/destination-alphasender-resource)
and [ChannelSenders](https://www.twilio.com/docs/messaging/api/messaging-service-channelsender-resource)
references label REST Messaging Service configuration **Public Beta**, while message
sending is GA (checked 2026-10-03). Preserve the complete public vendor artifact, including
those features, and report that lifecycle limitation. The source's removal of old
`x-maturity` annotations is not evidence of graduation to GA. This artifact also resets
from `1.56.1` to `1.0.0` at vendor PR 111; retain historical versions. Classic Message
sending routes, other service descriptions, previews and TwiML are separate scope.
The validated import is currently blocked by GitHub push protection on a published
account-SID example (checked 2026-10-03). A source-specific import guard prevents repeated
attempts while preserving read-only freshness checks. The repo owner must review
allowlisting or authorize an exact, documented redaction; do not bypass protection or
silently modify the example. This is a delivery blocker, not a schema-validation failure.

Twilio Verify follows the existing official `spec/json/twilio_verify_v2.json` artifact
and the [Verify v2 API overview](https://www.twilio.com/docs/verify/api). Its complete
public description includes Passkeys, which the [vendor overview](https://www.twilio.com/docs/verify/passkeys)
explicitly labels **private beta** (checked 2026-10-03). This refresh monitors the same
broad artifact already stored here; it is not a stable-only subset. Record that feature
limitation in coverage reports. Removed old maturity annotations and the spec project's
GA label do not establish feature graduation. This artifact's declared version also
resets from `1.56.1` to `1.0.0` at vendor PR 111; preserve historical directories and
compare pinned content rather than numeric version order. Other Twilio services,
preview artifacts and TwiML remain separate scope.

Snowflake's View and Stage services are registered separately from its other resources.
The [REST reference](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/reference)
identifies the public catalog as generally available. Their
[View guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/view/view-introduction)
and [Stage guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/stages/stages-introduction)
carry no preview designation (checked 2026-10-03). These guides summarize service scope;
they are not a replacement for the complete source description. View bundles `common.yaml`;
Stage also bundles `common-file-format.yaml`, all from the same pinned revision. Shared
helper files are not separate APIs. Both declare version `0.0.1`; compare their content
rather than assuming this placeholder advances with changes. Other Snowflake services,
especially individually designated previews, still need their own lifecycle review.

Snowflake Task is a distinct resource API registered from `specifications/task.yaml`.
The [GA REST tutorial overview](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/tutorials-overview)
explicitly includes task management, and the [Task guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/tasks/tasks-introduction)
and [complete reference](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/reference/task)
carry no preview designation (checked 2026-10-03). Retain the vendor's deprecated
`current_graphs` / `complete_graphs` endpoints alongside their hyphenated replacements,
including their annotations. Bundle only the task entry and `common.yaml` from one pinned
revision. The declared `0.0.1` is kept unchanged; full-content comparisons are required.
This artifact describes Task REST management, not every SQL task command or other
Snowflake services. Shared helper files are not APIs.

Snowflake User and Role are separate resource APIs from the official catalog. Their
[User guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/users/users-introduction)
and [Role guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/roles/roles-introduction),
and complete references, carry no preview designation (checked 2026-10-06).
The introductory tables omit tag actions that are included in both full references
and source artifacts; keep all 7 paths / 11 operations for User and 11 / 14 for Role.
Each bundles only its entry plus `common.yaml` from one pinned revision with Redocly
2.57.0, zero warnings and no patches or version conversion. Preserve all native
authentication alternatives, privilege/revocation restrictions and the active-warehouse
requirement for retrieving tag assignments. Neither is complete SQL coverage or the
separate Database Role API. Keep vendor `0.0.1` and compare full content on future checks.

Snowflake Database Role is a separate database-scoped resource API, distinct from the
account-level Role and User descriptions. Its [guide](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/database-role/database-role-introduction)
and [complete reference](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/reference/database-role)
have no preview designation (checked 2026-10-06). Keep all 10 paths / 13 operations,
including three tag actions absent from the introductory table; bundle the entry and
`common.yaml` with zero warnings and no patches. Retain the native authentication,
restrict/cascade and parallel-grant behavior, and the active-warehouse requirement for
get-tags. Keep literal vendor `0.0.1`; this is not complete SQL or platform coverage.
The separate native `grant.yaml` and current Grant reference mark **all seven operations
deprecated**. That valid but wholly deprecated candidate is neither registered nor
imported; publication alone is not a reason to add a current-priority API. The native
lifecycle decision and source hashes are retained in the maintenance discovery cache.

Discord follows `discord/discord-api-spec/specs/openapi.json`, the vendor's standard
stable public v10 HTTP artifact. The [vendor README](https://github.com/discord/discord-api-spec/blob/main/README.md)
distinguishes it from `openapi_preview.json`, which includes experimental features.
The description itself remains a public preview, as its original title says; retain
that label. Discord's [API reference](https://docs.discord.com/developers/reference)
lists v10 as Available (checked 2026-10-03). The report explicitly limits coverage to
this HTTP artifact, excluding Gateway events and experimental features, and does not
claim that a source match establishes complete or production-ready documentation.
The declared version stays `10`, so content comparisons are required even when endpoint
counts stay fixed.

Meraki Dashboard follows the vendor-published `master/openapi/spec3.json`, used for the
public API Reference in the [official docs configuration](https://github.com/CiscoDevNet/Meraki-Dashboard-API-v1-Documentation/blob/e598959273954662886eda26b8dc2392a4616ef6/config%20copy.json).
The same configuration selects `v1-beta` for Early Access; do not substitute that branch
or the live streaming feed. The [public overview](https://developer.cisco.com/meraki/api-v1/overview/)
confirms release `1.74.0` (checked 2026-10-03). This deliberately reviews the native
OpenAPI 3 artifact alongside the Swagger companion already cited by the stored file.
Both have 701 paths / 998 operations, but the native artifact includes 15 callback
declarations and 13 deprecation notices absent from the converted Swagger companion.
It also references an undefined `oauth2` security scheme in 822 operations at source
revision `9029d122861222bbe912193b77d8f2bc442900d4`. Semantic validation therefore blocks
import; keep the existing spec until an official correction or a separately reviewed
exact repair is available. Do not fabricate an OAuth scheme or discard requirements.
The parked `x-preferred` policy remains unresolved. Other Meraki products need separate
source and lifecycle reviews.

Datadog v2 follows the exact SDK-generation artifact already cited by the stored spec:
`DataDog/datadog-api-client-python/.generator/schemas/v2/openapi.yaml`. The
[vendor README](https://github.com/DataDog/datadog-api-client-python/blob/master/README.md)
identifies generation from public OpenAPI descriptions and explains opt-in unstable
endpoints. Preserve the artifact's lifecycle annotations; this is not a stable-only
subset. Monitoring covers this v2 artifact, independently of v1 and other Datadog
products. The fixed declared version is `1.0`, so compare full content, including
separate endpoint additions and removals. A source-artifact removal is not proof that
the running API was retired; cross-check public documentation before merging removals.

Swagger 2.0 sources can register a `conversion` recipe with `tool: swagger2openapi`,
`version: 7.0.8`, and reviewed integer `expected_warnings` / `expected_patches` counts
(both default to zero). The pinned local converter uses `patch:true`, `warnOnly:true`,
`resolve:false` and target OpenAPI `3.0.0`. External references must first be bundled
from a pinned source; conversion itself does no network resolution. Unknown extension
references are also checked, and pre-existing converter warning markers require review.
Operations missing response declarations are rejected before the converter can fabricate
default responses. Conversion must retain every path and operation. A source-format,
warning-count or converter-patch-count change stops the recipe for review.

The cache retains the original bytes, normalized conversion input, converted JSON,
warning/patch observations and converter log, with input/output hashes. Conversion occurs
after optional bundling and before exact source-specific patches. Full OpenAPI validation,
reference checks and the serialized value/type guard remain mandatory: `warnOnly` does
not waive validation, and accepting a warning count does not repair missing schemas.
Imports record the Swagger → OpenAPI `x-origin` chain and actual conversion details in
`info.x-conversion`; they never describe converted files as having no version conversion.

Grafana follows the vendor-documented canonical `public/api-merged.json` source, with
zero expected warnings and converter patches. This is the existing legacy HTTP artifact,
whose declared version remains `0.0.1`. The vendor's
[HTTP reference](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/)
marks legacy routes deprecated in favor of newer `/apis` resources. Their descriptions
and Grafana Cloud need separate discovery; a match to this source does not establish their
coverage. This service-specific coverage note is displayed in audit reports. Vendor fake
example credentials remain unmodified; push protection must still be respected.

Square follows its official OpenAPI 3 source directly. Two exact patches replay the
previously reviewed required `vendor_id` parameter and empty OAuth scope list corrections.
Its undefined `CurrencyExchange` and `AppFeeAllocation` schemas remain unmodified, so
validation blocks imports while audits continue to report content drift. No schemas or
validation exceptions are invented. Vendor fixes stop patch replay for deliberate review.

Exact patches are registered in a source's `patches` list, with JSON recipes under
`maintenance/patches/`. Each replacement asserts both the original JSON value (including
its type) and selected sibling context before changing anything. Missing fields, changed
values, changed context, and duplicate pointers fail the run and require recipe review.
If the vendor fixes a defect, remove or revise the recipe deliberately rather than
silently skipping it. Original source bytes remain cached; comparisons and validation
use the patched document. The report and imported `info.x-conversion` record the recipe,
its hash, and its explanation, so the same transformation can be replayed.
Recipes may additionally declare a nonempty `assertions` list of exact
`{pointer, value}` pairs. These compare complete JSON nodes (including types) before
any operation in that recipe. Use them when a correction depends on a referenced
schema or optionality outside its immediate siblings. Missing/changed nodes, malformed
or duplicate assertions and unknown recipe fields fail closed; assertions do not
modify content. Recipe hashes/provenance include these preconditions. A simulated
valid vendor fix must stop replay, including changes to the referenced target.
An optional nonempty `unreferenced` list asserts that existing local JSON Pointer
targets have no pointer uses before any operation in that recipe. The conservative
scan includes strings in examples, extensions, mappings and keys, percent-decoded
fragments and escaped tokens. Uses of the target, its descendants or an enclosing
node (including the document root) stop replay. URI-prefixed pointer fragments also
block; named anchors and prose are not pointer references. This guard establishes
pointer absence, not an arbitrary vendor's implicit name-resolution semantics;
review those independently before removing an unused definition. Missing, malformed
or duplicate targets fail closed. Original bytes stay cached on guard failure.

Recipes can also remove an explicitly asserted invalid field using `remove: true` in
place of `value`. This never supplies a replacement value or infers server behavior.

Xero Accounting's recipe fixes only the 46 string `'false'` defaults/examples on 23
explicitly named boolean properties, verified in vendor commit
`fd9d44b04bf4934a7509b8e7ece51a9e0e462e4f`. Every replacement asserts `type: boolean`.
There is no general string-to-boolean coercion. The complete patched document must still
pass all normal OpenAPI and reference/parameter validation.

Split GitHub descriptions can register a `bundling` recipe. The updater resolves the
vendor revision, downloads its archive, checks that the archive entry matches the
independently fetched root, and selects the recursively referenced YAML/JSON files.
Archive links, unsafe paths, missing files, remote/query references, and unsupported
non-schema artifacts fail the run. Vendor scripts, plugins, overlays, and configurations
are not run. Redocly 2.57.0 bundles the pinned data with our empty configuration; full
OpenAPI and reference validation still run afterwards. The source snapshot hashes every
referenced file, so changes in helpers are detected even when the entry file is unchanged.
The cache preserves the archive, selected files, file hashes, bundled output, and logs.
Each import records the snapshot hash, tool version/options, and warning count.

DigitalOcean's recipe has 21 reviewed component naming warnings: separate definitions
with identical basenames are disambiguated, retaining both contents. A changed warning
count stops the run for review. The local bundle was compared with DigitalOcean's
official published bundle by resolving references across paths and common components.
Two invalid null defaults in its GenAI `stop` schemas are removed by exact patches;
all declared alternatives and nullable annotations remain. The complete patched bundle
must pass validation. Other sources default to zero expected bundling warnings.

Snowflake's Database, Schema and Table resource-management descriptions are registered
separately from SQL execution and Warehouse management. Each is a two-file snapshot with
`common.yaml`, bundled at the same pinned vendor commit with zero expected warnings.
The public resource guides and descriptions carry no preview designation (checked
2026-10-02); other catalog services still require their own scope/release-status review.

Fern `x-fern-examples` code samples can register a `code_samples` recipe with
`kind: fern`, a repository-relative `root`, and allowed file `extensions`. Only
operation-level `code-samples[].code` objects containing exactly one `$ref` are
materialized. Files must be relative UTF-8 artifacts inside the configured root;
remote, query, fragment, escaped, and unexpected-extension references fail the check.
They are fetched from the entry document's pinned GitHub commit, cached byte for byte,
and substituted as code strings without execution or schema interpretation. Duplicate
references fetch once. The snapshot hashes the entry and every snippet, detecting
snippet-only drift. Provenance records the materialization and snapshot hash. Combined
schema bundling and sample recipes require explicit future support.

The YAML loader preserves unquoted scientific notation such as `1e-08` as a number,
as required by YAML 1.2. Quoted strings remain strings. This avoids silently corrupting
numeric schema constraints before OpenAPI 3.1 validation.
The writer also quotes vendor strings such as `"0.16001e0"` that would otherwise
be read as numbers under YAML 1.2. Numeric-looking strings and numeric values must
both survive serialization with their original types.
Every import re-parses its serialized output and compares values and types before writing
the file, blocking future serialization regressions instead of committing altered content.

Mistral's public artifact is `openapi-public-doc.yaml`: the vendor's publishing script
copies it to `docs.mistral.ai/openapi.yaml`, verified byte-identical on 2026-10-02.
It includes the vendor's labeled public-preview APIs. The other root `openapi.yaml`
is not the public download and must not be concatenated with it. Eleven exact patches
correct the speech streaming response's nine references and two discriminator mappings
from nonexistent document-root `$defs` to the existing definitions inside that response
schema. No schemas are invented. Changed source values/context block replay for review.

The weekly GitHub workflow runs tests and publishes the configured-source report and raw
snapshots. PRs changing the updater run its tests without network access. Automated PR
creation and monthly discovery have not been implemented yet; the one-week Codex
follow-up carries out that implementation and manual API delivery independently.

Reviewed GitHub sources can use a `release_catalog` recipe of kind
`numeric-directories`, with a repository-relative `directory`, `filename` and
`minimum_version`. This policy is only for vendor catalogs where canonical `major.minor`
directories denote published versions. It selects numerically (2.100 after 2.18), excludes
prerelease names and older releases, and rejects empty, inconsistent or potentially
truncated catalogs. Both the catalog and selected description come from the same pinned
commit. The declared `info.version` must match the directory. The complete catalog response
and its hash are cached and the release selection is recorded in the imported provenance.
There is no fallback to the old configured path when discovery fails. External bundling
or code-sample recipes combined with catalog selection need explicit future support.

Intercom uses this recipe: official documentation selects release 2.16, with Preview
listed separately (repository directory `0`). Future discovered versions still need their
public-release status checked before manual import/merge. Two exact parameter-list patches
retain all vendor headers/query parameters and restore the required string
`job_identifier` path parameter for reporting status/download, as in the earlier 2.14
import. Changed lists or operation context stop replay for recipe review. Sentry's
dereferenced public description is also registered, with fixed declared version `v0`.

Asana REST monitoring follows `Asana/openapi/defs/asana_oas.yaml`, the artifact linked
by the current public REST overview. The old `Asana/developer-docs` repository redirects
to an archived repository whose README explicitly names this replacement. App components
and the SDK-specific artifact are separate scope. The public description retains preview
Project briefs and beta rule-trigger wording; keep those limitations and deprecated routes.

Asana's own publishing workflow converts YAML to JSON before uploading its REST reference.
That conversion represents unquoted HTTP response-code keys as strings. Its reviewed
`yaml_response_keys` recipe does the same only for integer keys in path-operation Responses
Objects. It requires an exact count (1,556), codes 100–599, and no existing string-key
collision before any mutation. Shared YAML mappings are checked once. Response values,
payload keys, schema defaults and all other content retain their types; full validation
still applies. A changed count, vendor quotation fix or invalid key stops for review.
This is an opt-in representation repair, not global YAML coercion or an OpenAPI downgrade.

Vercel's public hosted REST description is registered at `https://openapi.vercel.sh/`,
the same artifact cited by its stored spec and selected by the official SDK workflow.
Its placeholder version stays `0.0.1` while content changes. The current 3.0.3 source
contains schema keywords outside that dialect and fails validation; imports are explicitly
blocked, while audits continue fetching, comparing and retaining evidence. The SDK's
separate overlaid snapshot also fails and is not a replacement. Preserve preview/deprecated
features and plan restrictions as published; hosted repository health remains unassessed.

Validation diagnostics now identify JSON Pointer locations and nested failing keywords
instead of dumping large response schemas or example/default values. Missing `$ref`
errors from an alternative Reference Object branch are omitted when actual schema failures
exist. This changes only error presentation: full pinned validation, reference and semantic
checks remain in force, and invalid sources still block import. Summaries are bounded to
five distinct leaf findings and 1,500 characters; the cached raw source remains the complete
evidence. Validation count still represents the caught top-level failure, not every leaf
or every subsequent structural failure in the document.

The pinned validator's schema-meta and default-value failures use schema-relative paths.
The adapter preserves location annotations through the library's normal error conversion;
the formatter locates resolved reference targets in the original document with a cycle
guard. These pointers identify the failing definition rather than the referring operation.

Zoom Meetings uses the product-specific JSON download named by its current public reference
and official repository inventory. The live page embeds native OpenAPI 3.0.0 and simplifies
authentication for its viewer; preserve the original download's OAuth requirements. Its
markdown rendering's 3.1.1 label is not the artifact's declared dialect. The reviewed exact
patch adds literal string `"null"` to `recording_source_type`'s enum, which omitted its own
published default and documented all-recordings mode. Assert the entire original parameter
list and operation identity; preserve both other alternatives, default, example and all
other fields. A vendor fix or context change stops replay for review. No null coercion,
constraint removal, version conversion or invented feature. Full validation still applies.

The maintained Meetings/Webinars product description has its own `zoom.us/meetings/2`
layout. The older combined `zoom.us/2.0.0` spans additional products and remains intact;
this narrower service artifact cannot replace it. Preserve deprecated fields and licensing
restrictions, review other product artifacts separately, and do not treat public-reference
publication as a guarantee that every feature is GA. Hosted source health is unassessed.

Zoom Users and Accounts follow the separate downloads named by their current public
product references and pinned official inventories. Each native 3.0.0 artifact declares
vendor version `2`, validates without patches and retains original OAuth requirements,
deprecated fields and plan/account restrictions. The viewer's simplified authentication
and markdown 3.1.1 label are not substitutes for the downloadable artifact. These distinct
services use `zoom.us/users/2` and `zoom.us/accounts/2`, retaining the broader historical
combined spec. They do not duplicate the Meetings artifact's operations. Review other
products separately; hosted source health remains unassessed, and public documentation
is not a guarantee of GA status for every feature.

A source may declare an `initial_baseline` for a historical `swagger.yaml` or
`openapi.yaml` inside the same provider directory. This is used only when neither the
new vendor-version destination nor the reviewed current `target` exists on the comparison
base. It preserves curation during migration to the first official OpenAPI release without
rewriting or deleting the historical Swagger file. Unsafe paths or missing configured
history fail the check/import. Once imported, the current destination/target takes priority;
future release comparisons and curation do not fall back to the old snapshot.

Mailchimp Transactional (`mailchimp-transactional`) monitors the vendor's native OpenAPI
3.1 input linked directly from its [public reference](https://mailchimp.com/developer/transactional/api/),
under the existing `mandrillapp.com` provider (Transactional Email was formerly Mandrill).
The artifact declares **1.4.0**, while the reference's display and separate Swagger SDK
input say **1.4.1**. Preserve the actual native version and dialect; do not concatenate
or convert the two descriptions. It covers 99 operations including public SMS routes,
not Mailchimp Marketing or every product's release guarantees. The older unofficial
`1.0/swagger.yaml` remains intact as the initial curation baseline. Human route comparisons
may account for its legacy `.json` suffix; the importer retains the exact vendor paths.

Mailchimp Marketing (`mailchimp-marketing`) monitors the expanded production Swagger
self-description linked by the vendor's [fundamentals](https://mailchimp.com/developer/marketing/docs/fundamentals/)
and used by its SDK-update instructions. Its version/path/operation counts match the SDK
snapshot while content differs, so the SDK label alone cannot establish production freshness.
The existing broad artifact includes vendor-labelled Audiences beta and account/plan limits;
monitoring it does not imply every feature is GA. This hosted source's health is unassessed.

The locked converter's 218 reviewed patch counts comprise 210 unchanged empty response
strings and eight explicit string-or-integer variant-ID unions translated to disjoint
`oneOf` alternatives. Zero warnings and unchanged path/operation sets are required.
Accepting these counts permits comparison, not import: boolean `false` defaults on string
notification fields still fail strict validation. No defaults are coerced/removed, no
schema is invented, and all stored Marketing versions remain unchanged pending a reviewed
vendor correction. A real-converter regression confirms these conversions retain invalid
string defaults and that the importer rejects them.

Zoom Whiteboard and Scheduler follow the exact native downloads named by their current
[Whiteboard](https://developers.zoom.us/docs/api/whiteboard/) and
[Scheduler](https://developers.zoom.us/docs/api/scheduler/) public references (reviewed
2026-10-05). Both are OpenAPI 3.0.0 / vendor version `2`, with no content patches,
conversion or bundling. The viewer changes authentication presentation; import the
original downloadable OAuth requirements and API-key scheme. All non-security content
matches the embedded public reference. Follow content changes at fixed version `2`,
retain account/license restrictions, and do not infer all features are GA from product
publication. Their 25/43 and 16/24 paths/operations are absent from historical combined
Zoom coverage; preserve that file and every other separately published Zoom service.
Hosted repository health remains unassessed. Other Zoom artifacts need separate review.

Zoom Canvas follows the native download named by its current
[Canvas reference](https://developers.zoom.us/docs/api/canvas/) and independently by
the vendor's older Zoom Docs inventory. That inventory's 20 paths / 26 operations are
not current coverage evidence: the live reference/download has 29 paths / 39 operations.
All non-security content matches the embedded reference; preserve original downloadable
OAuth requirements and API-key scheme. Retain native OpenAPI 3.0.0 / version `2`, without
patches, conversion or bundling. Canvas document/content, collaboration/access, tables,
imports/exports, archives and reports are distinct from the separate Hub API. These
routes are absent from all six previously stored Zoom artifacts; keep those files intact.
The public introduction lists enabled Canvas on Basic and paid plans without a release
designation. Example beta-testing prose and attachment-preview event names are not
prerelease labels; publication is not a universal feature-GA guarantee. Preserve scopes,
Gov-cluster and account/license restrictions. Hosted source health remains unassessed.

Zoom Hub follows the native download selected by its current
[Hub API reference](https://developers.zoom.us/docs/api/hub/) and
[introduction](https://developers.zoom.us/docs/hub/) (reviewed 2026-10-05). It declares
OpenAPI 3.0.0 / vendor version `2`: six paths / nine operations for file content import/
export, duplication/task polling and shared-folder management. All non-security content
matches the viewer; preserve original authentication, OAuth scopes, file-type/format
limits and Gov-cluster exclusions. No patches, conversion or bundling. It is separate
from Canvas and Zoom Events hubs, and does not implement every file/permission operation
or AI Productivity Suite feature described by the broader introduction. Account
prerequisites are public with no prerelease designation; publication is not a universal
feature-GA claim. Keep all seven prior Zoom descriptions intact. Hosted health remains
unassessed; monitor content changes at fixed vendor version `2`.

Datadog v1 follows the vendor's public `.generator/schemas/v1/openapi.yaml` in
[`DataDog/datadog-api-client-python`](https://github.com/DataDog/datadog-api-client-python).
The pinned README identifies public OpenAPI generation and demonstrates v1 Monitors;
current public Monitors docs still show v1 routes (reviewed 2026-10-05). Native OpenAPI
3.0.0 / declared version `1.0` has 150 paths / 235 operations and no endpoint overlap
with stored v2. Follow content at fixed vendor version, without borrowing the SDK package
version. No patches, conversion or bundling. Preserve authentication/permissions, regional
servers, 65 deprecated operations and four AWS Logs `x-sunset: 2027-02-20` annotations.
The SDK warns of opt-in unstable endpoints; the reviewed v1 operations have no unstable,
beta or private extensions, but publication is not a universal feature-GA guarantee.
Keep v2 intact; this v1 collection does not cover every Datadog or private product.

Auth0 Management follows the native JSON schema directly linked from its
[current reference](https://auth0.com/docs/api/management/v2), independently selected by
its official CLI. Vendor version stays `2.0`; content and lifecycle annotations change
without endpoint-count changes. The reference labels OpenAPI 3.1 schema support Beta,
and the artifact includes EA features. Authentication, My Account and My Organization
are distinct APIs. Its device-name schema has an incompatible phone-number pattern and
default; strict validation blocks imports. Hosted repository health is unassessed.

Cloudflare REST follows official `cloudflare/api-schemas/openapi.yaml` at a pinned commit,
with no source patches/conversion. The sibling official JSON is exactly equal using YAML
1.2 scalar parsing (verified 2026-10-05). Bare `=` keys/values and sexagesimal-looking
`1:10` examples remain strings. Decimal leading zeros, `0o` octal, hexadecimal and float
forms follow the YAML 1.2 core schema; strings that resemble those numbers are quoted on
write. Unsupported explicit tags remain rejected. This repairs parser interpretation,
without editing vendor files or relaxing schema/security validation. Cloudflare imports
remain blocked by an invalid DNS-order default and undefined assets upload security
schemes. Report additions/removals separately; URL-variable renames are not retirements.


Okta Admin Management follows the vendor's current `management-oneOfInheritance.yaml`
publication in [`okta/okta-management-openapi-spec`](https://github.com/okta/okta-management-openapi-spec).
This retains enum constraints, examples and explicit inheritance alternatives; noEnums,
noExamples and development variants are not replacements. It declares 3.0.3 / `2026.09.1`
with 485 paths / 731 operations at registration. Other Okta services and the existing
community `okta.local` submission are separate. Preserve tenant servers, authentication,
deprecation and native `x-okta-lifecycle` labels, including Early Access/Beta features.

The unmodified source fails strict validation: GET `/api/v1/hook-keys/{id}` overrides
its shared required path parameter with an inline declaration missing `required: true`.
A diagnostic-only repair exposes a null default on the nonnullable string
`Brand.customPrivacyPolicyUrl`. Neither repair is adopted; no schema constraints are
weakened and no API import is made. Audits retain the exact official source and report
validation failures. A vendor correction or separately reviewed exact recipe is needed.


Box Platform compatibility (`box-platform`) follows the vendor's root `openapi.json`
in [`box/box-openapi`](https://github.com/box/box-openapi), byte-identical to
`openapi/openapi.json` at registration. The current public versioning guide assigns
`2024.0` to endpoints preceding year-based versioning; this maintained artifact changes
at a fixed declared year version. Its 187 paths / 297 operations do not include every
API from separate 2025/2026 subsets. Do not select the highest filename as a replacement
for broad compatibility coverage or fabricate a combined description.

The historical `box.com/2.0.0` file supplies existing curation for the first `2024.0`
import and remains intact. Keep native stability, authentication and plan/admin
annotations, original literal fragment paths and source provenance. No source patches,
conversion or bundling are needed. Review all additions and removals independently;
a source omission alone does not prove runtime retirement.

Box Platform 2025 (`box-platform-2025`) follows the separate native year-versioned
`openapi/openapi-v2025.0.json` artifact. Its 24 paths / 37 operations add distinct
coverage to the compatibility collection; all require the `box-version: 2025.0`
header. Current vendor versioning and Doc Gen documentation identify this released
collection, including Enterprise Advanced requirements. Preserve original auth,
servers and account/admin restrictions. There is no cross-scope historical curation
baseline or hand-built union of year files. Review the 2026 subset independently,
including its explicit beta operations; a higher filename is not a broad replacement.

Box Platform 2026 (`box-platform-2026`) follows native
`openapi/openapi-v2026.0.json` as another distinct public route collection. All five
operations require `box-version: 2026.0`. The vendor's current reference marks both
Automate operations beta, while Notes conversion and the two query operations are
unmarked (latest stable per vendor versioning guidance). Preserve both beta labels
and native auth/server/account restrictions; there is no stable-only slice or
cross-scope curation baseline. The public viewer's embedded snippets strip lifecycle
extensions; use the full native artifact, and retain all prior Box histories.

ClickUp v2 (`clickup-v2`) follows the native public OpenAPI 3.1 description linked
from the [official guide](https://developer.clickup.com/docs/open-api-spec). Preserve
its declared `2.0`, native token security, OAuth guidance and plan/admin permissions.
The existing `clickup.com/1.0.0` entry is an unrelated Polls sample. Its explicit
`initial_baseline` preserves the two existing branding fields (`x-logo`,
`x-providerName`) on the coverage correction; no Polls server, title or API data is
copied. Before initial import the report's `/questions` removal is a comparison
with that sample, not a retired ClickUp endpoint. The historical file remains
unchanged, and subsequent audits use the real v2 destination. Public v3 is separately
published and currently fails native validation; it is not combined with v2.
Hosted repository health remains unassessed.

Zendesk Support (`zendesk-support`) follows the hosted OAS download linked from
the official Ticketing introduction, separate from Sunshine Conversations. Fixed
document version `2.0.0` continues to receive content updates. Its checked recipe
expresses the documented null-only alternative as explicit `type:string`,
`nullable:true`, `enum:[null]`, retaining every other alternative and original
`oneOf` exclusivity (including integer/number overlap). It removes only the invalid,
unused `UserLogin` path parameter component with query-only `deepObject` style.
Complete condition/parameter assertions and conservative pointer absence guards
stop on changed definitions, new uses or vendor corrections. Every path/operation,
other constraint and native tenant/auth/permission/lifecycle declaration remains.
The artifact models basic auth only; current public auth docs recommend OAuth and
mark API tokens deprecated. Retain that publication limitation without inventing
schemes. Original bytes, exact recipe hash and full validation remain required.

Zendesk Conversations (`zendesk-conversations`) follows the maintained official
`zendesk/sunshine-conversations-api-spec` public v2 source, separate from Support
and the deprecated generated SDK wrappers. Preserve vendor document version
`17.13.2`, tenant `/sc` and explicitly labelled legacy Smooch servers, basic/JWT
authentication, account/app/integration scope and account-type restrictions.
The checked recipe expresses `sourceType -> source` as supported `anyOf`/`not`
presence constraints, retaining every other reference constraint. It also moves
invalid boolean `required:true` from the `identities.email` child schema to the
containing filter's required array. The public List Users description explicitly
requires that email filter; the query parameter remains required. This repairs
malformed syntax using documented intent, rather than inferring server behavior.
Complete reference/filter nodes and operation prose are asserted before replay.
Changed constraints, requirements, documentation or vendor corrections stop the
recipe for review. Regression cases include positive and negative dependency
inputs, original required URI/length limits, filter presence/type, and vendor fixes.

ClickUp v3 (`clickup-v3`) follows the separately published public collection at
`ClickUp_PUBLIC_API_V3.yaml`. Its actual version is the literal `version`; preserve
that placeholder and native 3.0.0. Chat is [experimental](https://developer.clickup.com/docs/chat);
Docs/pages and other resources share this public artifact. Keep the complete mixed
collection and native auth/server/plan restrictions. A single invalid `parent` null
default is removed only after exact assertions on the complete containing schema
and referenced non-nullable object. Adding `nullable: true` upstream makes the
default valid and blocks replay for review. No nullability or replacement default
is inferred. This new v3 service has no old curation/comparison baseline; keep v2
and historical Polls bytes intact. Hosted health is unassessed.

### Coinbase Developer Platform v2

`coinbase-cdp` monitors the current hosted publication linked by the official
`coinbase/cdp-sdk` Makefile, rather than its lagging committed SDK snapshot. Fetch
metadata records the final URL, ETag, Last-Modified, time and raw hash; hosted repository
health remains `not_assessed`, and the CDN artifact has no claimed Git revision.
During source selection the plain URL and fresh timestamp query returned identical
bytes. If caching or public scope changes, recheck the vendor download and SDK input
before treating an unchanged CDN result as current.

The complete public collection contains generally available and Beta groups, including
account restrictions; it is not all Coinbase APIs. The exact recipe removes four
unsupported `required:false` Parameter Reference Object siblings only after asserting
the complete referenced optional header, original parameter lists and operation IDs.
It retains `$ref`, the target's `required:false` and all auth/schema/prose content.
A vendor fix or changed referenced contract stops replay for review. There is no
OpenAPI conversion, reference inlining, endpoint trimming or inferred authentication.

### Confluence Cloud REST v2

`confluence-v2` follows the moving Atlassian download directly linked by the official
v2 reference. The plain URL currently matches the documentation-build query; do not
freeze that query into a release. Hosted health remains `not_assessed`, with source
hash/time/ETag/Last-Modified recorded. This is the complete v2 collection, retaining
experimental and deprecated operations; v1 and Data Center are distinct artifacts.

Two optional space-label prefix filters declare string enum `my` or `team`, but
assign the invalid default `my, team`. The exact recipe asserts each complete
parameter and operation identity before removing only the defaults. Allowed values,
optionality, auth/scopes and all other content remain unchanged. It chooses no
replacement default and makes no claim about server behavior when omitted. A vendor
correction or contract change stops replay. The separately published v1 artifact also
has native defects and is not imported by this v2 registration.

### Confluence Cloud REST v1

`confluence-v1` separately follows the official v1 reference's hosted OpenAPI download.
Keep vendor document version `1.0.0`, native OpenAPI `3.0.1`, and the protocol-relative
tenant server. The complete publication includes seven experimental flags and two
deprecated descendant operations. Current publication does not prove that previously
announced retired operations remain available. Retain their labels and do not restore
removed endpoints or combine this collection with v2 or Data Center.

Full native validation finds three invalid null defaults: required label `name`, optional
label content `type`, and optional group `accessType`, all non-nullable strings. The
checked recipe asserts each complete parameter and operation identity, then removes
only those defaults. Requiredness, types, enums and every other constraint remain.
Positive and negative instance checks prove the accepted values are unchanged; vendor
nullable/default/contract corrections stop replay. No nullable widening, replacement
default, conversion, bundling, invented curation or runtime omission behavior is added.

## Monthly official-repository discovery

The separate read-only `discovery.py` command produces a review queue from
`discovery.json`, initially the Snowflake resource catalog and bounded HCP/Anthropic
SDK publication leads. Configure only reviewed major-vendor repositories with ownership
links, filename scope, context inputs and explicit file/size limits. It does not perform
an unrestricted web search, import APIs, apply patches, generate PRs or authorize merges.

```sh
git fetch origin main
python maintenance/discovery.py --base origin/main
```

The monthly workflow runs at 07:23 UTC on the first day, or manually. It runs the same
pinned regression suite first, has only `contents: read`, and publishes JSON, Markdown,
original source/metadata snapshots and the job summary. PR checks cover its code/config
and workflow changes. This is repository automation, independent of the local one-week
Codex task or laptop power state.

Each repository metadata observation guards public identity, archive/disable status and
redirects. The commit and complete untruncated tree are pinned together. Original file
bytes must match both the tree's Git blob identity and size; oversized files, symlinks,
truncated trees and candidate-limit overflows fail visibly. README/generation inputs are
cached as leads without executing them or following arbitrary embedded URLs. A renamed
repository or missing file is a review finding, never evidence to remove stored APIs.

Presence checks read fetched Git objects at full depth, including provider files outside
sparse checkout. Existing registered repository/path pairs are skipped without fetching
or claiming freshness; use `update.py check` for those. Shared helpers/config files are
excluded only after parsing proves they are not OpenAPI documents. Complete parsed
content identical to stored specs is excluded; identical candidate descriptions are
grouped with all provenance URLs. Same endpoint shapes are annotated for scope review,
not silently collapsed across versions, products or vendors. Native validation obstacles
and external-reference bundling requirements remain visible; they are not corrected here.
Every new candidate still needs release/lifecycle/scope/compatibility review and deliberate
per-API delivery. In particular, Snowflake's catalog includes compatibility descriptions
and resources with differing lifecycle; SDK files are not a basis for fabricated schemas.

Success means only the configured bounded scan completed. Failed scans keep the actual
previous successful scan date when the configuration is unchanged, and reports/cache
snapshots retain the new failure. A report with failures or inventory parse errors exits
nonzero; native-invalid discovered candidates remain a successful discovery with listed
import obstacles. No-candidate results are bounded leads, not proof the vendor publishes
no spec elsewhere or that the historical directory is current. Expanding patterns or
limits requires review, rather than silently sampling a prefix of a large catalog.

Scheduled PR publication remains separate follow-up work; the opt-in generator below
does not change this read-only discovery workflow.

## Explicit per-API draft generation

`draft_pr.py` fetches and validates one registered API, using the same pinned source
health, bundle/conversion/patch, metadata-preserving import and typed YAML machinery.
It defaults to a dry run and records complete candidate content, original snapshots,
review body and results under ignored `cache/maintenance/drafts/`. Fetch main first;
local maintenance code, configuration, recipes and locks must match the selected Git
tree. An older tree without the delivered generator is rejected. Existing source
publication blockers stop before fetching, including unanswered push-protection choices.

```sh
git fetch origin main
python maintenance/draft_pr.py --source plaid
# After deliberate candidate review, explicitly create one new draft:
python maintenance/draft_pr.py --source plaid --publish
```

Publication re-fetches and revalidates; it never loads or trusts an edited cached plan.
Only this fork's canonical/legacy origin is permitted, and remote main must still equal
the comparison commit. Both public GitHub REST artifacts declare the explicit
`github-public-rest` publication group: selecting either processes both as one API PR. Companion artifacts sharing a vendor
repository/ref use the same pinned source commit even if the branch advances mid-run.
Distinct Snowflake resources remain separate. Register new groups only after scope
review, not merely because artifacts share a provider.

The builder creates an exact API/target-only commit through a private temporary index
and the full Git tree. It retains historical versions and preserves sparse paths,
local files, the current branch and staged work. It checks configuration/recipe equality,
regular file/directory modes, the entire curated vendor view, complete native validation
and YAML types. It does not create timestamp-only spec commits. A lagging reviewed
baseline can produce a manifest-target-only correction, identified in the candidate.
Per-attempt candidate directories are keyed by their integrity digest; that digest is
an accidental-change guard, not an authorization token or proof of current freshness.

`--publish` needs Git push and authenticated `gh api` access with repository contents
and pull-request write permissions. It reads all open PRs and complete bounded file
pagination before creating anything. A PR touching any historical/current version of
the API, or the same generated branch, yields `existing_pending`. An orphan branch
yields `existing_branch`. Both outcomes preserve existing work; automatic branch/PR
updates remain unfinished. Do not remove a pending PR to force a duplicate delivery.
An atomic empty-ref lease permits only creating an absent branch, including under races.
The PR is always a **draft**, with official URL/hash/revision, scope, versions/counts,
additions/removals, transformations and validation results. Its returned repository,
head/base, draft/open state and complete file list must match the candidate.

A rejected push, advanced main after pushing, failed PR POST or unexpected PR response
creates `publication/GROUP/blocked.json`. A local exclusive `publishing.lock` prevents
overlapping attempts; a crash leaves that lock for review. Retain this cache across runs.
Never delete these guards as an automatic retry, redact a vendor example, or bypass
protection. Inspect GitHub read-only to recover an uncertain outcome, record it in
AGENTS.md, and continue independent work. A verified created URL is returned even if
subsequent verification fails. Codex callers must attempt `attach_artifact` for **every**
created PR, retain the GitHub link if the app attachment cap rejects it, and report the
real result. The standalone CLI does not perform desktop attachment or send messages.
Terminal failure results omit raw vendor examples and subprocess output; detailed
native planning diagnostics and original sources remain in the local cache.

Generated `codex/official-update-*` API PRs trigger the separate read-only
`api-draft-validation.yml` job, which checks out trusted base tools, reads full Git
objects outside sparse checkout and validates the exact head. It requires one commit
parented by the exact comparison base, complete native/typed YAML validation, regular
Git modes and precisely reconstructed manifest target edits for that API. Main advancing
requires deliberate re-planning/review; it never silently rebases or changes a pending
branch. Offline CI does **not** claim a fresh vendor comparison. Publication still needs
deliberate scope/lifecycle/removal review and actual checks before marking ready/merging;
the generator does not invoke a merge command or request blanket automatic merging.

Weekly audit and monthly discovery workflows retain `contents: read`. No scheduled
writer is enabled by this command. A future publisher must retain guards/outcome evidence
across runners and ensure PR validation actually runs: events created by Actions'
`GITHUB_TOKEN` generally do not start other workflows, per GitHub's
[token documentation](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).
Implement pending-PR updates and scheduled publication separately, with deliberate
per-API review; don't weaken permissions or waive checks just to trigger delivery.
