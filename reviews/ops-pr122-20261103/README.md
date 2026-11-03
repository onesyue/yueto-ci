# #122 shared-input admission: real reviewed source

The active seal binds PR #122 head
`56a7e0412e9bd1d297ba4a5dd3d363147fac463c`, replacing the unavailable
temporary local merge. The four after-blobs are unchanged; their modes, the
before-blobs, source tree, evidence digests and canonical policy identity were
recomputed from the real source objects. The predecessor remains
`c56159246c31ede8e24b40b8626b6a3c6b0b0137`.

As for #261/#234, the planner proves that both reviewed source revisions are
ancestors of the release and verifies their exact shared-input blobs and modes.
The reviewed PR head need not have the predecessor as its first parent.
Historical seals and the skip baseline remain unchanged.

#256 is pending final-head review. Its active seal has been removed; its review
bundle retains historical local-merge evidence only.

Reproduce against a read-only source checkout:

```sh
python3 reviews/ops-pr122-20261103/qualification-driver.py ./yueops-src
```

The driver checks evidence hashes and real Git objects, then runs admission
against base `c4f60c381e9eeb6c499bdf8313170e7f6f496c95` and head
`047bbf81034093db226b81ccde9f6159a2c782aa`, pinning only a disposable policy
copy. No source objects are created. Current output is in admission-results.json.

This is static shared-input and admission qualification only. Runtime execution,
full collection and production qualification were not performed. The original
review was performed in the same session, without a separate independent reviewer.

#260 remains unsealed: its broad dependency update includes auth/crypto and
database changes requiring focused reviews and qualifications.

## Validation

The requested admission precheck returned `ADMISSION_ACCEPTED` with the temporary
release pin; the checked-in first-native file was restored byte-for-byte.

The requested full-suite command completed with 634 passed and nine fixture
setup failures caused by GPG signing being unavailable in the read-only sandbox.
Repeating it with process-local
`GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=commit.gpgsign GIT_CONFIG_VALUE_0=false`
passed: **643 tests, 5725 subtests** (292.37s). Both runs used
`GOCACHE=/tmp/gocache-sf`, the requested virtualenv Python and
`-p no:cacheprovider`. No Git configuration was changed.

After adding the explicit pending-#256 rejection case, the final focused run of
`tests/test_ops_pr_shared_input_transitions.py` passed: **7 tests, 17 subtests**.
It also covers source-object availability, exact evidence bindings, non-parent
reviewed predecessors, unrelated history, mutated bundles and seal tampering.
`git diff --check` passed.
