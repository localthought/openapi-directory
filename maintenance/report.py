"""Readable audit results, preserving failed attempts and per-service check dates."""
import html
import re


def text(value):
    value = "Not recorded" if value is None else str(value)
    value = re.sub(r"\s+", " ", value).strip()
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def state(row):
    if row.get("status") == "failed":
        return "Fetch/prepare failed"
    if row.get("import_blocker") or row.get("validation_errors") or row.get("source_health_issue"):
        return "Import blocked"
    return {"matches_source": "Matches configured source", "changed": "Content changed",
            "missing": "Missing API"}.get(row.get("status"), "Not assessed")


def description(stats):
    if not stats:
        return "Not recorded"
    return (str(stats.get("version", "?")) + "; " + str(stats.get("paths", "?"))
            + " paths / " + str(stats.get("operations", "?")) + " operations")


def render(document):
    rows = document["sources"]
    states = [state(row) for row in rows]
    lines = ["# Official-source audit", "",
             "Report generated: " + text(document["generated_at"]) + ".",
             "Latest run base: " + text(document["base"]) + " at " + text(document["base_revision"]) + ".", "",
             str(len(rows)) + " recorded artifacts: " + str(states.count("Matches configured source"))
             + " source matches; " + str(states.count("Content changed")) + " changed; "
             + str(states.count("Missing API")) + " missing; " + str(states.count("Import blocked"))
             + " blocked; " + str(states.count("Fetch/prepare failed")) + " failed; "
             + str(states.count("Not assessed")) + " unassessed.", "",
             "Coverage is limited to configured services. A source match does not establish current vendor-wide coverage. "
             "Repository availability does not establish artifact maintenance or vendor ownership. "
             "Archived, failed or unassessed source health remains a separate finding. Subset runs retain older rows and dates; "
             "failed attempts do not advance successful-check timestamps.", "",
             "| Service | Result | Stored | Source | Last attempt | Last successful validation | Source health |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        cells = [row["id"], state(row), description(row.get("stored")), description(row.get("source")),
                 row.get("checked_at"), row.get("last_successful_validation"), row.get("source_health")]
        lines.append("| " + " | ".join(text(cell) for cell in cells) + " |")
    for row in rows:
        fetch = row.get("fetch", {})
        health = row.get("source_health_check", {})
        lines.extend(["", "## " + text(row["id"]), "",
                      "- Target: " + text(row.get("destination", row.get("target"))),
                      "- Comparison/curation baseline: " + text(row.get("baseline")),
                      "- Comparison base revision: " + text(row.get("base_revision")),
                      "- API coverage: " + text(row.get("coverage")),
                      "- Source: " + text(fetch.get("url")),
                      "- Source revision: " + text(fetch.get("revision")),
                      "- Entry SHA-256: " + text(fetch.get("sha256")),
                      "- Last successful fetch: " + text(row.get("last_successful_fetch")),
                      "- Last successful comparison: " + text(row.get("last_successful_comparison")),
                      "- Source-health scope: " + text(health.get("scope")),
                      "- Last source-health attempt: " + text(health.get("checked_at")),
                      "- Last successful source-health check: " + text(row.get("last_successful_source_health_check")),
                      "- Observed repository: " + text(health.get("full_name")),
                      "- Repository last push (not artifact freshness): " + text(health.get("pushed_at")),
                      "- Repository metadata URL: " + text(health.get("url")),
                      "- Repository metadata SHA-256: " + text(health.get("sha256")),
                      "- Repository metadata snapshot: " + text(health.get("snapshot")),
                      "- Pending PR: " + text(row.get("pending_pr"))])
        if row.get("declared_source_health"):
            lines.append("- Manifest source-health note: " + text(row["declared_source_health"]))
        for kind in ("paths", "operations"):
            added, removed = row.get("added_" + kind), row.get("removed_" + kind)
            if added is not None and removed is not None:
                lines.append("- " + kind.title() + ": " + str(len(added)) + " added / " + str(len(removed)) + " removed.")
                for label, changes in (("Added", added), ("Removed", removed)):
                    if changes:
                        lines.append("  - " + label + ": " + "; ".join(text(change) for change in changes))
        for problem in ([row.get("error"), row.get("import_blocker"), row.get("source_health_issue")] + row.get("validation_errors", [])):
            if problem:
                lines.append("- Blocker/error: " + text(problem))
        for step in fetch.get("transformations", []):
            lines.append("- Transformation: " + text(step))
    return "\n".join(lines) + "\n"
