# Receipts withdrawn: yueto-ci #179 and yueto #68

`merge-receipts/yueto-ci/179.json` and `merge-receipts/yueto/68.json` are
removed. They are not parity evidence and must not be treated as a pass.

Both claimed `parity.runner` `mac+linux`. The audit accepts only `box`,
`yueto-ci`, and `mac-5f08d00f`. Both parity files are prose excerpts, not
command transcripts, so they cannot support `parity.result: pass`.

## yueto-ci #179

Claimed head: `bd051adae75a3f924b2cb9faae5b933c1aa66283`.

`yueto-ci-179-review.txt` ends with
`VERDICT approve @7fb302a6627e413fb4bed5c968f9f8fe5bd526f3`.
That line does not name `bd051ada`.

Those two commits have the same tree
(`f0b390bd77c1a4fd9b3b8940756e8215d07af703`), checked in this repository.
Tree identity is not an exact-head verdict and not a parity run.

Still required: a verdict line that names `bd051ada`, a real command log from
one allowed runner at that head, and a receipt written from that log.

## yueto #68

Claimed head: `0827f9c0b7d1f0b76ec9b830eaf21034d8884d45`.

`yueto-68-review.txt` ends with
`VERDICT approve @4c426fe31c9b99ec58deaf9159bc66668de5655b`.
That line does not name `0827f9c0`.

Tree identity against `4c426fe31c9b99ec58deaf9159bc66668de5655b` was not
re-checked here. `yueto-68-parity.log` is a prose excerpt.

Still required: a verdict line that names `0827f9c0`, a real command log from
one allowed runner at that head, and a receipt written from that log.
