#!/usr/bin/env python3
"""Compare official sources with a Git tree and import one validated API at a time."""

import argparse
import copy
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml
from openapi_spec_validator import validate
import bundle
import samples

ROOT = Path(__file__).resolve().parents[1]
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
CURATION = {
    "x-apisguru-categories", "x-logo", "x-preferred", "x-permalink",
    "x-providerName", "x-serviceName", "x-hasEquivalentPaths",
}
PROVENANCE = {"x-origin", "x-conversion"}
MAP_FIELDS = {
    "schemas", "properties", "patternProperties", "$defs", "definitions",
    "parameters", "responses", "headers", "requestBodies", "securitySchemes",
    "callbacks", "links", "examples", "paths", "dependentSchemas",
}


class Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    pass


Loader.yaml_implicit_resolvers = {
    k: [(t, r) for t, r in v if t not in {"tag:yaml.org,2002:timestamp", "tag:yaml.org,2002:bool"}]
    for k, v in Loader.yaml_implicit_resolvers.items()
}
Loader.add_implicit_resolver("tag:yaml.org,2002:bool",
                             re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))
# YAML 1.2 numbers such as 1e-08 are valid without a decimal point. PyYAML's
# YAML 1.1 resolver leaves them as strings, corrupting numeric schema bounds.
Loader.add_implicit_resolver("tag:yaml.org,2002:float",
                             re.compile(r"^[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)[eE][-+]?[0-9]+$"),
                             list("-+0123456789."))


class Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    # Inspect the original bytes. Invalid control characters are a failure, not a
    # license to silently rewrite vendor content during automated imports.
    text = raw.decode("utf-8-sig")
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        spec = yaml.load(text, Loader=Loader)
    if not isinstance(spec, dict) or not (spec.get("openapi") or spec.get("swagger")):
        raise ValueError("Download is not an OpenAPI/Swagger description")
    if not isinstance(spec.get("info"), dict) or not isinstance(spec.get("paths"), dict):
        raise ValueError("Description must have info and paths objects")
    spec["info"]["version"] = str(spec["info"].get("version", ""))
    return spec


def request(url):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise ValueError("Sources must use HTTPS")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ontola-openapi-maintenance"})
            with urllib.request.urlopen(req, timeout=30) as response:
                if urllib.parse.urlsplit(response.url).scheme != "https":
                    raise ValueError("Source redirected away from HTTPS")
                return response.read(), {
                    "url": response.url, "etag": response.headers.get("ETag"),
                    "last_modified": response.headers.get("Last-Modified"),
                }
        except urllib.error.HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(attempt + 1)


def fetch(source):
    if "github" in source:
        config = source["github"]
        repository = config["repository"]
        ref = urllib.parse.quote(config["ref"], safe="")
        raw_commit, _ = request("https://api.github.com/repos/" + repository + "/commits/" + ref)
        revision = json.loads(raw_commit)["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise ValueError("Invalid source revision")
        url = "https://raw.githubusercontent.com/" + repository + "/" + revision + "/" + config["path"]
    else:
        revision = None
        url = source["url"]
    raw, metadata = request(url)
    metadata.update(revision=revision, sha256=sha256(raw), fetched_at=now())
    return raw, metadata


def stored(path, base):
    files = set(git("ls-tree", "-r", "--name-only", base, "APIs").decode().splitlines())
    if path not in files:
        return None
    return parse(git("show", base + ":" + path))


def reference_objects(value, trail=()):
    """Skip example payloads and extensions, but retain extension-named schemas."""
    if isinstance(value, dict):
        if isinstance(value.get("$ref"), str):
            yield value["$ref"]
        mapping = bool(trail and trail[-1] in MAP_FIELDS)
        for key, child in value.items():
            if not mapping and (str(key).startswith("x-") or key == "example"):
                continue
            # Example Objects carry literal arbitrary data in value.
            if key == "value" and len(trail) >= 2 and trail[-2] == "examples":
                continue
            yield from reference_objects(child, trail + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from reference_objects(child, trail + (index,))


def pointer(spec, ref):
    if not ref.startswith("#/"):
        raise ValueError("Only local JSON Pointer references can be dereferenced here")
    current = spec
    for token in urllib.parse.unquote(ref[2:]).split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", token):
                raise ValueError("Invalid array index in " + ref)
            current = current[int(token)]
        else:
            current = current[token]
    return current


def dereference(spec, value):
    seen = set()
    while isinstance(value, dict) and "$ref" in value:
        ref = value["$ref"]
        if ref in seen:
            raise ValueError("Reference cycle in a parameter or path item")
        seen.add(ref)
        value = pointer(spec, ref)
    return value


def validate_document(spec):
    errors = []
    refs = list(reference_objects(spec))
    external = sorted({ref.split("#")[0] for ref in refs if not ref.startswith("#")})
    if external:
        return ["External OpenAPI references require bundling: " + ", ".join(external[:8])]
    if not str(spec.get("openapi", "")).startswith(("3.0.", "3.1.")):
        return ["No conversion recipe for this OpenAPI/Swagger version"]
    try:
        validate(spec)
    except Exception as error:
        errors.append("OpenAPI validation: " + str(error)[:1500])
    try:
        for path, item in spec["paths"].items():
            item = dereference(spec, item)
            if not isinstance(item, dict):
                errors.append("Invalid path item: " + path)
                continue
            expected = set(re.findall(r"\{([^}]+)\}", path))
            if any(name.startswith("+") for name in expected):
                errors.append("Reserved expansion in " + path)
            for method in METHODS & item.keys():
                operation = item[method]
                if not operation.get("responses"):
                    errors.append(method.upper() + " " + path + " has no responses")
                parameters = item.get("parameters", []) + operation.get("parameters", [])
                declared = {param["name"] for raw in parameters
                            for param in [dereference(spec, raw)] if param.get("in") == "path"}
                if expected != declared:
                    errors.append(method.upper() + " " + path + " has mismatched path parameters")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        errors.append("Reference/parameter validation: " + str(error))
    return errors


def comparison_content(spec):
    result = copy.deepcopy(spec)
    info = result["info"]
    for key in CURATION | PROVENANCE:
        info.pop(key, None)
    contact = info.get("contact")
    if isinstance(contact, dict):
        contact.pop("x-twitter", None)
        if not contact:
            info.pop("contact", None)
    return result


def canonical(spec):
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def operation_set(spec):
    return {method.upper() + " " + path for path, item in spec["paths"].items()
            for method in METHODS & item.keys()}


def stats(spec):
    return {"version": spec["info"]["version"], "paths": len(spec["paths"]),
            "operations": len(operation_set(spec)), "format": spec.get("openapi", spec.get("swagger"))}


def compare(old, new):
    if old is None:
        return {"status": "missing", "source": stats(new)}
    old_view = comparison_content(old)
    new_view = comparison_content(preserve_curation(old, new))
    changed = canonical(old_view) != canonical(new_view)
    return {
        "status": "changed" if changed else "matches_source",
        "stored": stats(old), "source": stats(new),
        "added_paths": sorted(set(new["paths"]) - set(old["paths"])),
        "removed_paths": sorted(set(old["paths"]) - set(new["paths"])),
        "added_operations": sorted(operation_set(new) - operation_set(old)),
        "removed_operations": sorted(operation_set(old) - operation_set(new)),
    }


def destination(source, spec):
    version = spec["info"]["version"]
    if not version or version in {".", "..", "None"} or not re.fullmatch(r"[A-Za-z0-9_.+-]+", version):
        raise ValueError("A safe nonempty vendor version is required")
    target = Path(source["target"])
    if target.parts[:2] != ("APIs", source["provider"]) or target.name != "openapi.yaml" or ".." in target.parts:
        raise ValueError("Target must be an OpenAPI YAML path inside the provider directory")
    if source.get("version_policy") != "vendor":
        raise ValueError("This initial importer supports only declared vendor versions")
    return target.parent.parent / version / "openapi.yaml"


def preserve_curation(old, new):
    result = copy.deepcopy(new)
    if old:
        for key in CURATION:
            if key in old["info"]:
                result["info"][key] = copy.deepcopy(old["info"][key])
        twitter = old["info"].get("contact", {}).get("x-twitter")
        if twitter is not None:
            result["info"].setdefault("contact", {})["x-twitter"] = twitter
        for key in ("externalDocs", "tags"):
            if key in old and key not in result:
                result[key] = copy.deepcopy(old[key])
        if "tags" in old and "tags" in result:
            tags = {tag["name"]: copy.deepcopy(tag) for tag in old["tags"]}
            for tag in result["tags"]:
                tags.setdefault(tag["name"], {}).update(tag)
            result["tags"] = list(tags.values())
    return result


def import_document(source, new, metadata, old):
    if source.get("import_blocker"):
        raise ValueError(source["import_blocker"])
    errors = validate_document(new)
    if errors:
        raise ValueError("Import blocked:\n" + "\n".join(errors))
    result = preserve_curation(old, new)
    result["info"]["x-origin"] = [{"format": "openapi", "url": metadata["url"],
                                     "version": ".".join(new["openapi"].split(".")[:2])}]
    revision = " at commit " + metadata["revision"] if metadata.get("revision") else " on " + metadata["fetched_at"]
    result["info"]["x-conversion"] = [
        "Fetched from " + metadata["url"] + revision + "; entry source SHA-256 " + metadata["sha256"] + ".",
    ]
    result["info"]["x-conversion"].extend(metadata.get("transformations", []))
    if old:
        result["info"]["x-conversion"].append("Preserved existing APIs.guru curation metadata from " + source["target"] + ".")
    result["info"]["x-conversion"].append(
        "Serialized as YAML with PyYAML 6.0.3; no OpenAPI version conversion."
        if metadata.get("transformations") else
        "Parsed the vendor document and serialized it as YAML with PyYAML 6.0.3; no API content patches or OpenAPI version conversion.")
    errors = validate_document(result)
    if errors:
        raise ValueError("Preserving curation produced an invalid document:\n" + "\n".join(errors))
    return result


def load_sources(path):
    manifest = json.loads(path.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported source manifest version")
    ids = [entry["id"] for entry in manifest["sources"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source IDs")
    return manifest["sources"]


def cache_snapshot(cache, source_id, raw, metadata):
    cached = cache / source_id / metadata.get("snapshot_sha256", metadata["sha256"])
    cached.mkdir(parents=True, exist_ok=True)
    (cached / "source").write_bytes(raw)
    (cached / "fetch.json").write_text(json.dumps(metadata, indent=2) + "\n")


def prepare_document(source, raw, metadata=None, cache=None):
    """Replay reviewed exact replacements; source changes require recipe review."""
    transformations = []
    if source.get("bundling") and source.get("code_samples"):
        raise ValueError("Combined schema bundling and code sample recipes require explicit support")
    if source.get("bundling"):
        if metadata is None or cache is None:
            raise ValueError("Bundling requires fetch metadata and a source cache")
        raw, step = bundle.prepare(source, raw, metadata, cache, request, Loader)
        transformations.append(step)
    spec = parse(raw)
    if source.get("code_samples"):
        if metadata is None or cache is None:
            raise ValueError("Code samples require fetch metadata and a source cache")
        transformations.append(samples.prepare(source, spec, raw, metadata, cache, request))
    seen = set()
    for filename in source.get("patches", []):
        path = (ROOT / filename).resolve()
        directory = (ROOT / "maintenance/patches").resolve()
        if directory not in path.parents or path.suffix != ".json":
            raise ValueError("Patch recipes must be JSON files under maintenance/patches")
        recipe_raw = path.read_bytes()
        recipe = json.loads(recipe_raw)
        operations = recipe.get("operations")
        if (recipe.get("schema_version") != 1 or not recipe.get("description")
                or not isinstance(operations, list) or not operations):
            raise ValueError("Invalid patch recipe: " + filename)
        # Work on a separate parsed document. No caller's object or original
        # cached bytes are modified, even if a later precondition fails.
        for operation in operations:
            replacing = set(operation) == {"pointer", "from", "value", "context"}
            removing = set(operation) == {"pointer", "from", "remove", "context"} and operation["remove"] is True
            if not replacing and not removing:
                raise ValueError("Exact patches require pointer, from, context, and value or remove:true")
            ref = operation["pointer"]
            if not isinstance(ref, str) or not ref.startswith("#/") or ref in seen:
                raise ValueError("Invalid or duplicate patch pointer: " + str(ref))
            seen.add(ref)
            parent_ref, token = ref.rsplit("/", 1)
            parent = pointer(spec, parent_ref)
            token = urllib.parse.unquote(token).replace("~1", "/").replace("~0", "~")
            context = operation["context"]
            if not isinstance(parent, dict) or not isinstance(context, dict) or not context:
                raise ValueError("Patch requires an object parent and nonempty context: " + ref)
            for key, expected in context.items():
                if key not in parent or canonical(parent[key]) != canonical(expected):
                    raise ValueError("Patch context changed; review recipe: " + ref)
            # JSON comparison distinguishes false from 0 and preserves types.
            if token not in parent or canonical(parent[token]) != canonical(operation["from"]):
                raise ValueError("Patch source value changed; review recipe: " + ref)
            if removing:
                del parent[token]
            else:
                parent[token] = copy.deepcopy(operation["value"])
        transformations.append("Applied " + filename + " (SHA-256 " + sha256(recipe_raw)
                               + "): " + recipe["description"])
    return spec, transformations


def audit(source, base, cache):
    result = {"id": source["id"], "target": source["target"], "checked_at": now(),
              "source_health": source.get("source_health", "not_assessed"),
              "coverage": "Configured service only; freshness of the whole provider is not established."}
    try:
        raw, metadata = fetch(source)
        result.update(fetch=metadata, last_successful_fetch=metadata["fetched_at"])
        cache_snapshot(cache, source["id"], raw, metadata)
        spec, transformations = prepare_document(source, raw, metadata, cache)
        metadata["transformations"] = transformations
        cache_snapshot(cache, source["id"], raw, metadata)
        dest = str(destination(source, spec))
        # Once a new version lands, compare that version rather than forever
        # comparing the old manifest target and generating duplicate updates.
        old = stored(dest, base) or stored(source["target"], base)
        result.update(compare(old, spec), fetch=metadata, destination=dest)
        result["last_successful_comparison"] = now()
        result["validation_errors"] = validate_document(spec)
        if not result["validation_errors"]:
            result["last_successful_validation"] = now()
        if source.get("import_blocker"):
            result["import_blocker"] = source["import_blocker"]
    except Exception as error:
        result.update(status="failed", error=str(error))
    return result


def write_report(path, results, base):
    previous = {}
    if path.exists():
        previous = {row["id"]: row for row in json.loads(path.read_text()).get("sources", [])}
    for result in results:
        for field in ("last_successful_fetch", "last_successful_comparison", "last_successful_validation"):
            if field not in result and field in previous.get(result["id"], {}):
                result[field] = previous[result["id"]][field]
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**previous, **{row["id"]: row for row in results}}
    path.write_text(json.dumps({"generated_at": now(), "base": base,
                               "base_revision": git("rev-parse", base).decode().strip(),
                               "sources": list(merged.values())}, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "import"))
    parser.add_argument("--source", action="append", help="Manifest ID; repeat to select sources")
    parser.add_argument("--manifest", type=Path, default=ROOT / "maintenance/sources.json")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--cache", type=Path, default=ROOT / "cache/maintenance")
    parser.add_argument("--report", type=Path, default=ROOT / "cache/maintenance/report.json")
    args = parser.parse_args(argv)
    sources = load_sources(args.manifest)
    if args.source:
        unknown = set(args.source) - {source["id"] for source in sources}
        if unknown:
            parser.error("Unknown source IDs: " + ", ".join(sorted(unknown)))
        sources = [source for source in sources if source["id"] in args.source]
    if args.command == "import":
        if len(sources) != 1:
            parser.error("Import exactly one source at a time using --source")
        source = sources[0]
        raw, metadata = fetch(source)
        cache_snapshot(args.cache, source["id"], raw, metadata)
        spec, transformations = prepare_document(source, raw, metadata, args.cache)
        metadata["transformations"] = transformations
        cache_snapshot(args.cache, source["id"], raw, metadata)
        dest = destination(source, spec)
        old_dest = stored(str(dest), args.base)
        old = old_dest or stored(source["target"], args.base)
        if old_dest and compare(old_dest, spec)["status"] == "matches_source":
            print("Already matches the source; no file written.")
            return 0
        output = ROOT / dest
        if output.exists():
            expected = git("show", args.base + ":" + str(dest)) if old_dest else None
            if expected != output.read_bytes():
                raise ValueError("Refusing to overwrite local changes: " + str(dest))
        result = import_document(source, spec, metadata, old)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(yaml.dump(result, Dumper=Dumper, default_flow_style=False,
                                    sort_keys=False, allow_unicode=True, width=100000))
        print(str(dest))
        print(json.dumps(compare(old, spec), indent=2))
        return 0
    results = [audit(source, args.base, args.cache) for source in sources]
    write_report(args.report, results, args.base)
    for result in results:
        print(result["id"] + ": " + result["status"] +
              ("; import blocked" if result.get("import_blocker") or result.get("validation_errors") else ""))
    print("Report: " + str(args.report))
    return 1 if any(row["status"] == "failed" or row.get("validation_errors") or row.get("import_blocker") for row in results) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
