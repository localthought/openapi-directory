#!/usr/bin/env python3
"""Explicitly refresh an untouched generated draft; preserve its initial PR text."""
import argparse
import copy
import json
from pathlib import Path

import draft_pr
import eligibility
import pending_pr
import update


def policy(plan, review):
    if review["status"] != "pending_refresh_requires_review":
        return review["status"]
    if review.get("publication_protocol") != 2:
        return "Legacy PR body is not labelled an immutable initial snapshot; deliberate reconciliation required"
    if not (plan["base_revision"] == review["original_base"] == review["advertised_base"]):
        return "Main/base advanced; no automatic rebase of a pending PR"
    prior = pending_pr.retained_candidate(Path(review["prior_cache"]), plan, review["pr_snapshot"])
    for row, comparison in zip(plan["sources"], review["comparisons_from_pending"]):
        previous_row = next(r for r in prior["sources"] if r["id"] == row["id"])
        old = update.stored(previous_row["destination"], review["head"])
        content = plan["files"].get(row["destination"])
        new = update.parse(content.encode()) if content is not None else update.stored(row["destination"], plan["base_revision"])
        reason = eligibility.content_hold(old, new, comparison)
        if reason:
            return reason
    return None


def refresh(plan, fresh_cache, prior_cache):
    """The explicit caller has requested publication; a review digest grants none."""
    draft_pr.verify_plan(plan)
    directory = prior_cache / "publication" / plan["group"]
    if directory.is_symlink():
        raise ValueError("Redirected publication guard directory")
    directory.mkdir(parents=True, exist_ok=True)
    blocked, lock = directory / "blocked.json", directory / "publishing.lock"
    if blocked.exists() or blocked.is_symlink():
        raise ValueError("Retained failed/uncertain publication; no retry")
    try:
        with lock.open("x") as handle:
            handle.write(plan["seal"] + "\n")
    except FileExistsError:
        raise ValueError("Publication running/interrupted; preserve retained lock") from None
    release_lock = True
    try:
        if blocked.exists() or blocked.is_symlink():
            raise ValueError("Retained failed/uncertain publication; no retry")
        draft_pr.remote_guard(plan)
        review = pending_pr.review_pending(plan, prior_cache, pending_pr.observation(plan))
        review["prior_cache"] = str(prior_cache)
        reason = policy(plan, review)
        if reason:
            return {"status": "held", "reason": reason, "review": review, "publication_authorized": False}
        pr = review["pr_snapshot"]
        plan = copy.deepcopy(plan)
        if review.get("branch"):
            plan["branch"] = review["branch"]  # the reviewed generation's branch
        marker = {"previous_head": review["head"], "previous_candidate_sha256": review["prior_candidate_sha256"],
                  "creation_candidate_sha256": review["creation_candidate_sha256"],
                  "body_sha256": update.sha256(pr["body"].encode())}
        plan["pending_update"] = marker
        plan["seal"] = draft_pr.seal(plan)
        # Reserve an immutable attempt before any push. A missing success receipt
        # after an interruption never becomes permission to repeat the operation.
        attempt = prior_cache / plan["group"] / plan["seal"]
        if attempt.parent.is_symlink():
            raise ValueError("Redirected retained candidate directory")
        attempt.mkdir(parents=True, exist_ok=False)
        (attempt / "candidate.json").write_text(json.dumps(plan, indent=2) + "\n")
        (attempt / "attempt.json").write_text(json.dumps({"status": "prepared", "source_cache": str(fresh_cache),
                                                        "recorded_at": update.now(), **marker}, indent=2) + "\n")
        (attempt / "current-report.md").write_text(draft_pr.pr_body(plan))
        commit = draft_pr.commit_plan(plan)
        endpoint = "repos/" + draft_pr.REPOSITORY + "/pulls/" + str(pr["number"])
        current = draft_pr.gh_json(endpoint)
        pending_pr.check_identity(current, plan)
        if pending_pr.snapshot(current) != pr or draft_pr.pages(endpoint + "/reviews"):
            raise ValueError("Pending PR changed before push; preserve review work")
        draft_pr.remote_guard(plan)
        stage = "push_pending_head"
        release_lock = False
        try:
            branch = "refs/heads/" + plan["branch"]
            # Compare-and-swap the exact verified generated head. A concurrent
            # commit cannot be discarded. The old object/receipt are retained.
            draft_pr.git("push", "--porcelain", "--force-with-lease=" + branch + ":" + review["head"],
                         "origin", commit + ":" + branch)
            stage = "verify_pending_update"
            draft_pr.remote_guard(plan)
            updated = draft_pr.gh_json(endpoint)
            pending_pr.check_identity(updated, plan)
            if (updated["head"]["sha"] != commit or updated["base"]["sha"] != plan["base_revision"]
                    or updated["body"] != pr["body"] or updated["title"] != pr["title"]
                    or updated["number"] != pr["number"] or updated["html_url"] != pr["html_url"]
                    or draft_pr.pages(endpoint + "/reviews")):
                raise ValueError("Pending state changed during update; deliberate outcome review required")
            files = draft_pr.pages(endpoint + "/files", limit=30)
            pending_pr.verify_prior(plan, plan, updated, files,
                                   pending_pr.creation_candidate(prior_cache, plan, pr,
                                       pending_pr.retained_candidate(prior_cache, plan, pr)))
            if pending_pr.snapshot(draft_pr.gh_json(endpoint)) != pending_pr.snapshot(updated):
                raise ValueError("Pending PR changed during outcome verification")
            result = {"status": "draft_updated", "group": plan["group"], "candidate_sha256": plan["seal"],
                      "base_revision": plan["base_revision"], "files": sorted(plan["files"]),
                      "number": pr["number"], "url": pr["html_url"], "head": commit,
                      "initial_pr_text_preserved": True, "recorded_at": update.now(), **marker}
            (attempt / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            release_lock = True
            return result
        except Exception as error:
            receipt = {"stage": stage, "candidate_sha256": plan["seal"], "branch": plan["branch"],
                       "head": commit, "previous_head": review["head"], "number": pr["number"],
                       "url": pr["html_url"], "recorded_at": update.now(), "error_type": type(error).__name__}
            blocked.write_text(json.dumps(receipt, indent=2) + "\n")
            release_lock = True
            raise draft_pr.PublicationFailure(receipt) from error
    finally:
        # If neither success nor failure evidence can be saved after a push,
        # preserve the interrupted lock so a later run cannot repeat it.
        if release_lock:
            lock.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--cache", type=Path, default=update.ROOT / "cache/maintenance/pending-refresh")
    parser.add_argument("--prior-cache", type=Path, required=True)
    parser.add_argument("--publish", action="store_true", help="Explicitly update one verified untouched draft head; never merge or edit PR text")
    args = parser.parse_args(argv)
    if args.cache.resolve() == args.prior_cache.resolve():
        parser.error("Fresh and original publication cache roots must differ")
    args.cache.mkdir(parents=True, exist_ok=True)
    try:
        plan = draft_pr.build_plan(args.source, args.base, args.cache)
        draft_pr.run_plan(plan, argparse.Namespace(cache=args.cache, publish=False))
        result = refresh(plan, args.cache, args.prior_cache) if args.publish and plan["files"] else pending_pr.review(plan, args.prior_cache)
    except Exception as error:
        result = {"status": "failed", "source": args.source, "error_type": type(error).__name__,
                  "recorded_at": update.now(), "publication_authorized": False,
                  "note": "Inspect retained guards/attempts and actual PR read-only; never automatically retry."}
        if isinstance(error, draft_pr.PublicationFailure):
            result.update(url=error.receipt.get("url"), stage=error.receipt["stage"], head=error.receipt["head"])
        (args.cache / "failure.json").write_text(json.dumps({**result, "diagnostic": str(error)}, indent=2) + "\n")
    (args.cache / "refresh-result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 1 if result["status"] in {"held", "failed"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
