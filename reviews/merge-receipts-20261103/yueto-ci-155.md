# yueto-ci #155 review at fb0b231f791716508bd758ed98675261a8e94b54

VERDICT: approve   (or VERDICT: changes)
followed by concise bullet findings with file:line.
codex
I’ll review the exact commit diff and read surrounding code where needed to check for bugs and regressions, without modifying files or printing secret values.
exec
/bin/bash -lc 'git diff --stat f21fb3fada4aed33685dcac9bfbda6c16291709b fb0b231f791716508bd758ed98675261a8e94b54 && git diff --name-only f21fb3fada4aed33685dcac9bfbda6c16291709b fb0b231f791716508bd758ed98675261a8e94b54' in /home/box/Projects/yueto/yueto-ci
 succeeded in 0ms:
 scripts/pytest-shards.py         | 13 +++++++++-
 tests/test_ops_shard_workflow.py | 55 ++++++++++++++++++++++++++++++++++++++++
 2 files changed, 67 insertions(+), 1 deletion(-)
scripts/pytest-shards.py
tests/test_ops_shard_workflow.py

exec
/bin/bash -lc "rg --files -g AGENTS.md -g '"'!node_modules'"' -g '"'!vendor'"'" in /home/box/Projects/yueto/yueto-ci
 exited 1 in 0ms:
exec
/bin/bash -lc 'git diff f21fb3fada4aed33685dcac9bfbda6c16291709b fb0b231f791716508bd758ed98675261a8e94b54 -- scripts/pytest-shards.py tests/test_ops_shard_workflow.py' in /home/box/Projects/yueto/yueto-ci
 succeeded in 0ms:
diff --git a/scripts/pytest-shards.py b/scripts/pytest-shards.py
index daf7587..b3a158d 100755
--- a/scripts/pytest-shards.py
+++ b/scripts/pytest-shards.py
@@ -2848,6 +2848,16 @@ def map_bounded(functions, limit):
         return list(pool.map(lambda fn: fn(), functions))
 
 
+def shard_pythonpath(source, site):
+    """Expose the recorder and admitted source to pytest and its children.
+
+    Use only absolute, policy-selected entries: inherited/relative entries
+    would change meaning when a test launches Python from telegram-bot/yue.
+    Keep the verified recorder first, including each reference part's copy.
+    """
+    return os.pathsep.join(str(path.resolve()) for path in (site, source))
+
+
 def _collect_reference_part(expected, source, output, site, actual_runner, timing, assignment):
     part = output / "parts" / assignment["id"]
     site = part / "site"
