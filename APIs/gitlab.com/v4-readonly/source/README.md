# GitLab OpenAPI source

`openapi_v3.yaml` is the unmodified official GitLab OpenAPI 3.0 document from
`gitlab-org/gitlab` commit `e8b0b4728b9a69a9767a623ca6bf745998061b78`, at
`doc/api/openapi/openapi_v3.yaml` (SHA-256
`264b5a2ceeada43d2401c1dccd2a576cbb712ac5aa0254d7fec47086255ef764`). The official
GitLab docs identify this as the maintained source and say the OpenAPI 2.0 file is
deprecated: <https://docs.gitlab.com/api/openapi/>.

Run `python3 generate_subset.py` with PyYAML installed to reproduce
`../openapi.yaml`. The generator retains the official operation definitions and their
transitive component references, removes the `/api/v4` prefix from paths because it is
part of the subset's server URL, and selects only the three documented GET operations.

GitLab REST pagination is offset based by default. List requests use `page` and
`per_page`; clients should follow the response `Link` header's `rel="next"` URL. GitLab
also documents `x-next-page` and related headers, while noting that some pagination
headers may be omitted on GitLab.com. See <https://docs.gitlab.com/api/rest/#pagination>.
