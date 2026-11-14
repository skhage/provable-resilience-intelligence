# P81 Partial v4 Cutover: Readiness Report

Owner: @devops. Refreshed: 2026-11-14 (@devops P207). Read-only check: nothing was run against data.

## Verdict

READY TO RUN once the CEO authorizes it. The runbook code, tests, bundle and decision gates pass. Only one item blocks P81: the CEO has not written an AUTHORIZE P81 row to `ceo_directives`. P89, the live rollback rehearsal, is also still open and should run first.

## Gate matrix

| Gate | Source | State |
| --- | --- | --- |
| GO code for partial mode | decisions id 50 `DEC-PRI-V4-CUTOVER-GO-PARTIAL` | decided |
| Execute-impl authorization | decisions id 52 | decided |
| Pin fingerprint gates | decisions id 40 | decided |
| Candidate pin backups (2b) | decisions id 51, BUG-QA-110 | decided / completed |
| Rollback via DEEP CLONE backup | decisions id 46 | decided |
| P88 open points (scratch rehearsal approved) | decisions id 53 | decided |
| QA re-verify execute impl | P89-QA-REVERIFY-EXECUTE-IMPL, BUG-QA-112/113/114 | completed |
| Live rollback rehearsal | P89-DEVOPS-LIVE-ROLLBACK-REHEARSAL (`ops/p89_live_rollback_rehearsal.ipynb`) | BLOCKED: waiting for the CEO to run it interactively |
| CEO authorization | `ceo_directives` AUTHORIZE P81 row | MISSING (directives max id 3) |
| PM escalation | P88-PM-ESCALATE-CUTOVER-AUTH | open, re-escalated as #142 |

## Code and CI evidence (clean clone of devops/session-25-hygiene)

* `tests/test_v4_cutover_runbook.py`: 92 pass.
* `tests/test_v4_frozen_write_guard.py`: 38 pass, 2 skip (these need Spark).
* Full suite: 1446 pass, 6 fail, 60 skip. All 6 failures are BUG-QA-070 in `test_pipeline_completeness`. They clear only with P43 (bundle pipeline sync), which waits for the v3 freeze to be lifted.
* ruff: clean.
* `bundle validate`: passes for both dev and prod.

## Run sequence after AUTHORIZE

1. Run P89: rehearse execute and rollback in `cdm_tmforum.pri_scratch_rollback_rehearsal`, then drop the schema (DEC id 53).
2. Run `dry_run(partial_cutover=True)`. Confirm there are no blocking findings and the pin guard passes.
3. Run `execute(partial_cutover=True)`. Mark P81 complete promptly so that P82-DP-MANIFEST-DEFERRED-V41-POST-SWAP can start.
4. After the swap: P60 / P43 constraints (AFTER_SWAP subset only). Never run them on v3 FROZEN tables.

## Branch hygiene

* origin: main = develop = 2632e12. devops/session-25-hygiene is about 171 commits ahead of main, 0 behind, and in sync with origin.
* Open PR #1 (devops/session-24-ci-review, d17a694) is stale and needs the CEO to close or delete it.
* Uncommitted WIP from other agents is left alone: the v4 writer notebooks, `ops/p96`, `runbooks/`, and a 1-line docstring change in `test_product_catalog_tiers_dw169.py`.
