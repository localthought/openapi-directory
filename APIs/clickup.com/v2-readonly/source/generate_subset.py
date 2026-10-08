#!/usr/bin/env python3
"""Build an OAS 3.0 read-only ClickUp v2 subset from the maintained OAS 3.1 source."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
import yaml

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[1] / "v2" / "2.0" / "openapi.yaml"
OUTPUT = HERE.parent / "openapi.yaml"
SOURCE_SHA256 = "91786855cf012ef7472ba15f86c2e164d69e994a5faae1b584c5338adabbf9de"
SOURCE_COMMIT = "f3b0d16b015e11f98aaa78aebfb7d5c954436dbe"
SOURCE_URL = "https://developer.clickup.com/openapi/clickup-api-v2-reference.json"
SELECTED_PATHS = (
    "/v2/team",
    "/v2/team/{team_Id}/task",
    "/v2/task/{task_id}",
)
SUBSCHEMA_MAPS = {
    "properties", "patternProperties", "definitions", "$defs", "dependentSchemas"
}
SUBSCHEMA_SINGLE = {
    "items", "additionalProperties", "not", "if", "then", "else", "contains",
    "propertyNames", "contentSchema",
}
SUBSCHEMA_ARRAYS = {"allOf", "oneOf", "anyOf", "prefixItems"}


def pointer_target(document, ref):
    if not isinstance(ref, str) or not ref.startswith("#/"):
        raise ValueError(f"Unsupported non-local reference: {ref!r}")
    target = document
    for token in ref[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        target = target[int(token)] if isinstance(target, list) else target[token]
    return target


def component_name(ref):
    return "SourceSchema_" + sha256(ref.encode("utf-8")).hexdigest()[:16]


def main():
    raw = SOURCE.read_bytes()
    actual_sha = sha256(raw).hexdigest()
    if actual_sha != SOURCE_SHA256:
        raise SystemExit(
            f"Maintained source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_sha}"
        )
    source = yaml.safe_load(raw)
    schemas = {}
    active = set()

    def normalize_schema(schema):
        if isinstance(schema, bool):
            return schema
        if not isinstance(schema, dict):
            raise ValueError(f"Expected a JSON Schema object, got {type(schema).__name__}")
        result = deepcopy(schema)
        ref = result.pop("$ref", None)
        if ref is not None:
            name = component_name(ref)
            if name not in schemas and name not in active:
                active.add(name)
                schemas[name] = normalize_schema(pointer_target(source, ref))
                active.remove(name)
            siblings = normalize_schema(result) if result else {}
            if siblings:
                # In OAS 3.0 a Reference Object ignores siblings. allOf keeps sibling
                # constraints and annotations active beside the referenced schema.
                return {"allOf": [{"$ref": f"#/components/schemas/{name}"}], **siblings}
            return {"$ref": f"#/components/schemas/{name}"}

        schema_type = result.get("type")
        if isinstance(schema_type, list):
            non_null_types = [item for item in schema_type if item != "null"]
            if len(non_null_types) == 1 and len(schema_type) == 2:
                result["type"] = non_null_types[0]
                result["nullable"] = True
            else:
                raise ValueError(f"Cannot represent source type union in OAS 3.0: {schema_type!r}")

        if "const" in result:
            const = result.pop("const")
            if "enum" in result and const not in result["enum"]:
                raise ValueError("A const value conflicts with the source enum")
            result["enum"] = [const]

        encoding = result.pop("contentEncoding", None)
        if encoding is not None:
            format_name = {"int32": "int32", "int64": "int64", "double": "double"}.get(encoding)
            if format_name is None:
                result["x-json-schema-contentEncoding"] = encoding
            else:
                if "format" in result and result["format"] != format_name:
                    raise ValueError(f"Conflicting format/contentEncoding: {result['format']!r}, {encoding!r}")
                result["format"] = format_name

        examples = result.pop("examples", None)
        if examples:
            result.setdefault("example", examples[0])
            if len(examples) > 1:
                result["x-json-schema-examples"] = examples

        for key in SUBSCHEMA_MAPS:
            if isinstance(result.get(key), dict):
                result[key] = {name: normalize_schema(value) for name, value in result[key].items()}
        for key in SUBSCHEMA_SINGLE:
            child = result.get(key)
            if isinstance(child, dict):
                result[key] = normalize_schema(child)
            elif isinstance(child, list):
                result[key] = [normalize_schema(value) if isinstance(value, dict) else value for value in child]
        for key in SUBSCHEMA_ARRAYS:
            if isinstance(result.get(key), list):
                result[key] = [normalize_schema(value) for value in result[key]]
        return result

    def copy_openapi_node(value):
        if isinstance(value, dict):
            return {
                key: normalize_schema(item) if key == "schema" else copy_openapi_node(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [copy_openapi_node(item) for item in value]
        return deepcopy(value)

    paths = {}
    for path in SELECTED_PATHS:
        source_item = source["paths"][path]
        if "get" not in source_item:
            raise ValueError(f"Expected GET operation missing at {path}")
        item = {key: value for key, value in source_item.items() if key == "get" or key in {"parameters", "servers", "summary", "description"}}
        paths[path] = copy_openapi_node(item)

    subset = {
        "openapi": "3.0.3",
        "info": {
            "title": "ClickUp API v2 (read-only subset)",
            "version": "v2-readonly",
            "description": (
                "Read-only subset for authorized Workspace discovery and task synchronization. "
                "Derived from the maintained ClickUp v2 source pinned in source/README.md. "
                "The source is OpenAPI 3.1; this document converts its schema null unions, "
                "numeric contentEncoding annotations, and schema examples to OAS 3.0 forms. "
                "The pinned source task examples do not fully match their response schemas; "
                "they are retained as published."
            ),
            "x-origin": [{"format": "openapi", "url": SOURCE_URL, "version": "3.1.0"}],
            "x-providerName": "clickup.com",
            "x-serviceName": "v2-readonly",
            "x-source-commit": SOURCE_COMMIT,
            "x-source-sha256": SOURCE_SHA256,
        },
        "servers": deepcopy(source["servers"]),
        "security": deepcopy(source["security"]),
        "paths": paths,
        "components": {
            "securitySchemes": deepcopy(source["components"]["securitySchemes"]),
            "schemas": schemas,
        },
    }
    OUTPUT.write_text(yaml.safe_dump(subset, sort_keys=False, allow_unicode=True, width=100))


if __name__ == "__main__":
    main()
