# PR: devops/session-25-hygiene -> main (Lakelink Fiber Provable Resilience Intelligence)

**Open in one click:** https://github.com/skhage/provable-resilience-intelligence/compare/main...devops/session-25-hygiene?expand=1
Paste this file as the PR description. Prepared by @devops for P39-DEVOPS-V4-CANDIDATE-CODE-COVERAGE, refreshed for P41-DEVOPS-GUARD-COMMIT-AND-STRICT-CI (2026-10-26).

## Summary

The branch is 32+ commits ahead of `main` (`main` = `develop` = `2632e12`). It brings `main` up to the PRI-DEMO-FREEZE-v3 demo state and adds the v4 shadow-build guardrails:

* **Branch hygiene (S25-S37):** pending agent work checked in. That covers BUG-QA-060 conduit-level HSI, P28/P32 scoring pipeline V2 alignment, the V4 KPI copy spec, `rescore_harness_v4.ipynb` and `ml_freeze_guard.py`.
* **v4 freeze write guard (P35/P37/P39):** `tests/test_v4_frozen_write_guard.py` statically blocks any v4-scoped code that writes to the 53 FROZEN v3 objects (`tests/frozen_v3_objects.json`). It also checks that every live `*_v4_candidate` object has a versioned writer.
* **v4 candidate registry (P39):** `tests/v4_candidate_objects.json` lists all 14 live candidates (re-captured 2026-10-26). For each one it records `expected_writer`, `owner_role` and `owner_task`.
* **CI (P39):** a dedicated `v4 Freeze Guard` job, so the check can be marked required. `bundle/requirements.txt` now includes `pydantic-settings`; without it, collection failed on `test_mrc_protected.py` and `test_conduit_coverage.py`.
* **Writers (9/14 covered):** `ml_v4_candidate_writers.ipynb` (ML S38) covers `span_risk_predictions_v4_candidate` and `resilience_score_snapshot_v4_candidate`. `pipelines/srlg_v4_candidate_derivation.ipynb` (DE S40, 484aed8) covers the 5 derived SRLG tables plus `unified_shared_risk_group_v4_candidate`; the v3 `srlg_colocation_derivation` notebook was reverted, so its cell 7 is gone. The DA P40 writer (f0d29c3) covers `kpi_delta_attribution_v4_candidate`.
* **App (APP-DEV S38-S40):** MRC Protected KPI behind `PRI_V4_KPIS` (default false), plus WCAG fixes BUG-DW-089 and BUG-DW-092.

## Test evidence (committed tree, 2026-10-26)

| Check | Result |
| --- | --- |
| `pytest tests/test_v4_frozen_write_guard.py` (non-strict) | 37 passed, 2 skipped (Spark-only live checks), 1 coverage warning |
| Same, `PRI_V4_COVERAGE_STRICT=1` (P41) | 36 passed, 0 FROZEN-write hits. 1 failed: 5/14 candidates still have no versioned writer, all owned by P37-DE-V4-WRITERS-CHECKIN (was 12/14) |
| Full `pytest` | 6 failed in `test_pipeline_completeness.py` (BUG-QA-070, see caveats); the rest pass or skip |
| `ruff check tests/` | All checks passed |
| `databricks bundle validate` (bundle root = project root) | dev OK, prod OK |

## Freeze-v4 caveats (read before merging)

1. **No live v4 promotion.** This PR changes code and CI only. The v3 FROZEN objects stay pinned, and `*_v4_candidate` objects are shadow-only. Cutover needs a FREEZE-v4 manifest from @data-planner, @qa sign-off and a @pm decision (DEC-PRI-V4-SHADOW-BUILD).
2. **Writer coverage is advisory.** `PRI_V4_COVERAGE_STRICT` defaults to `0`. Set the repo variable to `1` (Settings > Secrets and variables > Actions > Variables) once these are checked in:
   * P37-DE-V4-WRITERS-CHECKIN (@data-engineer, the only remaining item): physical_resource_span / physical_resource_conduit / hazard_span_intersection / hazard_proximity_count / mv_mrc_protected -> `pipelines/de_v4_candidate_writers.ipynb`
   * Done: BUG-ML-V4-GUARD-SRLG-PIPELINE (484aed8) and P40-DA-V4-WRITERS-CHECKIN (f0d29c3).
3. **SRLG split resolved (P41).** The v4 SRLG derivation now lives in `pipelines/srlg_v4_candidate_derivation.ipynb` (write_enabled defaults to false). The v3 notebook is back to its frozen state, and the guard reports 0 FROZEN hits.
4. **Known red check: BUG-QA-070.** `bundle/pipeline/resilience_scoring_pipeline.py` is the stale bronze-only DAB stub, and `tests/test_pipeline_completeness.py` fails on it on purpose. Replacing it changes the deployable pipeline, so it is a post-freeze fix (sync from `pipelines/resilience_scoring_pipeline`). Merge with this check red, or merge after the post-freeze sync.
5. **CI secrets.** `Bundle Validate` needs the `DATABRICKS_HOST` and `DATABRICKS_TOKEN` repo secrets.

## After merge (CEO / repo admin)

* Branch protection on `main` and `develop`: require the `v4 Freeze Guard`, `Lint + Unit Tests` and `Branding Compliance` status checks.
* Fast-forward `develop` to `main`.
* Delete `devops/session-24-ci-review`. It is fully contained in this branch.

Branding: Lakelink Fiber only. Tag: `telco_project: provable_resilience_intelligence`.
