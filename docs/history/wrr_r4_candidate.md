# Historical: WRR r4 frozen candidate

## WRR r4 frozen candidate (historical)

- Package: `dist/wrr_final_candidate_20261101_r4.zip`
- Package SHA256: recorded in `dist/wrr_final_candidate_20261101_r4.manifest.json`
  and `results/final_release_20261101_r4/acceptance.json`. It is not embedded
  here because this README is a package member and rebuilding the archive
  changes its own bytes and hash.
- Reviewed Git base: `bef47bf663927cc9726c4ec632ca750a3881d528`

**r4 is uncommitted.** The external manifest and acceptance record identify the
local r4 archive; the Git base commit alone does not contain all r4 changes. Do
not treat a clean checkout of that commit, or an older passing package check, as
r4 acceptance.

Run these commands from the repository root. They write their records into
`results/final_release_20261101_r4/`.

```bash
python scripts/980_final_release.py verify
python scripts/978_process_experiment_delivery.py --archive dist/wrr_final_candidate_20261101_r4.zip --output results/final_release_20261101_r4/package_delivery_check.json
python scripts/983_verify_extension_replay.py
python scripts/982_final_release_tests.py
python scripts/984_full_pytest_summary.py --out results/final_release_20261101_r4
python scripts/985_build_local_ci_summary.py --out results/final_release_20261101_r4
python scripts/980_final_release.py accept
```

`make review-current-candidate` runs verify, delivery, replay and accept in that
order. Run `make review-current-tests` separately when the targeted/full test
records need refreshing; acceptance consumes the records already present in the
result directory.

**Historical commands.** `make review-package-check` and
`make review-process-experiments-package-check` keep their older defaults
(`dist/wrr_review_response_candidate.zip` and
`dist/wrr_process_experiments_20261029.zip`). They are historical checks and
must not be read as r4 acceptance.
