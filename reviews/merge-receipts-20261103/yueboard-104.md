# Evidence withheld: onesyue/yueboard#104

This note is not a merge receipt and not merge-ready. Parity is WITHHELD.

## Not read

Checked 2026-11-03T09:17:32Z:

- Unauthenticated `GET https://api.github.com/repos/onesyue/yueboard` returned HTTP 404.
- Unauthenticated `GET https://api.github.com/repos/onesyue/yueboard/pulls/104` returned HTTP 404.
- `gh pr view 104 --repo onesyue/yueboard` returned `Could not resolve to a Repository with the name 'onesyue/yueboard'`.

Pull-request state, head, merge commit, and review threads for #104 were not read. No Mac path was read. No parity log is in this commit.

## Public yueto-ci facts

- `origin/master` is `ad3ce28c3761ba94c5748cb4a3119c2198b1bf17` (`receipt: yueto #71 (gen 328 ledger d1d7aa97) (#205)`).
- That commit has `merge-receipts/yueboard/101.json` and does not have `merge-receipts/yueboard/104.json`.
- yueto-ci pull request #196 head `b49a15491f2664bea27e72f1d6bfea4cbfe60fdc` wrote a PRE-MERGE PREP note for this number. Its review file was one line, `VERDICT: APPROVE`, and that line does not name a 40-hex head. The note also named head `b864e7e4a5804591f337d65d9fbb5f706d0ac941` and branch `cx/ui-admin-unify`. Those strings were not checked against yueboard. The Mac log path, line number, and SHA256 in that note are not files in that commit or in this one, so they are not repeated.
- Independent review comment `6598680358` (2026-11-03T08:14:49Z) on pull request #196 BLOCKed `b49a15491f2664bea27e72f1d6bfea4cbfe60fdc` for that reason.

## Still required

A writer that can read `onesyue/yueboard` has to confirm whether #104 is open, merged, or closed. This note does not decide that, and it does not rebase the pull request. If #104 is still open, schema 1 still needs a verdict that names the exact head and a command log from an allowed runner (`box`, `yueto-ci`, or `mac-5f08d00f`) at that head. No `merge-receipts/yueboard/104.json` is created here. Schema 1 cannot represent withheld parity.
