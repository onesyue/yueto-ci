"""Read workflow shell contracts through their actual shared script entrypoints."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def workflow_text(path=None):
    path = path or ROOT / '.github/workflows/build.yml'
    text = Path(path).read_text(encoding='utf-8')
    pattern = r'^          bash "\$GITHUB_WORKSPACE/\.ci-policy/(scripts/ops-validation-[a-z-]+\.sh)"$'

    def expand(match):
        script = (ROOT / match.group(1)).read_text(encoding='utf-8')
        if script.startswith('#!/bin/bash\n# Shared by build.yml'):
            script = '\n'.join(script.splitlines()[2:])
        return '\n'.join('          ' + line if line else '' for line in script.splitlines())

    return re.sub(pattern, expand, text, flags=re.MULTILINE)
