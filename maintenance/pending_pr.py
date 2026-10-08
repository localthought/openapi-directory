#!/usr/bin/env python3
"""Review a pending generated API draft against fresh sources; never publish or update."""
import argparse
import copy
import json
import re
import subprocess
import tempfile
from pathlib import Path

import draft_pr
import embedded
import update


def read_json(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or redirected retained publication evidence")
    return embedded.strict_json(path.read_text())


def snapshot(pr):
    """Fields whose change during pagination invalidates this observation."""
    return {key: copy.deepcopy(pr.get(key)) for key in (
        "number", "html_url", "state", "draft", "head", "base", "body", "title",
        "updated_at", "changed_files", "comments", "review_comments",
        "requested_reviewers", "requested_teams")}


def check_identity(pr, plan):
    number = pr.get("number")
    if (type(number) is not int or number < 1
            or pr.get("html_url") != "https://github.com/" + draft_pr.REPOSITORY + "/pull/" + str(number)
            or pr.get("state") != "open" or pr.get("draft") is not True
            or pr.get("head", {}).get("ref") != plan["branch"]
            or any(not re.fullmatch(r"[0-9a-f]{40}", pr.get(side, {}).get("sha") or "")
                   for side in ("head", "base"))
            or pr.get("base", {}).get("ref") != "main"
            or any(pr.get(side, {}).get("repo", {}).get("full_name") != draft_pr.REPOSITORY
                   for side in ("head", "base"))):
        raise ValueError("Pending PR is not an open generated draft in this fork")
    if (pr.get("comments") != 0 or pr.get("review_comments") != 0
            or pr.get("requested_reviewers") != [] or pr.get("requested_teams") != []):
        raise ValueError("Pending PR has human/bot discussion or review requests; deliberate review required")


def candidate_evidence(directory):
    if directory.is_symlink() or not re.fullmatch(r"[0-9a-f]{64}", directory.name):
        raise ValueError("Redirected or invalid retained candidate directory")
    receipt = read_json(directory / "result.json")
    prior = read_json(directory / "candidate.json")
    if (not re.fullmatch(r"[0-9a-f]{40}", receipt.get("head") or "")
            or receipt.get("candidate_sha256") != directory.name
            or draft_pr.seal(prior) != directory.name or prior.get("seal") != directory.name
            or receipt.get("base_revision") != prior.get("base_revision")
            or receipt.get("group") != prior.get("group")
            or receipt.get("files") != sorted(prior.get("files", {}))):
        raise ValueError("Retained candidate/creation receipt integrity changed")
    return prior, receipt


def creation_candidate(cache, plan, pr, prior):
    """Follow a bounded, intact successful-update chain to its original body."""
    directory = cache / plan["group"]
    visited = set()
    current = prior
    for _ in range(100):
        if current["seal"] in visited:
            raise ValueError("Cyclic retained update history")
        visited.add(current["seal"])
        current, receipt = candidate_evidence(directory / current["seal"])
        if (receipt.get("number") != pr["number"] or receipt.get("url") != pr["html_url"]
                or current.get("group") != plan["group"] or current.get("branch") != plan["branch"]
                or [s["configuration"] for s in current["sources"]] != [s["configuration"] for s in plan["sources"]]):
            raise ValueError("Source group/recipe changed in retained update history, or PR identity differs")
        marker = current.get("pending_update")
        if receipt.get("status") == "draft_created":
            if marker:
                raise ValueError("Creation receipt contains an update marker")
            if prior.get("pending_update", {}).get("creation_candidate_sha256", current["seal"]) != current["seal"]:
                raise ValueError("Retained update history has a different creation root")
            return current
        if receipt.get("status") != "draft_updated" or not isinstance(marker, dict):
            raise ValueError("Retained update history lacks a successful receipt")
        if any(receipt.get(key) != marker.get(key) for key in (
                "previous_head", "previous_candidate_sha256", "creation_candidate_sha256", "body_sha256")):
            raise ValueError("Retained update receipt/marker changed")
        digest = marker.get("previous_candidate_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("Invalid retained update parent")
        previous, previous_receipt = candidate_evidence(directory / digest)
        if (marker.get("previous_head") != previous_receipt.get("head")
                or current["base_revision"] != previous["base_revision"]
                or current.get("publication_protocol") != 2 or previous.get("publication_protocol") != 2
                or marker.get("body_sha256") != update.sha256(pr["body"].encode())
                or marker.get("creation_candidate_sha256") != prior["pending_update"].get("creation_candidate_sha256")):
            raise ValueError("Retained update predecessor head/base/protocol/body changed")
        verify_artifact(previous, plan, previous_receipt["head"])
        current = previous
    raise ValueError("Retained update history exceeds review bounds")


def retained_candidate(cache, plan, pr):
    """Require a successful original creation receipt, not a branch-name assumption."""
    directory = cache / plan["group"]
    paths = sorted(directory.glob("*/result.json"))
    if len(paths) > 200:
        raise ValueError("Retained candidate search exceeds review bounds")
    found = []
    for path in paths:
        if not re.fullmatch(r"[0-9a-f]{64}", path.parent.name):
            continue
        if path.parent.is_symlink() or directory.is_symlink():
            raise ValueError("Redirected retained candidate directory")
        receipt = read_json(path)
        if (receipt.get("status") in {"draft_created", "draft_updated"} and receipt.get("head") == pr["head"]["sha"]
                and receipt.get("number") == pr["number"] and receipt.get("url") == pr["html_url"]):
            prior, _ = candidate_evidence(path.parent)
            found.append(prior)
    if len(found) != 1:
        raise ValueError("Exactly one retained successful creation receipt is required for the actual head")
    return found[0]


def verify_artifact(prior, plan, head):
    """Check retained full Git content without executing historical/vendor code."""
    base = prior.get("base_revision")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("Invalid retained comparison revision")
    if draft_pr.git("rev-list", "--parents", "-n", "1", head).decode().split() != [head, base]:
        raise ValueError("Pending head is not the retained single-parent generated commit")
    expected_message = ("Update official " + plan["group"] + " API description\n\nCandidate SHA-256: "
                        + prior["seal"] + "\n")
    if draft_pr.git("show", "-s", "--format=%B", head).decode().rstrip("\n") != expected_message.rstrip("\n"):
        raise ValueError("Pending commit is not the retained generated candidate")
    original = draft_pr.git("show", base + ":" + draft_pr.MANIFEST)
    group, sources = draft_pr.select_sources(json.loads(original), plan["sources"][0]["id"])
    prefixes = sorted({str(Path(s["target"]).parent.parent) + "/" for s in sources})
    if (prior.get("schema_version") != 1 or prior.get("group") != group or group != plan["group"]
            or prior.get("branch") != plan["branch"] or prior.get("service_prefixes") != prefixes
            or [s["configuration"] for s in prior["sources"]] != sources
            or [s["id"] for s in prior["sources"]] != [s["id"] for s in sources]
            or [s["configuration"] for s in plan["sources"]] != sources):
        raise ValueError("Source group/recipe changed since publication; deliberate review required")
    changed = draft_pr.git("diff-tree", "--no-commit-id", "--name-only", "-r", base, head).decode().splitlines()
    if not prior["files"] or set(changed) != set(prior["files"]):
        raise ValueError("Pending full Git file scope differs from retained candidate")
    allowed = {s["destination"] for s in prior["sources"]} | {draft_pr.MANIFEST}
    if not set(changed) <= allowed:
        raise ValueError("Pending candidate contains unrelated files")
    draft_pr.guard_tree_paths(base, allowed)
    draft_pr.guard_tree_paths(head, allowed)
    with tempfile.TemporaryDirectory() as directory:
        manifest = Path(directory) / "sources.json"
        manifest.write_bytes(original)
        for source, row in zip(sources, prior["sources"]):
            destination = row["destination"]
            raw = draft_pr.git("show", head + ":" + destination)
            spec = update.parse(raw)
            if (str(update.destination(source, spec)) != destination or update.validate_document(spec)
                    or update.serialize_document(spec).encode() != raw):
                raise ValueError("Retained pending artifact fails target/native/typed-YAML validation")
            advance = update.advance_target(manifest, source, Path(destination))
            if advance:
                manifest.write_bytes(advance[1])
        if manifest.read_bytes() != draft_pr.git("show", head + ":" + draft_pr.MANIFEST):
            raise ValueError("Retained pending manifest contains unrelated configuration changes")
    for path, content in prior["files"].items():
        if not isinstance(content, str) or draft_pr.git("show", head + ":" + path) != content.encode():
            raise ValueError("Pending Git bytes differ from retained candidate")
    return base, prefixes, changed


def verify_prior(prior, plan, pr, files, creation=None):
    base, prefixes, changed = verify_artifact(prior, plan, pr["head"]["sha"])
    if (type(pr.get("changed_files")) is not int or pr["changed_files"] != len(files)
            or len(files) != len(changed) or {f["filename"] for f in files} != set(changed)):
        raise ValueError("Pending PR file scope differs from retained candidate")
    creation = creation or prior
    if (pr.get("body") != draft_pr.pr_body(creation)
            or pr.get("title") != "Update official " + plan["group"] + " API"):
        raise ValueError("Pending title/body has been edited; preserve existing review work")
    if prior.get("pending_update") and update.sha256(pr["body"].encode()) != prior["pending_update"].get("body_sha256"):
        raise ValueError("Retained update body integrity changed")
    # Unrelated main advances are observable, but changes to this API's baseline
    # or configuration never become an implicit overwrite/rebase permission.
    draft_pr.git("merge-base", "--is-ancestor", base, plan["base_revision"])
    draft_pr.git("merge-base", "--is-ancestor", base, pr["base"]["sha"])
    draft_pr.git("merge-base", "--is-ancestor", pr["base"]["sha"], plan["base_revision"])
    main_changes = draft_pr.git("diff", "--name-only", base, plan["base_revision"]).decode().splitlines()
    if draft_pr.MANIFEST in main_changes or any(p.startswith(prefix) for p in main_changes for prefix in prefixes):
        raise ValueError("Main changed this API or source manifest; deliberate reconciliation required")
    return main_changes


def observation(plan):
    return {"schema_version": 1, "group": plan["group"], "base_revision": plan["base_revision"],
              "candidate_sha256": plan["seal"], "checked_at": update.now(),
              "read_only": True, "publication_authorized": False}


def review(plan, prior_cache):
    result = observation(plan)
    directory = prior_cache / "publication" / plan["group"]
    if any(p.exists() or p.is_symlink() for p in (directory / "blocked.json", directory / "publishing.lock")):
        return {**result, "status": "held", "reason": "Retained failed/uncertain publication or lock; no retry"}
    return review_pending(plan, prior_cache, result)


def review_pending(plan, prior_cache, result):
    """Read-only verification; writers call this only under their owned guard/lock."""
    pending = draft_pr.existing_pr(plan)
    if not pending:
        return {**result, "status": "no_pending_pr", "source_status": plan["status"]}
    result["pull_requests"] = pending
    if len(pending) != 1:
        return {**result, "status": "held", "reason": "Multiple overlapping PRs; preserve all existing work"}
    endpoint = "repos/" + draft_pr.REPOSITORY + "/pulls/" + str(pending[0]["number"])
    try:
        pr = draft_pr.gh_json(endpoint)
        # A later generation (codex/official-update-<group>--g<N>) is reviewed as
        # that generation; its own retained creation receipt is still required.
        plan = draft_pr.with_branch(plan, pr.get("head", {}).get("ref"))
        result["branch"] = plan["branch"]
        check_identity(pr, plan)
        if pr["head"]["sha"] != pending[0]["head"] or pr["html_url"] != pending[0]["url"]:
            raise ValueError("Pending identity changed during discovery")
        if draft_pr.pages(endpoint + "/reviews"):
            raise ValueError("Pending PR has submitted reviews; preserve review work")
        files = draft_pr.pages(endpoint + "/files", limit=30)
        prior = retained_candidate(prior_cache, plan, pr)
        creation = creation_candidate(prior_cache, plan, pr, prior)
        main_changes = verify_prior(prior, plan, pr, files, creation)
        if snapshot(draft_pr.gh_json(endpoint)) != snapshot(pr):
            raise ValueError("Pending PR changed during verification")
        comparisons = []
        for row, old in zip(plan["sources"], prior["sources"]):
            previous = update.stored(old["destination"], pr["head"]["sha"])
            content = plan["files"].get(row["destination"])
            current = update.parse(content.encode()) if content is not None else update.stored(row["destination"], plan["base_revision"])
            comparisons.append({"id": row["id"], **update.compare(previous, current)})
        unchanged = all(c["status"] == "matches_source" for c in comparisons)
        status = "pending_matches_source" if unchanged else "pending_refresh_requires_review"
        if not unchanged and not plan["files"]:
            status = "pending_superseded_by_main_requires_review"
        return {**result, "status": status, "head": pr["head"]["sha"],
                "original_base": prior["base_revision"], "advertised_base": pr["base"]["sha"],
                "prior_candidate_sha256": prior["seal"], "intervening_main_changes": main_changes,
                "creation_candidate_sha256": creation["seal"],
                "publication_protocol": creation.get("publication_protocol", 1),
                "pr_snapshot": snapshot(pr),
                "comparisons_from_pending": comparisons,
                "note": "Exact retained draft verified; fresh comparison is a review result, not permission to mutate, rebase, close or merge."}
    except (ValueError, KeyError, TypeError, OSError) as error:
        return {**result, "status": "held", "reason": str(error)[:1000]}
    except subprocess.CalledProcessError:
        return {**result, "status": "held", "reason": "Required Git objects or ancestry could not be verified; deliberate reconciliation required"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--cache", type=Path, default=update.ROOT / "cache/maintenance/pending-review")
    parser.add_argument("--prior-cache", type=Path, required=True,
                        help="Retained cache root used by the original create-only generator")
    args = parser.parse_args(argv)
    if args.cache.resolve() == args.prior_cache.resolve():
        parser.error("--cache must differ from --prior-cache to preserve original creation receipts")
    args.cache.mkdir(parents=True, exist_ok=True)
    try:
        plan = draft_pr.build_plan(args.source, args.base, args.cache)
        draft_pr.run_plan(plan, argparse.Namespace(cache=args.cache, publish=False))
        result = review(plan, args.prior_cache)
    except Exception as error:
        result = {"status": "failed", "source": args.source, "error_type": type(error).__name__,
                  "read_only": True, "publication_authorized": False, "checked_at": update.now()}
        (args.cache / "failure.json").write_text(json.dumps({**result, "diagnostic": str(error)}, indent=2) + "\n")
    (args.cache / "pending-review.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 1 if result["status"] in {"held", "failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
