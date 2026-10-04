"""Pinned OpenAPI validation with ECMAScript patterns and cycle-safe collection."""

from importlib.metadata import version
from collections.abc import Mapping
from jsonschema.exceptions import ValidationError

from openapi_schema_validator._regex import has_ecma_regex
from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator
from openapi_spec_validator.schemas import schema_v30, schema_v31
from openapi_spec_validator.schemas.backend.jsonschema import create_validator
from openapi_spec_validator.validation import keywords
from openapi_spec_validator.validation.exceptions import OpenAPIValidationError

DESCRIPTION = ("openapi-spec-validator 0.9.0 with openapi-schema-validator 0.9.0, "
               "the Python jsonschema backend, regress 2026.9.1 ECMAScript regex "
               "syntax/matching with no flags, and cycle-safe property collection")


def describe_error(error, spec=None):
    """Locate nested failures without dumping whole vendor schemas or payloads."""
    if not isinstance(error, ValidationError):
        return str(error)[:1500]
    prefix = getattr(error, "maintenance_schema_parts", ())
    target = getattr(error, "maintenance_schema_value", None)
    # Schema meta/default errors from the pinned validator have schema-relative
    # paths. Locate their original schema by identity, including local $ref targets.
    if spec is not None and isinstance(target, (Mapping, list)):
        pending, seen = [(spec, ())], set()
        while pending:
            value, path = pending.pop()
            if value is target:
                prefix = path
                break
            if not isinstance(value, (Mapping, list)) or id(value) in seen:
                continue
            seen.add(id(value))
            entries = list(value.items()) if isinstance(value, Mapping) else list(enumerate(value))
            pending.extend((child, path + (key,)) for key, child in reversed(entries))
    prefix += getattr(error, "maintenance_value_suffix", ())
    pending, leaves = [error], []
    while pending:
        current = pending.pop()
        if current.context:
            pending.extend(reversed(current.context))
        else:
            leaves.append(current)
    # OAS 3.0 frequently offers Reference Object as an alternative to Schema
    # Object. Its missing-$ref branch obscures the actual invalid schema keyword.
    useful = [e for e in leaves if not (e.validator == "required"
              and e.validator_value == ["$ref"])] or leaves
    messages = []
    for failure in useful:
        pointer = "#/" + "/".join(str(k).replace("~", "~0").replace("/", "~1")
                                  for k in prefix + tuple(failure.absolute_path))
        if failure.validator in ("required", "additionalProperties"):
            reason = failure.message[:200]
        elif failure.validator == "type":
            reason = "expected " + str(failure.validator_value) + "; got " + type(failure.instance).__name__
        elif failure.validator is None:
            reason = failure.message[:200]
        else:
            reason = str(failure.validator) + " constraint failed"
        message = pointer[:500] + ": " + reason
        if message not in messages:
            messages.append(message)
        if len(messages) == 5:
            break
    return "\n".join(messages)[:1500]


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


class SchemaDiagnostics:
    def _validate_schema_meta(self, schema, schema_value):
        error = super()._validate_schema_meta(schema, schema_value)
        if error is not None:
            error.maintenance_schema_parts = tuple(schema.parts)
            error.maintenance_schema_value = schema_value
        return error

    def __call__(self, schema, **options):
        for error in super().__call__(schema, **options):
            # The spec validator wraps bare jsonschema errors and discards custom
            # attributes. Perform that same conversion before attaching location.
            if not isinstance(error, OpenAPIValidationError):
                error = OpenAPIValidationError.create_from(error)
            if not hasattr(error, "maintenance_schema_parts"):
                error.maintenance_schema_parts = tuple(schema.parts)
                error.maintenance_schema_value = schema.read_value()
                # Other typed errors yielded by these pinned schema validators
                # validate default values, rather than the schema meta-document.
                if error.validator is not None:
                    error.maintenance_value_suffix = ("default",)
            yield error


class Schema30(SchemaDiagnostics, CycleSafeProperties, keywords.OpenAPIV30SchemaValidator):
    pass


class Schema31(SchemaDiagnostics, CycleSafeProperties, keywords.OpenAPIV31SchemaValidator):
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
