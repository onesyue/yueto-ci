# Job G source review: I10 skip blob successor

Source before: e18f0ec8ccd21bacc8e249238ed89a8774ba8347.
Source after: 5277e42a459bd1d530e4eea97f4056af7f3d529f.
Rejected promotion: 40945710923 (reported by owner; no network used).

The full admission sweep covers 1,045 cases, one collection skip and 140 modules.
Only signed-closure and the already sealed Mini retirement changed in this interval.
The latter is already admitted by reviewed_retired_host_transition and needs no change.
No skip/skipif/xfail/importorskip call changes occur in the full tests diff.

The signed-closure diff changes only the other test
`test_pinned_verifier_policy_is_unchanged_and_reproduces_old_rejection`:
script/required counts 32/35 become 33/36 and the expected script set gains
`scripts/systemd/zz-i10-loadshed.conf.pause.conf`.
The complete decorated function
`test_real_linux_signed_fixture_when_explicitly_requested` is byte-identical;
its source segment SHA256 is
4e927f3235298f6846aa2bf7ff4011f7763ac02afbe4480cc3af199c73becb49.
The module changes from 3b3443dcf3a8fa9bce9cfa57da51969e2ab7ea1a
to 74403b075bb053e563ad5fc5a3a1461c6be49e60. Its condition, body,
reason and skipped outcome remain unchanged.

Contrary to the initial incident hypothesis, this ID belongs to baseline cases,
not reviewed_hosted. Its predecessor blob is the existing release successor.
Approve exactly this ordinary historical case/blob successor; preserve its
reason and outcome through skip_blob_successors. Hosted cases remain excluded.

Review method: primary agent source review and separate second-pass diff review,
as requested; no independent person or external execution is claimed.
Per-case sweep and full source diff are retained in the Job G state directory.
