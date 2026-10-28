"""I33 A03: bind the actual CI generator to the shared valid manifest vector.

CI has no manifest validator. Invalid-vector consumer checks remain a follow-up;
this test exercises generation rather than inventing a production validator.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "testdata/ui-manifest-vectors.json"
DATA = json.loads(CORPUS.read_text())


def test_manifest_vector_agreement():
    assert DATA["schema_version"] == 1
    assert len(DATA["vectors"]) >= 20
    assert hashlib.sha256(CORPUS.read_bytes()).hexdigest() == CORPUS.with_suffix(".sha256").read_text().split()[0]
    spec = importlib.util.spec_from_file_location("manifest_vector_ui_units", ROOT / "scripts/ui_static_units.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = next(case["manifest"] for case in DATA["vectors"] if case["id"] == "ci-list")
    # Execute unmodified production JS in a sandbox. No /out writes or image build.
    harness = r"""
const vm = require('vm');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const files = input.files;
const fs = {
  readdirSync(dir) {
    if (dir !== 'dist') throw Error('unexpected directory ' + dir);
    return Object.keys(files).reverse();
  },
  statSync() { return {isDirectory: () => false}; },
  readFileSync(name) {
    if (name === 'ui-requires.json') return JSON.stringify({requires_backend: ['v1']});
    const rel = name.replace(/^dist\//, '');
    if (!(rel in files)) throw Error('missing fixture ' + name);
    return Buffer.from(files[rel]);
  },
  mkdirSync(name) { if (name !== '/out') throw Error('unexpected output'); },
  writeFileSync(name, body) {
    if (name !== '/out/ui-manifest.json') throw Error('unexpected manifest');
    process.stdout.write(body);
  },
};
vm.runInNewContext(input.script, {
  require(name) { return name === 'fs' ? fs : require(name); },
  process: {env: {COMMIT: input.revision}, exit(code) { throw Error('exit ' + code); }},
  console,
});
"""
    result = subprocess.run(
        ["node", "-e", harness],
        input=json.dumps({"files": DATA["fixture_files"], "script": module._manifest_script(),
                          "revision": expected["source_revision"]}),
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
