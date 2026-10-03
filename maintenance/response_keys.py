"""Reviewed YAML response-code key repair, without coercing payload values."""

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def prepare(source, spec):
    recipe = source["yaml_response_keys"]
    if (not isinstance(recipe, dict) or set(recipe) != {"expected_conversions"}
            or type(recipe["expected_conversions"]) is not int
            or recipe["expected_conversions"] < 1):
        raise ValueError("Response-key recipe requires a positive exact conversion count")
    if not str(spec.get("openapi", "")).startswith(("3.0.", "3.1.")):
        raise ValueError("Response-key repair requires OpenAPI 3.0 or 3.1")
    pending, seen = [], set()
    for item in spec["paths"].values():
        for method in METHODS & item.keys():
            responses = item[method].get("responses", {})
            if id(responses) in seen:
                continue
            seen.add(id(responses))
            for key in responses:
                if isinstance(key, str):
                    continue
                if type(key) is not int or not 100 <= key <= 599:
                    raise ValueError("Unsupported non-string response key; review source")
                if str(key) in responses:
                    raise ValueError("Response key collision; refusing to overwrite")
                pending.append((responses, key))
    if len(pending) != recipe["expected_conversions"]:
        raise ValueError("Response-key conversion count changed; review recipe")
    # Check every precondition before changing the newly parsed document.
    for responses, key in pending:
        responses[str(key)] = responses.pop(key)
    return ("Quoted " + str(len(pending)) + " unquoted YAML HTTP response-code keys "
            "in path operations as strings, matching JSON object-key representation. "
            "Checked exact count, integer codes 100-599 and absence of collisions; "
            "response bodies, payload keys and schema values are unchanged.")
