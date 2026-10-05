# Official-source maintenance

This updater checks only the service artifacts configured in `sources.json`,
including both public GitHub REST descriptions. It does not claim coverage of the
entire directory, discover every vendor release, generate PRs, or merge them. Those remain explicit follow-up work
in AGENTS.md §9. Blocked services are included in the report rather than silently skipped.

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
