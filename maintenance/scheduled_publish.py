#!/usr/bin/env python3
"""Plan (default) or explicitly publish eligible generated drafts for all sources.

Groundwork for design/scheduled-publication.md. There is deliberately **no
schedule trigger and no write-permission workflow** for this command; it runs only
when an operator invokes it with their own credentials.

`plan`: read-only. Builds a fresh candidate for every unblocked publication group
and classifies it as matches_source, eligible (no hold class applies), or
needs_manual_review with the reason. At most --limit groups are eligible per run.

`publish`: explicit. For each eligible group (fresh rebuild, never a cached plan),
takes a lock in the durable state store, runs the normal create-only draft
publisher, records receipts and releases the lock in one commit. Stops at the
first failure. It never marks ready, approves, merges, deletes or retries.
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

import draft_pr
import eligibility
import state_store
import update

LIMIT = 5


def groups(manifest):
    seen, result = set(), []
    for source in manifest["sources"]:
        group = source.get("publication_group", source["id"])
        if group not in seen:
            seen.add(group)
            result.append((group, source["id"]))
    return result


def classify(plan):
    """None when no hold class applies to any member, else the first reason."""
    if not plan["files"]:
        return "matches_source"
    for row in plan["sources"]:
        old = update.stored(row["configuration"]["target"], plan["base_revision"])
        content = plan["files"].get(row["destination"])
        new = update.parse(content.encode()) if content is not None else update.stored(row["destination"], plan["base_revision"])
        if row["destination"] != row["configuration"]["target"]:
            return "New vendor version directory requires deliberate review"
        reason = eligibility.content_hold(old, new, row["comparison"])
        if reason:
            return reason
    return None


def plan_all(base, cache, limit=LIMIT, only=None, builder=None):
    builder = builder or draft_pr.build_plan
    revision = draft_pr.git("rev-parse", "--verify", base + "^{commit}").decode().strip()
    manifest = json.loads(draft_pr.git("show", revision + ":" + draft_pr.MANIFEST))
    report = {"base_revision": revision, "generated_at": update.now(), "limit": limit,
              "eligible": [], "needs_manual_review": [], "matches_source": [], "blocked": [], "failed": [],
              "note": "Read-only plan; eligibility is not merge or review approval."}
    for group, source_id in groups(manifest):
        if only and group not in only:
            continue
        members = [s for s in manifest["sources"] if s.get("publication_group", s["id"]) == group]
        blocker = next((s["import_blocker"] for s in members if s.get("import_blocker")), None)
        if blocker:
            report["blocked"].append({"group": group, "reason": blocker[:300]})
            continue
        try:
            plan = builder(source_id, revision, cache)
            reason = classify(plan)
        except Exception as error:  # Vendor fetch/validation problems are review findings.
            report["failed"].append({"group": group, "error_type": type(error).__name__, "detail": str(error)[:300]})
            continue
        if reason == "matches_source":
            report["matches_source"].append(group)
        elif reason:
            report["needs_manual_review"].append({"group": group, "reason": reason, "files": sorted(plan["files"])})
        elif len(report["eligible"]) < limit:
            report["eligible"].append({"group": group, "source": source_id, "candidate_sha256": plan["seal"],
                                       "files": sorted(plan["files"])})
        else:
            report["needs_manual_review"].append({"group": group, "reason": "Per-run limit reached"})
    return report


def collect(cache, group, seal_dirs_before):
    """Receipts produced by one publication attempt, in state-store naming."""
    receipts = {}
    for directory in sorted((cache / group).glob("*")):
        if directory.name in seal_dirs_before or not directory.is_dir():
            continue
        for name in ("candidate.json", "result.json", "body.md"):
            if (directory / name).is_file():
                receipts["candidates/" + directory.name + "/" + name] = (directory / name).read_bytes()
    guard = cache / "publication" / group
    for path in sorted(guard.rglob("*")) if guard.exists() else []:
        if path.is_file() and path.name != "publishing.lock":
            receipts[str(path.relative_to(guard))] = path.read_bytes()
    return receipts


def publish_all(base, store, groups_to_publish, builder=None, runner=None):
    builder = builder or draft_pr.build_plan
    runner = runner or draft_pr.run_plan
    outcomes = []
    for entry in groups_to_publish:
        group = entry["group"]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            plan = builder(entry["source"], base, cache)
            if classify(plan) is not None:
                outcomes.append({"group": group, "status": "no_longer_eligible"})
                continue
            locked = store.acquire(group, plan["seal"])
            store.export(locked, cache)
            before = {p.name for p in (cache / group).glob("*")} if (cache / group).exists() else set()
            failure = None
            try:
                result = runner(plan, argparse.Namespace(cache=cache, publish=True))
            except Exception as error:
                failure, result = error, {"status": "failed", "error_type": type(error).__name__}
            receipts = collect(cache, group, before)
            if failure is not None and "blocked.json" not in receipts:
                # Unknown outcome without a guard: keep the lock for human review.
                outcomes.append({"group": group, **result, "status": "interrupted_lock_retained"})
                return outcomes
            store.release(group, plan["seal"], locked, receipts)
            outcomes.append({"group": group, **result})
            if failure is not None or result.get("status") != "draft_created":
                return outcomes
    return outcomes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "publish"])
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--cache", type=Path, default=update.ROOT / "cache/maintenance/scheduled-plan")
    parser.add_argument("--limit", type=int, default=LIMIT)
    parser.add_argument("--group", action="append", help="Restrict to these publication groups")
    parser.add_argument("--state-remote", default="origin")
    args = parser.parse_args(argv)
    if not 1 <= args.limit <= LIMIT:
        parser.error("--limit must be between 1 and %d" % LIMIT)
    args.cache.mkdir(parents=True, exist_ok=True)
    report = plan_all(args.base, args.cache, args.limit, args.group)
    (args.cache / "plan.json").write_text(json.dumps(report, indent=2) + "\n")
    if args.command == "publish":
        store = state_store.Store(update.ROOT, args.state_remote)
        report["publication"] = publish_all(report["base_revision"], store, report["eligible"])
        (args.cache / "publication.json").write_text(json.dumps(report["publication"], indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if report["failed"] or any(o.get("status") not in ("draft_created", "no_longer_eligible")
                                        for o in report.get("publication", [])) else 0


if __name__ == "__main__":
    sys.exit(main())
