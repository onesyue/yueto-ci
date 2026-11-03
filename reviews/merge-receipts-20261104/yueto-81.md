# Yue.to PR 81 Darwin release-lock review

VERDICT: approve

Reviewed head: ca1747b872120cb7fb77b520469c77719fc172ba.
Reviewer: codex-link-independent, independent of the root implementation lane.

The signed commit has a verified G signature. Its binary diff SHA256 is 1104d8a5040119f5bbe6e358030025d549c49c3e6922cd5880beb50a93c9d7bc, identical to the reviewed frozen patch. Scope is scripts/release-lock.py and scripts/test-release-lock.py only.

Darwin uses native process metadata and exact NUL-delimited arguments, retaining only coordination environment fields. Native proc_bsdinfo ABI layout was checked against the installed SDK. Before/after microsecond birth identity rejects observed PID reuse. Fixture scoping precedes native reads. Protected foreign processes are classified using the kernel executable path, never spoofable ps comm/argv[0]. Unreadable same-user targets, recognized interpreters/scripts and unavailable executable metadata fail closed. Conservative native-process rows retain live PID identity with unknown birth; both dead_local and retirement preserve their locks. This inventory is not a security boundary against an adversarial account renaming an interpreter.

The first review rejected a normal-workstation EPERM failure and late fixture scoping. Follow-up rejected retirement treating unknown birth as PID reuse. Both findings are resolved. Regression tests exercise real native child argv (spaces and empty arguments), environment allowlisting, malformed buffers, protected interpreter refusal, and terminal-proven unknown-birth locks remaining held without archive/audit writes. No additional finding remains.

Validation evidence available at review: darwin-lock-tests-v2.log records 191 passed, zero skipped on the full two-module Mac run before semantics-preserving import/dict style cleanup. The final frozen-source focused run records 10 passed, 74 deselected in darwin-lock-focused-final.log. Linux parity on the exact frozen patch passed 190 cases with one explicitly Darwin-only native case skipped and zero unexpected skips. That native case passed on Mac. Linux image sha256:ee698ffafd0f02befc8b1350046f7c661001d0552dba5207e980022fdc6b0257; elapsed 46.19 seconds, exit 0. Bound Linux driver log SHA256 86b689915f31560b3f58ef61e38c99c15a4665fe317eda09456cdbd05a26ce3b. ran_at uses the runner receipt started_at. Logs are yueto-81-linux.log, yueto-81-mac.log and yueto-81-focused.log in this directory. This review does not claim installation or production readback.
