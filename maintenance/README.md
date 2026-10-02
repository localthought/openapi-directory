# Official-source maintenance

This initial updater checks six services through seven configured source artifacts,
including both public GitHub REST descriptions. It does not claim coverage of the
entire directory, discover every vendor release, bundle split descriptions, convert
Swagger, apply patches, generate PRs, or merge them. Those remain explicit follow-up work
in AGENTS.md §9. Blocked services are included in the report rather than silently skipped.

Use Python 3.9+ and the pinned dependencies:

```sh
python3 -m venv /tmp/openapi-maintenance-venv
/tmp/openapi-maintenance-venv/bin/pip install -r maintenance/requirements.txt
/tmp/openapi-maintenance-venv/bin/python -m unittest discover -s maintenance -v
git fetch origin main
/tmp/openapi-maintenance-venv/bin/python maintenance/update.py check
```

`requirements.in` records the two direct dependencies; `requirements.txt` pins their
transitive dependencies too. Update and test the lock deliberately. GitHub Actions are
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
reviewed exceptions before import; this initial tool has no validation bypass.

The weekly GitHub workflow runs tests and publishes the configured-source report and raw
snapshots. PRs changing the updater run its tests without network access. Automated PR
creation and monthly discovery have not been implemented yet; the one-week Codex
follow-up carries out that implementation and manual API delivery independently.
