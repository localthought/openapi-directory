"""Convert already fetched, self-contained Swagger using a locked local tool."""
import hashlib
import json
import subprocess
from pathlib import Path

import bundle

TOOL_VERSION = "7.0.8"
HERE = Path(__file__).resolve().parent


def prepare(source, spec, metadata, cache, resolve_path=None):
    config = source["conversion"]
    if config.get("tool") != "swagger2openapi" or config.get("version") != TOOL_VERSION:
        raise ValueError("Unsupported conversion recipe")
    if spec.get("swagger") != "2.0" or "openapi" in spec:
        raise ValueError("Conversion recipe requires Swagger 2.0; review changed source format")
    if any(not ref.startswith("#") for ref in bundle.refs(spec)):
        raise ValueError("External references require pinned bundling before conversion")

    def operations(document):
        found = set()
        for path, item in document["paths"].items():
            if "$ref" in item and resolve_path is None:
                raise ValueError("Referenced path items require a local resolver")
            item = resolve_path(document, item) if resolve_path else item
            for method in {"get", "put", "post", "delete", "options", "head", "patch", "trace"} & item.keys():
                operation = item[method]
                if not isinstance(operation, dict) or not isinstance(operation.get("responses"), dict) or not operation["responses"]:
                    raise ValueError("Operation has no responses; refusing to let the converter invent one: " + method.upper() + " " + path)
                found.add(method.upper() + " " + path)
        return found

    original_operations = operations(spec)

    def reserved(value):
        if isinstance(value, dict):
            return "x-s2o-warning" in value or any(reserved(v) for v in value.values())
        if isinstance(value, list):
            return any(reserved(v) for v in value)
        return False

    if reserved(spec):
        raise ValueError("Source contains converter warning markers; review before conversion")
    for field in ("expected_warnings", "expected_patches"):
        count = config.get(field, 0)
        if type(count) is not int or count < 0:
            raise ValueError("Conversion expectations must be nonnegative integer counts")
    package = HERE / "node_modules/swagger2openapi/package.json"
    if not package.exists() or json.loads(package.read_text())["version"] != TOOL_VERSION:
        raise ValueError("Install the pinned converter with npm ci --prefix maintenance --ignore-scripts")
    workspace = (cache / source["id"] / metadata.get("snapshot_sha256", metadata["sha256"])).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(spec, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    input_path, output_path = workspace / "conversion-input.json", workspace / "conversion-result.json"
    input_path.write_bytes(raw)
    process = subprocess.run(["node", str(HERE / "convert-swagger.cjs"), str(input_path), str(output_path)],
                             cwd=workspace, capture_output=True, text=True, timeout=120)
    (workspace / "converter.log").write_text(process.stdout + process.stderr)
    if process.returncode:
        raise ValueError("Swagger conversion failed: " + process.stderr[-1500:])
    result = json.loads(output_path.read_text())
    converted = result["openapi"]
    if converted.get("openapi") != "3.0.0" or "swagger" in converted:
        raise ValueError("Converter did not produce the configured OpenAPI version")
    if set(converted["paths"]) != set(spec["paths"]) or operations(converted) != original_operations:
        raise ValueError("Conversion changed paths or operations; review before importing")
    warnings, patches = result["warnings"], result["patches"]
    if not isinstance(warnings, list) or type(patches) is not int:
        raise ValueError("Invalid converter observations")
    if len(warnings) != config.get("expected_warnings", 0) or patches != config.get("expected_patches", 0):
        raise ValueError("Converter warning/patch count changed; review conversion-result.json before updating the recipe")
    output = (json.dumps(converted, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    (workspace / "converted.json").write_bytes(output)
    metadata["conversion"] = {"tool": "swagger2openapi", "version": TOOL_VERSION,
                              "from": "2.0", "to": "3.0.0",
                              "options": {"patch": True, "warnOnly": True, "resolve": False, "targetVersion": "3.0.0"},
                              "warnings": warnings, "patches": patches,
                              "input_sha256": hashlib.sha256(raw).hexdigest(),
                              "converted_sha256": hashlib.sha256(output).hexdigest()}
    step = ("Converted Swagger 2.0 to OpenAPI 3.0.0 with swagger2openapi " + TOOL_VERSION
            + " (patch:true, warnOnly:true, resolve:false, targetVersion:3.0.0); "
            + str(len(warnings)) + " warnings and " + str(patches) + " converter patches. "
            + "External resolution is disabled; the complete converted document must pass validation. "
            + "Converted SHA-256 " + metadata["conversion"]["converted_sha256"] + ".")
    return converted, step
