import copy
import json
import unittest

import update


def square():
    def operation(name, tag, schema):
        return {"summary": name, "operationId": name, "tags": [tag],
                "responses": {"200": {"description": "OK", "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/" + schema}}}}}}
    vendor = operation("UpdateVendor", "Vendors", "CurrencyExchange")
    vendor["parameters"] = []
    revoke = operation("RevokeToken", "OAuth", "AppFeeAllocation")
    revoke["security"] = [{"oauth2": None}]
    return {"openapi": "3.0.0", "info": {"title": "Square", "version": "2.0"},
            "paths": {"/v2/vendors/{vendor_id}": {"put": vendor}, "/oauth2/revoke": {"post": revoke}},
            "components": {"schemas": {}, "securitySchemes": {"oauth2": {"type": "oauth2", "flows": {
                "authorizationCode": {"authorizationUrl": "https://example.com/authorize",
                                      "tokenUrl": "https://example.com/token", "scopes": {}}}}}}}


class SquareRecipeTests(unittest.TestCase):
    def test_reviewed_corrections_replay_without_inventing_missing_schemas_and_stop_on_vendor_fix(self):
        source = {"patches": ["maintenance/patches/square.json"]}
        original = square()
        patched, steps = update.prepare_document(source, json.dumps(original).encode())
        parameter = patched["paths"]["/v2/vendors/{vendor_id}"]["put"]["parameters"][0]
        self.assertEqual((parameter["name"], parameter["in"], parameter["required"], parameter["schema"]),
                         ("vendor_id", "path", True, {"type": "string"}))
        self.assertEqual(patched["paths"]["/oauth2/revoke"]["post"]["security"], [{"oauth2": []}])
        self.assertEqual(patched["components"]["schemas"], {})
        self.assertEqual(set(update.reference_objects(patched)),
                         {"#/components/schemas/CurrencyExchange", "#/components/schemas/AppFeeAllocation"})
        self.assertTrue(update.validate_document(patched))
        self.assertIn("no schemas are invented", steps[0])
        for path, method, field in (("/v2/vendors/{vendor_id}", "put", "parameters"), ("/oauth2/revoke", "post", "security")):
            fixed = copy.deepcopy(original)
            fixed["paths"][path][method][field] = copy.deepcopy(patched["paths"][path][method][field])
            with self.assertRaisesRegex(ValueError, "source value changed"):
                update.prepare_document(source, json.dumps(fixed).encode())


if __name__ == "__main__":
    unittest.main()
