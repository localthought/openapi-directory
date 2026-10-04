import copy
import unittest

import update
from validation import describe_error


def document(version, schema):
    return {"openapi": version, "info": {"title": "Test", "version": "1"},
            "paths": {"/items/~id": {"get": {"responses": {"200": {
                "description": "OK", "content": {"application/json": {"schema": schema}}
            }}}}}}


class DiagnosticTests(unittest.TestCase):
    def test_nested_schema_keyword_points_to_cause_not_reference_alternative(self):
        spec = document("3.0.3", {"type": "object", "properties": {
            "status": {"type": "string", "const": "DO_NOT_DUMP_PAYLOAD"}}})
        original = copy.deepcopy(spec)
        errors = update.validate_document(spec)
        self.assertEqual(len(errors), 1)
        self.assertIn("#/paths/~1items~1~0id/get/responses/200/content/application~1json/schema/properties/status", errors[0])
        self.assertIn("'const'", errors[0])
        self.assertNotIn("DO_NOT_DUMP_PAYLOAD", errors[0])
        self.assertNotIn("'$ref' is a required property", errors[0])
        self.assertEqual(spec, original)

    def test_31_empty_union_and_invalid_boolean_bound_still_fail_at_exact_locations(self):
        for schema, keyword in (({"oneOf": []}, "oneOf"),
                                ({"type": "number", "exclusiveMaximum": True}, "exclusiveMaximum")):
            errors = update.validate_document(document("3.1.0", schema))
            self.assertEqual(len(errors), 1)
            self.assertIn("schema/" + keyword, errors[0])
            self.assertLessEqual(len(errors[0]), 1520)
        self.assertIn("expected number; got bool", errors[0])

    def test_invalid_default_omits_actual_value_and_non_schema_errors_remain_visible(self):
        errors = update.validate_document(document("3.0.3", {"type": "number", "default": "DO_NOT_DUMP_DEFAULT"}))
        self.assertTrue(errors)
        self.assertIn("expected number; got str", errors[0])
        self.assertNotIn("DO_NOT_DUMP_DEFAULT", errors[0])
        self.assertIn("schema/default", errors[0])
        self.assertEqual(describe_error(ValueError("source parsing failed")), "source parsing failed")

    def test_referenced_schema_failure_names_real_definition_pointer(self):
        spec = document("3.1.0", {"$ref": "#/components/schemas/BadSchema"})
        spec['components'] = {'schemas': {'BadSchema': {'properties': {'bad/key': {'oneOf': []}}}}}
        errors = update.validate_document(spec)
        self.assertIn("#/components/schemas/BadSchema/properties/bad~1key/oneOf", errors[0])
        self.assertNotIn("schema/oneOf", errors[0])
