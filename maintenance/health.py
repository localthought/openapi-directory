"""Dated GitHub repository observations, independent of API content comparisons."""
import copy
import hashlib
import json
import re


class Checker:
    def __init__(self, request, now, cache):
        self.request, self.now, self.cache = request, now, cache
        self.observations = {}

    def check(self, source):
        if "github" not in source:
            return {"source_health": "not_assessed", "source_health_check": {
                "status": "not_assessed",
                "scope": "Hosted source; repository health checks do not apply."
            }}
        repository = source["github"]["repository"]
        key = repository.casefold()
        if key not in self.observations:
            self.observations[key] = self.repository(repository)
        # Several services can share a repository; callers must not mutate its
        # shared observation, and failures must also fetch only once per run.
        return copy.deepcopy(self.observations[key])

    def repository(self, repository):
        observation = {"status": "failed", "checked_at": self.now(),
                       "configured_repository": repository,
                       "scope": "GitHub repository availability and identity only; vendor ownership, "
                                "artifact maintenance and current API coverage still require review."}
        result = {"source_health": "check_failed", "source_health_check": observation}
        try:
            if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository)
                    or any(part in {".", ".."} for part in repository.split("/"))):
                raise ValueError("Invalid GitHub repository name")
            url = "https://api.github.com/repos/" + repository
            raw, metadata = self.request(url)
            digest = hashlib.sha256(raw).hexdigest()
            snapshot = "source-health/" + repository + "/" + digest
            directory = self.cache / snapshot
            directory.mkdir(parents=True, exist_ok=True)
            directory.joinpath("repository.json").write_bytes(raw)
            evidence = {**metadata, "sha256": digest, "checked_at": observation["checked_at"]}
            directory.joinpath("fetch.json").write_text(json.dumps(evidence, indent=2) + "\n")
            observation.update(evidence, snapshot=snapshot)
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Repository metadata is not an object")
            name = data.get("full_name")
            owner = data.get("owner", {}).get("login") if isinstance(data.get("owner"), dict) else None
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name)
                    or not isinstance(owner, str) or owner.casefold() != name.split("/")[0].casefold()):
                raise ValueError("Repository identity is missing or inconsistent")
            for field in ("archived", "disabled", "private", "fork"):
                if type(data.get(field)) is not bool:
                    raise ValueError("Repository metadata must declare boolean " + field)
            if data["private"]:
                raise ValueError("Configured official source is not a public repository")
            if not isinstance(data.get("default_branch"), str) or not data["default_branch"]:
                raise ValueError("Repository default branch is missing")
            observation.update(status="checked", full_name=name, owner=owner,
                               **{field: data.get(field) for field in (
                                   "archived", "disabled", "private", "fork", "default_branch",
                                   "pushed_at", "updated_at")})
            # Recent pushed_at / updated_at dates are observations, not proof
            # that this particular description is maintained or complete.
            if name.casefold() != repository.casefold():
                state, issue = "identity_changed", "Official source repository redirected to " + name + "; review ownership before importing."
            elif data["disabled"]:
                state, issue = "disabled", "Official source repository is disabled; review a maintained replacement before importing."
            elif data["archived"]:
                state, issue = "archived", "Official source repository is archived; current API coverage is uncertain."
            else:
                state, issue = "repository_available", None
            result.update(source_health=state, last_successful_source_health_check=observation["checked_at"])
            if issue:
                result["source_health_issue"] = issue
        except Exception as error:
            observation["error"] = str(error)
            result["source_health_issue"] = "Source-health check failed: " + str(error)
        return result
