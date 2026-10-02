# Contributing

This repository is the `ontola/openapi-directory` fork. Its maintenance work prioritizes
official vendor descriptions of well-known industry APIs. The instructions below apply
to this fork; the upstream APIs.guru submission process is described separately at the end.

## Contributing to this fork

Read [AGENTS.md](AGENTS.md) for conventions, known defects and explicitly deferred work,
and [maintenance/README.md](maintenance/README.md) for updater commands and validation.
Check the fetched main tree and [open fork PRs](https://github.com/ontola/openapi-directory/pulls)
before proposing an addition or refresh. Sparse checkouts can hide providers on disk:

```sh
git fetch origin main
git ls-tree -r --name-only origin/main APIs
```

Search the full paths by provider domain, brand, service and aliases. Prefer descriptions
published in vendor-owned repositories or linked directly from official documentation.
Check public-release status and source health; a successful download or unchanged version
alone does not prove current coverage. File a [fork issue](https://github.com/ontola/openapi-directory/issues/new)
with the official source URL and service scope if the import needs investigation.

For reproducible updates, register the source and any reviewed bundling, sample, release
selection or exact patch recipes in `maintenance/`. Keep reusable updater changes in a
separate PR, with appropriate regression tests. Import one API per PR against this fork's
`main`, including the official source/revision, old/new versions, added and removed paths
and operations, transformations, known defects and validation results. Link relevant
upstream issues or PRs in the body.

Store new descriptions as YAML, retain historical versions for declared version bumps,
preserve existing curation on refresh, and record provenance in the spec's `info` block.
Use the validated importer and check the serialized output. Fix vendor defects upstream
when possible; fork patches must assert exact source values/context and explain why the
correction is justified. Never invent missing schemas or disable validation to import a
broken source. Respect the parked items recorded in AGENTS.md.

Direct spec PRs following this process are accepted by this fork. The inherited upstream
restriction below does not apply to these reproducible fork imports.

## Contributing to upstream APIs.guru

The remaining guidance describes the upstream project's process. Its web form and issue
tracker target `APIs-guru/openapi-directory`; submissions there do not automatically add
files to this fork, and fork imports do not establish publication in upstream's REST API.

### Adding an API upstream

To add an API to the collection, there must be a machine-readable API description in a format which is or can be converted to OpenAPI (formerly known as Swagger). These include RAML, API Blueprint, Postman Collections, Google Discovery Format, WADL and IO Docs.

First please check that the API you wish to add isn't already in the collection. You can
browse the APIs in [GitHub](https://github.com/APIs-guru/openapi-directory/tree/main/APIs) or on the [APIs.guru](https://apis.guru/) website.

Please also check the API isn't in the process of being added, by checking the [list of open issues](https://github.com/APIs-guru/openapi-directory/issues).

The API should meet the following criteria:

* Public - anyone can access it as long as they follow some clearly defined steps (subscribe, pay fees, etc.).
* Persistent - API is made with long-lived goal, and not for a particular event (conference, hackathon, etc.).
* Useful - API should provide useful functionality not only for its owner.

The process to request an API to be added is to use the [web form](https://apis.guru/add-api/).

### Amending an API definition upstream

#### Adding information

If you wish to only add information to the API definition, such as a description, category, logo, tag etc, please raise an issue with the relevant details.

#### Changing / Fixing an API definition

First please see if you can make your fix upstream with the owner of the API definition, this benefits everyone and is less work than maintaining patches.

Check the `info.contact` section of the API definition or the `x-origin` to see if there is an email or Twitter contact, or a GitHub repository you can contribute to.

##### Do not raise PRs to amend the openapi/swagger.yaml files directly

If you do this, your changes would be overwritten the next time the API update scripts are run. Such PRs will be closed.

##### If you want to run our API registry (add/update/validate/repair functions) locally

Please contact us for details.
