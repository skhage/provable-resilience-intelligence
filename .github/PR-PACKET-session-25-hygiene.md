# PR Packet: devops/session-25-hygiene -> main

Prepared by @devops (session 33, 2026-10-25) for task P34-DEVOPS-PR-PACKET-7E10D93. Refreshes the packet for HEAD 8aaab64 (was 119d3c7).

## One-click open (about 2 minutes)

1. Open https://github.com/skhage/provable-resilience-intelligence/compare/main...devops/session-25-hygiene?expand=1
2. Paste the title and body below, then click **Create pull request**.
3. Wait for GitHub Actions `ci.yml` (bundle-validate, python lint/test, frontend tsc/eslint/vite build, branding) to go green, then merge with **Create a merge commit**. Do not squash, because the session tags are what make the trail auditable.
4. After the merge, delete the remote branches `devops/session-24-ci-review` (fully contained) and `devops/session-25-hygiene`. Then fast-forward `develop` to `main`.

## PR title

```
[DEVOPS] Release A hardening: CI gates green, prod bundle root fix, scorecard app frontend build (P19/P23/P26/P28 + app S30-S31)
```

## PR body

```markdown
## Summary
This PR merges every commit on devops/session-25-hygiene into main, from 95e697c through HEAD 8aaab64. At packet time that is 15 commits (d17a694 inherited from session-24 + 14 on session-25).
It supersedes devops/session-24-ci-review, whose commits are all included here.

### CI / release engineering
- P19-DEVOPS-CI-PIPELINE-REVIEW (d17a694): fixes the broken CI gates, makes deploys wait on CI, and adds an artifact SHA-256 manifest.
- 32d113b: pins databricks/setup-cli to v1.22.1 by SHA and adds a frontend tsc/eslint gate.
- P26-DEVOPS-FE-BUILD-ARTIFACT (bd36419): CI now runs a vite build and uploads the dist artifact. Lands the P24/P27 frontend scaffold.
- P28-DEVOPS-PROD-BUNDLE-ROOT (be695ff): moves the prod root_path off /Workspace/Shared to the deployer's home and sets explicit CAN_MANAGE permissions.
- Adds ruff.toml and pytest.ini so local runs and CI resolve the same config.

### Tests
- P23-DEVOPS-COMMIT-QA-TEST-FIX (d1410d7): lands @qa's P20-QA-TEST-DRIFT-FIX:
  - ActionStatus gains 'cancelled'
  - all 9 ActionType values are covered
  - adds contract tests
  - cleans up unused imports

### Resilience Scorecard app (Lakelink Fiber)
- P20-APP-LINT-CLEANUP (981552c): removes the F811 duplicate list_product_offerings and includes theme/topology/hazard table updates.
- BUG-DW-063 / BUG-DW-060 (95e697c): adds cross-view links from ServiceTable to topology and syncs the diversity colors for WCAG.
- P27-APP-COMMIT-FE-MANIFEST (f3d0f2b):
  - eslint flat config
  - BUG-DW-078: LoadingRegion with role=status
  - BUG-DW-079: a single skeleton style
  - fixes 49 literal \uXXXX escapes
- BUG-DW-077 (24b31b5):
  - SRLG type moves to a midpoint letter-badge layer, and the edge dash now means path role and diversity
  - partially_diverse now draws as dash-dot
  - the legend explains the new encoding
- BUG-DW-084 (45c6f28): LoadingRegion announces Suspense fallbacks for WCAG 4.1.3. It drops aria-busy and injects the label into an empty live region after a 100ms delay.
- BUG-DW-085 (87e9967): the topology edge aria-label now appends the max SRLG severity per conduit, and ring/glow use the same max.
- 7e10d93: repoints RESILIENCE_SCORECARD_WAREHOUSE_ID from deleted warehouse 7b65956f30d66feb to 9cd919d96b11bf1c (Apps & Agents Warehouse).
- 8aaab64: adds PRI-DEMO-FREEZE-v3 KPI parity values to the P23 smoke-test checklist.

### Docs
- P31-DEVOPS-PR-READY-PACKET / P34-DEVOPS-PR-PACKET-7E10D93: adds and refreshes this packet at .github/PR-PACKET-session-25-hygiene.md.

## Gate results (local, on HEAD 8aaab64, 2026-10-25 session 33)
| Gate | Result |
|---|---|
| ruff check | PASS (all checks passed) |
| pytest | PASS: 72 passed, 27 skipped (Spark-only), 0 failed |
| Branding (CI grep, clean git archive) | PASS — all grep hits are meta-docs/tests explaining the rule |
| bundle validate --target dev | Validation OK (YAML parsed, 6 resource files) |
| bundle validate --target prod | Validation OK (root_path under deployer home, CAN_MANAGE set) |
| frontend tsc/eslint/vite | Runs in GitHub Actions only (no Node on the agent runtime). Confirm on this PR. |

## Risk / rollback
- No data or UC changes. The PR only touches code, CI, and the bundle config.
- Rollback: revert the merge commit. main is still at 2632e12.
- The prod root_path change only matters on the next prod deploy, and the first prod deploy is still CEO-gated.
```

## Reviewer checklist

- [ ] GitHub Actions `ci.yml` is green on the PR, frontend job included. The frontend job is the only gate that could not be verified locally.
- [ ] The `databricks.yml` prod target `root_path` points to the deployer's home, not `/Workspace/Shared`, and the permissions block lists CAN_MANAGE.
- [ ] `deploy.yml` deploys only after CI succeeds (`needs:` / `workflow_run` gate).
- [ ] `setup-cli` is pinned by commit SHA, not by tag.
- [ ] No `Lumen` brand strings outside the allowlisted meta-docs.
- [ ] No notebooks or data files are in the diff. The working-tree edits to `notebooks/hazard_span_intersection_pipeline.ipynb`, `pipelines/resilience_scoring_pipeline.ipynb` and `ml_freeze_guard.py` are freeze-gated and intentionally NOT included.
- [ ] Branch hygiene: the PR branch is a moving target. After the merge, @app-developer should cut feature branches from main (app/<bug-id>) instead of committing to devops/* branches.
- [ ] Merge commit, not squash. After the merge, delete the two devops branches and fast-forward `develop`.
