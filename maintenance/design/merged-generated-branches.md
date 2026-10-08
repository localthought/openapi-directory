# Design: handling already-merged generated branches

Status: **proposal only, not implemented.** No code, workflow, permission or branch
changes accompany this document. Written 2026-10-08 for HANDOVER.md item 1.

## Problem

`draft_pr.py --publish` always uses the fixed branch `codex/official-update-<group>`.
Before creating anything it reads all open PRs and the remote branch:

- an open PR touching the service, or on that branch → `existing_pending`;
- the branch exists without an open PR → `existing_branch`.

Both outcomes are correct holds. They also mean that **once a generated draft is
merged, that API can never be published by the generator again**, because the
repository keeps merged branches (`delete_branch_on_merge` is `false`, verified
2026-10-08). As of that date, seven generated branches are in this state:

| Branch | Merged PR |
| --- | --- |
| `codex/official-update-github-public-rest` | #232 |
| `codex/official-update-snowflake-compute-pool` | #219 |
| `codex/official-update-hcp-identity` | #222 |
| `codex/official-update-hcp-operations` | #225 |
| `codex/official-update-hcp-hvn` | #226 |
| `codex/official-update-hcp-rbac` | #227 |
| `codex/official-update-hcp-webhook` | #228 |

(plus every branch created by later generator runs). `refresh_pr.py` only updates
*open, untouched* drafts, so it does not cover this case either.

The handover says not to delete a branch merely to force publication. This design
keeps that rule.

## Goals

1. A later vendor change to an API whose previous generated draft was merged can be
   published as a new draft, without manual branch surgery.
2. No branch, ref, receipt or guard is deleted, rewritten or force-pushed.
3. Every non-merged outcome stays held exactly as today: an open PR, a closed but
   unmerged PR, an orphan branch, a branch that moved after merge, a retained
   `blocked.json`, or an interrupted `publishing.lock`.
4. It works on a machine that does not have the original creation cache (for
   example the VPS, which lacks the laptop's `cache/maintenance/drafts/`), without
   manufacturing receipts.

## Non-goals

Scheduled publication (see `scheduled-publication.md`), automatic merging, reconciling
closed-unmerged PRs, and updating open drafts (that is `refresh_pr.py`).

## Proposal: generation-suffixed branches, with a verified retirement observation

### Branch naming

Keep generation 1 as today (`codex/official-update-<group>`) so existing branches and
CI keep their meaning. Later generations use
`codex/official-update-<group>--g<N>`, with `N` = 2, 3, … The `--g` separator cannot
occur in a group ID, because group IDs match `[a-z0-9][a-z0-9-]{0,63}` and a doubled
hyphen followed by `g` and digits would be rejected for new IDs by an added check.

The `startsWith(github.head_ref, 'codex/official-update-')` CI trigger still matches.
`validate_commit` and `select_sources` currently require `branch ==
"codex/official-update-" + group`. They would instead parse an optional `--g<N>` suffix
(N ≥ 2, no leading zeros, bounded) and compare the remaining group exactly.

### Choosing the generation

When planning a publication, list remote refs matching
`refs/heads/codex/official-update-<group>` and `…--g*`. Pick the lowest unused `N`
only if **every** existing generation is a *verified merged outcome*. Otherwise return
the existing hold (`existing_pending` or `existing_branch`) unchanged.

A generation is a verified merged outcome only if all of these hold, read via REST GET:

1. Exactly one PR in this repository has that head ref, and it is `closed` with
   `merged_at` set.
2. The PR's recorded `head.sha` equals the branch's current tip. A branch that moved
   after merge is held.
3. That head commit is reachable from `origin/main`. This repository merges with merge
   commits, so the generated commit stays in main's history. A squash or rebase merge
   fails this check and is held for a human.
4. The head commit has exactly one parent and its message has the generator's form,
   `Update official <group> API description` plus a `Candidate SHA-256:` line.
5. The commit changes only that group's service prefixes and `maintenance/sources.json`,
   checked with `git diff-tree` against its parent, as `validate_commit` does.
6. No `blocked.json` or `publishing.lock` exists for that group in the local
   publication cache.

The tool does **not** require the original creation receipt for a merged generation.
Once merged, the generated content has been reviewed and is on main, and no command
will ever update that branch. Requiring a receipt the current machine never had would
hold every merged API forever on any new machine. The receipt is still required for
everything that *changes* an existing branch (`pending_pr.py`, `refresh_pr.py`); that
rule does not change.

### Retirement observation

Before creating generation `N`, write an immutable
`publication/<group>/retired/<branch-ref-hex>.json` with the PR number, merge commit,
head SHA, the result of each check above and the observation time. Label it plainly as
an observation, not a creation receipt. `pending_pr.py` and `refresh_pr.py` ignore it.
Reviewers and later runs can see why a new generation was allowed.

### Interaction with the other commands

- `pending_pr.py` / `refresh_pr.py` take the branch from the open PR that overlaps the
  service, rather than from the group name. They need the same suffix parsing and
  nothing else.
- The create-only push (`--force-with-lease=<ref>:`) and every existing post-push check
  stay as they are. Two concurrent runs picking the same `N` race on an absent ref; one
  wins and the other fails closed with `blocked.json`, as today.
- Old generations are never deleted. If the repository owner later wants tidier
  branches, deleting a verified merged generation loses no objects, because its head is
  in main's history. That remains a deliberate owner action, not part of the tool.

### Alternatives considered

- **Delete the merged branch, then reuse the name.** It loses no Git objects, but
  conflicts with the handover rule, needs `delete` permission and erases the
  branch-to-PR mapping that the pending reviewer uses. Rejected.
- **Turn on `delete_branch_on_merge`.** A repository-wide setting change that also
  affects human branches. That is the owner's call. It would also make an orphan
  branch indistinguishable from a deleted one after a failed merge. Not proposed.
- **Seal-suffixed branches (`…-<shortseal>`).** Unique without counting, but the name
  says nothing about order, and identical vendor content would produce identical
  names, colliding with the old branch. Rejected in favour of `--g<N>`.

## Tests to add with an implementation

Real-Git cases in the existing style: a merged generation 1 allows `--g2`; an open PR,
a closed-unmerged PR, an orphan branch, a moved tip, a squash merge (head not in main),
a foreign commit message and a retained `blocked.json` each hold; two concurrent
creators of `--g2` (one fails closed); `validate_commit` accepts `--g2` and rejects
`--g02`, `--g1`, `--g` and a suffix on an unknown group; `pending_pr.py` reviews a
`--g2` draft using that generation's own receipt.

## Rollout

1. Separate infrastructure PR implementing the above, with the tests, and actual CI.
2. A dry run against `github-public-rest`. It should report generation 2 as eligible
   only when vendor content has actually changed since #232.
3. The first real `--g2` publication is reviewed and merged by hand, like every
   generated draft today.
