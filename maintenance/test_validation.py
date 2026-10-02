import copy
import json
import subprocess
import unittest
from unittest.mock import patch

import update
import validation


def document(version="3.0.3"):
    return {"openapi": version, "info": {"title": "Validation regression", "version": "1.0"},
            "paths": {"/items": {"get": {"responses": {
                "200": {"description": "OK", "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/A"}}}}}}}},
            "components": {"schemas": {
                "A": {"type": "object", "properties": {"a": {"type": "string"}},
                      "allOf": [{"$ref": "#/components/schemas/B"}], "required": ["a"]},
                "B": {"oneOf": [{"$ref": "#/components/schemas/A"},
                                 {"type": "object", "properties": {"b": {"type": "string"}}}]}}}}


class ValidationTests(unittest.TestCase):
    def test_cyclic_compositions_terminate_without_losing_required_property_checks(self):
        for version in ("3.0.3", "3.1.0"):
            spec = document(version)
            before = copy.deepcopy(spec)
            self.assertEqual(update.validate_document(spec), [])
            self.assertEqual(spec, before)
            spec["components"]["schemas"]["A"]["required"] = ["missing"]
            self.assertTrue(update.validate_document(spec))

    def test_cycle_guard_keeps_unrelated_default_and_reference_validation(self):
        for version in ("3.0.3", "3.1.0"):
            spec = document(version)
            spec["components"]["schemas"]["Flag"] = {"type": "boolean", "default": "false"}
            self.assertTrue(update.validate_document(spec))
            del spec["components"]["schemas"]["Flag"]
            spec["components"]["schemas"]["B"]["oneOf"][1] = {"$ref": "#/components/schemas/Missing"}
            self.assertTrue(update.validate_document(spec))

    def test_ecmascript_named_captures_and_identity_escapes_validate_and_match_defaults(self):
        for version in ("3.0.3", "3.1.0"):
            for pattern, good, bad in ((r"^(?<label>[a-z]+)$", "abc", "123"),
                                       (r"^a\:b$", "a:b", "axb")):
                spec = document(version)
                spec["components"]["schemas"]["Code"] = {"type": "string", "pattern": pattern,
                                                            "default": good}
                self.assertEqual(update.validate_document(spec), [])
                spec["components"]["schemas"]["Code"]["default"] = bad
                self.assertTrue(update.validate_document(spec))

    def test_invalid_ecmascript_syntax_is_rejected_in_both_versions(self):
        for version in ("3.0.3", "3.1.0"):
            for pattern in ("[", r"(?P<label>x)"):
                spec = document(version)
                spec["components"]["schemas"]["Code"] = {"type": "string", "pattern": pattern}
                self.assertTrue(update.validate_document(spec))

    def test_no_flag_regex_semantics_match_node_including_unicode_property_escape(self):
        # Flags are not present in an OpenAPI pattern. Do not silently choose /u:
        # that changes property-escape matching and rejects vendor identity escapes.
        cases = [[r"^\p{L}+$", "é"], [r"^\p{L}+$", "p{L}"],
                 [r"^(?<name>[a-z]+)$", "abc"], [r"^(?<name>[a-z]+)$", "123"],
                 [r"^a\:b$", "a:b"], [r"^a\:b$", "axb"]]
        script = "let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>console.log(JSON.stringify(JSON.parse(s).map(([p,v])=>new RegExp(p).test(v)))));"
        expected = json.loads(subprocess.check_output(["node", "-e", script],
                                                      input=json.dumps(cases).encode(), timeout=10))
        for (pattern, value), valid in zip(cases, expected):
            spec = document()
            spec["components"]["schemas"]["Code"] = {"type": "string", "pattern": pattern,
                                                        "default": value}
            self.assertEqual(not update.validate_document(spec), valid, (pattern, value))

    def test_missing_ecmascript_backend_fails_instead_of_falling_back(self):
        with patch.object(validation, "has_ecma_regex", return_value=False):
            errors = update.validate_document(document())
        self.assertTrue(any("backend is unavailable" in error for error in errors))

    def test_boolean_schema_and_discriminator_annotation_in_openapi31(self):
        spec = document("3.1.0")
        spec["components"]["schemas"]["A"]["allOf"].append(True)
        self.assertEqual(update.validate_document(spec), [])
        spec["components"]["schemas"]["Tagged"] = {
            "oneOf": [{"type": "integer"}, {"type": "boolean"}],
            "discriminator": {"propertyName": "kind"}, "default": "invalid"}
        self.assertTrue(update.validate_document(spec))

    def test_empty_oneof_is_rejected_in_openapi31(self):
        spec = document("3.1.0")
        spec["components"]["schemas"]["Never"] = {"oneOf": []}
        self.assertTrue(update.validate_document(spec))
