#!/usr/bin/env python3
"""Generate the readable Moneybird record subset from the official OpenAPI spec.

This is deliberately data driven: routes and schemas are copied from the source
spec, while the classification rules below only decide which GET operations are
primary list/detail records for an importer.
"""
from __future__ import annotations

import copy
import json
import re
import argparse
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "v2" / "openapi.yaml"
OUT = HERE / "openapi.yaml"
MANIFEST = HERE / "coverage.json"
COLLECTIONS = HERE / "collections.json"

PRIMARY_LIST_NAMES = {
    "administrations", "assets", "contacts", "custom_fields", "document_styles",
    "general_documents", "general_journal_documents", "purchase_invoices",
    "receipts", "typeless_documents", "estimates", "external_sales_invoices",
    "financial_accounts", "financial_mutations", "identities", "ledger_accounts",
    "products", "projects", "purchase_transactions", "recurring_sales_invoices",
    "sales_invoices", "subscription_templates", "subscriptions", "task_lists",
    "task_list_templates", "tax_rates", "time_entries", "users", "verifications",
    "webhooks", "workflows",
}

def normalized_path(path: str) -> str:
    return path.replace("{format}", ".json")

def path_kind(path: str, op_id: str) -> tuple[str, str]:
    p = path.lower()
    if "/synchronization" in p:
        return "sync_helper", "ID/version synchronization endpoint"
    if any(x in p for x in ("/download", "/checkout_identifier", "customer_contact_portal")):
        return "binary_or_helper", "download, portal-link, or checkout helper"
    if "/reports/" in p:
        return "report", "report dataset rather than a primary record collection"
    if p.endswith("/default{format}"):
        return "child_or_singleton", "default singleton endpoint"
    if p.endswith("/payments/{id}{format}") or "/contact_people/" in p or "/additional_charges" in p or "/moneybird_payments_mandate" in p:
        return "child_or_singleton", "child resource or singleton-only endpoint"
    if re.search(r"/(find_by_[^/]+|customer_id)/", p):
        return "lookup_helper", "duplicate lookup for a primary collection"
    # Collection paths have no terminal path parameter; detail paths do.
    if re.search(r"/\{[^}]+\}\{format\}$", path):
        return "primary_detail", "primary record detail endpoint"
    if "/filter{format}" in path:
        return "lookup_helper", "alternate filtered collection endpoint"
    return "primary_list", "primary JSON list collection"

def deref_name(ref: str) -> str | None:
    return ref.rsplit("/", 1)[-1] if isinstance(ref, str) and ref.startswith("#/components/schemas/") else None

def nullable_to_30(node):
    """Convert OpenAPI 3.1 type arrays to valid 3.0 nullable schemas."""
    if isinstance(node, dict):
        out = {k: nullable_to_30(v) for k, v in node.items()}
        typ = out.get("type")
        if isinstance(typ, list):
            nullable = "null" in typ
            branches = [t for t in typ if t != "null"]
            if len(branches) == 1:
                out["type"] = branches[0]
            elif branches:
                out.pop("type", None)
                # OpenAPI 3.0 does not allow a union-valued `type`, and
                # `nullable` on a parent oneOf is not portable across parsers.
                # Carry nullability on every concrete branch instead.
                out["anyOf"] = [{"type": t} for t in branches]
                # OpenAPI 3.0 cannot express a nullable union directly. A
                # dedicated nullable branch avoids oneOf rejecting values
                # that match more than one branch.
                if nullable:
                    out["anyOf"].append({"type": "object", "nullable": True})
            if nullable and len(branches) == 1:
                out["nullable"] = True
        if "examples" in out and "example" not in out and isinstance(out["examples"], list) and out["examples"]:
            out["example"] = out["examples"][0]
        return out
    if isinstance(node, list):
        return [nullable_to_30(x) for x in node]
    return node

def main():
    global SOURCE, OUT, MANIFEST, COLLECTIONS
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--coverage", type=Path, default=MANIFEST)
    parser.add_argument("--collections", type=Path, default=COLLECTIONS)
    args = parser.parse_args()
    SOURCE, OUT, MANIFEST, COLLECTIONS = args.source, args.output, args.coverage, args.collections
    src = yaml.safe_load(SOURCE.read_text())
    routes = []
    output_paths = {}
    imported_routes = {}
    for path, item in src["paths"].items():
        for method, operation in item.items():
            if method.lower() != "get":
                continue
            kind, reason = path_kind(path, operation.get("operationId", ""))
            route = {
                "path": normalized_path(path),
                "method": "GET",
                "operationId": operation.get("operationId"),
                "summary": operation.get("summary"),
                "kind": kind,
                "reason": reason,
                "imported": (path != "/administrations{format}" and (kind in {"primary_list"} or (kind == "child_or_singleton" and "/additional_charges" in path))),
                "route_in_openapi": (path != "/administrations{format}" and (kind in {"primary_list", "primary_detail"} or (kind == "child_or_singleton" and "/additional_charges" in path))),
                "parameters": [p.get("$ref", p.get("name")) for p in operation.get("parameters", [])],
            }
            routes.append(route)
            # Import primary list/detail endpoints. Filtered and lookup routes are
            # retained in the manifest but do not create duplicate importer routes.
            if path == "/administrations{format}":
                continue
            if kind not in {"primary_list", "primary_detail"}:
                # Additional charges are useful child collections and are safe to
                # import when explicitly requesting billed and unbilled charges.
                if kind != "child_or_singleton" or "/additional_charges" not in path:
                    continue
            op = copy.deepcopy(operation)
            op.pop("parameters", None)
            params = []
            for param in operation.get("parameters", []):
                if param.get("$ref", "").endswith("/format"):
                    continue
                p = copy.deepcopy(param)
                if "$ref" not in p:
                    p = nullable_to_30(p)
                params.append(p)
            if params:
                op["parameters"] = params
            # Preserve contact integration identity from v2-readonly.
            if path == "/{administration_id}/contacts{format}":
                op["operationId"] = "get_administration_contacts"
            elif path == "/{administration_id}/contacts/{id}{format}":
                op["operationId"] = "get_administration_contact"
            op = nullable_to_30(op)
            route_path = normalized_path(path)
            if "/contacts/{id}/additional_charges" in route_path:
                route_path = route_path.replace("/contacts/{id}/", "/contacts/{contact_id}/")
                op["parameters"] = [({**p, "name": "contact_id"} if p.get("in") == "path" and p.get("name") == "id" else p) for p in op.get("parameters", [])]
            output_paths[route_path] = {"get": op}
            imported_routes[route_path] = (op, kind)

    # Copy every source schema so nested response objects remain available.
    schemas = nullable_to_30(copy.deepcopy(src["components"]["schemas"]))
    # Existing readonly consumers address the contact schema by this name.
    schemas["contact"] = copy.deepcopy(schemas.get("contact_response", {}))
    for path, item in output_paths.items():
        text = json.dumps(item)
        text = text.replace("#/components/schemas/contact_response", "#/components/schemas/contact")
        output_paths[path] = json.loads(text)

    # Retain non-schema component objects referenced by imported operations
    # (notably the shared 404 response) so every emitted $ref resolves.
    components = {
        key: nullable_to_30(copy.deepcopy(value))
        for key, value in src["components"].items()
        if key not in {"schemas", "parameters"}
    }
    components["schemas"] = schemas
    # Only keep parameter definitions referenced by imported routes.
    params = src["components"].get("parameters", {})
    used = set()
    for route in routes:
        if route["kind"] in {"primary_list", "primary_detail"}:
            for ref in route["parameters"]:
                if isinstance(ref, str) and ref.startswith("#/components/parameters/"):
                    used.add(ref.rsplit("/", 1)[-1])
    components["parameters"] = {k: nullable_to_30(copy.deepcopy(v)) for k, v in params.items() if k in used and k != "format"}
    components["securitySchemes"] = nullable_to_30(copy.deepcopy(src["components"].get("securitySchemes", {})))
    doc = {
        "openapi": "3.0.3",
        "info": {"title": "Moneybird readable record collections", "version": src["info"]["version"], "description": "Generated from the official Moneybird OpenAPI v2 specification."},
        "servers": copy.deepcopy(src["servers"]),
        "security": copy.deepcopy(src.get("security", [{"bearerAuth": []}])),
        "paths": output_paths,
        "components": components,
    }
    OUT.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    MANIFEST.write_text(json.dumps({"source": str(SOURCE), "source_get_count": len(routes), "imported_route_count": len(output_paths), "routes": routes}, indent=2) + "\n")
    collections = []
    for path, (operation, kind) in imported_routes.items():
        # Only array responses are importer collections; detail routes remain in
        # openapi.yaml but do not create another collection entry.
        schema = operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
        if kind == "primary_detail":
            continue
        response_is_array = schema.get("type") == "array"
        item_schema = schema.get("items", {}) if response_is_array else schema
        ref = item_schema.get("$ref") or schema.get("$ref")
        rest = path.removeprefix("/{administration_id}/")
        resource = rest.split("/", 1)[0].replace(".json", "") or "administrations"
        if path.startswith("/administrations"):
            resource = "administrations"
        if resource == "documents":
            parts = path.split("/documents/", 1)[1].split("/", 1)[0].replace(".json", "")
            resource = parts
        if "/additional_charges" in path:
            resource = "contact_additional_charges" if "/contacts/" in path else "subscription_additional_charges"
        q = []
        dynamic = []
        pagination = {"page": False, "per_page": False, "max_per_page": 100}
        for p in operation.get("parameters", []):
            if p.get("$ref"):
                name = p["$ref"].rsplit("/", 1)[-1]
                p = src["components"].get("parameters", {}).get(name, p)
                if name in {"page", "per_page"}:
                    pagination[name] = True
            elif p.get("in") == "query":
                name = p.get("name")
                if name in {"page", "per_page"}:
                    pagination[name] = True
                elif name == "include_archived" and "contacts" in path:
                    q.append({"name": name, "value": True, "reason": "include archived contacts"})
                elif name == "active" and resource in {"assets", "products"}:
                    q.append({"name": name, "value": False, "reason": "include inactive records"})
                elif name == "filter" and resource == "projects":
                    q.append({"name": name, "value": "state:all", "reason": "include archived projects"})
                elif name == "include_billed" and "/additional_charges" in path:
                    q.append({"name": name, "value": True, "reason": "include billed and unbilled charges"})
                elif p.get("required"):
                    dynamic.append(name)
        candidate_detail = path.rsplit(".json", 1)[0] + "/{id}.json"
        collections.append({
            "name": resource,
            "path": path,
            "operationId": operation.get("operationId"),
            "schema": ("contact" if resource == "contacts" else (ref or "").rsplit("/", 1)[-1]),
            "response_path": "$",
            "item_path": "$[*]" if response_is_array else "$",
            "response_is_array": response_is_array,
            "identity_field": "id",
            "detail_path": candidate_detail if candidate_detail in output_paths else None,
            "pagination": pagination,
            "constant_query": q,
            "required_dynamic_query": dynamic,
            "notes": "child collection" if kind == "child_or_singleton" else "primary record collection",
        })
    COLLECTIONS.write_text(json.dumps({"source": str(SOURCE), "collections": collections}, indent=2) + "\n")
    print(f"generated {OUT} ({len(output_paths)} routes, {len(schemas)} schemas)")
    print(f"wrote {MANIFEST} ({len(routes)} GET operations)")
    print(f"wrote {COLLECTIONS} ({len(collections)} collections)")

if __name__ == "__main__":
    main()
