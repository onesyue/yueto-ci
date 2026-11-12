#!/usr/bin/env python3
"""Bind original image candidates to a new, independently validated evidence source.

This tool reads GitHub/registry authority. Local JSON is a comparison input, never
an authorization substitute. It does not dispatch, build, tag or deploy anything.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "onesyue/yueto-ci"
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
NUMBER = re.compile(r"[1-9][0-9]*")
OPS = {"yueops-web", "checkin-api", "yue-bot"}


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def sealed(value: dict, field="binding_sha256") -> dict:
    return value | {field: sha(canonical(value))}


def selected(service):
    require(service == "yueops" or service in OPS, "resume only supports explicit Ops services")
    return sorted(OPS if service == "yueops" else {service})


class GitHub:
    def raw(self, path):
        return subprocess.check_output(["gh", "api", "--method", "GET", f"repos/{REPOSITORY}/{path}"], timeout=60)

    def get(self, path):
        return json.loads(self.raw(path))

    def pages(self, path, field):
        result, total, ids = [], None, set()
        for page in range(1, 102):
            response = self.get(f"{path}?per_page=100&page={page}")
            count, rows = response.get("total_count"), response.get(field)
            require(type(count) is int and 0 <= count <= 10000 and isinstance(rows, list), "invalid paginated API response")
            require(total in (None, count), "API page count changed")
            total = count
            for row in rows:
                require(isinstance(row, dict) and type(row.get("id")) is int and row["id"] not in ids,
                        "duplicate or invalid API object")
                ids.add(row["id"])
                result.append(row)
            require(len(result) <= total, "API page exceeded declared count")
            if len(result) == total:
                return result
            require(len(rows) == 100, "incomplete API pagination")
        raise ValueError("API pagination exceeded bound")

    def policy_file(self, revision, path):
        value = self.get(f"contents/{path}?ref={revision}")
        require(value.get("encoding") == "base64", "policy object encoding differs")
        raw = base64.b64decode(value["content"])
        oid = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        require(oid == value.get("sha"), "policy blob identity differs")
        return raw

    def provenance(self, candidate):
        result = subprocess.run([
            "gh", "attestation", "verify", f"oci://{candidate['image']}@{candidate['digest']}",
            "--repo", REPOSITORY, "--bundle-from-oci", "--signer-workflow", "github.com/onesyue/yueto-ci/.github/workflows/build.yml",
            "--cert-oidc-issuer", "https://token.actions.githubusercontent.com",
            "--predicate-type", "https://slsa.dev/provenance/v1", "--format", "json",
        ], check=True, capture_output=True, text=True, timeout=180)
        verify_provenance(json.loads(result.stdout), candidate)


def verify_provenance(results, candidate):
    identities = set()
    for item in results if isinstance(results, list) else []:
        verified = item["verificationResult"]
        cert, statement = verified["signature"]["certificate"], verified["statement"]
        require(cert.get("buildSignerURI") == f"https://github.com/{REPOSITORY}/.github/workflows/build.yml@refs/heads/master"
                and cert.get("sourceRepositoryRef") == "refs/heads/master"
                and any(s.get("digest", {}).get("sha256") == candidate["digest"][7:]
                        for s in statement["subject"]), "verified original image provenance differs")
        invocation = re.fullmatch(rf"https://github.com/{REPOSITORY}/actions/runs/([1-9][0-9]*)/attempts/([1-9][0-9]*)",
                                  cert.get("runInvocationURI", ""))
        if invocation is None:
            raise ValueError("verified certificate has no original run identity")
        identities.add((invocation[1], invocation[2], cert.get("buildSignerDigest")))
    require(identities == {(candidate["run_id"], candidate["run_attempt"], candidate["workflow_sha"])},
            "verified provenance does not name the selected original build")


def attempt(api, run_id, run_attempt):
    require(NUMBER.fullmatch(run_id) and NUMBER.fullmatch(run_attempt), "invalid exact run or attempt")
    value = api.get(f"actions/runs/{run_id}/attempts/{run_attempt}")
    require(str(value.get("id")) == run_id and str(value.get("run_attempt")) == run_attempt
            and value.get("event") == "workflow_dispatch" and value.get("head_branch") == "master"
            and value.get("path") == ".github/workflows/build.yml" and SHA.fullmatch(value.get("head_sha", "")),
            "authoritative workflow run identity differs")
    jobs = api.pages(f"actions/runs/{run_id}/attempts/{run_attempt}/jobs", "jobs")
    for job in jobs:
        require(str(job.get("run_id")) == run_id and str(job.get("run_attempt", run_attempt)) == run_attempt
                and job.get("head_sha") == value["head_sha"], "job belongs to a different run/attempt/policy")
    return value, jobs


def successful_job(jobs, name):
    matches = [job for job in jobs if job.get("name") == name]
    require(len(matches) == 1 and matches[0].get("status") == "completed"
            and matches[0].get("conclusion") == "success", f"required job did not succeed: {name}")
    return matches[0]


def artifact(api, artifacts, name, run_id, policy, filenames):
    matches = [item for item in artifacts if item.get("name") == name]
    require(len(matches) == 1, "missing or duplicate exact artifact")
    item = matches[0]
    require(item.get("expired") is False and type(item.get("id")) is int
            and str(item.get("workflow_run", {}).get("id")) == run_id
            and item["workflow_run"].get("head_sha") == policy
            and DIGEST.fullmatch(item.get("digest", "")), "artifact authority is missing or differs")
    raw = api.raw(f"actions/artifacts/{item['id']}/zip")
    require(len(raw) <= 4 * 1024 * 1024 and "sha256:" + sha(raw) == item["digest"], "artifact archive digest differs")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        records = archive.infolist()
        require(len(records) == len(filenames) and {r.filename for r in records} == set(filenames)
                and all(r.file_size <= 2 * 1024 * 1024 for r in records), "unexpected artifact archive contents")
        values = {name: json.loads(archive.read(name)) for name in filenames}
    return values, {"id": item["id"], "name": name, "sha256": item["digest"]}


def exact_source(fp, source):
    evidence = load("source_evidence")

    class ExactGit(fp.LocalGit):
        def _git(self, *args):
            return evidence._git(self.repo, *args)

    return ExactGit(source)


def build_context(candidate, source, board, migration):
    require(SHA.fullmatch(board) and SHA.fullmatch(migration), "build context requires Board and migration identities")
    fp = load("input-fingerprint")
    entry = fp.load_services()[candidate["service"]]
    inputs = fp.compute(exact_source(fp, source), candidate["source_sha"], entry)
    recipe = fp.recipe(entry, (ROOT / ".github/workflows/build.yml").read_text())
    require(fp.compare(inputs, inputs) == "unchanged" and fp.compare(recipe, recipe) == "unchanged", "unprovable build inputs")
    return {"schema": 1, "status": "CANDIDATE_CONTEXT", "candidate": candidate,
            "board_revision": board, "migration_base": migration,
            "input_fingerprint": inputs["fingerprint"], "recipe_fingerprint": recipe["fingerprint"]}


def inspect(args, api=None):
    api = api or GitHub()
    services = selected(args.service)
    require(all(SHA.fullmatch(s or "") for s in (args.evidence_source, args.policy_sha, args.board, args.migration_base)),
            "resume identities must be exact commits")
    source_evidence = load("source_evidence")
    source_evidence.load(args.source, args.evidence_source)
    fp = load("input-fingerprint")
    git_source = exact_source(fp, args.source)
    current_entries = fp.load_services()
    run, jobs = attempt(api, args.build_run_id, args.build_attempt)
    require(run.get("status") == "completed", "original run is not complete")
    successful_job(jobs, "plan")
    artifacts = api.pages(f"actions/runs/{args.build_run_id}/artifacts", "artifacts")
    original_policy = run["head_sha"]
    old_entries = {e["service"]: e for e in json.loads(api.policy_file(original_policy, "services.json"))}
    old_workflow = api.policy_file(original_policy, ".github/workflows/build.yml").decode()
    current_workflow = (ROOT / ".github/workflows/build.yml").read_text()
    rows, original_sources = {}, set()
    for service in services:
        successful_job(jobs, f"candidate-{service}")
        payload, authority = artifact(api, artifacts, f"candidate-{args.build_run_id}-{args.build_attempt}-{service}",
                                      args.build_run_id, original_policy, {"candidate.json", "candidate-context.json"})
        candidate, context = payload["candidate.json"], payload["candidate-context.json"]
        expected = {"schema": 1, "service": service, "repository": "onesyue/yueops",
                    "source_sha": candidate.get("source_sha"), "workflow_sha": original_policy,
                    "run_id": args.build_run_id, "run_attempt": args.build_attempt,
                    "image": f"ghcr.io/onesyue/{service}", "digest": candidate.get("digest")}
        require(candidate == expected and SHA.fullmatch(candidate.get("source_sha", ""))
                and DIGEST.fullmatch(candidate.get("digest", "")), "original candidate receipt differs")
        require(not args.build_source or candidate["source_sha"] == args.build_source, "original source differs from request")
        original_sources.add(candidate["source_sha"])
        # Check raw original Git objects too; never allow replacement refs to invent inputs.
        source_evidence.tree_inputs(args.source, candidate["source_sha"])
        subprocess.run(["git", "--no-replace-objects", "-C", str(args.source), "merge-base", "--is-ancestor",
                        candidate["source_sha"], args.evidence_source], check=True, capture_output=True)
        old_inputs = fp.compute(git_source, candidate["source_sha"], old_entries[service])
        new_inputs = fp.compute(git_source, args.evidence_source, current_entries[service])
        old_recipe = fp.recipe(old_entries[service], old_workflow)
        new_recipe = fp.recipe(current_entries[service], current_workflow)
        require(fp.compare(old_inputs, new_inputs) == "unchanged" and fp.compare(old_recipe, new_recipe) == "unchanged",
                "original image inputs or recipe changed or are unknown")
        expected_context = {"schema": 1, "status": "CANDIDATE_CONTEXT", "candidate": candidate,
                            "board_revision": args.board, "migration_base": args.migration_base,
                            "input_fingerprint": old_inputs["fingerprint"], "recipe_fingerprint": old_recipe["fingerprint"]}
        require(context == expected_context, "original candidate context differs or is missing")
        api.provenance(candidate)
        rows[service] = {"source_revision": candidate["source_sha"], "digest": candidate["digest"],
                         "candidate": candidate, "artifact": authority, "input_fingerprint": new_inputs["fingerprint"]}
    require(len(original_sources) == 1, "original services do not share one source revision")
    return sealed({"schema": 1, "status": "RESUME_INPUTS_BOUND",
                   "original_build": {"run_id": args.build_run_id, "run_attempt": args.build_attempt,
                                      "source_revision": original_sources.pop(), "workflow_revision": original_policy},
                   "validation": {"run_id": None, "run_attempt": None, "source_revision": args.evidence_source,
                                  "policy_revision": args.policy_sha},
                   "services": rows, "board_revision": args.board, "migration_base": args.migration_base})


def request_from_binding(binding):
    require(isinstance(binding, dict), "binding is not an object")
    request = dict(binding)
    request.pop("binding_sha256", None)
    request.pop("request_sha256", None)
    request["validation"] = request["validation"] | {"run_id": None, "run_attempt": None}
    return sealed(request)


def prepare(args, api=None):
    request = inspect(args, api)
    run_id, run_attempt = os.environ.get("GITHUB_RUN_ID", ""), os.environ.get("GITHUB_RUN_ATTEMPT", "")
    require(NUMBER.fullmatch(run_id) and NUMBER.fullmatch(run_attempt) and run_id != args.build_run_id
            and os.environ.get("GITHUB_SHA") == args.policy_sha, "resume requires a new validation run identity")
    value = dict(request)
    value.pop("binding_sha256")
    value["request_sha256"] = request["binding_sha256"]
    value["validation"] = value["validation"] | {"run_id": run_id, "run_attempt": run_attempt}
    return sealed(value)


def check_binding(binding):
    copy = dict(binding)
    actual = copy.pop("binding_sha256", None)
    require(actual == sha(canonical(copy)) and binding.get("schema") == 1
            and binding.get("status") == "RESUME_INPUTS_BOUND", "resume binding digest or schema differs")
    request = request_from_binding(binding)
    require(binding.get("request_sha256", request["binding_sha256"]) == request["binding_sha256"], "resume request identity differs")
    return request


def validation_proof(api, binding, source):
    check_binding(binding)
    identity = binding["validation"]
    run_id, run_attempt, policy = identity["run_id"], identity["run_attempt"], identity["policy_revision"]
    run, jobs = attempt(api, run_id, run_attempt)
    require(run["head_sha"] == policy, "validation workflow differs")
    successful_job(jobs, "plan")
    successful_job(jobs, "validation-evidence")
    artifacts = api.pages(f"actions/runs/{run_id}/artifacts", "artifacts")
    documents, _ = artifact(api, artifacts, f"resume-binding-{run_id}-{run_attempt}", run_id, policy, {"resume-binding.json"})
    require(documents["resume-binding.json"] == binding, "authoritative plan binding differs")
    documents, _ = artifact(api, artifacts, f"ops-admission-{run_id}-{run_attempt}", run_id, policy, {"ops-admission.json"})
    admission = documents["ops-admission.json"]
    shards = load("pytest-shards")
    expected = dict(admission)
    admission_hash = expected.pop("admission_sha256", None)
    require(admission_hash == sha(shards.encoded(expected)) and admission.get("schema") == 1
            and admission.get("mode") == "sharded"
            and admission.get("source_revision") == identity["source_revision"]
            and admission.get("board_revision") == binding["board_revision"]
            and admission.get("identity") == {"policy_revision": policy, "run_id": run_id, "run_attempt": run_attempt},
            "canonical admission belongs to different validation inputs")
    plan = shards.validate_plan(admission["ops_plan"])
    roles = shards.role_order(plan)
    require(plan["source_revision"] == identity["source_revision"]
            and [row.get("ops_role") for row in admission["validation_matrix"]] == roles
            and all(row.get("repo") == "onesyue/yueops" and row.get("ref") == identity["source_revision"]
                    for row in admission["validation_matrix"]), "canonical role plan differs")
    require({j["name"] for j in jobs if j.get("name", "").startswith("validate-")}
            == {f"validate-yueops-{role}" for role in roles}, "missing or unexpected validation jobs")
    for role in roles:
        successful_job(jobs, f"validate-yueops-{role}")
    bound = load("source_evidence").load(source, identity["source_revision"])
    require(bound == admission.get("source_evidence"), "signed source evidence differs from complete join")
    filename = f"ops-validation-evidence-{run_id}-{run_attempt}.json"
    documents, authority = artifact(api, artifacts, f"ops-validation-evidence-{run_id}-{run_attempt}",
                                     run_id, policy, {filename})
    verdict = documents[filename]
    require(verdict.get("status") == "VALIDATION_MATRIX_COMPLETE" and verdict.get("mode") == "sharded"
            and verdict.get("admission_sha256") == admission_hash, "canonical join is incomplete or mismatched")
    return {"admission_sha256": admission_hash, "verdict_sha256": sha(canonical(verdict)),
            "verdict_artifact": authority}


def resolve(args, api=None):
    api = api or GitHub()
    binding = json.loads(args.binding.read_text())
    require(args.service in OPS and args.service in binding["services"], "service is outside resume binding")
    identity = binding["validation"]
    require(identity["run_id"] == os.environ.get("GITHUB_RUN_ID")
            and identity["run_attempt"] == os.environ.get("GITHUB_RUN_ATTEMPT")
            and identity["policy_revision"] == os.environ.get("GITHUB_SHA"), "publish runner differs from new validation")
    proof = validation_proof(api, binding, args.source)
    row = binding["services"][args.service]
    candidate = json.loads(args.candidate.read_text())
    require(candidate == row["candidate"], "downloaded original candidate differs from binding")
    api.provenance(candidate)
    return binding, proof, row


def publication(args, api=None):
    binding, proof, row = resolve(args, api)
    digest, revision = load("input-fingerprint").ghcr_latest(args.service, os.environ["GHCR_USER"], os.environ["GHCR_PASSWORD"])
    require((digest, revision) == (row["digest"], row["source_revision"]), "publication registry readback differs")
    return {"schema": 1, "status": "RESUME_PUBLICATION_BOUND", "service": args.service,
            "source_revision": revision, "digest": digest, "original_build": binding["original_build"],
            "validation": binding["validation"], "request_sha256": binding["request_sha256"],
            "binding_sha256": binding["binding_sha256"], **proof}


def verify_publication(args, api=None):
    api = api or GitHub()
    request = json.loads(args.binding.read_text())
    require(request == check_binding(request) and set(request["services"]) == set(selected(args.service))
            and request["validation"]["source_revision"] == args.evidence_source
            and request["validation"]["policy_revision"] == args.policy_sha, "caller request differs")
    original = request["original_build"]
    fresh_args = argparse.Namespace(**(vars(args) | {
        "build_run_id": original["run_id"], "build_attempt": original["run_attempt"],
        "build_source": original["source_revision"], "board": request["board_revision"],
        "migration_base": request["migration_base"],
    }))
    require(inspect(fresh_args, api) == request, "original authority changed or request was fabricated")
    value = dict(request)
    value.pop("binding_sha256")
    value["request_sha256"] = request["binding_sha256"]
    value["validation"] = value["validation"] | {"run_id": args.run_id, "run_attempt": args.attempt}
    binding = sealed(value)
    require(args.run_id != original["run_id"], "publication did not use a new validation run")
    proof = validation_proof(api, binding, args.source)
    run, jobs = attempt(api, args.run_id, args.attempt)
    require(run["head_sha"] == args.policy_sha, "new publication workflow differs")
    artifacts = api.pages(f"actions/runs/{args.run_id}/artifacts", "artifacts")
    services = {}
    for service, row in request["services"].items():
        job = successful_job(jobs, service)
        documents, _ = artifact(api, artifacts, f"resume-publication-{args.run_id}-{args.attempt}-{service}",
                                 args.run_id, args.policy_sha, {"resume-publication.json"})
        expected = {"schema": 1, "status": "RESUME_PUBLICATION_BOUND", "service": service,
                    "source_revision": row["source_revision"], "digest": row["digest"],
                    "original_build": original, "validation": binding["validation"],
                    "request_sha256": request["binding_sha256"], "binding_sha256": binding["binding_sha256"], **proof}
        require(documents["resume-publication.json"] == expected, "publication receipt differs")
        services[service] = {"source_revision": row["source_revision"], "digest": row["digest"], "publish_job_id": job["id"]}
    return {"schema": 1, "status": "RESUME_PUBLICATION_BOUND", "original_build": original,
            "validation": binding["validation"], "publication": {"run_id": args.run_id, "run_attempt": args.attempt,
                                                                  "workflow_revision": args.policy_sha},
            "request_sha256": request["binding_sha256"], "binding_sha256": binding["binding_sha256"],
            "services": services, **proof}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("context", "inspect", "prepare", "resolve", "publication", "verify-publication"))
    parser.add_argument("--source", type=Path, required=True)
    for name in ("build-run-id", "build-attempt", "build-source", "evidence-source", "policy-sha", "service", "board", "migration-base", "run-id", "attempt"):
        parser.add_argument("--" + name)
    for name in ("binding", "candidate", "output"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    if args.command == "context":
        value = build_context(json.loads(args.candidate.read_text()), args.source, args.board, args.migration_base)
    elif args.command in ("inspect", "prepare"):
        value = inspect(args) if args.command == "inspect" else prepare(args)
    elif args.command == "resolve":
        _, _, row = resolve(args)
        print("digest=" + row["digest"])
        return
    elif args.command == "publication":
        value = publication(args)
    else:
        value = verify_publication(args)
    raw = json.dumps(value, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x") as stream:
            stream.write(raw)
    else:
        print(raw, end="")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        raise SystemExit(f"resume binding refused: {error}") from error
