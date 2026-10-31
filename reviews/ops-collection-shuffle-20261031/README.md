# Reviewed optional collection hook

This envelope admits exactly `conftest.py` mode100644 blob
`05613fb260c40650ff94397493fe0bf8132d1e8e` introduced by signed Ops
`f683e5391c723fd00da42b82d21cfd049a529e8c`. The historical baseline beneath it
retains SHA-256 `d11a7572750c2e44d4781e92c2c0a910f40cae0e29b333aedd49132747842507`.
The planner proves the source ancestry and exact introduction. Admission removes
only that exact reviewed addition and then runs the entire old input-admission
chain. A changed blob/mode, missing proof, extra shared input or historical-input
mutation still fails. This is not a blanket conftest exemption.

`independent-review.md` transcribes the separate reviewer's source findings.
`source-freeze.json` binds the complete60shared inputs and immutable source tree.
`qualification.json` records actual same-tree Linux collection comparisons; its
source is exact Ops4e4630ec13c77b5b24bf51d2febd24e6a9a89eab, Board0b5a9fe3511decc55dbf838d108a389d1ee6bb08,
policy031b4cd34b1e6733a69e7eeaab8959c59b266c9e and immutable image97e9a5ce.
The disposable driver changes only this hook between comparisons, restores it,
and asserts no tracked source difference remains. All runs disable network and
use two CPUs/3GiB. The first harness attempt used a nonnumeric run identifier and
was rejected before collection; the corrected run completed with exit0.

Results: enabled/disabled full collection28568 and ordinary14164/14365 plus
serial39 have identical node order and global RNG state. Seed37 repeats exactly;
seed53 changes order; both preserve the full multiset and global RNG state.
The three assignments are disjoint and cover the full reference. Eleven actual
collection processes produced the hashes in the receipt. Full raw node lists and
logs remain in the coordinator's existing resume/ci-shuffle-qualification-r2
artifact directory. The checked-in driver reproduces the comparison in the same
disposable checkout layout.

This is collection qualification only. It does not claim ordinary tests, native
supplements, skip-policy reconciliation or the final join passed. Production
remains held until the final reviewed policy completes native expand, reference,
ordinary, serial, native-required stages and join with exact execution receipts.
