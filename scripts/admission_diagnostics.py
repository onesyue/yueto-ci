"""Stable, single-line admission diagnostics for local callers and Actions."""
import os
import sys
from pathlib import Path


def rejection(reason):
    line = "ADMISSION_REJECTED: " + " ".join(str(reason).split())
    if os.environ.get("GITHUB_ACTIONS") == "true":
        escaped = line.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print("::error::" + escaped, file=sys.stderr)
    else:
        print(line, file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a") as stream:
            stream.write(line + "\n")
