"""Extract an original description from a reviewed JSON script, without executing HTML."""
import hashlib
import json
from html.parser import HTMLParser


def strict_json(text):
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError("Duplicate key in embedded JSON")
            value[key] = child
        return value
    def nonfinite(value):
        raise ValueError("Nonfinite embedded JSON")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def pointer(document, path):
    if not isinstance(path, str) or not path.startswith("#/"):
        raise ValueError("Embedded pointers must start with #/")
    value = document
    for part in path[2:].split("/"):
        if "~" in part.replace("~0", "").replace("~1", ""):
            raise ValueError("Invalid JSON pointer escape")
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and str(int(key)) == key:
            value = value[int(key)]
        else:
            raise ValueError("Embedded pointer does not resolve")
    return value


class Script(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.found, self.active, self.closed, self.parts = 0, False, False, []

    def handle_starttag(self, tag, attrs):
        if tag != "script" or not any(k == "id" and v == "__NEXT_DATA__" for k, v in attrs):
            return
        self.found += 1
        if len({k for k, v in attrs}) != len(attrs) or dict(attrs).get("type") != "application/json" or "src" in dict(attrs):
            raise ValueError("Invalid original JSON script attributes")
        self.active = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.active:
            raise ValueError("Original JSON script must have a closing tag")

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.active, self.closed = False, True


def prepare(source, raw, metadata, cache):
    config = source["embedded_document"]
    if (not isinstance(config, dict) or set(config) != {"format", "pointer", "assertions"}
            or config["format"] != "next-data-json-string" or "github" in source
            or any(source.get(k) for k in ("bundling", "code_samples", "yaml_response_keys"))):
        raise ValueError("Unsupported embedded source recipe")
    if metadata.get("url") != source.get("url") or metadata.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise ValueError("Embedded source URL or original HTML hash changed")
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("Embedded HTML exceeds reviewed size limit")
    parser = Script()
    parser.feed(raw.decode("utf-8"))
    parser.close()
    if parser.found != 1 or not parser.closed or parser.active:
        raise ValueError("Expected exactly one complete original JSON script")
    script = "".join(parser.parts)
    data = strict_json(script)
    assertions = config["assertions"]
    if not isinstance(assertions, list) or not assertions:
        raise ValueError("Embedded source requires lifecycle/identity assertions")
    seen = set()
    for assertion in assertions:
        if not isinstance(assertion, dict) or set(assertion) != {"pointer", "value"} or assertion["pointer"] in seen:
            raise ValueError("Invalid embedded assertion")
        seen.add(assertion["pointer"])
        if json.dumps(pointer(data, assertion["pointer"]), sort_keys=True) != json.dumps(assertion["value"], sort_keys=True):
            raise ValueError("Embedded lifecycle/identity assertion changed: " + assertion["pointer"])
    document = pointer(data, config["pointer"])
    if not isinstance(document, str) or not document or len(document.encode()) > 10 * 1024 * 1024:
        raise ValueError("Embedded description must be an original JSON string")
    parsed = strict_json(document)
    if (not isinstance(parsed, dict) or not (parsed.get("swagger") or parsed.get("openapi"))
            or not isinstance(parsed.get("info"), dict) or not isinstance(parsed.get("paths"), dict)):
        raise ValueError("Embedded string is not an original description")
    extracted = document.encode("utf-8")
    observation = {"format": config["format"], "pointer": config["pointer"],
                   "script_sha256": hashlib.sha256(script.encode()).hexdigest(),
                   "document_sha256": hashlib.sha256(extracted).hexdigest(), "assertions": assertions}
    workspace = cache / source["id"] / metadata["sha256"]
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "embedded-document.json").write_bytes(extracted)
    (workspace / "embedded-extraction.json").write_text(json.dumps(observation, indent=2) + "\n")
    metadata["embedded_document"] = observation
    step = ("Extracted the original vendor JSON string at " + config["pointer"]
            + " from the sole __NEXT_DATA__ application/json script; no HTML or vendor code executed. "
            + "Lifecycle/identity assertions checked; original HTML retained unchanged. "
            + "Decoded description SHA-256 " + observation["document_sha256"] + ".")
    return extracted, step
