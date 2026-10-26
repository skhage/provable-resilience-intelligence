# PR: devops/session-25-hygiene -> main (Lakelink Fiber Provable Resilience Intelligence)

**Open in one click:** https://github.com/skhage/provable-resilience-intelligence/compare/main...devops/session-25-hygiene?expand=1
Paste this file as the PR description. Prepared by @devops for P39-DEVOPS-V4-CANDIDATE-CODE-COVERAGE (2026-10-26).

## Summary

The branch is 29 commits ahead of `main` (`main` = `develop` = `2632e12`). It brings `main` up to the PRI-DEMO-FREEZE-v3 demo state and adds the v4 shadow-build guardrails:

* **Branch hygiene (S25-S37):** pending agent work checked in. That covers BUG-QA-060 conduit-level HSI, P28/P32 scoring pipeline V2 alignment, the V4 KPI copy spec, `rescore_harness_v4.ipynb` and `ml_freeze_guard.py`.
* **v4 freeze write guard (P35/P37/P39):** `tests/test_v4_frozen_write_guard.py` statically blocks any v4-scoped code that writes to the 53 FROZEN v3 objects (`tests/frozen_v3_objects.json`). It also checks that every live `*_v4_candidate` object has a versioned writer.
* **v4 candidate registry (P39):** `tests/v4_candidate_objects.json` lists all 14 live candidates (re-captured 2026-10-26). For each one it records `expected_writer`, `owner_role` and `owner_task`.
* **CI (P39):** a dedicated `v4 Freeze Guard` job, so the check can be marked required. `bundle/requirements.txt` now includes `pydantic-settings`; without it, collection failed on `test_mrc_protected.py` and `test_conduit_coverage.py`.
* **Writers:** `ml_v4_candidate_writers.ipynb` (ML S38) covers `span_risk_predictions_v4_candidate` and `resilience_score_snapshot_v4_candidate`.
* **App (APP-DEV S38-S40):** MRC Protected KPI behind `PRI_V4_KPIS` (default false), plus WCAG fixes BUG-DW-089 and BUG-DW-092.

## Test evidence (committed tree, 2026-10-26)

| Check | Result |
| --- | --- |
| `pytest tests/test_v4_frozen_write_guard.py` (non-strict) | 37 passed, 2 skipped (Spark-only live checks), 1 coverage warning |
| Same, `PRI_V4_COVERAGE_STRICT=1` | 1 failed: 12/14 candidates have no versioned writer yet (expected, see caveats) |
| Full `pytest` | 137 passed, 29 skipped, 6 failed in `test_pipeline_completeness.py` (BUG-QA-070, see caveats) |
| `ruff check tests/` | All checks passed |
| `databricks bundle validate` (bundle root = project root) | dev OK, prod OK |

## Freeze-v4 caveats (read before merging)

1. **No live v4 promotion.** This PR changes code and CI only. The v3 FROZEN objects stay pinned, and `*_v4_candidate` objects are shadow-only. Cutover needs a FREEZE-v4 manifest from @data-planner, @qa sign-off and a @pm decision (DEC-PRI-V4-SHADOW-BUILD).
2. **Writer coverage is advisory.** `PRI_V4_COVERAGE_STRICT` defaults to `0`. Set the repo variable to `1` (Settings > Secrets and variables > Actions > Variables) once these are checked in:
   * P37-DE-V4-WRITERS-CHECKIN (@data-engineer): physical_resource_span / physical_resource_conduit / hazard_span_intersection / hazard_proximity_count / mv_mrc_protected
   * BUG-ML-V4-GUARD-SRLG-PIPELINE (@data-engineer, critical): the 5 derived SRLG tables + `unified_shared_risk_group_v4_candidate`
   * P40-DA-V4-WRITERS-CHECKIN (@data-analyst): `kpi_delta_attribution_v4_candidate`
3. **SRLG pipeline WIP is deliberately NOT in this PR.** There is an uncommitted v4 cell in `pipelines/srlg_colocation_derivation.ipynb`. It turns the whole notebook v4-scoped, and cells 2-5 `CREATE OR REPLACE` four FROZEN v3 `derived_srlg_*` tables, so the guard fails with 8 hits. Data is safe: the tables were last altered 2026-10-23. The fix (split into `pipelines/srlg_v4_candidate_derivation.ipynb`) is owned by @data-engineer.
4. **Known red check: BUG-QA-070.** `bundle/pipeline/resilience_scoring_pipeline.py` is the stale bronze-only DAB stub, and `tests/test_pipeline_completeness.py` fails on it on purpose. Replacing it changes the deployable pipeline, so it is a post-freeze fix (sync from `pipelines/resilience_scoring_pipeline`). Merge with this check red, or merge after the post-freeze sync.
5. **CI secrets.** `Bundle Validate` needs the `DATABRICKS_HOST` and `DATABRICKS_TOKEN` repo secrets.

## After merge (CEO / repo admin)

* Branch protection on `main` and `develop`: require the `v4 Freeze Guard`, `Lint + Unit Tests` and `Branding Compliance` status checks.
* Fast-forward `develop` to `main`.
* Delete `devops/session-24-ci-review`. It is fully contained in this branch.

Branding: Lakelink Fiber only. Tag: `telco_project: provable_resilience_intelligence`.
