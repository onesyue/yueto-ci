# Shared-input source review

Reviewer: Codex main agent, independent of the source PR authors.

The shared helper diff adds only deploy_ai_exit.py to DEPLOY_BACKEND. The full
helper retains its exact disk-membership check, line-count floor, source reading
and AST function extraction. No skip, collection, import, subprocess or network
behavior changes. The registered module contains ordinary role-selection
functions and imports only re; registering its path does not import it.
The successor expands the scan surface to match the newly extracted module.

Scope: exact shared-input admission only; no full execution or production acceptance claimed.

VERDICT: APPROVE
