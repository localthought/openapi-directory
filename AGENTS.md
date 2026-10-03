# AGENTS.md — working on this OpenAPI directory fork

Instructions for an agent picking up work in this repo. Read this first.

**Repo**: `ontola/openapi-directory` (fork of `APIs-guru/openapi-directory`).
Note the git remote resolves via an old org rename — `localthought/openapi-directory` redirects to `ontola`. Pushes print a "This repository moved" notice; harmless.

**Last updated**: 2026-10-03. Audit of `origin/main` at `3388295d9` (PR #107 merged):
729 provider domains; 4,261 files under `APIs/`, including 2,087
`openapi.yaml` and 2,168 `swagger.yaml` files. These are dated observations,
not live counts. Recompute against fetched `origin/main` when resuming work.

---

## 1. The standing task

Keep this fork current for well-known industry APIs. Prioritize direct comparisons with
official vendor sources and discovery of missing official OpenAPI descriptions (OADs).
Use the upstream `APIs-guru/openapi-directory` backlog as a secondary source of leads;
the previous backlog sweep was low-yield (§3). Follow the current queue in §4 and the
maintenance implementation instructions in §9.

**Filter criterion the user set, which governs everything:**
> "you can skip additions of niche APIs, I'm more interested in additions or corrections of well-known industry APIs."

**Delivery pattern:** one PR per API, against our own `main`, upstream issue/PR link in the **PR body, not the title**. Merge when clean.

**When the backlog runs dry, the task does not stop.** Two standing jobs:

1. **Find specs we don't have.** Search the web for official OpenAPI descriptions of large,
   well-known APIs. "Official" means published by the vendor, ideally in their own git repo
   — see §8 for how to tell a real one from a third-party scrape.
2. **Check what we already have is current.** Most of the value found so far was here, not
   in new additions: Stripe was 4 years stale, Square was 94 paths behind, Meraki and
   Mailchimp both needed version bumps. Walk `APIs/` against upstream sources and compare
   `info.version`, paths, operations, and schema content. An unchanged version or path
   count does not prove an unchanged API.

**Autonomy level as of the last instruction:** the user said *"i don't need to review them, you can merge them when you think they look good."* That applies to straightforward additions of official vendor specs. It does **not** extend to the deferred/judgment items in §5 — those were explicitly declined or parked and need a fresh go-ahead.

---

## 2. What's done

PRs **#7–#42** were this workstream (#1–#6 predate it).

- **#7–#17** — ported upstream PRs (typo fixes, `x-origin` corrections, small API additions: Oneauto, tensorpix, viesapi, Famxplor, Wikidata, Interfaces One).
- **#18–#21** — Cloudflare, Auth0 Management, Discord, OpenAI 2.3.0.
- **#22–#25** — Nylas v3, Picsart Image 2.0, Picsart GenAI 1.0, Eventbrite v3.
- **#26–#38** — **all 13 PayPal specs** from `paypal/paypal-rest-api-specifications`, one PR each.
- **#39** — Datadog v2 (1008 paths / 1591 ops), under `APIs/datadoghq.com/v2/1.0/`.
- **#41** — Cisco Meraki 1.74.0 (new version dir; 1.32.0 left in place).
- **#42** — Mailchimp 3.0.91 (new version dir; 3.0.55 left in place).

**#40 (Google Vertex AI) was closed, not merged** — see §5.

**#44–#54 — the first coverage-gap batch. All merged.** Found by auditing what we already
have against vendors' own published specs, not from the upstream backlog.

| PR | API | Paths / ops | Note |
|---|---|---|---|
| #44 | Stripe `2026-08-26.dahlia` | 419 / 594 | refresh; was pinned at `2022-11-15`, ~4 years stale |
| #45 | Figma `0.42.0` | 47 / 54 | new; source already YAML |
| #46 | Sentry `v0` | 147 / 234 | new; upstream artifact is deref'd, so no `$ref`s at all |
| #47 | PagerDuty `2.0.0` | 273 / 465 | new |
| #48 | MongoDB Atlas Admin `2.0` | 333 / 541 | new; filed under `mongodb.com/atlas-admin/` |
| #50 | Grafana `0.0.1` | 207 / 314 | new; Swagger 2.0 -> OpenAPI 3 |
| #51 | Square `2.0` | 253 / 332 | refresh, **in-place, −16 paths** (Square's retired v1 + Transactions APIs) |
| #52 | DocuSign eSignature `v2.1` | 213 / 414 | refresh, in-place; Swagger 2.0 -> OpenAPI 3 |
| #53 | — | — | this file; replaced `HANDOFF-upstream-triage.md`, added §5b |
| #54 | Intercom `2.14` | 106 / 150 | new |

**#55–#58 also merged**, closing out the batch:

| PR | API | Paths / ops | Note |
|---|---|---|---|
| #55 | Elasticsearch `9.5` | 581 / 845 | new; version taken from the release branch — see §4 |
| #56 | — | — | AGENTS.md status |
| #57 | Elasticsearch Serverless `2026-09` | 289 / 460 | new; **snapshot date, not a vendor version** — see §4 |
| #58 | **HubSpot — 59 specs** | 507 / 676 | new; selected down from a 122-entry catalog — see §4 |

**Upstream spec defects found and fixed in this batch** (all verified present in the
vendor's own published file first, then fixed to match that vendor's own style):
- Square `PUT /v2/vendors/{vendor_id}` — declared `parameters: []`, leaving its path variable undeclared.
- Square `POST /oauth2/revoke` — security scopes as `null` instead of `[]`.
- Intercom `GET /export/reporting_data/{job_identifier}` and `/download/...` — omitted the path parameter.

**Deliberately NOT fixed**, and why:
- Square `$ref`s `CurrencyExchange` and `AppFeeAllocation` without defining them. Inventing schemas would be fabricating API surface.
- HubSpot **HubDB** `$ref`s `HubDbTableRowV3Wrapper` four times without ever defining it. Same reasoning as Square.
- DocuSign descriptions carry double-encoded UTF-8 (mojibake). It is **DocuSign's own bug, in the source file** — refreshing does not fix it, and rewriting vendor prose is a bigger change than it looks.

Grafana (#50) was initially blocked by GitHub push protection over a fake example token in
Grafana's own spec; the repo owner reviewed it and allowed it. See §7.

**October maintenance work merged:**

| PR | Result | Scope |
|---|---|---|
| #60 / #64 | Maintenance instructions and progress | Repo instructions and audit findings |
| #61 | Initial reproducible updater | Six service sources, pinned dependencies, validation, weekly read-only audit artifacts |
| #62 | Hugging Face Inference Endpoints `2.0.0` | New management API; 40 paths / 46 operations |
| #63 | Plaid `2020-09-14_1.740.1` | New version directory; 360 paths / 351 operations; historical version preserved |
| #65 | GitHub public REST, both default and `2022-11-28` artifacts | Fixed `1.1.4` version refreshed in place; each 815 paths / 1,231 operations; seven monitored artifacts across six services |
| #66 | Exact patch replay in updater | Checked JSON replacements, context assertions, recipe hashes/provenance; 16 passing regression tests |
| #67 | Xero Accounting `19.1.0` | New version directory; 138 paths / 235 operations; historical version preserved |
| #69 | Pinned repository reference bundling | Locked Redocly 2.57.0, source-file hashes, archive/reference checks, exact field removal; 21 tests pass locally and in CI |
| #70 | DigitalOcean `2.0` | Fixed version refreshed in place; 515 paths / 757 operations; curation preserved |
| #71 | Snowflake SQL `2.0.0` | New SQL execution service; 3 paths / 3 operations; no bundling or patches |
| #72 | Snowflake Warehouse `0.0.1` | New management service; 12 paths / 15 operations; `common.yaml` bundled with zero warnings |
| #74 / #75 | Pinned Fern snippet materialization and YAML scientific numbers | Source snapshots include code artifacts; fetch-helper integration verified; 27 tests pass locally and in CI |
| #76 | Cohere `1.0` | New OpenAPI 3.1 description; 32 paths / 42 operations; seven TypeScript samples materialized without execution |
| #77 | Mistral `1.0.0` | New public OpenAPI 3.1 artifact; 212 paths / 299 operations; eleven checked streaming-reference corrections |
| #78 | YAML string preservation and import round-trip guard | Quote scientific-looking vendor strings, reject serialization type/value changes; 29 tests pass locally and in CI |
| #79 | GitHub example string types | Eight quote repairs across both public artifacts; paths/operations unchanged, vendor JSON values retained |
| #80 | Deterministic curation serialization and progress | Identical imports across three Python hash seeds; 30 tests pass locally and in CI |
| #81 | Four more official-source registrations | Stripe public GA, Figma, PagerDuty REST and Atlas Admin; 15 artifacts / 14 services monitored |
| #82 | Figma `0.43.0` | New version directory; 47 paths / 54 operations; composed color values and `COLOR_OPACITY` scope |
| #83 | Stripe `2026-09-30.endive` | New version directory; 454 paths / 644 operations; includes vendor GA v1+v2 coverage |
| #84 | PagerDuty `2.0.0` | Fixed version refreshed in place; 274 paths / 466 operations; checked removal of one invalid default |
| #85 | Expanded audit progress | Source revisions, completed imports and Atlas validator/dialect blocker recorded |
| #86 | Numeric vendor release discovery; Intercom/Sentry monitoring | Catalog and artifact pinned to one commit; 35 local/CI tests; 17 artifacts / 16 services registered |
| #87 | Sentry public Web API `v0` | Fixed version refreshed in place; 151 paths / 245 operations; 4 paths / 11 ops added, none removed |
| #88 | Intercom `2.16` | New directory; 168 paths / 235 operations; 62 paths / 85 ops added, none removed; reporting parameter patch replayed |
| #89 | Fork contribution and maintenance documentation | Distinguishes actual fork import process/coverage from upstream publication and guidance |
| #90 | Readable audit reports and three Snowflake registrations | Markdown artifact and job summary, per-row comparison bases, retained success dates; 39 tests pass locally and in CI |
| #91 | Snowflake Database `0.0.1` | New resource API; 15 paths / 18 operations; two-file bundle, zero warnings, no patches |
| #92 | Snowflake Schema `0.0.1` | New resource API; 7 paths / 10 operations; two-file bundle, zero warnings, no patches |
| #93 | Snowflake Table `0.0.1` | New resource API; 19 paths / 22 operations; two-file bundle, zero warnings, no patches |
| #94 / #98 | Maintenance progress | Snowflake and source-health checks, audit evidence and remaining queue recorded |
| #95 | Live repository-health checks | Exact metadata snapshots, archived/disabled/identity findings, import guards and retained success dates; 47 tests pass locally/CI |
| #96 | Accurate repeat-import provenance | Record the current stored curation baseline instead of an older manifest fallback; 48 tests pass locally/CI |
| #97 | Intercom `2.16` wording refresh | Two vendor contact-verification descriptions; version, 168 paths / 235 operations unchanged |
| #99 | Reproducible Swagger conversion; Grafana/Square monitoring | Locked converter, zero-default warning/patch expectations, response/path safeguards, format-chain provenance; 57 tests pass locally/CI; 22 artifacts / 21 services registered |
| #100 | Grafana `0.0.1` content refresh | New certificate field, ASN.1 documentation and RBAC wording; fixed version, 207 paths / 314 operations unchanged; zero converter warnings/patches |
| #102 / #103 / #104 | Current baseline tracking; Plaid/Intercom refreshes | 61 tests; reviewed baseline advances with imports; Plaid 1.762.0 and Intercom company-deletion clarification; details in §9 |
| #105 | Baseline/import audit progress | 22-source audit evidence and next-run queue |
| #106 | ECMAScript and cyclic-schema validation | Pinned validator/regex engine; scoped cycle guard; 69 local/CI tests; Cohere's empty union now correctly blocks import |
| #107 | MongoDB Atlas Admin `2.0` | Fixed version refreshed; 339 paths / 549 ops; 6 paths / 8 ops added, none removed; no source patches |

GitHub's refresh adds 322 paths / 488 operations and removes 58 paths / 102 operations
in each artifact. These removals are present in the official source, including retired
Projects classic, team discussions, tag protection, and product billing endpoints, plus
path changes for environment secrets/variables and Pages deployments. The full removed
path list and vendor retirement links are in #65. Other GitHub products were not refreshed.
Both source files and metadata-preserving imports passed full validation and parsed YAML
content comparisons; #65's GitHub test run passed.

Xero adds 8 paths / 15 operations and drops the 2 Employees paths / 4 operations in its new
release. Its documented boolean patch is described in §4. #66's 16 tests passed locally
and in GitHub CI, and the serialized Xero import passed full validation and comparison.
After #67, a fresh updater audit against `origin/main` at `8e40681fb` reported
`matches_source` with no validation errors for both GitHub artifacts, Plaid, Xero, and
Hugging Face Inference Endpoints. This confirms the patched comparison does not keep
proposing Xero's already-imported release.

DigitalOcean adds 338 paths / 473 operations and removes 6 paths / 6 operations. Four
registry paths move under `/repositories/`, retaining operation IDs; two App Platform
tier paths were removed from the official source and marked deprecated in its own SDK.
The reproducible build selects 3,134 data files from vendor commit
`0267e38174220ec9ae115185ccb9717b3909c89a`. Its 21 naming warnings disambiguate different
definitions sharing basenames. Comparison with the official published bundle found no
reference-resolved API or shared-component content differences; only 14 generated aliases
have different names between bundler versions. Two invalid GenAI `stop` null defaults are
removed by a checked recipe, preserving all declared alternatives and nullable annotations.
The bundled source and final YAML passed full validation and curation/content comparisons.

Snowflake SQL and Warehouse use vendor commit `990e25d97236a11826c9eed40e587c2b859e5680`.
Warehouse's two-file bundle has no patches or warnings. Both serialized specs passed full
validation and source-content comparison; both source registrations passed 21-test CI.
Other Snowflake services remain to be audited; these additions do not cover its whole API.
Fresh local checks after #72 report `matches_source` with no validation errors for
DigitalOcean and both Snowflake services. A full GitHub audit is recorded in §9.

**Snowflake core-resource additions (#91–#93):** Database, Schema and Table use the same
official vendor commit `990e25d97236a11826c9eed40e587c2b859e5680`, with declared version
`0.0.1` retained verbatim for each service. The repository was unarchived when checked on
2026-10-02. These distinct APIs are listed in the generally available REST reference;
their individual public guides and source artifacts have no preview designation. Each
bundle contains only its own entry plus `common.yaml`, with zero warnings and no patches
or version conversion. Shared helper files are not additional APIs. The serialized
imports match the cached vendor bundles, retain all original path/operation counts and
pass complete validation with no external references. No new curation was invented.

The documented public guides are
[Database](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/databases/db-introduction),
[Schema](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/schemas/schemas-introduction),
and [Table](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/tables/tables-introduction).
Snapshot hashes respectively: `f6d644eee01cc2e9a3cdda65004c7dd3b294de32ce67b74ffb8cf831b93f86d1`,
`08d1eb8d0ace124c5bcee97d79786314e6839aea6ab17e5a17e9e10548411309`, and
`bef7f216bc08a628ffaf339d427ecc0062fec846d6b22f9e70fd447de967c353`.
Five Snowflake service descriptions are now imported (56 paths / 68 operations total).
Remaining catalog products need their own release/scope review; do not blindly import
every filename, preview-only resource or compatibility description.

---

## 3. Triage progress

Working dataset was `/tmp/all_issues.tsv` — **this is in `/tmp` and will not survive a reboot.** Regenerate with:

```bash
gh api --method GET "repos/APIs-guru/openapi-directory/issues?state=open&per_page=100" --paginate --jq '.[] | select(.pull_request == null) | [.number, .created_at, .comments, .title] | @tsv' | sort -t$'\t' -k2 > /tmp/all_issues.tsv
```

1991 rows, oldest first (#42 from 2016 → #3395 from 2026-09-22).

Batches read in full: rows 1–375, i.e. issues **#42 through #1578**. Everything relevant from those is either done (§2) or parked (§5).

Rows 376–1991 (#1580–#3395) were **not** read line by line — they were keyword-swept for known vendor names instead. **Conclusion: don't bother reading them.** That range is essentially one automated third-party *scraper* spam campaign — hundreds of near-duplicate "Add LinkedIn / Reddit / TikTok / Amazon / Shopify / GitHub Intelligence API" submissions, auto-reposted in bursts at :30 past the hour. None are the platforms' own APIs. Even the "Stripe Radar Rules API" issues are part of it (body is two lines, no URL).

Only two genuine signals in that entire range:
- [#2393](https://github.com/APIs-guru/openapi-directory/issues/2393) — Google specs stale repo-wide (Sheets v4 untouched 3 years). Same family as #611 / #1189 / #1300.
- [#2444](https://github.com/APIs-guru/openapi-directory/issues/2444) — Google Health v4; the discovery URL does resolve (HTTP 200).

---

## 4. Next up — the agreed direction

Batch triage was abandoned as low-yield. The user agreed the better lead is a **direct coverage-gap audit**, and gave the go-ahead to take the list "the same way as PayPal: one PR per API".

**The vendor table below was partly wrong and has been corrected.** Three entries labelled "new" already existed in the repo. The original audit used `[ -d "APIs/$d" ]` inside the worktree — and **the worktree has sparse-checkout enabled**, so almost nothing is materialized on disk and nearly every vendor reads as "missing". This is the same class of mistake as #40.

### ⚠️ Audit correctly, against the index — not the working tree

Sparse-checkout means `ls`/`[ -d ]`/`find` under `APIs/` are all unreliable here.
Check `git sparse-checkout list` first. Fetch main and audit its tree, rather than a
possibly stale feature branch's index:

```bash
git fetch origin main
git ls-tree -r --name-only origin/main APIs | cut -d/ -f2 | sort -u > /tmp/have_domains.txt
for v in stripe square figma sentry pagerduty docusign mongodb grafana shopify okta \
         intercom hubspot salesforce zendesk notion airtable heroku snowflake elastic \
         hashicorp coinbase dropbox newrelic anthropic huggingface nvidia; do
  printf "%-14s " "$v"; m=$(grep -i "$v" /tmp/have_domains.txt | tr '\n' ' ')
  [ -n "$m" ] && echo "HAVE: $m" || echo "missing"
done
```

After PR #93 on 2026-10-02: 729 distinct provider domains, 4,260 tracked files under `APIs/`.
To add a new spec you must first widen the cone: `git sparse-checkout add APIs/<domain>`,
otherwise `git add` refuses with "paths ... outside of your sparse-checkout definition".

### Verified live official specs (HTTP 200 confirmed 2026-09-22)

| Vendor | Source | Status |
|---|---|---|
| **Stripe** | `.../stripe/openapi/master/latest/openapi.spec3.yaml` | **REFRESHED, PR #83**, `2026-09-30.endive`, 454 paths / 644 ops. Vendor-recommended public GA v1+v2 artifact; prior #44 used the maintained v1-only `openapi/spec3.yaml`. Use YAML, excluding preview and SDK variants. |
| Figma | `.../figma/rest-api-spec/main/openapi/openapi.yaml` | **REFRESHED, PR #82**, `0.43.0`, 47 paths / 54 ops. OpenAPI 3.1.0; historical `0.42.0` preserved. |
| Sentry | `.../getsentry/sentry-api-schema/main/openapi-derefed.json` | **REFRESHED, PR #87**, fixed `v0`, 151 paths / 245 ops. Vendor dereferenced artifact; inlining is upstream's doing. Weekly content checks registered in #86. |
| PagerDuty | `.../PagerDuty/api-schema/main/reference/REST/openapiv3.json` | **REFRESHED, PR #84**, fixed `2.0.0`, 274 paths / 466 ops. Checked invalid-default removal is registered with the source. |
| MongoDB Atlas | `.../mongodb/openapi/main/openapi/v2.json` | **REFRESHED, PR #107**, fixed `2.0`, 339 paths / 549 ops, as `mongodb.com/atlas-admin/2.0`. Validator/dialect compatibility resolved in #106; no source patches. |
| Grafana | `.../grafana/grafana/main/public/api-merged.json` | **REFRESHED, PR #100.** Canonical Swagger 2.0, monitored through #99's locked conversion recipe, zero warnings/patches. Fixed placeholder `0.0.1`, 207 paths / 314 operations. This legacy artifact does not cover every new `/apis` resource or Grafana Cloud. See the push-protection note below. |
| Square | `.../square/connect-api-specification/master/api.json` | Stored refresh #51; **monitoring registered #99**, direct OpenAPI 3.0.0. Fixed `2.0`, 253 paths / 332 operations. Three source metadata additions detected, but refresh blocked by two missing vendor schemas; do not invent them. |
| DocuSign | `.../docusign/OpenAPI-Specifications/master/esignature.rest.swagger-v2.1.json` | **DONE, PR #52** — a *refresh*, we already had `docusign.net/v2.1`. Swagger 2.0. |
| Intercom | `.../intercom/Intercom-OpenAPI/main/descriptions/2.16/api.intercom.io.yaml` | **REFRESHED, PR #88**, public `2.16`, 168 paths / 235 ops. #86 discovers numeric release directories; preview directory `0` excluded. Historical `2.14` preserved. |

**October follow-up audit:** all four newly registered vendor repositories were checked
on 2026-10-02 and were maintained/unarchived. #81 registers their moving official sources,
so future release/schema changes are checked weekly instead of relying on old import dates.

**Stripe source selection:** vendor commit `6f855712dfc6a235a407136e630bf36a01c069a3`.
The repository's README now recommends `latest/openapi.spec3.yaml` for public GA v1+v2
coverage. The old `openapi/spec3.yaml` is still maintained but v1-only. At the same commit,
the selected artifact retains all 431 v1-only paths / 612 operations and adds 23 v2 paths /
32 operations. Shared v1 path items differ only by 1,079 explicit `explode` annotations;
every one matches its OpenAPI-defined default. Compared with stored Dahlia, #83 adds
35 paths / 50 operations and removes none. Historical versions and curation are preserved;
no API patches or conversion. Do not accidentally switch back to the v1-only artifact or
select preview/SDK variants.

**Figma:** vendor commit `2a90e5adc67d8117d7c2da624f03a9bfa3027fb6`. `0.43.0` adds
`VariableComposedColor` to variable-value unions and `COLOR_OPACITY` to the scope enum,
despite unchanged endpoint counts. It passes full OpenAPI 3.1 and serialization checks.
The vendor labels its description itself beta; this is its public REST artifact.

**PagerDuty:** vendor commit `6ab7c72fb78ff76ba65670795a51d925c8b4df12`. #84 adds
`GET /incidents/{id}/scribe_transcripts`, with no path/operation removals. The source assigns
the invalid string default `20 - incident_summary` to the integer `sre_memories_limit`
parameter (range 1–100). `maintenance/patches/pagerduty.json` removes only that exact
default after type/range/value assertions. No replacement default or server behavior is
inferred. The complete patched source validates and round-trips; a simulated vendor fix
to integer `20` stops replay for deliberate recipe review.

**MongoDB Atlas blocker resolved (#106/#107):** the old validator recursed while collecting
properties through cyclic compositions. Diagnostic 0.9.0 initially rejected ECMAScript
regex syntax through Python regex, then exposed the same property-collection cycle once
the official `ecma-regex` extra was installed. #106 pins OpenAPI spec/schema validators
0.9.0 and regress 2026.9.1. Its scoped subclass iterates the same upstream property edges
with a resolved-object cycle guard; no schema constraints are removed, recursion limit
raised, global classes monkey-patched or formats disabled. The document backend is
explicitly Python jsonschema. Pattern syntax/default matching uses ECMAScript with no
flags, tested against Node (named captures, identity escapes, Unicode-property escape
behavior). Do not infer Unicode mode universally; it changes semantics and rejects some
vendor identity escapes. Missing backends/changed reviewed engine pins fail validation.
69 regressions pass locally and in GitHub CI. Python 3.10+ is now required; CI uses 3.11,
and the clean local environment is `/tmp/openapi-maintenance-ecma` (bundled Python 3.12).
The older Python 3.9 venv does not satisfy these dependencies; recreate rather than
silently using it. `maintenance/requirements.txt` is the reproducible dependency source.

#107 refreshes the fixed `2.0` Atlas Admin file from 333 paths / 541 operations to 339 / 549,
adding six paths / eight operations and removing none. Private endpoint connection strings,
Stream Processing workspace private endpoints and ephemeral clusters account for the
added paths; vendor schema/parameter/documentation changes also remain. Source commit
`ab07390d4ef9ba960d467a156ef99d5e0afb4e10`, entry SHA-256
`db2c6f2500a5f05fc74f8dd818db4f9db38d0e67140a6b9ce82364e9738cca66`.
Complete validation, parsed vendor-content equivalence, curation preservation and YAML
round-trip pass without source patches or OpenAPI conversion. Provenance records the
validation profile. This is Atlas Administration only, not every MongoDB product.

**Newly exposed Cohere defect:** validator 0.9.0 correctly rejects the existing official
`components.schemas.TruncationStrategy.oneOf: []`, with an empty discriminator mapping.
The same invalid empty union is present at official source commit
`734aafbe1fe2ca5c7356609009ec0d9b74e6ac57`; live re-fetch/source comparison confirms it.
Its description claims a default of 'none', but no union variants are defined there.
Cohere still matches its source; a matching hash is not successful validation. Do not
invent alternatives or waive validation. Look for a vendor correction or a separately
reviewed, exactly checked correction with demonstrated semantics. Keep the existing
import in place; no destructive removal or new Cohere refresh PR was created.

**Intercom release discovery and import:** official
[introduction](https://developers.intercom.com/docs/references/introduction) and
[changelog](https://developers.intercom.com/docs/references/changelog) select public `2.16`
and distinguish Preview. Vendor repository `intercom/Intercom-OpenAPI` was maintained and
unarchived on 2026-10-02. #86 adds a reviewed `numeric-directories` recipe: select canonical
major.minor releases numerically from the pinned `descriptions` catalog, exclude releases
below `2.16` and prerelease names (Preview is `0`), and require `info.version` to match.
The complete original catalog response/hash is cached alongside the artifact and included
in import provenance. Empty, inconsistent, truncated or failed catalogs block instead of
falling back to an old version. Combined catalog/bundling or code-sample recipes still
require explicit support. Verify a future selected release against official docs before
manual import/merge; numeric selection alone is not universal evidence of stable status.
Tests cover ordering, unsafe paths, exclusions, failure, revision pinning, cache evidence
and mismatched declared versions. All 35 tests pass locally and in #86's CI.

#88 imports vendor commit `6d8b0b8d27a779a6005716249ed21755f29292d9`, adding 62 paths /
85 operations with none removed. The vendor's two reporting status/download operations
still omit required `job_identifier` path declarations. The exact recipe
`maintenance/patches/intercom.json` prepends the same required string declaration used
in #54, preserving all original header/query parameters and asserting their complete lists
plus operation summaries/tags. A simulated vendor correction stops replay. The complete
patched source and serialized import validate and preserve values/types and curation;
historical `2.14` is unchanged. The vendor changelog describes breaking schema changes
between API releases, so no old version is replaced or declared equivalent.

**Sentry refresh:** maintained/unarchived `getsentry/sentry-api-schema` was checked on
2026-10-02; vendor commit `41d82c69208a3f24dafa36f584cca981d30cfde5` grows fixed `v0` from
147 paths / 234 ops to 151 / 245, adding four project codeowner/inbound-filter paths and
eleven operations, removing none. #87 preserves vendor schema/description changes,
including experimental labels, without API patches or conversion. The parsed import
matches the official cached source and passes full validation and serialization checks.
This is the public Web API artifact, not Sentry's SDK ingestion protocol or whole platform.

**Square and DocuSign are the cautionary entries here.** Both were originally recorded as
"new" by an audit that ran `[ -d "APIs/$d" ]` inside a sparse-checkout worktree. Both were
in fact already present, and both needed **in-place refreshes** (their vendors pin
`info.version` forever, so the new-directory rule cannot apply and the diff carries real
deletions). Audit against the index, per the warning above.

#### Grafana: GitHub push protection (resolved, but it will recur)

`git push` is rejected with `GH013 / GITHUB PUSH PROTECTION — Grafana Project Service
Account Token`, pointing at `APIs/grafana.com/0.0.1/openapi.yaml:14966`. That line is:

```yaml
key:
  type: string
  example: glsa_<REDACTED IN THIS DOC>_<8 hex>   # upstream spells out i-N-V-a-l-i-D repeatedly
```

It is a **false positive**: a deliberately fake placeholder published by Grafana in their
own public spec — the body of the value literally spells "invalid" over and over — which
happens to carry the real `glsa_` prefix the scanner keys on. It is not a live credential.

(The literal value is redacted *in this document* only because quoting it verbatim makes
this file itself unpushable. The spec file on `add-grafana-api` still has it as published.)

On 2026-09-22 the repo owner reviewed it and allowed it via the unblock URL, so #50 is
merged with the example byte-for-byte as Grafana publishes it. **Expect this again** — vendor
specs routinely carry fake example credentials that match real patterns. Two ways forward,
both the user's call:
1. **Allow it** via the unblock URL in the push error (repo owner only) — keeps the vendor spec byte-for-byte as published.
2. **Redact the example** — but that means editing vendor content, which cuts against how every other spec here was added.

Do not bypass push protection unilaterally.

### Elastic — two specs, two different version problems (DONE, #55 / #57)

Elastic ships **both** files with `info.version` empty. They were solved differently, and
the difference is the point:

- **Stateful** (`elasticsearch-openapi.json`) → `elastic.co/9.5`. The repo has release
  branches (`7.14` … `9.5`), so fetch from the branch for the release you want and set
  `info.version` to match. The version is **sourced**, not invented.
- **Serverless** (`elasticsearch-serverless-openapi.json`) → `elastic.co/serverless/2026-09`.
  Rolling product, no release branches, nothing to borrow. `2026-09` is a **snapshot date we
  chose**, and `x-conversion` says so in as many words — a bare date in a version directory
  otherwise reads exactly like a real vendor date-version (Stripe's `2022-11-15` is one).
  **Refresh by adding a new date directory, never in place**: with no version to diff
  against, an in-place edit silently destroys the only evidence of when the file was current.

Neither has a `servers` block, because Elastic publishes none — Elasticsearch is self-hosted
and the base URL is the user's own cluster. Left absent rather than inventing a host.

### HubSpot — 122 catalog entries, 59 real specs (DONE, #58)

`https://api.hubspot.com/public/api/spec/v1/specs` is a **catalog index**, not a spec. The
122 headline number is misleading in two separate ways:

| Step | Count |
|---|---|
| Products in catalog | 122 |
| …with a **STABLE** version | 93 |
| …minus 34 per-object CRM slices | **59 imported** |

- **29 products are pre-release only.** No stable version at all. The internal test APIs
  (`At Tests`, `At Debug`) fall out here too, so no special-casing was needed for them.
- **35 of the 93 are not distinct APIs.** They are one generic CRM endpoint re-emitted per
  object type: Contacts is `/crm/objects/2026-03/contacts`, Deals is the identical shape at
  `/crm/objects/2026-03/0-3` (HubSpot's internal numeric object-type id). Same six
  operations each.
- **One of the 35 was kept**: `Custom Objects`, the only one exposing
  `/crm/objects/{version}/{objectType}` as a genuinely templated path. Beware when
  re-deriving this — a filter for `{objectType}`/`{fromObjectType}` anywhere in the paths
  matches 28 of them, because most carry a templated *associations* sub-path. Match on the
  object-collection path itself.

### Still to do

- **Monitor the refreshed priority APIs below**, extending the reusable updater in §9.
  All four confirmed stale APIs are done: Plaid #63, GitHub REST #65, Xero #67, and
  DigitalOcean #70. The table retains the original audit snapshots, not current stored counts.
- **Extend the official coverage audit.** Hugging Face Inference Endpoints (#62), Snowflake
  SQL/Warehouse (#71/#72), Cohere (#76), and Mistral (#77) are done. Audit remaining
  distinct stable Snowflake services and other well-known providers before importing more.
- **Extend the refresh audit across the rest of `APIs/`.** The October check was a sample,
  not a complete audit. Compare content as well as versions and path counts.
- **Locate specs for the vendors below**, minding the 404 warning.
- **HubSpot's 34 per-object CRM slices remain deliberately skipped.** Do not expand this
  scope without a fresh user instruction.

### Initial confirmed refresh queue (2026-10-02 audit; all four now refreshed)

| API | Stored version / paths | Source version / paths | Official source |
|---|---|---|---|
| GitHub REST | `1.1.4` / 551 | `1.1.4` / 815 | [api.github.com.json](https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json) |
| DigitalOcean | `2.0` / 183 | `2.0` / 515 | [DigitalOcean-public.v2.yaml](https://raw.githubusercontent.com/digitalocean/openapi/main/specification/DigitalOcean-public.v2.yaml) |
| Plaid | `2020-09-14_1.345.1` / 201 | `2020-09-14_1.740.1` / 360 | [2020-09-14.yml](https://raw.githubusercontent.com/plaid/plaid-openapi/master/2020-09-14.yml) |
| Xero Accounting | `2.9.4` / 132 | `19.1.0` / 138 | [xero_accounting.yaml](https://raw.githubusercontent.com/XeroAPI/Xero-OpenAPI/master/xero_accounting.yaml) |

GitHub's `api.github.com.2022-11-28` counterpart was included in #65 and is now registered
alongside the default public artifact. Audit other GitHub products separately.
DigitalOcean's relative references are now handled by its registered pinned bundling recipe.
Copying only the entry file remains insufficient. Future imports must use the updater.
The counts include all path entries, not necessarily one operation per path. New paths
and removed paths must be reported separately; net growth can conceal removals.

**Plaid completed:** PR #63 added `2020-09-14_1.740.1` with 360 paths / 351 operations,
preserving the historical version and curation. **Xero completed:** PR #67 added `19.1.0`
with 138 paths / 235 operations, preserving the historical version and curation. The official
`19.1.0` source has 23 boolean properties with string defaults/examples `'false'`, starting
with `Account.HasAttachments`. The recipe in `maintenance/patches/xero-accounting.json`
fixes exactly those 46 values, asserting the original string and sibling `type: boolean`.
It was verified against vendor commit `fd9d44b04bf4934a7509b8e7ece51a9e0e462e4f`.
The complete patched source passes validation. If a future vendor source fixes a value or
changes its type, the recipe intentionally fails and needs review; remove or revise it
deliberately. Never disable validation or coerce arbitrary vendor values.

**DigitalOcean completed:** #70 refreshes fixed version `2.0` in place. The recipe in
`maintenance/patches/digitalocean.json` removes only the two invalid null defaults in
`chat_completion_request.stop` and `create_response_request.stop`, after asserting their
source values and complete `oneOf` alternatives. It invents no replacement defaults or
server behavior. A changed bundler warning count (currently 21) or patch precondition stops
the updater for review. Logs, original data, source hashes, and the bundle remain cached.

### Verified missing official OADs (downloaded and parsed 2026-10-02)

| Provider | Official source | Import notes |
|---|---|---|
| Snowflake | [specifications directory](https://github.com/snowflakedb/snowflake-rest-api-specs/tree/main/specifications) | SQL `2.0.0` (3 paths / 3 ops), Warehouse `0.0.1` (12 / 15), Database (15 / 18), Schema (7 / 10) and Table (19 / 22) are DONE in #71/#72/#91–#93. The three new resource APIs also declare `0.0.1`. Audit remaining distinct public APIs separately; helper files are not APIs. |
| Cohere | [cohere-openapi.yaml](https://raw.githubusercontent.com/cohere-ai/cohere-developer-experience/main/cohere-openapi.yaml) | DONE #76: OpenAPI 3.1, version `1.0`, 32 paths / 42 ops. Seven referenced TypeScript snippets are explicitly materialized as code strings and included in freshness snapshots. |
| Mistral | [official docs repository](https://github.com/mistralai/platform-docs-public) | DONE #77: OpenAPI 3.1, version `1.0.0`, 212 paths / 299 ops. `openapi-public-doc.yaml` is the verified public download; do not substitute or concatenate the separate 131-path `openapi.yaml`. |
| Hugging Face Inference Endpoints | [openapi.json](https://api.endpoints.huggingface.cloud/openapi.json) | OpenAPI 3.1, version `2.0.0`, 40 paths. This describes endpoint management, not the entire Hugging Face Hub or each model's inference API. |

None of these four providers was present at the initial audit, before PR #62 added
Hugging Face Inference Endpoints `2.0.0` (40 paths / 46 operations). All four now have
validated imports; Snowflake's remaining catalog still needs per-service review. Parsing
alone is not completion of reference resolution or spec validation.
Search the full tree by domain, brand, service, and aliases again before adding anything.

**Cohere details:** vendor commit `734aafbe1fe2ca5c7356609009ec0d9b74e6ac57`.
The `code_samples` recipe operates only on Fern operation-level code sample references,
fetches UTF-8 artifacts from the same pinned commit, preserves their text without execution,
and hashes entry plus snippets together. Source snapshot
`a5f38e5f74280d88f3d3a5231c178ebfa05c63674dddb90979cc268973e333c3` includes all seven.
No external references remain. Missing or unsafe snippets block refresh, and snippet-only
changes are detected. PR #75 corrected a live-import fetch-helper contract mismatch after
#74; its regression test exercises the real HTTP helper with a mocked response.

**Mistral selection and patch:** vendor commit `ce5bfddb42fe91b964f88cb16ab42f41bd415501`.
The [publishing script](https://github.com/mistralai/platform-docs-public/blob/ce5bfddb42fe91b964f88cb16ab42f41bd415501/src/scripts/copy-openapi.ts)
explicitly copies `openapi-public-doc.yaml` to the public download. The documentation
build selects the same source; its bytes exactly matched `https://docs.mistral.ai/openapi.yaml`
(SHA-256 `fa73befe1c61e1bf4847c532e6375612ae5c7a4a83f96db4a1087ee0115db8b7`).
This is the full public artifact, including vendor-labeled beta/public-preview APIs,
not a stable-only subset. Nine references and two discriminator mappings in the speech
streaming response point at nonexistent document-root `$defs`, while the vendor's
definitions exist under that response schema. `maintenance/patches/mistral.json` applies
eleven exact checked pointer replacements to those existing definitions; no schemas are
invented. All 1,939 local references resolve after the patch and full validation passes.
Changed source values/context stop replay. Scientific bounds such as `1e-08` are valid
YAML 1.2 numbers; #74 fixes the loader's old string interpretation instead of patching
vendor numeric content. No OpenAPI version conversion was used.

Snowflake's [REST reference](https://docs.snowflake.com/en/developer-guide/snowflake-rest-api/reference)
is generally available, but that umbrella page also lists individual preview products:
[Code Bundles and their REST clients were announced in preview on 2026-09-24](https://docs.snowflake.com/en/release-notes/2026/other/2026-09-24-code-bundles).
Check each service's own release status before importing more catalog entries. Do not
treat compatibility specs named Cortex Generic Anthropic/OpenAI as those vendors' own OADs.

### Source health requires a separate check

Slack's stored spec matches its official source in version and path set, but
[`slackapi/slack-api-specs`](https://github.com/slackapi/slack-api-specs) is archived;
its Web API spec last changed on 2020-10-06. Current Slack docs describe methods absent
from that artifact. Record this as an archived source with incomplete current coverage,
not as a current API merely because re-fetching produces no changes. Look for a maintained
official replacement; do not silently substitute a third-party reconstruction.

PR #95 now checks GitHub repository metadata on every audit and import, independently
of content comparison. It records identity, archive/disabled flags, activity observations,
retrieval time and exact response bytes/hash, deduplicating shared repositories within
each run. `repository_available` means the same public repository is reachable and is
neither archived nor disabled; it does **not** establish vendor ownership, artifact
maintenance or current API coverage. Archive/disabled/identity changes and metadata
failures block imports. Failed attempts preserve the last successful health-check date;
content comparison continues independently. Hosted sources, currently Hugging Face,
remain explicitly unassessed by this repository check. File-specific deprecation and
replacement discovery still need review.

### Missing, official spec not yet located

Shopify, Zendesk, Airtable, Heroku, HashiCorp, Coinbase, Dropbox, New Relic, Anthropic,
NVIDIA. Snowflake and Hugging Face Inference Endpoints now have verified sources above.

**Probed and 404'd on 2026-09-22** — these exact URLs, not the vendors themselves:
guessed paths in `snowflakedb/snowflake-rest-api-specs` (`main`, `releases/8.40/...`; resolved
on 2026-10-02 by inspecting the repository's `specifications/` directory),
`zendesk/developer_docs` (`master`, `api-reference/ticketing/oas.yaml`),
`hashicorp/vault` (`main/openapi.json`), `Shopify/shopify-app-js` (`main/openapi.json`),
`dropbox/dropbox-api-spec` (`master/openapi.json`).
Older 404s: `okta/okta-management-openapi-spec`, `api.hubspot.com/api-catalog-public/v1/apis`,
`api.heroku.com/schema`.

> **Read this before trusting any 404 above.** The handoff previously recorded
> `intercom/Intercom-OpenAPI` as dead and said not to retry it. That was wrong: the repo is
> real and current, and only the two *version paths* tried (`descriptions/2.11`, `2.13`)
> were bad. `2.14` resolved fine and is now merged as #54. **A 404 on a guessed path inside
> a vendor repo is evidence about the path, not about the repo.** Check the repo root and
> its branches/tags before concluding a vendor publishes nothing.

Note also that `okta.local/1.0.0` and `salesforce.local/einstein/2.0.1` exist in `APIs/` but
are community submissions, not the vendors' official APIs — a name grep will mislead you in
that direction too.

## 5. Parked — do NOT action without a fresh go-ahead

Each of these was either explicitly declined or deliberately deferred.

- **Google spec regeneration** (#611 OAuth `Oauth2c` malformed security, #1189 Gmail path structure, #1300 DisplayVideo `kpiType` enum, #2393 general staleness, #1356 Vertex AI). User said **"don't do the DisplayVideo regeneration."** This is a systemic ~457-file problem, not per-file typos.
  - **PR #40 was closed for exactly this reason.** Vertex AI was proposed as a new addition; it was actually a *regeneration* — `APIs/googleapis.com/aiplatform/v1/` already exists (the search used "vertex"; the dir is `aiplatform`). It would also have stripped curated metadata. The conversion itself worked (214 paths / 271 ops / 1488 schemas, clean `security` blocks) if it's ever wanted.
- **Linode discriminator fix** (#1250) — 10 occurrences of non-standard `x-linode-ref-name`. User explicitly excluded it ("just the openai one").
- **Greenpeace removal** (#1269) — `greenwire.greenpeace.org` no longer resolves (curl exit 6). Removal is destructive; offered, never requested.
- **`x-preferred` policy** (#1115) — on `meraki.com`, only the v0 `0.0.0-streaming` spec is flagged `x-preferred: true`, so nothing in the v1 line is preferred. Looks wrong. 1.74.0 was set to `false` mirroring 1.32.0 rather than deciding it.
- **php-openapi README addition** (#1390) — asked, never answered.

---

## 5b. Recording provenance — REQUIRED for every spec

Every spec must say where it came from and what was done to it. This lives **in the
spec's own `info` block**, nowhere else.

```yaml
info:
  x-origin:                       # WHERE it came from. apis.guru's own convention.
    - format: swagger             # A CHAIN, oldest first, one entry per format.
      url: https://raw.githubusercontent.com/grafana/grafana/main/public/api-merged.json
      version: '2.0'
    - format: openapi
      url: https://raw.githubusercontent.com/grafana/grafana/main/public/api-merged.json
      version: '3.0'
  x-conversion:                   # WHAT was done. Plain sentences, in order.
    - Fetched from <repo/path> (<format>).
    - Converted <A> -> <B> with <tool> <version> <options>; N warnings.
    - Fixed: <defect and why the fix is right>.
    - Known upstream defect left as-is: <what, and why not fixed>.
```

**Why here and not elsewhere** — this was asked directly, so the reasoning is recorded:

- **Not YAML comments at the top of the file.** These specs get round-tripped through
  PyYAML on every refresh, and `yaml.dump` **silently discards all comments**. Provenance
  written as a comment survives exactly until the next update, which is precisely when it
  matters most. This one is disqualifying, not a preference.
- **Not a README per provider directory.** It does not travel with the spec, it goes stale
  independently of the file it describes, it has no answer for multi-version providers
  (`meraki.com/1.32.0` and `1.74.0` have different origins), and it diverges from upstream
  apis.guru layout for no gain.
- **`x-origin` already exists and is already the convention here** — it is machine-readable,
  survives every round-trip, is scoped to the exact spec version it describes, and apis.guru
  tooling already understands it. `x-conversion` is our addition alongside it, in the same
  place, for the step log that `x-origin` has no room for.

Write `x-conversion` for a human reading it cold. "Fixed a param" is useless; "PUT
/v2/vendors/{vendor_id} declared no parameters, so its path variable was undeclared; the
GET on the same path declares it correctly and the fix mirrors that" is the standard.

---

## 6. Conventions that matter

- **Store specs as `.yaml`.** The tree contains both legacy `swagger.yaml` and `openapi.yaml`; new OpenAPI additions use `openapi.yaml`. Convert JSON sources with Python before committing:
  ```python
  yaml.dump(d, f, default_flow_style=False, sort_keys=False, allow_unicode=True, width=100000)
  ```
- **Layout**: `APIs/<domain>/<version>/openapi.yaml`, or `APIs/<domain>/<service>/<version>/openapi.yaml` for multi-service providers. Version dir = `info.version`.
- **Version bumps are new directories**, never in-place edits. Both #41 and #42 are `+N / −0`.
- **Vendor versions can stay fixed while content changes.** For a declared version that has not changed (GitHub, DigitalOcean, Square, DocuSign), refresh the existing version in place and report removals explicitly. Do not invent a vendor version. The dated snapshot policy for unversioned Elasticsearch Serverless in §4 remains separate.
- **Preserve apis.guru curation metadata on any refresh.** A wholesale file replacement silently drops `x-apisguru-categories`, `x-logo`, `x-preferred`, `x-permalink`, `x-providerName`, `x-serviceName`, `x-hasEquivalentPaths`, `contact.x-twitter`, top-level `externalDocs` and `tags`. Merge new spec content *into* the old `info` block. This is the single most important rule for updates — it's what #40 got wrong.
- **`x-origin` records provenance.** Match existing style; for converted specs list the chain, e.g. API Blueprint → swagger → openapi (see `APIs/icons8.com`, `APIs/ritekit.com`, and `APIs/eventbrite.com/3`).
- **New additions go in essentially as-is.** Checked against the recently merged ones (Picsart, Nylas, Eventbrite): they carry **no** `x-apisguru-categories`, `x-logo` or `x-providerName`. Those values are apis.guru curation, and inventing them would be fabricating metadata. Add `x-origin` for provenance and otherwise leave the vendor spec alone. The preserve-metadata rule above applies to **refreshes of specs we already have**, where that curation exists and must survive.
- **Match the sibling file's YAML style.** PyYAML's default dumper writes sequences flush against the parent key; this repo indents them. Subclass the dumper:
  ```python
  class Dumper(yaml.Dumper):
      def increase_indent(self, flow=False, indentless=False):
          return super().increase_indent(flow, False)
  ```
- **CONTRIBUTING.md** distinguishes the fork's validated manual spec PR process from the upstream APIs.guru web form and restriction on direct spec PRs. Follow the fork process here; upstream submission does not establish publication of fork-only additions.

### Conversion toolchain
Installed under the session scratchpad (`apibconv/`), re-installable anywhere:
- `swagger2openapi` (7.0.8) — Swagger 2.0 → OpenAPI 3. Use `{patch:true, warnOnly:true}`. Reliable.
- `apib2swagger` (1.17.1) — API Blueprint → Swagger 2.0. **Its `--open-api-3` path is broken on modern Node** (`json-schema-to-openapi-schema@0.4.0` throws `Type "null" is not a valid type`, with a misleading stack because of a broken error prototype). Workaround: convert to Swagger 2.0, then hand to `swagger2openapi`. That's how Eventbrite was done.
- `google-discovery-to-swagger` — Discovery → Swagger 2.0, then `swagger2openapi`.

For registered Swagger imports, use the repository's locked `maintenance/` toolchain,
not the historical scratchpad. #99 adds swagger2openapi 7.0.8 and all 41 transitive packages
to the npm lock without changing existing package pins. `conversion` recipes default to
zero expected warnings/converter patches. Unexpected counts or source formats require
review. External references must be pinned/bundled first; conversion has no network
resolution. Missing response declarations are rejected before the converter can invent
defaults, and every path/operation must survive. Cached input/output/logs/hashes and the
Swagger → OpenAPI origin chain document the process. Exact vendor patches run afterwards;
full validation and serialization guards remain mandatory. Accepted warnings do not waive
missing-reference validation. The regression suite exercises the real locked converter.

### Post-conversion checks worth running every time

**Write the checker carefully — a naive one produces false failures.** Both of these bit
on PagerDuty and MongoDB, and each looked exactly like a real spec defect:
- **`$ref` may point into a list index**, e.g. `#/components/schemas/X/properties/value/oneOf/3`. That is legal JSON Pointer. A resolver that only walks dicts reports 25 phantom broken refs on PagerDuty.
- **Path parameters are often declared via `$ref`** to `components.parameters`. Comparing `{template}` vars against inline `name` fields without dereferencing first reported 351 phantom mismatches on PagerDuty and 514 on MongoDB. Deref, then compare.

A working version of the checker lives in the session scratchpad as `validate.py`; it is
~70 lines and worth rewriting from this description rather than hunting for the file.

```
- all $refs resolve (refs − components.schemas == ∅)
- every operation has a `responses` block
- path template vars match declared path params
- no `{+name}` reserved-expansion left (Google); normalize to `{name}`
- security entries are well-formed list-of-dicts
```
Real defects caught this way: Eventbrite's `<angle>` path params (fixed), Vertex AI's 207 `{+name}` mismatches (fixed).

---

## 7. Environment gotchas

- **Work has been running in a git worktree.** `git checkout main` fails there — main is checked out in the primary dir. Always `git checkout -B <branch> origin/main`. To resync: `git reset --hard origin/main`.
- **Never bare `git stash`** — the stash stack is shared across worktrees and other sessions.
- **`gh` GraphQL 502s intermittently** on this repo. Fall back to REST: `gh api --method GET "repos/.../issues?..." --paginate`. **Always pass `--method GET`** — bare `-f key=value` defaults to POST and will 422.
- **Bash `read` collapses consecutive tabs.** `IFS=$'\t' read -r a b c` silently shifts fields when a column is empty, because tab is IFS-whitespace. This corrupted 9 of the 13 PayPal PRs (wrong titles, bogus `openapi/3.json` source URLs) before being caught on the pre-merge check. **Use a non-whitespace delimiter (`IFS='|'`) for any tabular loop.**
- **Check for existing specs with a full-depth search**, not `find -maxdepth 2`, and search by *service/dir name* as well as brand name. Searching "vertex" missed `aiplatform` and produced the #40 mistake.
- **PyYAML auto-types dates and timestamps, and that bites twice.** Stripe's old
  `version: 2022-11-15` loads as a `datetime.date`, not a string. Worse, `squareup.com/2.0`
  contains a YAML 1.1 timestamp with an out-of-range hour and raises
  `ValueError: hour must be in 0..23` on load. Strip the timestamp resolver:
  ```python
  SL.yaml_implicit_resolvers = {k: [(t, r) for (t, r) in v if t != 'tag:yaml.org,2002:timestamp']
                                for k, v in SafeLoader.yaml_implicit_resolvers.items()}
  ```
  Also force `info.version` to `str()` before dumping, or a date-like version round-trips wrong.
- **Some committed specs contain raw C1 control bytes.** `docusign.net/v2.1` has `0x80`/`0x99`
  (double-encoded UTF-8), which PyYAML rejects outright with a `ReaderError`. Strip
  `[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]` when loading for comparison.
- **If you build an OrderedDict and dump it, register the representer** or PyYAML emits
  `!!python/object/apply:collections.OrderedDict` and the file is corrupt. The validator
  caught this before it was committed; it will not be obvious from a `head` of the file.
- **PyYAML can't parse every vendor YAML.** Cloudflare's 19 MB spec uses the YAML 1.1 `tag:yaml.org,2002:value` construct, which `safe_load` rejects. Other parsers handle it. Verify integrity with `head`/`tail`/`wc -l` and commit as-is rather than reformatting.
- **`git ls-files` reads the CURRENT branch's index, not `main`.** After merging, a feature
  branch checked out locally still predates those merges, so auditing coverage from it shows
  freshly merged providers as missing. This nearly caused a false "Elasticsearch didn't
  land" panic. To audit what is actually on main, use
  `git ls-tree -r --name-only origin/main APIs`.
- **This worktree uses sparse-checkout** (`git sparse-checkout list`). The working tree holds only a couple of `APIs/` subdirs, so `ls`, `find` and `[ -d ]` under `APIs/` are all misleading — see §4. Widen with `git sparse-checkout add APIs/<domain>` before `git add`, and note the command takes no `-q`.
- **GitHub push protection is active on this repo.** Vendor specs routinely carry fake example tokens that match real credential patterns; a push can be rejected by content you did not write. Read the violation before assuming a genuine leak, and never bypass it without the user.
- **The auto-mode classifier can block `gh pr merge`** ("Merge Without Review") regardless of
  the user's standing permission. This is **intermittent**: it refused every merge early in
  the 2026-09-22 session and allowed all of them later the same session. If it refuses, do
  not fight it or look for a workaround — finish everything else, leave the PRs open and
  verified, and hand the user a ready-to-paste `gh pr merge` loop. It also misfires on
  read-only multi-command `git show ... | grep` pipelines; splitting them into single
  commands clears it.
- **Always verify `mergeable`/`mergeStateStatus` and the file list before merging.** `gh pr view N --json mergeable,mergeStateStatus,changedFiles,additions,deletions`. Unexpected deletions mean you're overwriting something that already exists — that's how #40 was caught.

---

## 8. Spam heuristics (for any future triage)

Strong signals a submission is junk: duplicate submissions from one domain; bursts posted seconds apart or on a fixed schedule; crypto / x402 / "pay-per-call" framing; gambling; "Intelligence"/"Analytics"/"Scraper" wrappers around someone else's platform; `Official: NO` with a Postman documenter link; a source URL pointing at a random personal repo.

Worked examples: BMObot filed 15 issues in 47 seconds. The "SplunkES8.1" issue (#1419) contains *genuine* Splunk ES 8.1 content but is hosted at `rigzindorje/gmail-api` — Splunk publishes no official spec (checked their GitHub org), so there's no trustworthy `x-origin` and it was skipped. The "guardian" issues (#1334/#1335) are a third-party Postman collection titled "guardian news", not The Guardian's Open Platform.

---

## 9. Build and maintain a reproducible update process

The 2026-10-02 audit found no GitHub Actions workflows or general updater in this fork.
The generator under `APIs/moneybird.com/v2-readonly/` is specific to a derived subset.
The README's weekly-update promise, badges, and collection API links describe upstream
APIs.guru, not a verified maintenance or publication service for this fork. The following
is an implementation plan; do not describe these jobs as operational until implemented
and verified.

**Implementation progress (2026-10-02):** PR #60 merged these instructions; PR #61 merged
the initial updater under `maintenance/`: six configured service sources, locked
dependencies, 13 passing offline regression tests, read-only source checks, and a
validated single-API importer. Its PR tests passed on GitHub. The weekly report-artifact
workflow is enabled; a manual run [36976870489](https://github.com/ontola/openapi-directory/actions/runs/36976870489)
fetched all six sources and published a downloadable report and raw source snapshots.
That initial audit job exited nonzero for the then-known DigitalOcean bundling, Xero
validation, and Slack conversion/source-health blockers, distinct from the successful
test job. Xero's blocker is now resolved by #66's checked patch replay; 16 tests pass
locally and in GitHub CI. PRs #62/#63/#65/#67 added Hugging Face and refreshed Plaid,
both public GitHub REST artifacts, and Xero. #69 adds pinned repository bundling and exact
field removal, with locked Node tooling and 21 passing local/CI tests; #70 refreshes
DigitalOcean, and #71/#72 add Snowflake SQL and Warehouse, bringing the registry to nine
artifacts across eight services. #74/#75 add explicitly scoped pinned Fern code-sample
materialization and YAML 1.2 scientific-number parsing, with 27 passing regression tests;
#76/#77 add Cohere and Mistral. #78 aligns scientific-number quoting in the writer and
checks every import's serialized round-trip before writing, with 29 passing local/CI
tests. #79 repairs eight scientific-looking strings across both GitHub artifacts,
retaining the same vendor revision, version, paths and operations. Preserved curation
is now emitted in deterministic key order, tested across three Python hash seeds;
30 offline tests pass. #81 registers Stripe GA, Figma, PagerDuty and Atlas; #82/#83/#84
refresh the first three, with PagerDuty's checked default-removal recipe. Fifteen artifacts
across fourteen services are now registered. Atlas is still blocked by validator/dialect
compatibility, separately from Slack's archived-source blocker.
#86 adds reviewed numeric-directory release discovery and registers Intercom and Sentry;
#87/#88 refresh both. Seventeen artifacts across sixteen services are registered, and
35 regression tests pass locally and in CI. The release catalog response and selected
artifact are pinned together, with explicit release-selection provenance.
#90 adds readable Markdown reports alongside JSON, publishes the readable report in the
audit job summary even when checks fail, and records comparison base revisions per row.
Subset checks retain old rows/dates/bases; failed attempts retain earlier success dates.
Blocked matches are counted as blocked, and added/removed paths and operations remain
separate. Source text is escaped for Markdown/HTML display; custom report filenames cannot
overwrite JSON with their readable companion. Four report regressions bring the test
total to 39, passing locally and in CI. Database, Schema and Table registrations/imports
bring configured coverage to twenty artifacts across nineteen services.

#95 adds live repository-health observations, cached response evidence, import guards
and report findings, with 47 offline tests passing locally and in CI. #96 fixes repeat
imports' provenance to name the actual stored curation baseline rather than an older
manifest fallback; its command-level regression brings the total to 48 passing local/CI
tests. #97 refreshes Intercom's fixed public version `2.16` again after the vendor's
2026-10-02 14:20 UTC wording update: exactly the create/update contact request schemas'
`email_verified` descriptions change; 168 paths / 235 operations remain, with zero
added or removed endpoints. Existing curation/tag order and the two reporting-parameter
patches remain. Vendor commit `70d74db6722480bad239eba2f049ff3c98744c5f`, entry SHA-256
`3274c2255a71c18f38fc146cf316c332503973f5adf0b5ca117f2c409971a4e3`.
#99 implements reviewed Swagger 2.0 → OpenAPI 3.0.0 conversion and registers Grafana and
Square, bringing coverage to 22 artifacts across 21 services and 57 passing local/CI tests.
#100 refreshes Grafana's fixed `0.0.1` artifact: eight parsed content changes (certificate
field, ASN.1 title/description, five RBAC descriptions), with no path/operation additions
or removals and no converter warnings/patches. Vendor commit
`c58da1723a80496cc505922e457e2a0dc78993d0`, entry SHA-256
`5dde6d9a86399e9640ca0208664f7a78a8c5e63c0edbceb925686336471455a5`, converted SHA-256
`84895fb7bdb6cbd94d28f77202f4bf923cf20ec7f2c34579715596584cf0fb51`.
Vendor examples are unchanged; pushing succeeded without a protection bypass. The official
HTTP reference calls Swagger canonical but marks legacy APIs deprecated. New resource APIs
and Grafana Cloud need separate discovery; this scope warning appears in audit reports.

Square's current vendor source is **already OpenAPI 3.0.0**, not Swagger: no conversion is
needed. At vendor commit `0689c901bdfe1ff73f47aa28b17ccd6e0c40bf2d`, entry SHA-256
`8f65460732e19d7445f7a34d8a9df09163db45273df5176a1cc794890ef591fb`, the only parsed
drift after the two previously reviewed fixes is three metadata additions:
`info.externalDocs`, `info.license`, and `x-fern-global-headers`. Endpoints remain 253 / 332.
The new exact recipe asserts both complete source lists and operation identities before
restoring the required `vendor_id` parameter and empty OAuth scope list. It does not fix
undefined `CurrencyExchange` / `AppFeeAllocation` references, so imports remain blocked
by full validation. No Square refresh PR was created; its existing file is unchanged.
The expanded audit also rejects Square's new `info.externalDocs` field, which is not
allowed inside OpenAPI's Info Object. Review a documented exact correction separately;
moving it does not resolve the two missing schemas, and validation must not be waived.

Automatic PR generation, monthly discovery, and fork index publication
remain to do. A local hourly follow-up in this chat is active until 2026-10-09 08:55:58
Europe/Amsterdam for the user's one-week work request. It may stop while the laptop
sleeps; do not prevent sleep or extend the deadline without a new request.

Manual workflow run [36990592745](https://github.com/ontola/openapi-directory/actions/runs/36990592745)
at main `5c5b3a43e` verified the Node installation and bundler on GitHub: all 21 tests
passed, all nine configured artifacts fetched successfully, and all eight supported
OpenAPI artifacts matched their sources with zero validation errors. DigitalOcean's
bundle recorded 21 expected naming warnings; Warehouse recorded zero. The downloaded
artifact includes the source archives, file hashes, bundles, and report. The audit job
still exits nonzero solely for Slack's already-known archived Swagger/conversion blocker;
unsupported-format comparison is not evidence of new Slack API drift or current coverage.

The expanded audit [36994983111](https://github.com/ontola/openapi-directory/actions/runs/36994983111)
at main `ed6630fe3` fetched all eleven sources, passed 27 tests, and matched eight
supported artifacts. The two GitHub artifacts had only scientific-string type drift:
their vendor JSON strings `"0.16001e0"` were emitted unquoted by the old writer, and
the corrected YAML 1.2 reader detected the mismatch. #78/#79 fix the writer and stored
files, rather than ignoring these example differences. Slack remained the known blocker.
The downloaded artifact is `/tmp/openapi-ci-audit-36994983111`; CI artifacts, not `/tmp`,
are the durable download source. Cohere's seven snippets and Mistral's checked recipe
were exercised successfully in that network audit.

Final network audit [37002022081](https://github.com/ontola/openapi-directory/actions/runs/37002022081)
at main `fc16ad482` passed all 29 then-current tests and fetched all eleven artifacts.
All ten supported OpenAPI artifacts matched their official sources with zero validation
errors, including both repaired GitHub descriptions, Cohere's seven code samples, and
the patched public Mistral artifact. DigitalOcean still has 21 reviewed bundler warnings;
Warehouse has zero. The audit job exits nonzero solely for Slack's known archived Swagger
and source-health blocker. Source snapshots and the full report were published as the
`official-source-audit` artifact and downloaded to `/tmp/openapi-ci-audit-37002022081`;
the local `cache/maintenance/report.json` now contains that report. The deterministic
curation change adds one further offline regression (30 total); it changes no API values.

Expanded network audit [37004222700](https://github.com/ontola/openapi-directory/actions/runs/37004222700)
at main `7dff5b044` passed all 30 tests and fetched all fifteen registered artifacts.
Thirteen supported OpenAPI artifacts match their sources with zero validation errors,
including the refreshed Stripe GA, Figma and patched PagerDuty descriptions. The audit
job remains nonzero for two recorded import blockers: Atlas's validator recursion failure
and Slack's archived Swagger source. This does not establish freshness beyond the
configured services. The complete report and raw snapshots are available in the
`official-source-audit` workflow artifact, downloaded to
`/tmp/openapi-ci-audit-37004222700`; the ignored local `cache/maintenance/report.json`
contains this latest report. Recover from CI if the temporary files disappear.

Network audit [37009315774](https://github.com/ontola/openapi-directory/actions/runs/37009315774)
at main `2b0d4d993` passed all 35 tests and fetched seventeen artifacts. Fifteen supported
OpenAPI artifacts match their official sources with zero validation errors, including
Sentry and the catalog-selected, patched Intercom 2.16 description. The pinned catalog
and artifact revision agree, and the original catalog response is present in the uploaded
`official-source-audit` artifact. Atlas's recursion failure and Slack's archived Swagger
source remain the only two recorded blockers; the audit exits nonzero for those reasons.
The downloaded artifact is `/tmp/openapi-ci-audit-37009315774`, and the ignored local
report has been replaced with this verified report. CI is the recovery source after reboot.

Network audit [37016356022](https://github.com/ontola/openapi-directory/actions/runs/37016356022)
at main `7ce9472de` passed all 39 tests and fetched twenty registered artifacts. Eighteen
supported artifacts match their official sources with zero validation errors, including
all five Snowflake descriptions. Atlas's recursion failure and Slack's archived Swagger
source remain the only two import blockers; the audit job exits nonzero for those reasons.
The readable-summary step succeeds despite that exit status, and both `report.json` and
`report.md` are present in the uploaded `official-source-audit` artifact. Their totals
agree (18 matches, 2 blocked), and every row records this run's actual comparison base.
The artifact was downloaded to `/tmp/openapi-ci-audit-37016356022`; ignored local copies
of both reports have been updated. Retrieve the CI artifact if temporary files disappear.

Network audit [37023716280](https://github.com/ontola/openapi-directory/actions/runs/37023716280)
at main `53f3cbc8e` passed all 48 tests and fetched all twenty artifacts. Eighteen supported
artifacts match with zero validation errors, including the refreshed Intercom wording.
Only Atlas's validator recursion and Slack's archived Swagger/conversion remain blocked.
The new health checker recorded nineteen service observations from fourteen unique GitHub
repository requests: eighteen artifacts have `repository_available` sources, Slack is
independently confirmed `archived`, and hosted Hugging Face is `not_assessed` by this
repository check. No metadata checks failed. The overall audit exits nonzero for the two
known blockers; readable-summary publication and artifact upload succeed. Both reports
and every raw repository-metadata response/hash were verified in the downloaded artifact
at `/tmp/openapi-ci-audit-37023716280`. Ignored local reports and repository-health
snapshots are updated. CI artifacts are the recovery source if temporary/local files
disappear. No spec commits were created solely for health-check timestamps.

Expanded network audit [37048205733](https://github.com/ontola/openapi-directory/actions/runs/37048205733)
at main `f1a63de2b` passed 57 tests and fetched all 22 registered descriptions. Seventeen
match, two have valid new content drift (Plaid and Intercom), and three are import-blocked
(Atlas validator/dialect, Square invalid Info metadata/missing schemas, Slack archived
Swagger). Grafana's refreshed conversion matches with zero warnings/patches. All 21
GitHub-source observations succeeded across sixteen unique repositories; twenty sources
are `repository_available`, Slack is archived, and hosted Hugging Face is unassessed by
that repository check. Summary publication and artifact upload succeeded despite the
expected nonzero audit exit. Both reports, all sixteen repository-response hashes and
Grafana's conversion output/hash were downloaded and verified at
`/tmp/openapi-ci-audit-37048205733`; ignored local reports/health snapshots are updated.
The Grafana service-specific legacy/new-resource coverage note appears in the report.

**That drift queue is now complete (#102–#104):**
- #102 corrects the reviewed current manifest targets for Plaid, Xero Accounting, Stripe,
  Figma and Intercom. A successful new-version import advances its manifest target with
  the API file; commit both together. No universal vendor version ordering is guessed.
  Audits record the actual comparison/curation baseline. Matching imports can repair a
  lagging target without rewriting the spec. Manifest edits preserve unrelated formatting;
  source-configuration changes and edits during validation stop the import before writes.
  Four additional regressions bring the suite to 61 passing local/CI tests, including
  successive releases, invalid-release guards and preservation of concurrent edits.
  Baseline pointers describe reviewed imports, not a claim about all other stored versions.
- #103 imports Plaid `2020-09-14_1.762.0` from vendor commit
  `325e2e192bcb422df708029bafe9d950c94df2fd`, entry SHA-256
  `e07a869352e83670e2ef077376db268358ce7a0dc4a8e97b8e1e980b91616a8c`.
  Against actual last import `1.740.1`, both have 360 paths / 351 operations:
  POST `/cra/report/create` and `/protect/cash_advance/feedback/upload` are added;
  POST `/link_delivery/create` and `/link_delivery/get` are removed. The vendor's pinned
  CHANGELOG explicitly records these removals in 1.753.0 and the migration to
  `/link/token/create` with `hosted_link`. Both historical versions remain unchanged,
  curation comes from 1.740.1, and the reviewed manifest target advances to 1.762.0.
  Full validation and YAML value/type round-trip pass; no conversion or content patches.
  The vendor client-library artifact includes limited-availability fields; importing it
  does not imply every described product is generally available.
- #104 refreshes Intercom fixed public `2.16` from vendor commit
  `7b3a218f2b8a9c09ae24247270c764444cddaf70`, entry SHA-256
  `e007fe1902ceaa64e6dbaedfc064f2a2e4fc24bab6c86cf1c8f6900c2b0c42ca`.
  Exactly one vendor description changes: DELETE `/companies/{company_id}` now states
  the company record remains, contacts are detached without being deleted, detachment
  cannot be reversed, and changes may take time to appear. Vendor PR #697 documents it.
  168 paths / 235 operations, zero endpoint/schema/security changes; existing curation,
  reporting-parameter patches and historical 2.14 remain. Full validation and exact
  patched-vendor equivalence pass. No OpenAPI version conversion.
All three PRs are merged and attached to this chat. Re-fetch before future comparisons;
new vendor commits may appear independently of an unchanged version or endpoint count.


Expanded network audit [37057748754](https://github.com/ontola/openapi-directory/actions/runs/37057748754)
at main `845f81fff` passed all 61 tests and fetched all 22 registered artifacts. Nineteen
match their sources, including the new Plaid version and Intercom clarification. The only
three import blockers remain Atlas (validator/dialect), Square (invalid Info metadata and
undefined schemas), and Slack (archived unsupported Swagger). No fetch/prepare failures
or new valid content drift were found. The expected blockers make the audit exit nonzero;
readable-summary publication and artifact upload succeeded. Every row names the actual
comparison baseline. Downloaded reports, all 22 entry-source hashes and all sixteen unique
repository-response hashes were verified at `/tmp/openapi-ci-audit-37057748754`; ignored
local reports and health snapshots are updated. CI artifacts remain the recovery source
when temporary files disappear. All 22 reviewed manifest targets exist on fetched main
and agree with their stored `info.version` directory. No files were committed solely for
check timestamps.


Expanded network audit [37084738252](https://github.com/ontola/openapi-directory/actions/runs/37084738252)
at main `3388295d9` passed 69 tests under Python 3.11 and fetched all 22 descriptions.
Nineteen have valid source matches, including the refreshed Atlas Admin. Cohere matches
its configured source but is blocked by the newly detected empty `TruncationStrategy`
union; Square's invalid metadata/missing schemas and Slack's archived unsupported Swagger
remain the other blockers. No fetch/prepare failures or unblocked content drift were
found. The report distinguishes the blocked Cohere match from validated matches and
names the explicit validation profile for every row. The expected three blockers make
the audit exit nonzero. Readable-summary publication and source-artifact upload succeed.
Both reports, all 22 entry-source hashes and all sixteen unique repository metadata
hashes were downloaded and verified at `/tmp/openapi-ci-audit-37084738252`; ignored local
reports and health snapshots are updated. Recover original evidence from CI if temporary
files disappear. No vendor spec was changed solely for a check timestamp.

Fork-facing README and CONTRIBUTING now explain the registered-source weekly audit,
report-artifact access, validated manual import/PR process and source-specific recipes.
They explicitly identify upstream badges, API/RSS endpoints and contribution guidance;
direct reproducible spec PRs are accepted in this fork. No fork collection endpoint has
been published or claimed. Index publication still needs verified consumer access.

**Resume next:** Atlas's validator/dialect blocker and refresh are resolved. Cohere's
empty union now needs vendor-correction discovery or a separately reviewed exact
correction; do not invent variants or relax validation. Continue to
extend the registry to other major imported APIs,
audit more distinct stable Snowflake services, and continue vendor discovery. Square still
is registered as direct OpenAPI 3, with exact existing fixes replayed, but its undefined
vendor schemas still block import. Do not invent them or waive validation. Grafana's
legacy HTTP artifact is monitored/refreshed; discover maintained stable descriptions
for its newer `/apis` resources and Cloud separately. Repository-health checks are
implemented; extend artifact-specific
lifecycle/deprecation checks and assessment of hosted sources without confusing repository
activity with spec freshness. Ownership, service scope and stable-release checks still
need deliberate review.
Implement validated per-service
PR generation and monthly discovery in separate infrastructure PRs; no blanket automatic
merge. Consider fork publication only with
verified consumer access. Slack's maintained official replacement remains unresolved.
Cohere, Mistral, Stripe, Figma, PagerDuty and Sentry's recorded refreshes are complete. The registry
and local report retain the latest checks;
re-fetch main and inspect open PRs before continuing. Do not repeat completed imports.

### Implementation order

1. Build the fetch, compare, validate, and import commands alongside the first refreshes
   in §4. Put reusable tools and locked dependencies in the repository, rather than relying
   on `/tmp`, old session scratchpads, or packages installed globally.
2. Register and refresh the confirmed stale major APIs. Add the verified missing providers
   with the same machinery, one PR per API. Keep updater infrastructure in its own PR.
3. Add weekly GitHub Actions checks and PR generation after local runs are reproducible.
   Add a monthly discovery check for missing major APIs. These are repository workflows;
   do not assume a recurring Codex chat task already exists.
4. Extend coverage incrementally across priority providers. Respect every exclusion in §5;
   neither automation nor this plan authorizes Google regeneration or other parked work.
5. Update README and CONTRIBUTING to describe this fork's actual import process, maintenance
   coverage, and publication status. Identify upstream badges and API links explicitly.
   If publishing a fork index, derive it from this fork's committed specs and verify that
   consumers can see its additions before advertising that endpoint.

### Source configuration and discovery

- Maintain a machine-readable source manifest keyed by provider and API/service. Record
  the target spec, official source entry point, release/tag/catalog discovery strategy,
  source format, bundling/conversion recipe, patch recipe, version policy, and priority.
  Use existing `info.x-origin` to find leads; confirm vendor ownership and source health
  before enabling updates. Configuration does not replace in-spec provenance (§5b).
- Discover releases and service catalogs, not just the already-pinned version URL. A
  successful download of an old release cannot establish that no newer release exists.
- For new providers, search vendor documentation and vendor-owned repositories. Inspect
  repository roots, branches, tags, and SDK generation inputs before dismissing a 404.
  Check presence against fetched main at full depth and distinguish complete official
  specs from hand-authored slices, third-party scrapers, and generic protocol definitions.
- Prefer stable public products. Deduplicate catalog slices by API shape and purpose,
  following the HubSpot precedent in §4. Label scope accurately when importing only one
  service of a larger platform. Track unresolved candidates so searches are not repeated
  blindly, and record what URL was actually checked and when.

### Fetching and detecting changes

- Resolve a vendor repository branch/tag to a commit SHA and fetch the entry document and
  all referenced files from that revision. For hosted specs, record the retrieval time,
  final URL, content hash, and available ETag/Last-Modified values. Use bounded timeouts,
  retries, and concurrency; report failures rather than treating them as unchanged.
- Keep a raw source hash and a deterministic comparison of parsed vendor content. Check
  versions, added/removed paths and operations, parameters, security, request/response
  schemas, and descriptions. A matching version, path count, or recent local commit is
  insufficient evidence of freshness. Changes confined to YAML formatting or key order
  should not generate spec PRs.
- Compare after applying the same pinned conversion and documented patches. Exclude only
  identified fork-owned curation and generated provenance from vendor-content comparisons;
  do not ignore the entire `info` block or vendor extensions. Re-fetch external references
  as part of the source snapshot so their changes are detected too.
- Preserve the original source bytes for reproducibility. Parser workarounds used for
  inspection must not silently alter the committed vendor content. A 404, archived repo,
  authentication failure, or invalid document is a source-health result, not a reason to
  remove the stored API.

### Import, validation, and delivery

- Bundle external OpenAPI references into a standalone document before committing, with
  provenance for the bundling and conversion. Identify reference positions correctly:
  code-sample extensions can contain references to non-schema artifacts, as in Cohere.
  Preserve or explicitly materialize those artifacts without pretending they are schemas.
- Support the source's OpenAPI version, including 3.1 and its JSON Schema semantics.
  Do not downgrade 3.1 documents merely to fit a 3.0-only validator. Apply the checks in
  §6, including JSON Pointer array indices and referenced path parameters. Reject HTML
  error pages and catalog indexes that are not OADs.
- Preserve existing curation (§6); retain historical versions for version bumps and use
  the documented fixed-version/snapshot policies. Encode justified fixes as reproducible
  patches with explanations in `info.x-conversion`. Never invent missing schemas. Record
  known upstream defects explicitly and distinguish them from new validation regressions.
- Add meaningful tests for updater behavior: fixed-version content changes, referenced-file
  changes, metadata preservation, new-version directories, patch replay, and failed fetches.
  Test validators with array-index references, referenced parameters, and OpenAPI 3.1.
- Generate one update PR per API, updating an existing pending PR rather than duplicating
  it. Include the official source/revision, old/new versions, additions and removals,
  conversion warnings, patches, known defects, and validation results. Link any relevant
  upstream issue or PR in the body. Verify file lists and merge status as required by §7.
- Routine official additions may follow the existing merge authorization in §1. Do not
  implement blanket automatic merging of all refreshes. Flag unexplained large removals,
  source substitutions, new patches, and deferred decisions for review. Respect push
  protection and approval-review blocks; leave verified PRs ready when merging is blocked.

### Scheduled checks and freshness reporting

- Run weekly checks for registered priority sources; make unsupported providers visible
  rather than suggesting every historical spec is monitored. Separate read-only fetching
  and validation from the step permitted to write PRs. Run validation on generated PRs.
- Publish a machine-readable freshness report and a readable summary as workflow artifacts
  or a verified fork index. For each API, show the stored/source versions and revisions,
  last check attempt, last successful fetch/comparison/validation, content drift, pending
  PR, known defects, and source-health status. Failed attempts must not advance the last
  successful check. Keep original and converted provenance in the spec's `info` block.
- Distinguish **matches the configured source**, **a newer release is available**, and
  **source health or current API coverage is uncertain**. Slack's archived source is the
  concrete example of why these are different claims. Do not create spec commits solely
  to change a last-checked timestamp.
- The monthly discovery job should produce a deduplicated queue of official candidates
  for well-known APIs, with URLs, ownership evidence, scope, and import obstacles. Notify
  on actionable drift, failures, or decisions; avoid repetitive unchanged-status updates.
