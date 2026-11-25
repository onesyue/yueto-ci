"""Derive skip reasons from test source and report blob mismatches."""
from __future__ import annotations

import ast

from .config import (
    NEZHA_RETIRED_MODULE,
    ORDINARY_BINDING_KEYS,
    RETIRED_HOST_AFTER_BLOB,
    RETIRED_HOST_MODULE,
    RETIRED_HOST_SECOND_AFTER_BLOB,
    SHA,
    _SKIP_UNKNOWN,
)
from .skip_bindings import case_scope_successor, prepare_skip_bindings
from .support import RETIRED_HOST_SECOND_IDS


def _case_blob(case):
    if not isinstance(case, dict):
        return None
    blob = case.get("module_blob")
    if isinstance(blob, str) and SHA.fullmatch(blob):
        return blob
    return None


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _const_arg(call, index):
    if index >= len(call.args):
        return None
    arg = call.args[index]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    return None


def _docker_returncode(args):
    """Return code the central runner produces for one docker invocation.

    Docker and nginx are installed. A pinned image is not already loaded, and
    this precheck does not pull it: image inspect fails. info, run, and the
    other provisioning commands succeed.
    """
    if not args:
        return _SKIP_UNKNOWN
    if args[0] == "info":
        return 0
    if args[:2] == ["image", "inspect"]:
        return 1
    if args[0] in {"run", "rm", "exec", "build", "network", "cp", "pull"}:
        return 0
    return _SKIP_UNKNOWN


def _command_prefix(node, count):
    if not isinstance(node, ast.List) or len(node.elts) < count:
        return None
    values = []
    for item in node.elts[:count]:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        values.append(item.value)
    return values


def _positional_docker_code(call):
    first = _const_arg(call, 0)
    if first is None:
        return _SKIP_UNKNOWN
    second = _const_arg(call, 1)
    if second is None:
        return _docker_returncode([first])
    return _docker_returncode([first, second])


def _subprocess_docker_code(call):
    if not call.args:
        return _SKIP_UNKNOWN
    prefix = _command_prefix(call.args[0], 2)
    if prefix is None or prefix[0] != "docker":
        return _SKIP_UNKNOWN
    longer = _command_prefix(call.args[0], 3)
    return _docker_returncode((longer or prefix)[1:])


def _eval_call(node, env):
    dotted = _dotted(node.func)
    if dotted == "os.geteuid":
        return 0
    if dotted == "shutil.which":
        name = _const_arg(node, 0)
        if name in {"docker", "nginx"}:
            return "/usr/bin/" + name
        return _SKIP_UNKNOWN
    if dotted in {"os.environ.get", "os.getenv"}:
        key = _const_arg(node, 0)
        if key == "GITHUB_ACTIONS":
            return "true"
        if key in {"YUEOPS_RELEASE_ENV", "XRAY_PROBE_TEST_BIN", "TICKET_JOBS_TEST_DSN"}:
            return None
        return _SKIP_UNKNOWN
    if dotted in {"_docker", "docker"}:
        code = _positional_docker_code(node)
        return code if code is _SKIP_UNKNOWN else {"returncode": code}
    if dotted == "subprocess.run":
        code = _subprocess_docker_code(node)
        return code if code is _SKIP_UNKNOWN else {"returncode": code}
    if dotted == "os.uname":
        return {"sysname": "Linux"}
    if isinstance(node.func, ast.Attribute) and node.func.attr == "is_file":
        owner = node.func.value
        if isinstance(owner, ast.Name) and "SCHEMA" in owner.id:
            return True
        return _SKIP_UNKNOWN
    if isinstance(node.func, ast.Name) and not node.args and not node.keywords:
        return _call_function_return(node.func.id, env)
    return _SKIP_UNKNOWN


def _call_function_return(name, env):
    """Evaluate a zero-argument helper whose body is a single return."""
    if name in env["stack"]:
        return _SKIP_UNKNOWN
    function = env["functions"].get(name)
    if function is None:
        return _SKIP_UNKNOWN
    body = [stmt for stmt in function.body
            if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)]
    if len(body) != 1 or not isinstance(body[0], ast.Return):
        return _SKIP_UNKNOWN
    env["stack"].add(name)
    try:
        return _eval_skip_expr(body[0].value, env)
    finally:
        env["stack"].discard(name)


def _eval_name(node, env):
    if node.id not in env["values"]:
        return _SKIP_UNKNOWN
    value = env["values"][node.id]
    if isinstance(value, ast.AST):
        return _eval_skip_expr(value, env)
    return value


def _eval_attribute(node, env):
    if _dotted(node) == "sys.platform":
        return "linux"
    base = _eval_skip_expr(node.value, env)
    if isinstance(base, dict) and node.attr in base:
        return base[node.attr]
    return _SKIP_UNKNOWN


def _eval_not(node, env):
    value = _eval_skip_expr(node.operand, env)
    if value is _SKIP_UNKNOWN:
        return _SKIP_UNKNOWN
    return not value


def _eval_bool(node, env):
    values = [_eval_skip_expr(item, env) for item in node.values]
    if isinstance(node.op, ast.And):
        if any(value is False for value in values):
            return False
        if any(value is _SKIP_UNKNOWN for value in values):
            return _SKIP_UNKNOWN
        return all(value is True or value not in (False, _SKIP_UNKNOWN) and bool(value)
                   for value in values)
    if any(value is True for value in values):
        return True
    if any(value is _SKIP_UNKNOWN for value in values):
        return _SKIP_UNKNOWN
    return any(bool(value) for value in values)


def _eval_compare(node, env):
    if len(node.ops) != 1 or len(node.comparators) != 1:
        return _SKIP_UNKNOWN
    left = _eval_skip_expr(node.left, env)
    right = _eval_skip_expr(node.comparators[0], env)
    if left is _SKIP_UNKNOWN or right is _SKIP_UNKNOWN:
        return _SKIP_UNKNOWN
    op = node.ops[0]
    if isinstance(op, (ast.Eq, ast.Is)):
        return left == right
    if isinstance(op, (ast.NotEq, ast.IsNot)):
        return left != right
    return _SKIP_UNKNOWN


def _eval_skip_expr(node, env):
    """True/False when the central runner decides the expression, else unknown."""
    if node is None:
        return _SKIP_UNKNOWN
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return _eval_name(node, env)
    if isinstance(node, ast.Attribute):
        return _eval_attribute(node, env)
    if isinstance(node, ast.Call):
        return _eval_call(node, env)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _eval_not(node, env)
    if isinstance(node, ast.BoolOp):
        return _eval_bool(node, env)
    if isinstance(node, ast.Compare):
        return _eval_compare(node, env)
    return _SKIP_UNKNOWN


def _remember_assign(stmt, env):
    if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)):
        env["values"][stmt.targets[0].id] = _eval_skip_expr(stmt.value, env)


def _contains_direct_fail(stmts):
    for stmt in stmts:
        if isinstance(stmt, ast.Raise):
            return True
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and _dotted(stmt.value.func) == "pytest.fail"):
            return True
    return False


def _skip_calls(stmts):
    found = []
    for stmt in stmts:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Call) and _dotted(node.func) in {"pytest.skip", "pytest.xfail"}:
                found.append(node)
    return found


def _walk_skip_block(stmts, env, *, reached=True):
    """Record whether each pytest.skip/xfail in this block fires.

    False means the central runner does not reach it. None means the guard
    could not be decided, which the precheck treats as a skip it must report.
    """
    sites = []
    if not reached:
        return [False for _ in _skip_calls(stmts)]
    local = {"values": dict(env["values"]), "functions": env["functions"], "stack": env["stack"]}
    dominated = False
    for stmt in stmts:
        if dominated:
            sites.extend(False for _ in _skip_calls([stmt]))
            continue
        if isinstance(stmt, ast.Assign):
            _remember_assign(stmt, local)
            continue
        if isinstance(stmt, ast.If):
            sites.extend(_walk_skip_if(stmt, local))
            if _eval_skip_expr(stmt.test, local) is True and _contains_direct_fail(stmt.body):
                dominated = True
            continue
        if isinstance(stmt, ast.Try):
            sites.extend(_walk_skip_block(stmt.body, local))
            # A skip in an exception handler is a failed docker/postgres setup.
            # The validation runner's ordinary shards complete those fixtures.
            for handler in stmt.handlers:
                sites.extend(False for _ in _skip_calls(handler.body))
            sites.extend(_walk_skip_block(stmt.orelse, local))
            sites.extend(_walk_skip_block(stmt.finalbody, local))
            continue
        if isinstance(stmt, (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith)):
            sites.extend(_walk_skip_block(stmt.body, local))
            continue
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call) and _dotted(
                stmt.value.func) in {"pytest.skip", "pytest.xfail"}:
            sites.append(True)
    return sites


def _walk_skip_if(stmt, env):
    condition = _eval_skip_expr(stmt.test, env)
    if condition is True:
        return _walk_skip_block(stmt.body, env)
    if condition is False:
        return _walk_skip_block(stmt.orelse, env)
    if _skip_calls(stmt.body) or _skip_calls(stmt.orelse):
        return [None]
    return []


def _decorator_skip_sites(decorators, env):
    sites = []
    for decorator in decorators:
        if not isinstance(decorator, ast.Call):
            continue
        name = _dotted(decorator.func)
        if name == "pytest.mark.skip" or name == "pytest.mark.xfail" and not decorator.args:
            sites.append(True)
        elif name in {"pytest.mark.skipif", "pytest.mark.xfail"} and decorator.args:
            condition = _eval_skip_expr(decorator.args[0], env)
            sites.append(None if condition is _SKIP_UNKNOWN else bool(condition))
    return sites


def _module_mark_sites(tree, env):
    sites = []
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "pytestmark"
                   for target in stmt.targets):
            continue
        value = stmt.value
        marks = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
        sites.extend(_decorator_skip_sites(marks, env))
    return sites


def _fixture_names(function):
    names = [arg.arg for arg in function.args.args if arg.arg not in {"self", "cls"}]
    for decorator in function.decorator_list:
        if isinstance(decorator, ast.Call) and _dotted(decorator.func) == "pytest.mark.usefixtures":
            names.extend(arg.value for arg in decorator.args
                         if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
    return names


def _autouse(function):
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call) or _dotted(decorator.func) != "pytest.fixture":
            continue
        for keyword in decorator.keywords:
            if (keyword.arg == "autouse" and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is True):
                return True
    return False


def _index_functions(tree):
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name not in found:
            found[node.name] = node
    return found


def _reachable_functions(seeds, functions):
    queue = list(seeds)
    queue.extend(function for function in functions.values() if _autouse(function))
    seen = set()
    ordered = []
    while queue:
        function = queue.pop()
        if function.name in seen:
            continue
        seen.add(function.name)
        ordered.append(function)
        for name in _fixture_names(function):
            if name in functions:
                queue.append(functions[name])
        for node in ast.walk(function):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                callee = functions.get(node.func.id)
                if callee is not None:
                    queue.append(callee)
    return ordered


def central_runner_observes_skip(source, nodeid):
    """Whether the validation runner still skips or xfails this catalog case.

    That runner is Linux, root, and GitHub Actions, with Docker, nginx, and the
    yueboard schema checkout. XRAY_PROBE_TEST_BIN is unset, so an opt-in native
    probe still skips. A pinned image that a test only inspects is absent, so
    that skip still happens. Skips that require a missing docker binary, a
    non-root user, or a missing schema do not. GitHub Actions turns the locale
    image guard into a failure rather than a skip. Join never sees the skips
    this function rejects, so a stale catalog row is not a release blocker.
    """
    if not isinstance(source, str) or not source:
        return True
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return True
    functions = _index_functions(tree)
    env = {"values": {}, "functions": functions, "stack": set()}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            _remember_assign(stmt, env)
    test_name = nodeid.split("::")[-1].split("[", 1)[0]
    test = functions.get(test_name)
    if test is None:
        return True
    sites = _module_mark_sites(tree, env)
    for function in _reachable_functions([test], functions):
        sites.extend(_decorator_skip_sites(function.decorator_list, env))
        sites.extend(_walk_skip_block(function.body, env))
    return any(site is not False for site in sites)


def _ordinary_blobs(bound, nodeid):
    found = set()
    blob = _case_blob(bound["baseline"]["cases"].get(nodeid))
    if blob:
        found.add(blob)
    for key in ORDINARY_BINDING_KEYS:
        blob = _case_blob(bound[key].get(nodeid))
        if blob:
            found.add(blob)
    return found


def _retired_blob_admitted(bound, nodeid, live):
    retirement = bound.get("retirement")
    sealed = bound["sealed_baseline"]["cases"].get(nodeid)
    if retirement is None or not isinstance(sealed, dict):
        return False
    if nodeid not in retirement.get("surviving_ids", []):
        return False
    sealed_blob = sealed.get("module_blob")
    if live == sealed_blob:
        return True
    return (live == RETIRED_HOST_SECOND_AFTER_BLOB and nodeid not in RETIRED_HOST_SECOND_IDS
            and sealed_blob == RETIRED_HOST_AFTER_BLOB)


def _source_of(sources, module):
    if callable(sources):
        return sources(module)
    if isinstance(sources, dict):
        return sources.get(module)
    return None


def skip_blob_mismatch_lines(bound, live_blobs, sources, derivable=None):
    """Lines for catalog skips whose live module blob join would reject.

    Reviewed cases and collection skips are exact: the evidence join compares
    those blobs whenever the file is still in the tree. Ordinary and retired-host
    rows are reported only when the central runner still emits that skip.
    """
    live_blobs = live_blobs if isinstance(live_blobs, dict) else {}
    grouped = {}

    def add(module, old, new, nodeid):
        if derivable is not None and "::collection" not in nodeid and derivable(nodeid, old, new):
            return
        row = grouped.setdefault(module, {"olds": set(), "new": new, "ids": set()})
        if isinstance(old, str) and old:
            row["olds"].add(old)
        row["ids"].add(nodeid)

    for module, row in bound["baseline"].get("collection_skips", {}).items():
        live = live_blobs.get(module)
        expected = _case_blob(row)
        if live is None or expected is None or live == expected:
            continue
        add(module, expected, live, module + "::collection")
    reviewed = bound["reviewed"].get("cases", {})
    for nodeid, case in reviewed.items():
        module = nodeid.split("::", 1)[0]
        live = live_blobs.get(module)
        expected = _case_blob(case)
        if live is None or expected is None or live == expected:
            continue
        add(module, expected, live, nodeid)
    ordinary_ids = set(bound["baseline"]["cases"])
    for key in ORDINARY_BINDING_KEYS:
        ordinary_ids.update(bound[key])
    retirement = bound.get("retirement")
    for nodeid in ordinary_ids:
        if not isinstance(nodeid, str) or "::" not in nodeid or nodeid in reviewed:
            continue
        module = nodeid.split("::", 1)[0]
        live = live_blobs.get(module)
        if live is None or module == NEZHA_RETIRED_MODULE:
            continue
        if retirement is not None and module == RETIRED_HOST_MODULE:
            if _retired_blob_admitted(bound, nodeid, live):
                continue
            accepted = set()
            sealed_blob = _case_blob(bound["sealed_baseline"]["cases"].get(nodeid))
            if sealed_blob:
                accepted.add(sealed_blob)
        else:
            accepted = _ordinary_blobs(bound, nodeid)
        if live in accepted:
            continue
        source = _source_of(sources, module)
        if source is not None and not central_runner_observes_skip(source, nodeid):
            continue
        old = ",".join(sorted(accepted))
        add(module, old, live, nodeid)
    lines = []
    for module in sorted(grouped):
        row = grouped[module]
        old = ",".join(sorted(row["olds"])) if row["olds"] else "none"
        shown = ", ".join(sorted(row["ids"]))
        lines.append(f"{module}  {old} -> {row['new']}  ({shown})")
    return lines


def skip_blob_report(value, sources, *, policy=None, checkout=None):
    """Bind skips with join's successor order, then list blob mismatches."""
    prepare = prepare_skip_bindings if policy is None else policy.prepare_skip_bindings
    bound = prepare(
        value, {"obligations": {}}, require_native=False, check_shared_inputs=False)
    blobs = value.get("skip_module_blobs") if isinstance(value, dict) else {}
    derivable = None
    if checkout is not None:
        def derivable(nodeid, old, new):
            return case_scope_successor(checkout, nodeid, new, [{"module_blob": old}],
                                        lambda r: True) is not None
    return skip_blob_mismatch_lines(bound, blobs if isinstance(blobs, dict) else {}, sources,
                                    derivable)
