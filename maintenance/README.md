# Official-source maintenance

This initial updater checks six services through seven configured source artifacts,
including both public GitHub REST descriptions. It does not claim coverage of the
entire directory, discover every vendor release, convert
Swagger, generate PRs, or merge them. Those remain explicit follow-up work
in AGENTS.md §9. Blocked services are included in the report rather than silently skipped.

Use Python 3.9+, Node.js 22.12+ (CI uses Node 24), and the pinned dependencies:

```sh
python3 -m venv /tmp/openapi-maintenance-venv
/tmp/openapi-maintenance-venv/bin/pip install -r maintenance/requirements.txt
npm ci --prefix maintenance --ignore-scripts --no-audit --no-fund
/tmp/openapi-maintenance-venv/bin/python -m unittest discover -s maintenance -v
git fetch origin main
/tmp/openapi-maintenance-venv/bin/python maintenance/update.py check
```

`requirements.in` records the two direct dependencies; `requirements.txt` pins their
transitive dependencies too. `package-lock.json` pins the Redocly bundler package and its
integrity; that release includes its runtime dependencies. Update and test both locks
deliberately. GitHub Actions are
pinned to verified release commit SHAs.

`check` reads committed specs from `origin/main`, so sparse checkouts and stale feature
branches cannot hide existing providers. It resolves GitHub sources to a commit before
fetching, stores the exact original bytes and fetch metadata under `cache/maintenance/`,
and compares paths, operations, schemas, security, and other vendor content. Versions
alone are insufficient. An unchanged source is reported as `matches_source`; it is not
a guarantee that the vendor still maintains that source or that it covers the current API.

The JSON report records check times, successes, validation errors, separate additions and
removals, source revisions/hashes, and import blockers. A failed check preserves previous
success timestamps. A check of selected sources keeps other report rows and their old
timestamps. The command exits nonzero for fetch/parse failures, validation errors, and
explicit blockers; valid content drift itself is an actionable finding, not a failed check.
The ignored cache is local state, not durable publication. CI uploads it as an artifact.

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
the comparison baseline; the old configured target is only the fallback. An unchanged
import writes no file, avoiding timestamp churn. Versions must be safe directory names.
Empty versions and snapshot policies require an explicit future recipe, not an invented
vendor version. Existing curation tags are merged by name, with vendor fields taking
precedence and curated tags preserved.

Run `check --source plaid` to select one service, or repeat `--source` for several. Use
`--report PATH` and `--cache PATH` to retain state in an appropriate location. Add sources
to `sources.json` only after verifying ownership, service scope, stable-release selection,
and absence from the full main tree. Known upstream defects need documented patches or
reviewed exceptions before import; this tool has no validation bypass.

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

The weekly GitHub workflow runs tests and publishes the configured-source report and raw
snapshots. PRs changing the updater run its tests without network access. Automated PR
creation and monthly discovery have not been implemented yet; the one-week Codex
follow-up carries out that implementation and manual API delivery independently.
