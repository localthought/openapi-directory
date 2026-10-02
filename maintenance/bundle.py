"""Build standalone OADs from a pinned vendor repository without running vendor code."""

import hashlib
import io
import json
import os
import posixpath
import re
import subprocess
import tarfile
import urllib.parse
from pathlib import Path

import yaml

TOOL_VERSION = "2.57.0"
HERE = Path(__file__).resolve().parent


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def relative_path(path):
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        raise ValueError("Invalid repository path")
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        raise ValueError("Repository path escapes the snapshot")
    return normalized


def snapshot_files(archive, root):
    """Select plain data files, rejecting links and unsafe archive member names."""
    root = relative_path(root)
    files = {}
    total = 0
    prefix = None
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for index, member in enumerate(tar):
            if index >= 20000:
                raise ValueError("Repository archive has too many members")
            name = relative_path(member.name)
            folder, _, path = name.partition("/")
            if prefix is None:
                prefix = folder
            if folder != prefix:
                raise ValueError("Repository archive has multiple roots")
            if not path or member.isdir():
                continue
            if root != "." and not path.startswith(root + "/"):
                continue
            if not member.isfile():
                raise ValueError("Repository snapshot contains a link or special file: " + path)
            if Path(path).suffix.lower() not in {".yaml", ".yml", ".json"}:
                continue
            total += member.size
            if member.size > 20000000 or total > 100000000:
                raise ValueError("Repository snapshot exceeds data size limits")
            if path in files:
                raise ValueError("Duplicate repository archive member: " + path)
            files[path] = tar.extractfile(member).read()
    return files


def refs(value):
    # This preflight is conservative: unknown extension refs are not silently
    # handed to a tool that could fetch unpinned remote content.
    if isinstance(value, dict):
        if "$ref" in value:
            if not isinstance(value["$ref"], str):
                raise ValueError("Non-string reference")
            yield value["$ref"]
        for child in value.values():
            yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def reference_graph(files, entry, loader):
    entry = relative_path(entry)
    pending = [entry]
    reachable = {}
    while pending:
        path = pending.pop()
        if path in reachable:
            continue
        if path not in files:
            raise ValueError("Referenced file missing from pinned snapshot: " + path)
        raw = files[path]
        reachable[path] = raw
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = yaml.load(raw, Loader=loader)
        for ref in refs(value):
            parts = urllib.parse.urlsplit(ref)
            if parts.scheme or parts.netloc or parts.query:
                raise ValueError("Unpinned remote or query reference: " + ref)
            if parts.path:
                child = urllib.parse.unquote(parts.path)
                if child.startswith("/") or "\\" in child:
                    raise ValueError("Absolute reference: " + ref)
                target = relative_path(posixpath.join(posixpath.dirname(path), child))
                pending.append(target)
    return reachable


def run_bundle(workspace, entry):
    package = HERE / "node_modules/@redocly/cli/package.json"
    if not package.exists():
        raise ValueError("Install the pinned bundler with npm ci --prefix maintenance --ignore-scripts")
    if json.loads(package.read_text())["version"] != TOOL_VERSION:
        raise ValueError("Installed Redocly version does not match the pinned recipe")
    output = workspace / "bundled.json"
    command = ["node", str(HERE / "node_modules/@redocly/cli/bin/cli.js"), "bundle",
               str(workspace / "repository" / entry), "--output", str(output),
               "--config", str(HERE / "redocly.yaml"),
               "--component-renaming-conflicts-severity", "warn"]
    env = {**os.environ, "REDOCLY_TELEMETRY": "off", "NO_COLOR": "1"}
    result = subprocess.run(command, cwd=workspace, env=env, capture_output=True,
                            text=True, timeout=180)
    log = result.stdout + result.stderr
    (workspace / "bundler.log").write_text(log)
    if result.returncode:
        raise ValueError("Reference bundling failed: " + log[-4000:])
    warnings = len(re.findall(r"\bwarning\b", log, flags=re.IGNORECASE))
    return output.read_bytes(), warnings


def prepare(source, raw, metadata, cache, request, loader):
    config = source["bundling"]
    if config.get("tool") != "redocly" or config.get("version") != TOOL_VERSION:
        raise ValueError("Unsupported bundling recipe")
    github = source.get("github")
    revision = metadata.get("revision", "")
    if not github or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Reference bundling requires a pinned GitHub source")
    url = "https://codeload.github.com/" + github["repository"] + "/tar.gz/" + revision
    archive, _ = request(url)
    if len(archive) > 60000000:
        raise ValueError("Repository archive is too large")
    files = snapshot_files(archive, config["root"])
    entry = relative_path(github["path"])
    if files.get(entry) != raw:
        raise ValueError("Archive entry differs from the independently fetched pinned source")
    graph = reference_graph(files, entry, loader)
    hashes = {path: digest(content) for path, content in sorted(graph.items())}
    snapshot_hash = digest(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode())
    workspace = (cache / source["id"] / snapshot_hash).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "repository.tar.gz").write_bytes(archive)
    (workspace / "source-files.json").write_text(json.dumps(hashes, indent=2) + "\n")
    for path, content in graph.items():
        output = workspace / "repository" / path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
    bundled, warnings = run_bundle(workspace, entry)
    if warnings != config.get("expected_warnings", 0):
        raise ValueError("Bundler warning count changed; review bundler.log before updating the recipe")
    metadata.update(snapshot_sha256=snapshot_hash, bundled_sha256=digest(bundled),
                    bundling={"tool": "@redocly/cli", "version": TOOL_VERSION,
                              "warnings": warnings, "archive_url": url,
                              "archive_sha256": digest(archive), "files": hashes})
    step = ("Bundled " + str(len(graph)) + " pinned repository files with @redocly/cli "
            + TOOL_VERSION + ", using bundle and an empty configuration; distinct components with conflicting basenames are renamed, not merged; "
            + str(warnings) + " warnings. Source-file snapshot SHA-256 " + snapshot_hash + ".")
    return bundled, step
