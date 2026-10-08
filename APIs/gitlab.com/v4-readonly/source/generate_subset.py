#!/usr/bin/env python3
"""Rebuild the GitLab.com read-only OAD subset from the pinned official OAS."""
from copy import deepcopy
from pathlib import Path
import re
import yaml

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "openapi_v3.yaml"
OUTPUT = HERE.parent / "openapi.yaml"
SELECTED_PATHS = {
    "/api/v4/projects": {"get"},
    "/api/v4/projects/{id}": {"get"},
    "/api/v4/projects/{id}/issues": {"get"},
    "/api/v4/projects/{id}/issues/{issue_iid}": {"get"},
}


def refs(value):
    if isinstance(value, dict):
        if "$ref" in value and value["$ref"].startswith("#/components/"):
            yield value["$ref"].split("#", 1)[1]
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def lookup(document, pointer):
    node = document["components"]
    for token in pointer.removeprefix("/components/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        node = node[token]
    return node


def main():
    source = yaml.safe_load(SOURCE.read_text())
    paths = {}
    for source_path, methods in SELECTED_PATHS.items():
        item = source["paths"][source_path]
        paths[source_path.removeprefix("/api/v4")] = {
            key: deepcopy(value)
            for key, value in item.items()
            if key in methods or key in {"parameters", "servers", "summary", "description"}
        }

    # The current upstream OAS declares the issue list response as a single issue,
    # but GitLab's current Issues API docs define this as a paginated list. Preserve
    # the source unchanged and correct the subset's response shape to the documented
    # collection shape.
    paths["/projects/{id}/issues"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] = {
        "type": "array",
        "items": {"$ref": "#/components/schemas/APIEntitiesIssue"},
    }

    components = {}
    pending = list(refs(paths)) + list(refs(source.get("security", [])))
    while pending:
        pointer = pending.pop()
        if pointer in components:
            continue
        value = deepcopy(lookup(source, pointer))
        components[pointer] = value
        pending.extend(refs(value))

    rebuilt_components = {}
    for pointer, value in components.items():
        match = re.fullmatch(r"/components/([^/]+)/(.+)", pointer)
        if not match:
            raise ValueError(f"Unexpected component pointer: {pointer}")
        section, name = match.groups()
        rebuilt_components.setdefault(section, {})[name] = value

    # The selected security requirements must have corresponding definitions.
    rebuilt_components["securitySchemes"] = deepcopy(source["components"]["securitySchemes"])

    subset = {
        "openapi": source["openapi"],
        "info": {
            "title": "GitLab REST API (read-only subset)",
            "version": "v4-readonly",
            "description": (
                "Read-only GitLab.com subset for project discovery and issue synchronization. "
                "The project list retains GitLab's membership filter; consumers can select "
                "projects with membership=true. Based on GitLab's official OpenAPI 3.0 "
                "source, pinned and preserved in source/openapi_v3.yaml. Only GitLab.com "
                "is represented; self-managed instance hosts are not included. The official "
                "Issues API reference describes the list response as a collection; this "
                "subset corrects a single-object response shape in the pinned upstream OAS; "
                "see https://docs.gitlab.com/api/issues/#list-project-issues."
            ),
            "termsOfService": source["info"].get("termsOfService"),
            "license": source["info"].get("license"),
            "x-origin": [{
                "format": "openapi",
                "url": "https://gitlab.com/gitlab-org/gitlab/-/raw/e8b0b4728b9a69a9767a623ca6bf745998061b78/doc/api/openapi/openapi_v3.yaml",
                "version": "19.5",
            }],
            "x-providerName": "gitlab.com",
            "x-serviceName": "v4-readonly",
        },
        "servers": [{"url": "https://gitlab.com/api/v4", "description": "GitLab.com REST API v4"}],
        "security": [
            {"http": []},
            {"oauth2": ["read_api"]},
            {"apiKey": []},
        ],
        "paths": paths,
        "components": rebuilt_components,
    }
    OUTPUT.write_text(yaml.safe_dump(subset, sort_keys=False, allow_unicode=True, width=100))


if __name__ == "__main__":
    main()
