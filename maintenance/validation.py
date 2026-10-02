"""Pinned OpenAPI validation with ECMAScript patterns and cycle-safe collection."""

from importlib.metadata import version
from collections.abc import Mapping

from openapi_schema_validator._regex import has_ecma_regex
from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator
from openapi_spec_validator.schemas import schema_v30, schema_v31
from openapi_spec_validator.schemas.backend.jsonschema import create_validator
from openapi_spec_validator.validation import keywords

DESCRIPTION = ("openapi-spec-validator 0.9.0 with openapi-schema-validator 0.9.0, "
               "the Python jsonschema backend, regress 2026.9.1 ECMAScript regex "
               "syntax/matching with no flags, and cycle-safe property collection")


class CycleSafeProperties:
    def _collect_properties(self, schema):
        # The pinned upstream implementation recursively collects through these
        # same edges, but lacks the visited-object guard used by schema validation.
        # Resolve SchemaPaths before comparing identity so aliases/cycles converge.
        properties, seen, pending = set(), set(), [schema]
        while pending:
            current = pending.pop()
            value = current.read_value()
            if not isinstance(value, Mapping):
                continue
            identity = id(value)
            if identity in seen:
                continue
            seen.add(identity)
            if "properties" in current:
                properties.update((current / "properties").keys())
            for keyword in ("allOf", "anyOf", "oneOf"):
                if keyword in current:
                    pending.extend(current / keyword)
            for keyword in ("items", "not"):
                if keyword in current:
                    pending.append(current / keyword)
        return properties


class Schema30(CycleSafeProperties, keywords.OpenAPIV30SchemaValidator):
    pass


class Schema31(CycleSafeProperties, keywords.OpenAPIV31SchemaValidator):
    pass


class Spec30(OpenAPIV30SpecValidator):
    schema_validator = create_validator(schema_v30)
    keyword_validators = {**OpenAPIV30SpecValidator.keyword_validators, "schema": Schema30}


class Spec31(OpenAPIV31SpecValidator):
    schema_validator = create_validator(schema_v31)
    keyword_validators = {**OpenAPIV31SpecValidator.keyword_validators, "schema": Schema31}


def validate(spec):
    # Fail rather than silently fall back to Python regex or drift private APIs.
    for package, expected in (("openapi-spec-validator", "0.9.0"),
                              ("openapi-schema-validator", "0.9.0"),
                              ("regress", "2026.9.1")):
        if version(package) != expected:
            raise ValueError("Validation dependency differs from the reviewed pin: " + package)
    if not has_ecma_regex():
        raise ValueError("The required ECMAScript regex backend is unavailable")
    if spec["openapi"].startswith("3.0."):
        validator = Spec30
    elif spec["openapi"].startswith("3.1."):
        validator = Spec31
    else:
        raise ValueError("This validation profile supports only OpenAPI 3.0 and 3.1")
    validator(spec).validate()
