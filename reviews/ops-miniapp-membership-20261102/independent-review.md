- Helper diff registers exactly one path, `miniapp_membership_hint.py`. No collection, import, skip, conftest, subprocess, network, or filesystem-write behavior changes.
- New module is ordinary application code with no collection hooks or credential handling. Import initializes constants, a lock, and cache state; background work and settings reads occur only on function calls. The helper reads/parses source without importing it.
- Bundle reports no helper-touching commits between `source_after` and release; the release helper matches the displayed change.

VERDICT: APPROVE — The bundle supports a single-path registration with no additional helper changes or collection-time execution.
