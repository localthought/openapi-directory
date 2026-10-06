#!/usr/bin/env python3
"""Read-only, bounded discovery of OpenAPI candidates in reviewed vendor repositories."""
import argparse
import fnmatch
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import health
import report
import update
import yaml

FIELDS = {"id", "provider", "repository", "ref", "patterns", "context_paths", "max_candidates",
          "max_blob_bytes", "ownership_evidence", "review_scope"}
EXTENSIONS = {".json", ".yaml", ".yml", ".jsonc"}


def safe_path(path):
    return (isinstance(path, str) and bool(path) and not path.startswith("/")
            and "\\" not in path and not any(ord(c) < 32 for c in path)
            and all(p not in {"", ".", ".."} for p in path.split("/")))


def load_config(path):
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or set(config) != {"schema_version", "repositories"} or config["schema_version"] != 1:
        raise ValueError("Unsupported discovery manifest")
    entries = config["repositories"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("Discovery requires reviewed repository entries")
    ids, repos = set(), set()
    for item in entries:
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError("Discovery entry fields differ from the reviewed schema")
        if not isinstance(item["id"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", item["id"]) or item["id"] in ids:
            raise ValueError("Invalid or duplicate discovery ID")
        ids.add(item["id"])
        repo = item["repository"]
        if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not safe_path(repo) or repo.casefold() in repos:
            raise ValueError("Invalid or duplicate discovery repository")
        repos.add(repo.casefold())
        if not isinstance(item["provider"], str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", item["provider"]) or ".." in item["provider"]:
            raise ValueError("Invalid provider domain")
        for field in ("ref", "ownership_evidence", "review_scope"):
            if not isinstance(item[field], str) or not item[field].strip():
                raise ValueError("Missing reviewed discovery " + field)
        for field in ("patterns", "context_paths"):
            if not isinstance(item[field], list) or (field == "patterns" and not item[field]) or any(not safe_path(p) for p in item[field]):
                raise ValueError("Unsafe discovery " + field)
        for field, ceiling in (("max_candidates", 128), ("max_blob_bytes", 10000000)):
            if type(item[field]) is not int or not 0 < item[field] <= ceiling:
                raise ValueError("Discovery limit outside reviewed bounds: " + field)
    return entries


def fingerprint(value):
    return update.sha256(update.canonical(value).encode())


def snapshot(cache, label, raw, metadata, clock):
    digest = update.sha256(raw)
    path = cache / label / digest
    path.mkdir(parents=True, exist_ok=True)
    (path / "source").write_bytes(raw)
    evidence = {**metadata, "sha256": digest, "fetched_at": clock(), "snapshot": str(path)}
    (path / "fetch.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value)


def blob(entry, item, revision, request, cache, clock):
    path = item["path"]
    if not safe_path(path) or item.get("mode") not in {"100644", "100755"}:
        raise ValueError("Unsupported or unsafe repository blob: " + str(path))
    if type(item.get("size")) is not int or not 0 <= item["size"] <= entry["max_blob_bytes"] or not sha(item.get("sha")):
        raise ValueError("Blob size/hash outside reviewed bounds: " + path)
    url = "https://raw.githubusercontent.com/" + entry["repository"] + "/" + revision + "/" + quote(path, safe="/")
    raw, metadata = request(url)
    evidence = snapshot(cache, "blobs", raw, metadata, clock)
    if len(raw) > entry["max_blob_bytes"] or len(raw) != item["size"]:
        raise ValueError("Fetched blob size differs from pinned tree: " + path)
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != item["sha"]:
        raise ValueError("Fetched bytes differ from pinned Git blob: " + path)
    return raw, {**evidence, "source_url": url, "git_blob_sha": actual}


def inventory(base, entries):
    revision = update.git("rev-parse", base).decode().strip()
    paths = update.git("ls-tree", "-r", "--name-only", revision, "APIs").decode().splitlines()
    providers = {e["provider"] for e in entries}
    specs, errors = [], []
    for path in paths:
        if path.split("/")[1] not in providers or not path.endswith(("/openapi.yaml", "/swagger.yaml")):
            continue
        try:
            specs.append((path, update.parse(update.git("show", revision + ":" + path))))
        except Exception as error:
            errors.append({"path": path, "error": str(error)[:1000]})
    manifest = json.loads(update.git("show", revision + ":maintenance/sources.json"))
    return revision, paths, specs, errors, manifest["sources"]


def scan(entry, registered, stored, request, clock, cache, checker):
    row = {"id": entry["id"], "provider": entry["provider"], "repository": entry["repository"],
           "config_sha256": fingerprint(entry), "checked_at": clock(), "status": "failed",
           "patterns": entry["patterns"], "ownership_evidence": entry["ownership_evidence"],
           "review_scope": entry["review_scope"], "artifacts": [], "contexts": [], "errors": []}
    row.update(checker.check({"github": {"repository": entry["repository"]}}))
    if row.get("source_health_issue"):
        row["errors"].append(row["source_health_issue"])
        return row
    try:
        root = "https://api.github.com/repos/" + entry["repository"]
        raw, metadata = request(root + "/commits/" + quote(entry["ref"], safe=""))
        row["commit_fetch"] = snapshot(cache, "commits", raw, metadata, clock)
        commit = json.loads(raw)
        revision, tree_sha = commit["sha"], commit["commit"]["tree"]["sha"]
        if not sha(revision) or not sha(tree_sha):
            raise ValueError("Invalid pinned revision/tree identity")
        row["revision"] = revision
        raw, metadata = request(root + "/git/trees/" + tree_sha + "?recursive=1")
        row["tree_fetch"] = snapshot(cache, "trees", raw, metadata, clock)
        tree = json.loads(raw)
        if tree.get("truncated") is not False or tree.get("sha") != tree_sha or not isinstance(tree.get("tree"), list):
            raise ValueError("Incomplete or mismatched pinned repository tree; no absence inference")
        row["submodule_paths_not_scanned"] = [item.get("path") for item in tree["tree"]
                                             if item.get("type") == "commit"]
        blobs = {}
        for item in tree["tree"]:
            if item.get("type") != "blob":
                continue
            path = item.get("path")
            if not safe_path(path) or path in blobs:
                raise ValueError("Unsafe or duplicate repository tree path")
            blobs[path] = item
        paths = sorted(p for p in blobs if PurePosixPath(p).suffix.lower() in EXTENSIONS
                       and any(fnmatch.fnmatchcase(p.lower(), pattern.lower()) for pattern in entry["patterns"]))
        row.update(tree_blob_count=len(blobs), selected_path_count=len(paths))
        if len(paths) > entry["max_candidates"]:
            raise ValueError("Candidate limit exceeded; review bounds before scanning, no partial absence claim")
        for path in entry["context_paths"]:
            if path not in blobs:
                row["contexts"].append({"path": path, "status": "missing_at_revision"})
            else:
                _, evidence = blob(entry, blobs[path], revision, request, cache, clock)
                row["contexts"].append({"path": path, "status": "fetched", **evidence})
        for path in paths:
            item = {"path": path}
            row["artifacts"].append(item)
            ids = sorted(s["id"] for s in registered if s.get("github", {}).get("repository", "").casefold() == entry["repository"].casefold()
                         and s["github"].get("path") == path)
            if ids:
                item.update(status="already_registered", registered_ids=ids,
                            note="Artifact not fetched; use the freshness updater for these services.")
                continue
            try:
                raw, evidence = blob(entry, blobs[path], revision, request, cache, clock)
                item.update(evidence)
                value = yaml.load(raw, Loader=update.Loader)
                if not isinstance(value, dict) or not ("openapi" in value or "swagger" in value):
                    item["status"] = "not_openapi"
                    continue
                spec = update.parse(raw)
                item.update(status="review_candidate", stats=update.stats(spec),
                            content_sha256=fingerprint(update.comparison_content(spec)),
                            endpoint_shape_sha256=fingerprint(sorted(update.operation_set(spec))),
                            validation_errors=update.validate_document(spec),
                            lifecycle="Not reviewed; public repository is not a stable-release guarantee.")
                item["external_refs"] = sorted({r.split("#")[0] for r in update.reference_objects(spec) if not r.startswith("#")})
                identical, shapes = [], []
                for stored_path, old in stored:
                    if stored_path.split("/")[1] != entry["provider"]:
                        continue
                    if update.compare(old, spec)["status"] == "matches_source":
                        identical.append(stored_path)
                    if update.operation_set(old) == update.operation_set(spec):
                        shapes.append(stored_path)
                item["same_endpoint_shape_as"] = shapes
                if identical:
                    item.update(status="already_stored", stored_paths=identical)
            except Exception as error:
                item.update(status="inspection_failed", error=str(error)[:1500])
                row["errors"].append(path + ": " + item["error"])
        row["status"] = "partial" if row["errors"] else "scanned"
        if row["status"] == "scanned":
            row["last_successful_scan"] = clock()
    except Exception as error:
        row["errors"].append(str(error)[:1500])
    return row


def queue(rows):
    groups = {}
    for row in rows:
        for artifact in row["artifacts"]:
            if artifact["status"] != "review_candidate":
                continue
            key = (row["provider"], artifact["content_sha256"])
            evidence = {"repository": row["repository"], "revision": row["revision"],
                        "path": artifact["path"], "source_url": artifact["source_url"],
                        "sha256": artifact["sha256"], "snapshot": artifact["snapshot"],
                        "ownership_evidence": row["ownership_evidence"]}
            if key not in groups:
                groups[key] = {"provider": row["provider"], "content_sha256": artifact["content_sha256"],
                               "endpoint_shape_sha256": artifact["endpoint_shape_sha256"],
                               "stats": artifact["stats"], "validation_errors": artifact["validation_errors"],
                               "external_refs": artifact["external_refs"], "same_endpoint_shape_as": artifact["same_endpoint_shape_as"],
                               "review_scope": row["review_scope"], "lifecycle": artifact["lifecycle"], "sources": []}
            groups[key]["sources"].append(evidence)
    candidates = list(groups.values())
    for candidate in candidates:
        candidate["same_endpoint_shape_candidates"] = [
            {"content_sha256": other["content_sha256"],
             "source_urls": [s["source_url"] for s in other["sources"]]}
            for other in candidates if other is not candidate
            and (other["provider"], other["endpoint_shape_sha256"])
            == (candidate["provider"], candidate["endpoint_shape_sha256"])]
    return candidates


def render(document):
    lines = ["# Official-repository discovery", "", "Generated: " + report.text(document["generated_at"]),
             "Base: " + report.text(document["base_revision"]), "",
             "Bounded configured repositories/patterns only. Candidate discovery is not import approval, "
             "stable lifecycle assessment, freshness auditing or proof of absence elsewhere. "
             "Identical parsed descriptions are grouped; matching endpoint shapes still need purpose/scope review.", "",
             "| Repository | Scan | Selected files | Last successful scan | Review candidates |", "| --- | --- | --- | --- | --- |"]
    for row in document["repositories"]:
        lines.append("| " + " | ".join(report.text(v) for v in (row["repository"], row["status"], row.get("selected_path_count"),
                     row.get("last_successful_scan"), sum(a["status"] == "review_candidate" for a in row["artifacts"]))) + " |")
    for row in document["repositories"]:
        for error in row["errors"]:
            lines.extend(["", report.text(row["repository"] + ": " + error)])
        for path in row.get("submodule_paths_not_scanned", []):
            lines.extend(["", "Submodule contents not scanned: " + report.text(path)])
    for error in document["inventory_errors"]:
        lines.extend(["", "Inventory error: " + report.text(error)])
    lines.extend(["", "## Deduplicated review queue", "", str(len(document["queue"])) + " candidate groups; no API files or PRs written."])
    for candidate in document["queue"]:
        lines.extend(["", "### " + report.text(candidate["provider"] + " / " + candidate["sources"][0]["path"]), "",
                      report.text(report.description(candidate["stats"])), "", report.text(candidate["review_scope"]), "",
                      report.text(candidate["lifecycle"])])
        for source in candidate["sources"]:
            lines.append("- [Pinned source](" + source["source_url"] + ") — " + report.text(source["sha256"]))
            lines.append("  Ownership evidence: " + report.text(source["ownership_evidence"]))
        for error in candidate["validation_errors"]:
            lines.append("- Validation obstacle: " + report.text(error))
        for path in candidate["same_endpoint_shape_as"]:
            lines.append("- Same endpoint shape, review scope/content: " + report.text(path))
        for other in candidate["same_endpoint_shape_candidates"]:
            for url in other["source_urls"]:
                lines.append("- [Another candidate with the same endpoint shape](" + url + "); review purpose/content before grouping.")
    lines.extend(["", "## Unresolved publication leads", ""])
    for row in document["repositories"]:
        if not any(a["status"] in {"review_candidate", "already_registered", "already_stored"} for a in row["artifacts"]):
            lines.extend(["- " + report.text(row["repository"] + ": " + row["review_scope"]),
                          "  Ownership evidence: " + report.text(row["ownership_evidence"]),
                          "  Scan result: " + report.text(row["status"])])
            for context in row["contexts"]:
                if context["status"] == "fetched":
                    lines.append("  [Pinned publication input: " + report.text(context["path"]) + "](" + context["source_url"] + ")")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=update.ROOT / "maintenance/discovery.json")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--cache", type=Path, default=update.ROOT / "cache/maintenance/discovery/monthly")
    parser.add_argument("--report", type=Path, default=update.ROOT / "cache/maintenance/discovery-report.json")
    args = parser.parse_args(argv)
    entries = load_config(args.config)
    revision, paths, specs, errors, registered = inventory(args.base, entries)
    previous = json.loads(args.report.read_text()) if args.report.exists() else {}
    checker = health.Checker(update.request, update.now, args.cache)
    rows = [scan(e, registered, specs, update.request, update.now, args.cache / e["id"], checker) for e in entries]
    for row in rows:
        if "last_successful_scan" not in row:
            old = next((r for r in previous.get("repositories", []) if r["id"] == row["id"] and r.get("config_sha256") == row["config_sha256"]), {})
            if old.get("last_successful_scan"):
                row["last_successful_scan"] = old["last_successful_scan"]
                row["successful_scan_retained_from_previous_report"] = True
    document = {"schema_version": 1, "generated_at": update.now(), "base_revision": revision,
                "config_sha256": update.sha256(args.config.read_bytes()), "api_file_count": len(paths),
                "inventory_errors": errors, "repositories": rows, "queue": queue(rows)}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(document, indent=2) + "\n").encode()
    args.report.write_bytes(raw)
    args.report.with_suffix(".md").write_text(render(document))
    snapshot(args.cache, "reports", raw, {"base_revision": revision}, update.now)
    print(str(len(document["queue"])) + " review candidates; report " + str(args.report))
    return int(bool(errors) or any(r["status"] != "scanned" for r in rows))


if __name__ == "__main__":
    raise SystemExit(main())
