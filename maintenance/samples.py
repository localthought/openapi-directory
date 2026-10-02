"""Materialize explicitly configured Fern code samples as text, never as schemas."""
import hashlib
import json
import posixpath
import re
import urllib.parse
from pathlib import Path

import bundle

METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def prepare(source, spec, raw, metadata, cache, request):
    config = source["code_samples"]
    if (set(config) != {"kind", "root", "extensions"} or config["kind"] != "fern"
            or not isinstance(config["extensions"], list) or not config["extensions"]
            or any(not re.fullmatch(r"\.[a-z]+", x) for x in config["extensions"])):
        raise ValueError("Code samples require an explicit Fern root and file extensions")
    github = source.get("github")
    if not github or not re.fullmatch(r"[0-9a-f]{40}", metadata.get("revision", "")):
        raise ValueError("Code samples require a pinned GitHub revision")
    root = bundle.relative_path(config["root"])
    entry = bundle.relative_path(github["path"])
    replacements = []
    # These are documentation artifacts. Do not traverse arbitrary examples,
    # schemas, or extension payloads that might contain literal $ref keys.
    for item in spec["paths"].values():
        for method, operation in item.items():
            if method not in METHODS or not isinstance(operation, dict):
                continue
            for example in operation.get("x-fern-examples", []):
                for sample in example.get("code-samples", []):
                    code = sample.get("code")
                    if not isinstance(code, dict) or "$ref" not in code:
                        continue
                    if set(code) != {"$ref"} or not isinstance(code["$ref"], str):
                        raise ValueError("Referenced code must contain only a string $ref")
                    ref = code["$ref"]
                    parts = urllib.parse.urlsplit(ref)
                    if (parts.scheme or parts.netloc or parts.query or parts.fragment
                            or "%" in ref or parts.path.startswith("/")):
                        raise ValueError("Code sample references must be plain relative file paths")
                    path = bundle.relative_path(posixpath.join(posixpath.dirname(entry), parts.path))
                    if not path.startswith(root + "/") or Path(path).suffix not in config["extensions"]:
                        raise ValueError("Code sample reference is outside the configured root/extensions: " + ref)
                    replacements.append((sample, path))
    paths = sorted({path for _, path in replacements})
    if not paths or len(replacements) > 100:
        raise ValueError("Expected between 1 and 100 referenced code samples; review recipe")
    files = {entry: raw}
    fetches = {}
    for path in paths:
        url = ("https://raw.githubusercontent.com/" + github["repository"] + "/"
               + metadata["revision"] + "/" + urllib.parse.quote(path, safe="/"))
        content, fetch_metadata = request(url)
        if len(content) > 1000000:
            raise ValueError("Code sample exceeds 1 MB: " + path)
        # Decode strictly and preserve whitespace; never execute vendor code.
        content.decode("utf-8")
        files[path] = content
        fetches[path] = {**fetch_metadata, "sha256": sha256(content)}
    if sum(map(len, files.values())) > 10000000:
        raise ValueError("Code sample snapshot exceeds 10 MB")
    hashes = {path: sha256(content) for path, content in sorted(files.items())}
    snapshot = sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())
    workspace = cache / source["id"] / snapshot
    for path, content in files.items():
        target = workspace / "repository" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    (workspace / "source-files.json").write_text(json.dumps(hashes, indent=2) + "\n")
    metadata.update(snapshot_sha256=snapshot, code_samples={
        "kind": "fern", "files": fetches, "references": len(replacements)})
    for sample, path in replacements:
        sample["code"] = files[path].decode("utf-8")
    return ("Materialized " + str(len(replacements)) + " Fern code-sample references from "
            + str(len(paths)) + " UTF-8 files at the same vendor commit as the entry document; "
            + "preserved their text without executing it or treating it as schemas. "
            + "Source snapshot SHA-256 " + snapshot + ".")
