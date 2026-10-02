"""Select releases only for reviewed vendor catalogs of numeric version directories."""
import json
import hashlib
import re
import urllib.parse
from pathlib import PurePosixPath


def numeric_version(value):
    # Canonical components avoid aliases such as 2.016 and exclude prereleases.
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value):
        raise ValueError("Release versions must be canonical major.minor numbers")
    return tuple(int(part) for part in value.split("."))


def safe_path(value):
    if (not isinstance(value, str) or not value or value.startswith("/")
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or any(char in value for char in "\\?#{}")):
        raise ValueError("Release catalog paths must be safe repository-relative paths")
    return value


def select(config, revision, request):
    recipe = config["release_catalog"]
    if recipe.get("kind") != "numeric-directories":
        raise ValueError("Unsupported release catalog recipe")
    directory = safe_path(recipe["directory"])
    filename = safe_path(recipe["filename"])
    minimum = numeric_version(recipe["minimum_version"])
    url = ("https://api.github.com/repos/" + config["repository"] + "/contents/"
           + urllib.parse.quote(directory, safe="/") + "?ref=" + revision)
    raw, _ = request(url)
    entries = json.loads(raw)
    if not isinstance(entries, list) or len(entries) >= 1000:
        raise ValueError("Invalid or potentially truncated release catalog")
    candidates = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid release catalog entry")
        if entry.get("type") != "dir":
            continue
        name = entry.get("name")
        try:
            version = numeric_version(name)
        except ValueError:
            continue
        if entry.get("path") != str(PurePosixPath(directory) / name) or name in candidates:
            raise ValueError("Inconsistent release catalog directory")
        if version >= minimum:
            candidates[name] = version
    if not candidates:
        raise ValueError("No release at or above the reviewed minimum version")
    selected = max(candidates, key=candidates.get)
    path = str(PurePosixPath(directory) / selected / filename)
    # Retain the exact catalog response alongside the selected source for replay.
    return path, {"url": url, "response_text": raw.decode("utf-8"),
                  "sha256": hashlib.sha256(raw).hexdigest(), "selected_version": selected,
                  "selected_path": path, "minimum_version": recipe["minimum_version"]}
