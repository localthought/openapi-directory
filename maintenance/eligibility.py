"""Shared hold classes for unattended or explicit generated-draft writes.

The same content rules protect explicit pending-draft refreshes (refresh_pr.py)
and the scheduled-publication runner (scheduled_publish.py). A None result means
"no hold class applies"; it never authorizes a merge or skips human review.
"""
import update


def content_hold(old, new, comparison):
    """Return a reason string when a change needs deliberate human reconciliation."""
    if old is None:
        return "Initial import of a new artifact requires deliberate review"
    if (comparison["stored"]["version"] != comparison["source"]["version"]
            or comparison["removed_paths"] or comparison["removed_operations"]):
        return "Version change or endpoint removal requires deliberate reconciliation"
    for spec in (old, new):
        if not isinstance(spec.get("components", {}), dict):
            return "Unverifiable security/schema content"
    if (old.get("servers") != new.get("servers") or old.get("security") != new.get("security")
            or old.get("components", {}).get("securitySchemes") != new.get("components", {}).get("securitySchemes")):
        return "Server or authentication change requires deliberate reconciliation"
    if set(old.get("components", {}).get("schemas", {})) - set(new.get("components", {}).get("schemas", {})):
        return "Schema removal requires deliberate reconciliation"
    if (old.get("webhooks") != new.get("webhooks")
            or old.get("components", {}).get("callbacks") != new.get("components", {}).get("callbacks")):
        return "Callback/webhook change requires deliberate reconciliation"
    for path in old["paths"]:
        a, b = update.dereference(old, old["paths"][path]), update.dereference(new, new["paths"][path])
        if a.get("servers") != b.get("servers"):
            return "Path server change requires deliberate reconciliation"
        for method in update.METHODS & a.keys():
            if a[method].get("callbacks") != b[method].get("callbacks"):
                return "Operation callback change requires deliberate reconciliation"
            if a[method].get("security") != b[method].get("security") or a[method].get("servers") != b[method].get("servers"):
                return "Operation authentication/server change requires deliberate reconciliation"
    return None
