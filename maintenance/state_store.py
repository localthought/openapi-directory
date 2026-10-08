#!/usr/bin/env python3
"""Append-only publication guard/receipt store on an orphan Git branch.

Runner disks are ephemeral and local caches differ between machines, so
publication locks, failure guards and creation/update receipts can be kept on
`refs/heads/maintenance-state` in this repository (design: scheduled-publication.md).

Rules enforced here:
- every write is one commit pushed with an exact lease on the previously seen
  state commit (create-only when the ref is absent), so concurrent writers fail
  closed instead of overwriting each other;
- history is never rewritten and existing files are never modified or deleted,
  except `publication/<group>/publishing.lock`, which a holder removes only in the
  same commit that records the outcome receipt;
- a `blocked.json` or `publishing.lock` makes the group unavailable; clearing a
  block needs a reviewed `cleared.json` committed by a human, never a deletion.

This module performs Git operations only when called explicitly. Nothing in the
repository workflows calls it with write credentials.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

REF = "refs/heads/maintenance-state"
GROUP = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
SAFE_PATH = re.compile(r"publication/[a-z0-9][a-z0-9-]{0,63}/[A-Za-z0-9._/-]{1,200}")


class StateConflict(ValueError):
    """Another writer advanced the state, or a guard makes the group unavailable."""


class Store:
    def __init__(self, root, remote="origin", ref=REF):
        self.root, self.remote, self.ref = Path(root), remote, ref

    def git(self, *args, data=None, env=None):
        return subprocess.run(["git", *args], cwd=self.root, input=data, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=True, env=env, timeout=120).stdout

    def head(self):
        """The remote state commit, fetched into a private ref, or None."""
        line = self.git("ls-remote", self.remote, self.ref).decode().split()
        if not line:
            return None
        self.git("fetch", "-q", "--no-tags", self.remote, "+" + self.ref + ":refs/maintenance-state/seen")
        sha = self.git("rev-parse", "refs/maintenance-state/seen").decode().strip()
        if sha != line[0]:
            raise StateConflict("State advanced while reading; retry the whole read")
        return sha

    def files(self, sha):
        if sha is None:
            return {}
        names = self.git("ls-tree", "-r", "-z", "--name-only", sha).decode().split("\0")
        return {name: self.git("show", sha + ":" + name) for name in names if name}

    def group_state(self, sha, group):
        prefix = "publication/" + group + "/"
        return {k[len(prefix):]: v for k, v in self.files(sha).items() if k.startswith(prefix)}

    def available(self, sha, group):
        state = self.group_state(sha, group)
        if "publishing.lock" in state:
            return False, "A publication lock is held or was interrupted; review before continuing"
        blocks = [k for k in state if k == "blocked.json" or k.endswith("/blocked.json")]
        cleared = {k[:-len("cleared.json")] for k in state if k.endswith("cleared.json")}
        if any(k[:-len("blocked.json")] not in cleared for k in blocks):
            return False, "A retained failure guard has not been cleared by a reviewed commit"
        return True, None

    def commit(self, expected, changes, message, removals=()):
        """Append files (and remove only an own lock) in one leased commit."""
        current = self.files(expected)
        for path, content in changes.items():
            if not SAFE_PATH.fullmatch(path) or ".." in path.split("/"):
                raise ValueError("Unsafe state path: " + path)
            if path in current and current[path] != content:
                raise StateConflict("State files are append-only: " + path)
            if not isinstance(content, bytes):
                raise ValueError("State content must be bytes")
        for path in removals:
            if not path.endswith("/publishing.lock") or path not in current:
                raise ValueError("Only an existing publishing.lock may be removed")
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
            if expected:
                self.git("read-tree", expected, env=env)
            else:
                self.git("read-tree", "--empty", env=env)
            for path, content in changes.items():
                blob = self.git("hash-object", "-w", "--stdin", data=content).decode().strip()
                self.git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + path, env=env)
            for path in removals:
                self.git("update-index", "--remove", "--", path, env=env)
            tree = self.git("write-tree", env=env).decode().strip()
        parents = ["-p", expected] if expected else []
        commit = self.git("commit-tree", tree, *parents, data=message.encode()).decode().strip()
        try:
            self.git("push", "--porcelain", "--force-with-lease=" + self.ref + ":" + (expected or ""),
                     self.remote, commit + ":" + self.ref)
        except subprocess.CalledProcessError as error:
            raise StateConflict("State push rejected (concurrent writer or protection); not retried") from error
        return commit

    def acquire(self, group, seal):
        if not GROUP.fullmatch(group) or not re.fullmatch(r"[0-9a-f]{64}", seal):
            raise ValueError("Invalid group or candidate seal")
        expected = self.head()
        ok, reason = self.available(expected, group)
        if not ok:
            raise StateConflict(reason)
        return self.commit(expected, {"publication/" + group + "/publishing.lock": (seal + "\n").encode()},
                           "Lock " + group + " for candidate " + seal)

    def release(self, group, seal, expected, receipts):
        """Record outcome receipts and drop the own lock in the same commit."""
        lock = "publication/" + group + "/publishing.lock"
        if self.files(expected).get(lock) != (seal + "\n").encode():
            raise StateConflict("Lock is not held for this candidate; keep it for review")
        changes = {"publication/" + group + "/" + name: content for name, content in receipts.items()}
        return self.commit(expected, changes, "Record " + group + " outcome for " + seal, removals=[lock])

    def export(self, sha, destination):
        """Materialize the store as a local draft cache root (for --prior-cache).

        State `publication/<group>/candidates/<seal>/<file>` becomes the local
        `<group>/<seal>/<file>` receipt layout; every other state file keeps its
        `publication/<group>/...` guard path.
        """
        destination = Path(destination)
        for path, content in self.files(sha).items():
            parts = path.split("/")
            if len(parts) == 5 and parts[2] == "candidates" and re.fullmatch(r"[0-9a-f]{64}", parts[3]):
                target = destination / parts[1] / parts[3] / parts[4]
            else:
                target = destination / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return destination
