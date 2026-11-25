"""Load one historical pytest-shards policy and run the skip-blob precheck."""
from __future__ import annotations

import inspect
import subprocess
import sys
import tempfile
import types
from pathlib import Path

from . import skip_bindings
from .config import SHA, _POLICY_HELPERS
from .skip_bindings import load_ops_skip_evidence, prepare_skip_bindings
from .support import (
    EvidenceUnavailable,
    ROOT,
    git,
    require,
    safe_module,
    source_evidence,
    tree_inputs,
)

# Load order matches the package import graph. A historical binder is executed
# with this checkout's module paths so its seals stay the current files.
_PACKAGE_ORDER = (
    "config",
    "support",
    "timing",
    "sharding",
    "transitions_relay",
    "transitions_native",
    "transitions_estate",
    "transitions_pr",
    "transitions_admit",
    "skip_baseline",
    "collection",
    "reporting",
    "skip_bindings",
    "skip_report",
    "policy_history",
    "cli",
)


def _package_entry(source):
    return b"def plan(" not in source and b"pytest_shards.cli" in source


def _load_historical_package(repo, revision):
    """Execute scripts/pytest_shards at one revision against this checkout's seals."""
    try:
        listing = git(
            repo, "ls-tree", "-r", "--name-only", revision, "scripts/pytest_shards").decode()
    except subprocess.CalledProcessError as error:
        raise ValueError("historical pytest-shards policy is not in this clone") from error
    sources = {}
    for relative in listing.splitlines():
        if not relative.endswith(".py"):
            continue
        name = relative.removeprefix("scripts/pytest_shards/")[:-3]
        if not name or "/" in name:
            continue
        try:
            sources[name] = git(repo, "show", f"{revision}:{relative}")
        except subprocess.CalledProcessError as error:
            raise ValueError("historical pytest-shards policy is not in this clone") from error
    if "skip_bindings" not in sources:
        raise ValueError("historical pytest-shards package is not in this clone")
    pkg_name = "skip_blob_policy_" + revision
    package = types.ModuleType(pkg_name)
    package.__package__ = pkg_name
    package.__path__ = []
    package.__file__ = str(ROOT / "scripts" / "pytest_shards" / "__init__.py")
    sys.modules[pkg_name] = package
    if "__init__" in sources:
        exec(compile(sources["__init__"], package.__file__, "exec"), package.__dict__)
    current = ROOT / "scripts" / "pytest_shards"
    order = [name for name in _PACKAGE_ORDER if name in sources]
    order.extend(name for name in sources if name not in order and name != "__init__")
    for name in order:
        mod_name = pkg_name + "." + name
        module = types.ModuleType(mod_name)
        module.__name__ = mod_name
        module.__package__ = pkg_name
        module.__file__ = str(current / f"{name}.py")
        sys.modules[mod_name] = module
        setattr(package, name, module)
        try:
            exec(compile(sources[name], module.__file__, "exec"), module.__dict__)
        except SyntaxError as error:
            raise ValueError("historical pytest-shards policy is unreadable") from error
    binder = package.skip_bindings
    if "prepare_skip_bindings" not in binder.__dict__:
        binder.__dict__["inspect"] = inspect
        for name in _POLICY_HELPERS:
            exec(inspect.getsource(getattr(skip_bindings, name)), binder.__dict__)
    return binder


_TREE_SEQ = 0


def load_policy_tree(scripts_dir):
    """Execute an on-disk pytest_shards tree. Module paths stay inside that tree."""
    global _TREE_SEQ
    scripts_dir = Path(scripts_dir)
    pkg_dir = scripts_dir / "pytest_shards"
    sources = {path.stem: path.read_bytes() for path in pkg_dir.glob("*.py")}
    if "skip_bindings" not in sources:
        raise ValueError("pytest_shards package is not in this tree")
    _TREE_SEQ += 1
    pkg_name = f"pytest_shards_tree_{_TREE_SEQ}"
    package = types.ModuleType(pkg_name)
    package.__package__ = pkg_name
    package.__path__ = [str(pkg_dir)]
    package.__file__ = str(pkg_dir / "__init__.py")
    sys.modules[pkg_name] = package
    if "__init__" in sources:
        exec(compile(sources["__init__"], package.__file__, "exec"), package.__dict__)
    order = [name for name in _PACKAGE_ORDER if name in sources]
    order.extend(name for name in sources if name not in order and name != "__init__")
    for name in order:
        mod_name = pkg_name + "." + name
        module = types.ModuleType(mod_name)
        module.__name__ = mod_name
        module.__package__ = pkg_name
        module.__file__ = str(pkg_dir / f"{name}.py")
        sys.modules[mod_name] = module
        setattr(package, name, module)
        exec(compile(sources[name], module.__file__, "exec"), module.__dict__)
    return package


def load_policy_module(ci_revision, checkout=None):
    """Return the current skip binder, or policy as of one historical ci revision.

    The checked-out baseline JSON is what join reads. A historical script is
    executed with this checkout's file path so those seals stay the current
    ones, while its successor functions stay the ones that revision shipped.
    Helper functions that did not exist yet are installed into that module so
    both paths call one binder. A revision that stores the package is loaded
    from ``scripts/pytest_shards`` the same way. ``checkout`` defaults to this
    repository. A revision this clone does not contain is an input error.
    """
    if ci_revision in (None, ""):
        return skip_bindings
    require(isinstance(ci_revision, str) and SHA.fullmatch(ci_revision),
            "skip-blob-precheck requires an exact ci revision")
    repo = ROOT if checkout is None else checkout
    try:
        source = git(repo, "show", f"{ci_revision}:scripts/pytest-shards.py")
    except subprocess.CalledProcessError as error:
        raise ValueError("historical pytest-shards policy is not in this clone") from error
    if _package_entry(source):
        return _load_historical_package(repo, ci_revision)
    path = Path(tempfile.mkdtemp(prefix="skip-blob-policy-")) / "pytest-shards.py"
    path.write_bytes(source)
    module = types.ModuleType("skip_blob_policy_" + ci_revision[:12])
    module.__file__ = str(ROOT / "scripts" / "pytest-shards.py")
    module.__dict__["__file__"] = module.__file__
    try:
        exec(compile(source, str(path), "exec"), module.__dict__)
    except SyntaxError as error:
        raise ValueError("historical pytest-shards policy is unreadable") from error
    if "prepare_skip_bindings" not in module.__dict__:
        module.__dict__["inspect"] = inspect
        for name in _POLICY_HELPERS:
            exec(inspect.getsource(getattr(skip_bindings, name)), module.__dict__)
    return module


def skip_blob_precheck(checkout, revision, *, ci_revision=None):
    """Prove an ops commit is readable. A changed module blob is not a skip rejection.

    validation-evidence admits a skip or xfail that carries a non-empty reason.
    This command fails a missing commit, a historical policy commit that is not
    in this clone, or ops-commit skip evidence that is malformed or does not
    succeed an admitted skip. It does not reject a blob that has no successor seal.
    """
    require(isinstance(revision, str) and SHA.fullmatch(revision),
            "skip-blob-precheck requires an exact ops revision")
    if ci_revision:
        load_policy_module(ci_revision)
    files = tree_inputs(checkout, revision)
    if not ci_revision:
        bound = source_evidence.optional(checkout, revision)
        if bound is not None:
            source_evidence.validate_baseline(
                bound, {path: blob for path, (_, blob) in files.items()})
    record = load_ops_skip_evidence(checkout, revision)
    if record is None:
        return []
    # The release pin lived in the retired first-native seal. Skip admission
    # does not consult it, including when the binder is a historical module.
    blobs = {path: blob for path, (mode, blob) in files.items() if safe_module(path)}
    value = {
        "skip_module_blobs": blobs,
        "source_revision": revision,
        "pin_is_ancestor": False,
        "ops_skip_evidence": record,
    }
    prepare_skip_bindings(value, {"obligations": {}}, require_native=False,
                          check_shared_inputs=False)
    return []


def skip_blob_precheck_command(args):
    """Read-only precheck. Exit 2 on a usage or input error. A blob change is not a miss."""
    revision = getattr(args, "ops_rev", None)
    ci_revision = getattr(args, "ci_rev", None)
    checkout = getattr(args, "ops_checkout", None)
    if not isinstance(revision, str) or not SHA.fullmatch(revision):
        print("skip-blob-precheck: --ops-rev must be a 40-character commit", file=sys.stderr)
        return 2
    if ci_revision not in (None, "") and not (isinstance(ci_revision, str) and SHA.fullmatch(ci_revision)):
        print("skip-blob-precheck: --ci-rev must be a 40-character commit", file=sys.stderr)
        return 2
    if not isinstance(checkout, Path) or not checkout.is_dir():
        print("skip-blob-precheck: --ops-checkout is not a directory", file=sys.stderr)
        return 2
    try:
        lines = skip_blob_precheck(checkout, revision, ci_revision=ci_revision or None)
    except subprocess.CalledProcessError:
        print("skip-blob-precheck: git could not read the ops checkout", file=sys.stderr)
        return 2
    except (EvidenceUnavailable, ValueError, OSError) as error:
        print("skip-blob-precheck: " + str(error), file=sys.stderr)
        return 2
    if lines:
        print("\n".join(lines))
        return 1
    print("skip-blob-precheck ok")
    return 0
