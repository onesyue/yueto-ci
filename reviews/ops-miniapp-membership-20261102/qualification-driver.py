#!/usr/bin/env python3
"""Re-run the qualification: pytest of every yueops test importing tests/_miniapp_source.py at the release revision."""
import subprocess, sys
rev = sys.argv[1] if len(sys.argv) > 1 else "157f1559a171399cbff242149ad0634bd7f1c9d3"
files = subprocess.check_output(["git", "ls-files", "tests"], text=True).split()
tests = [f for f in files if "/test_" in f and "_miniapp_source" in open(f, encoding="utf-8").read()]
sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *tests]))
