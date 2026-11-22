"""Resolve each planned image's validation from GitHub job conclusions."""
import importlib
import json
import os
import sys
from pathlib import Path


def results(builds, validations, jobs):
    by_name = {}
    for job in jobs:
        by_name.setdefault(job["name"], []).append(job)

    def completed(name):
        matches = by_name.get(name, [])
        if len(matches) == 1 and matches[0].get("status") == "completed":
            return matches[0]
        return {}

    def passed(job, service):
        if job.get("conclusion") == "success":
            return True
        if job.get("conclusion") != "failure" or not job.get("name", "").startswith("validate-yueops"):
            return False
        # Owned pytest failures in a shared Ops shard are re-raised by the
        # final per-owner steps. Setup, collection and shared failures stay red.
        failed = {s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"}
        owned = {"Owned pytest verdict for " + b["service"] for b in builds if b["validation"] == "yueops"}
        return bool(failed) and failed <= owned and "Owned pytest verdict for " + service not in failed

    groups = {}
    for row in validations:
        group = row["validation"]
        role = row.get("board_role") or row.get("ops_role") or row.get("node_profile")
        name = "validate-" + group
        if role and role != "legacy":
            name += "-" + role
        groups.setdefault(group, []).append(completed(name))
    services = {}
    for build in builds:
        service, group = build["service"], build["validation"]
        checks = groups.get(group, [])
        services[service] = bool(checks) and all(passed(job, service) for job in checks)
        if group == "yueops":
            services[service] &= completed("select-" + service).get("conclusion") == "success"
    shared_ops_ok = all(passed(job, "") for job in groups.get("yueops", []))
    return services, shared_ops_ok


if __name__ == "__main__":
    builds = json.loads(os.environ["BUILDS"]) or json.loads(os.environ["SELECTION"])
    if sys.argv[1] == "collect":
        shards = importlib.import_module("pytest-shards")
        admission = shards.envelope(json.loads(Path(sys.argv[2]).read_bytes()))
        if admission["admission_sha256"] != os.environ["ADMISSION_SHA256"]:
            raise ValueError("plan job admission digest differs")
        pages = json.load(sys.stdin)
        services, ok = results(builds, admission["validation_matrix"],
                               [job for page in pages for job in page["jobs"]])
        print("services=" + json.dumps(services))
        print("ops_result=" + ("success" if ok else "failure"))
    else:
        services = json.loads(os.environ["SERVICES"])
        for build in builds:
            if build["validation"] == "yueops" and os.environ["JOIN_RESULT"] != "success":
                services[build["service"]] = False
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a") as summary:
            for service, ok in services.items():
                print(f"- {service}: {'passed' if ok else 'blocked'}", file=summary)
        print("services=" + json.dumps(services))
