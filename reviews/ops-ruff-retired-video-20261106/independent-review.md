# Independent exact shared-input transition review

VERDICT: APPROVE

Reviewer: /root/integration_review. Scope is exclusively the reviewed Ops pyproject.toml transition, not the later CI implementation or a full runtime gate.

Source before: 3a5bcd22fcf9b8b548a7d1ad8d075d9074e0b923.
Source after: cc27ad66ae2176553f0c3928a490292ba7d5a5e0.
Integrated revision: d4880f37a7a9a3dbc9b6d32a16125745691fb88e.
Before blob: 1d861dc9e1da3fbe876ded02f454a3fd26f2cd27.
After blob: fbedf7789a78aaa402835eb3747e8be2e24772d2.
Mode remains 100644.

The actual Git diff removes only the string yuetube-video from tool.ruff.extend-exclude. Read-only TOML parsing independently confirms that removing exactly this one old list member makes the complete before and after configuration objects equal. Integrated d4880f37 contains the identical after bytes. Git tree lookup confirms the excluded retired directory is absent from that revision. Thus the change does not narrow lint coverage, change dependency resolution, test selection, pytest configuration or runtime settings. No arbitrary pyproject changes are approved by this receipt.

Read source-freeze.json and qualification.json under reviews/ops-ruff-retired-video-20261106 in the CI candidate. The qualification correctly states static shared-input qualification only and explicitly does not claim execution of the full gate. This approval permits only the exact above blob transition and cannot rewrite historical PR256/PR122 seals, waive the 52 native obligations, accept unknown shared-input differences or replace the same-run execution receipts. The later CI implementation must retain those constraints and receive its own independent review.

No source, Git state, production data or credentials were changed. No full tests were rerun. Original evidence and recovery coordinates remain intact.
