#!/usr/bin/env python3
"""Measure a Git checkout against its reviewed complexity and dead-code budgets."""

import argparse
import json
import subprocess
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path

BASELINE = ".quality/complexity-baseline.json"
LIMITS = {"ccn": 30, "nloc": 200}
DEAD_CODE = ("go", "python")
EXTENSIONS = {".py", ".go", ".ts", ".tsx", ".dart"}
EXCLUDED_DIRS = {".venv", "venv", "vendor", "node_modules", ".dart_tool"}


@dataclass(frozen=True)
class Function:
    metrics: dict[str, int]
    fingerprint: str


def run(repo, *command):
    return subprocess.run(command, cwd=repo, check=True, stdout=subprocess.PIPE).stdout


def functions(path, source):
    import lizard

    lines = source.splitlines(keepends=True)
    occurrences = Counter()
    for function in lizard.analyze_file.analyze_source_code(path, source).function_list:
        name = function.long_name
        occurrences[name] += 1
        key = f"{path}::{name}#{occurrences[name]}"
        body = "".join(lines[function.start_line - 1 : function.end_line])
        yield (
            key,
            Function(
                {"ccn": function.cyclomatic_complexity, "nloc": function.nloc},
                sha256(body.encode()).hexdigest(),
            ),
        )


def over_limit(metrics):
    return any(metrics[name] > limit for name, limit in LIMITS.items())


def compare(current, previous, dead, baseline):
    violations = []
    for key, function in current.items():
        budget = baseline["functions"].get(key)
        if budget is not None:
            for metric, value in function.metrics.items():
                if value > budget[metric]:
                    violations.append(
                        f"{key}: {metric} grew from {budget[metric]} to {value}"
                    )
        elif over_limit(function.metrics) and function != previous.get(key):
            violations.append(
                f"{key}: new or changed function exceeds limits {function.metrics}"
            )
    for language, count in dead.items():
        budget = baseline["dead_code"][language]
        if count > budget:
            violations.append(f"{language} dead code grew from {budget} to {count}")
    return violations


def shrink(current, dead, baseline):
    return {
        "functions": {
            key: {
                metric: min(value, budget[metric])
                for metric, value in current[key].metrics.items()
            }
            for key, budget in baseline["functions"].items()
            if key in current and over_limit(current[key].metrics)
        },
        "dead_code": {
            language: min(count, baseline["dead_code"][language])
            for language, count in dead.items()
        },
    }


def validate_baseline(raw):
    baseline = json.loads(raw)
    if not isinstance(baseline, dict) or set(baseline) != {"functions", "dead_code"}:
        raise ValueError("expected functions and dead_code baseline objects")

    def validate_counts(counts, keys):
        if not isinstance(counts, dict) or set(counts) != set(keys):
            raise ValueError(f"expected baseline counters {', '.join(keys)}")
        if any(type(value) is not int or value < 0 for value in counts.values()):
            raise ValueError("baseline counters must be nonnegative integers")

    if not isinstance(baseline["functions"], dict):
        raise TypeError("expected function budgets object")
    for metrics in baseline["functions"].values():
        validate_counts(metrics, LIMITS)
    validate_counts(baseline["dead_code"], DEAD_CODE)
    return baseline


def usable_path(path):
    return not EXCLUDED_DIRS.intersection(Path(path).parts)


def tracked_paths(repo):
    output = run(repo, "git", "ls-files", "-z")
    return sorted(
        {path for path in output.decode().split("\0") if path and usable_path(path)}
    )


def read_source(repo, path):
    if Path(path).suffix == ".py":
        with tokenize.open(repo / path) as source:
            return source.read()
    return (repo / path).read_text(encoding="utf-8")


def count_dead_code(repo, paths, sources):
    from vulture import Vulture
    from vulture.utils import ExitCode

    scanner = Vulture()
    for path, source in sources.items():
        if Path(path).suffix == ".py":
            scanner.scan(source, filename=path)
    if scanner.exit_code != ExitCode.NoDeadCode:
        raise ValueError("vulture could not scan all Python files")

    go_files = {Path(path) for path in sources if Path(path).suffix == ".go"}
    modules = {Path(path).parent for path in paths if Path(path).name == "go.mod"}
    targets = [(repo / module, "./...") for module in sorted(modules)]
    targets.extend(
        (repo, f"./{path.as_posix()}")
        for path in sorted(go_files)
        if modules.isdisjoint(path.parents)
    )
    tracked_go = {repo / path for path in go_files}
    dead_go = set()
    for directory, target in targets:
        packages = json.loads(run(directory, "deadcode", "-test", "-json", target))
        for package in packages or []:
            for function in package["Funcs"]:
                position = function["Position"]
                file = directory / position["File"]
                if file in tracked_go:
                    dead_go.add((file, position["Line"], position["Col"]))
    return {
        "go": len(dead_go),
        "python": len(scanner.get_unused_code(min_confidence=100)),
    }


def previous_functions(repo, base, candidates):
    if not candidates:
        return {}
    tree = run(repo, "git", "ls-tree", "-r", "--name-only", "-z", base)
    base_paths = set(tree.decode().split("\0"))
    previous = {}
    for path in sorted(candidates & base_paths):
        raw = run(repo, "git", "show", f"{base}:{path}")
        encoding = "utf-8"
        if Path(path).suffix == ".py":
            encoding, _ = tokenize.detect_encoding(BytesIO(raw).readline)
        source = raw.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
        previous.update(functions(path, source))
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="root of the target Git checkout")
    parser.add_argument("--base", help="comparison commit, default HEAD")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--init-baseline",
        action="store_true",
        help="create the first reviewed baseline",
    )
    mode.add_argument(
        "--update-baseline",
        action="store_true",
        help="remove or shrink existing budgets",
    )
    args = parser.parse_args()

    try:
        repo = args.repo.resolve()
        if (
            Path(run(repo, "git", "rev-parse", "--show-toplevel").decode().strip())
            != repo
        ):
            raise ValueError("repo must be the root of the target Git checkout")
        baseline_path = repo / BASELINE
        if args.init_baseline or args.update_baseline:
            if args.init_baseline and baseline_path.exists():
                raise ValueError("baseline already exists")
            baseline = (
                validate_baseline(baseline_path.read_bytes())
                if args.update_baseline
                else None
            )
        else:
            base = (
                run(
                    repo,
                    "git",
                    "rev-parse",
                    "--verify",
                    "--end-of-options",
                    f"{args.base or 'HEAD'}^{{commit}}",
                )
                .decode()
                .strip()
            )
            entries = run(repo, "git", "ls-tree", base, "--", BASELINE)
            if not entries:
                raise ValueError(
                    f"missing {BASELINE} in comparison commit {base}; initialize and review it"
                )
            baseline = validate_baseline(run(repo, "git", "show", f"{base}:{BASELINE}"))

        paths = tracked_paths(repo)
        sources = {
            path: read_source(repo, path)
            for path in paths
            if Path(path).suffix in EXTENSIONS and not (repo / path).is_symlink()
        }
        if not sources:
            raise ValueError("no supported tracked source files")
        by_path = {
            path: dict(functions(path, source)) for path, source in sources.items()
        }
        current = {
            key: value
            for measured in by_path.values()
            for key, value in measured.items()
        }
        dead = count_dead_code(repo, paths, sources)
        print(
            f"Scanned {len(sources)} files, {len(current)} functions, dead code {dead}"
        )

        if args.init_baseline:
            updated = {
                "functions": {
                    key: function.metrics
                    for key, function in current.items()
                    if over_limit(function.metrics)
                },
                "dead_code": dead,
            }
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with baseline_path.open("x") as output:
                output.write(json.dumps(updated, indent=2, sort_keys=True) + "\n")
        elif args.update_baseline:
            updated = shrink(current, dead, baseline)
            baseline_path.write_text(
                json.dumps(updated, indent=2, sort_keys=True) + "\n"
            )
        else:
            candidates = {
                path
                for path, measured in by_path.items()
                if any(
                    key not in baseline["functions"] and over_limit(function.metrics)
                    for key, function in measured.items()
                )
            }
            violations = compare(
                current, previous_functions(repo, base, candidates), dead, baseline
            )
            for violation in violations:
                print(violation)
            return int(bool(violations))
    except (
        OSError,
        ValueError,
        subprocess.CalledProcessError,
        ImportError,
        KeyError,
        TypeError,
    ) as error:
        print(f"Quality ratchet could not complete: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
