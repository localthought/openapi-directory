# Design: scheduled publication of generated API drafts

Status: **proposal only, not implemented and not enabled.** No workflow, permission,
secret, environment or repository setting is changed by this document. Written
2026-10-08 for HANDOVER.md item 2.

## Today

| Piece | What it does | Permissions |
| --- | --- | --- |
| `maintenance.yml` weekly audit | tests + `update.py check` of all registered sources | `contents: read` |
| `discovery.yml` monthly | bounded official-repository discovery | `contents: read` |
| `draft_pr.py --publish` | run **by hand** from a checkout; creates one draft per API/group | the operator's `gh`/Git credentials |
| `refresh_pr.py --publish` | run by hand; updates one untouched open draft | operator credentials |
| `api-draft-validation.yml` | offline validation of an exact generated head on `pull_request` | `contents: read` |
| merge | always by hand, after actual CI, exact head/base/files and CLEAN/MERGEABLE checks | human |

Publication guards live in a **local** cache (`publication/<group>/blocked.json`,
`publishing.lock`, creation/update receipts). That is why the handover lists the
laptop cache as required evidence. Moving to the VPS left those receipts behind.

## Repository facts that constrain the design (verified 2026-10-08)

- `main` has **no branch protection**. Nothing technically requires a check before merge.
- Repository default workflow token permission is **`write`**, and
  `can_approve_pull_request_reviews` is **true**. Every current workflow overrides this
  with `permissions: contents: read`. A future workflow file that forgets its
  `permissions:` block would get a write token that can also approve PRs.
- `allow_auto_merge` is `false`, and `delete_branch_on_merge` is `false`.
- Events created with the workflow's own `GITHUB_TOKEN` do not start other workflows,
  except `workflow_dispatch` and `repository_dispatch` ([GitHub docs][token]). So a draft
  pushed and opened by a scheduled job using `GITHUB_TOKEN` would **not** trigger
  `api-draft-validation.yml`. Without a deliberate fix, "generated" PRs would appear with
  no validation run at all.

[token]: https://docs.github.com/en/actions/tutorials/authenticate-with-github_token

## Goals

1. Drafts for genuine vendor drift appear without someone running a command on a
   particular machine.
2. Per-API review stays human: the job creates **drafts only**. It never marks ready,
   approves or merges, and never enables auto-merge.
3. Exactly the same guards as the manual tools apply: source health, native
   validation, typed YAML, exact tree scope, create-only refs, no retry after rejection,
   and no push-protection bypass or redaction.
4. Guards and receipts survive across ephemeral runners and across machines.
5. Every generated head gets a real validation run tied to that exact SHA.
6. Read-only auditing stays separate from the step that can write.

## Proposal

### 1. Two jobs, two permission sets

```
schedule / manual ─► job "plan"  (contents: read)
                       tests → update.py check → draft_pr.py (dry run) per drifting source
                       → upload candidates + report as an artifact
                     job "publish" (needs: plan; environment: publication)
                       permissions: contents: write, pull-requests: write, actions: write
                       → for each eligible candidate: draft_pr.py --publish (rebuilds from source)
                       → dispatch validation for the created head
```

`plan` is today's audit plus dry runs; it can never write. `publish` runs in a GitHub
**Environment** named `publication` with **required reviewers** (the repository owner).
Every scheduled run pauses until a human approves that run's publish step. This gives
scheduled *preparation* with human-gated *publication*, without per-command laptop
access. Turning the gate off later is a separate decision, not part of this design.

`publish` never trusts `plan`'s artifact as content. As today, `--publish` re-fetches,
revalidates and seals a new plan. The artifact only lists which source IDs to try.

### 2. Eligibility: narrower than the manual command

The scheduled publisher only *creates* drafts whose candidate has:

- no endpoint, operation or schema-name removals;
- no server or authentication changes on existing operations;
- no new recipe or transformation, and no changed expected warning or patch counts;
- no vendor-version change that needs lifecycle review. New version directories,
  initial imports from an `initial_baseline` and new registrations are left to a human run.

These are the same hold classes `refresh_pr.py` already implements. Factor them into a
shared function rather than duplicating them. Everything else is reported in the run
summary as "needs manual review" and is never published automatically. Blocked
sources (`import_blocker`, publication guards, push-protection holds) are skipped
before fetching, as `draft_pr.py` already does.

At most **five** drafts per run, processed serially, stopping at the first
`PublicationFailure`. The job never deletes a guard to continue.

### 3. Durable guard and receipt store

Runner disks are discarded, so the publication cache must live somewhere durable and
reviewable. Proposed: an **append-only orphan branch** `maintenance-state` holding
`publication/<group>/…` exactly as the local cache does today.

- `publish` checks it out at start and refuses to run if a `publishing.lock` or
  `blocked.json` exists for the group it would touch.
- It writes the lock as a commit, pushed with `--force-with-lease=<ref>:<seen-sha>`. A
  second concurrent run fails to push its lock and stops; GitHub `concurrency:` on the
  workflow serializes runs as a first line of defence.
- After each outcome it commits the receipt (`result.json`, `candidate.json`,
  `blocked.json` on failure) and removes the lock only after the receipt commit lands.
  If that push fails, the lock remains and later runs stop, which is the same semantics
  as the local `publishing.lock`.
- History is never rewritten. A human clears a block by committing a reviewed
  `cleared.json` next to it, never by deleting it.

Manual runs on any machine would fetch this branch to use as their `--prior-cache`.
That closes the laptop/VPS gap for *future* drafts. Receipts that were only ever on the
laptop are **not** recreated; drafts that depend on them stay held.

Alternatives: Actions artifacts expire (max 90 days) and cannot be locked. A separate
repository adds credentials. Release assets are not append-only. Rejected.

### 4. Making validation actually run on generated heads

Two options, in order of preference:

1. **Explicit dispatch.** Add a `workflow_dispatch` trigger to
   `api-draft-validation.yml` with inputs `pr`, `head` and `base`. After creating a draft,
   `publish` dispatches it (allowed with `GITHUB_TOKEN` and `actions: write`). The
   validation job re-reads the PR, refuses if head/base differ from the inputs, runs
   today's offline validation and posts a commit status on that exact head SHA under a
   fixed context (`generated-api-draft-validation`). It keeps `contents: read`, and
   needs only `statuses: write` for that single status.
2. **A GitHub App** with contents/pull-requests write, owned by the repository owner,
   whose installation token creates the PR. App-created events do trigger
   `pull_request` workflows. This needs a new credential and owner setup; it is a
   decision for Michiel, not a default.

A personal access token for the bot is not proposed (it is broad and tied to one person).

### 5. Repository-setting recommendations (owner decisions, not made here)

- Set the default workflow token permission to **read**, and turn off "Allow GitHub
  Actions to create and approve pull requests" until option 4.1 (which needs creation,
  not approval) is adopted. If it is adopted, allow creation only.
- Protect `main` so that the generated-draft validation status (and the maintenance
  tests for infrastructure PRs) must pass before merge. Today, merge discipline is purely
  procedural.

Each of these widens or narrows what automation can do, so each needs Michiel's explicit
approval. None is applied by this proposal.

## What stays manual

Ready-for-review, merging, lifecycle and scope review, removals, auth changes, new
registrations, push-protection outcomes, and clearing blocks.

## Implementation order (each a separate infrastructure PR with actual CI)

1. Factor the refresh hold classes into a shared eligibility check, with tests. No
   behaviour change for manual commands.
2. `maintenance-state` store: read/write/lock library and tests using real local bare
   repositories. Manual commands gain `--state-branch` as an alternative to
   `--prior-cache`.
3. `workflow_dispatch` validation with the exact-SHA status, with tests and a dry run
   on an existing merged generated commit (read-only).
4. The `publish` job behind the `publication` environment, initially `workflow_dispatch`
   only (no `schedule:` line), so the first runs are deliberate.
5. Only after several reviewed manual dispatches: add the `schedule:` trigger, on
   Michiel's explicit go-ahead.
