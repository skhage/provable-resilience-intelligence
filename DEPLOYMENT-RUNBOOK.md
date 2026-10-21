# Deployment Runbook — Provable Resilience Intelligence

> DAB-managed deployment for Lakelink Fiber resilience scoring on Databricks.
> Last updated: 2026-10-21 by @devops

---

## 1. Architecture Overview

```
provable-resilience-intelligence/
├── databricks.yml              # Bundle root config (targets, variables)
├── bundle/
│   ├── resources/              # Resource definitions (6 YMLs)
│   │   ├── resilience_pipeline.pipeline.yml
│   │   ├── resilience_job.job.yml
│   │   ├── resilience_scorecard.app.yml
│   │   ├── resilience_model.serving.yml
│   │   ├── lakelink_fiber_provable_resilience_scorecard.dashboard.yml
│   │   └── resilience_dashboard.dashboard.yml  (superseded)
│   ├── pipeline/               # SDP pipeline source
│   └── src/                    # Dashboard JSON
├── apps/resilience-scorecard/  # React/FastAPI app
├── .github/workflows/          # CI/CD (ci.yml + deploy.yml)
├── BRANCH-STRATEGY.md          # Git flow docs
└── tests/                      # Unit tests
```

## 2. Deployment Targets

### Dev Target

| Property | Value |
| --- | --- |
| Target name | `dev` |
| Mode | `development` |
| Root path | `/Users/${workspace.current_user.userName}/.bundle/provable-resilience-intelligence/dev` |
| Catalog | `cdm_tmforum` |
| Schema | `provable_resilience_intelligence` |
| Name prefix | `[dev <username>]` (auto-applied) |
| Pipeline mode | Development (auto) |
| Triggers | Paused (auto) |
| Lock | Disabled |

### Prod Target

| Property | Value |
| --- | --- |
| Target name | `prod` |
| Mode | `production` |
| Root path | `/Shared/.bundle/provable-resilience-intelligence/prod` |
| Catalog | `cdm_tmforum` |
| Schema | `provable_resilience_intelligence` |
| Name prefix | None |
| Triggers | Active |
| Service principal | TODO: configure `provable-resilience-prod` SP |

> **Warning:** Prod root path `/Shared` is writable by all workspace users.
> After creating the service principal, update `databricks.yml` to uncomment
> `run_as` and change `root_path` to `/Workspace/Users/<sp-name>/.bundle/...`.

## 3. Environment Variables & Secrets

### CI/CD Secrets (GitHub Actions)

These must be configured in the GitHub repo Settings > Secrets:

| Secret | Purpose | Where to get it |
| --- | --- | --- |
| `DATABRICKS_HOST` | Workspace URL (e.g. `https://adb-xxx.azuredatabricks.net`) | Workspace settings |
| `DATABRICKS_TOKEN` | Service principal PAT or OAuth token | Service principal config |

For prod deployments, configure a separate GitHub Environment named `production`
with its own secrets (separate SP with tighter permissions).

### Bundle Variables

| Variable | Default | Description |
| --- | --- | --- |
| `catalog` | `cdm_tmforum` | Unity Catalog catalog for all tables |
| `schema` | `provable_resilience_intelligence` | Schema for resilience assets |
| `warehouse_id` | (lookup: Serverless Starter Warehouse) | SQL warehouse for dashboards |

Override at deploy time:
```bash
databricks bundle deploy --target prod --var="catalog=prod_catalog"
```

### SQL Warehouse Dependency

The bundle uses `warehouse_id` with a warehouse lookup:
```yaml
warehouse_id:
  lookup:
    warehouse: Serverless Starter Warehouse
```

This auto-resolves the warehouse ID at deploy time. If the warehouse name changes:
1. Update `databricks.yml` variable definition
2. Or override: `--var="warehouse_id=abc123def456"`

## 4. Managed Resources (6)

| Resource | Type | Name (prod) | Key dependencies |
| --- | --- | --- | --- |
| `resilience_pipeline` | Pipeline (SDP) | `provable-resilience-intelligence-pipeline` | Bronze/Silver/Gold tables in `cdm_tmforum.provable_resilience_intelligence` |
| `resilience_daily` | Job | `provable-resilience-intelligence-daily` | Pipeline (runs it as task), cron 6AM CT |
| `resilience_scorecard` | App | `resilience-scorecard-<user>` | App source in `apps/resilience-scorecard/` |
| `span_risk_endpoint` | Model Serving | `provable-resilience-span-risk` | ML model `span_risk_classifier` v1, inference table logging |
| `lakelink_fiber_provable_resilience_scorecard` | Dashboard | Lakelink Fiber — Provable Resilience Scorecard | Metric views in schema |
| `resilience_dashboard` | Dashboard | (superseded — empty) | N/A |

## 5. Deployment Procedures

### 5.1 First-Time Setup

```bash
# Clone the repo
git clone https://github.com/skhage/provable-resilience-intelligence.git
cd provable-resilience-intelligence

# Install Databricks CLI
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

# Authenticate
databricks auth login --host <WORKSPACE_URL>

# Validate the bundle
databricks bundle validate --target dev

# Deploy to dev
databricks bundle deploy --target dev
```

### 5.2 Standard Dev Deployment

```bash
# From develop branch
git checkout develop
git pull origin develop

# Validate
databricks bundle validate --target dev

# Deploy
databricks bundle deploy --target dev

# Verify
databricks bundle run --target dev resilience_pipeline
```

### 5.3 Production Deployment

```bash
# Merge develop into main via PR (required)
# After PR approval and CI passes:
git checkout main
git pull origin main

# Validate prod
databricks bundle validate --target prod

# Deploy prod
databricks bundle deploy --target prod

# Verify pipeline
databricks pipelines get <pipeline-id>

# Verify job schedule
databricks jobs get <job-id>
```

### 5.4 CI/CD Automated Flow

| Trigger | Action | Target |
| --- | --- | --- |
| PR to `main` or `develop` | `ci.yml`: validate + lint + test | N/A (checks only) |
| Push to `develop` | `deploy.yml`: `bundle deploy --target dev` | Dev |
| Push to `main` | `deploy.yml`: `bundle deploy --target prod` + auto-tag | Prod |

Auto-tags follow the format: `v2026.10.21-cfe7a15` (calendar + short SHA).

## 6. Rollback Procedure

### Scenario A: Bad Prod Deploy (code/config issue)

```bash
# 1. Revert the merge commit on main
git log --oneline -5  # find the bad commit
git revert <bad-commit-sha>
git push origin main
# CI/CD auto-deploys the reverted state

# 2. If urgent, manually deploy the previous good commit
git checkout <last-good-sha>
databricks bundle deploy --target prod
git checkout main
```

### Scenario B: Bad Pipeline Run (data issue)

```bash
# 1. Pause the job to stop further runs
databricks jobs update <job-id> --json '{"schedule": null}'

# 2. Check pipeline run status
databricks pipelines list-updates <pipeline-id>

# 3. Roll back tables using Delta time travel
# In SQL:
# RESTORE TABLE cdm_tmforum.provable_resilience_intelligence.<table>
#   TO VERSION AS OF <version_number>;

# 4. Fix the issue, redeploy, re-enable schedule
```

### Scenario C: Model Serving Regression

```bash
# 1. Check endpoint status
databricks serving-endpoints get provable-resilience-span-risk

# 2. Roll back to previous model version
# Update resilience_model.serving.yml: entity_version: <prev>
databricks bundle deploy --target prod

# 3. Or use the UI to swap served entity version immediately
```

## 7. Health Checks

### Post-Deployment Checklist

- [ ] `databricks bundle validate --target <target>` passes
- [ ] Pipeline exists and is in `IDLE` state (not `FAILED`)
- [ ] Job exists with correct schedule (6AM CT daily)
- [ ] Model serving endpoint is `READY` (not `UPDATING` or `FAILED`)
- [ ] Dashboard loads without query errors
- [ ] App is deployed and responds to health endpoint

### Automated Health Check Script

```bash
#!/bin/bash
TARGET=${1:-dev}
echo "=== Health Check: $TARGET ==="

# 1. Bundle state
databricks bundle validate --target $TARGET && echo "✅ Bundle valid" || echo "❌ Bundle invalid"

# 2. Pipeline
PIPELINE_ID=$(databricks bundle summary --target $TARGET --output json | python3 -c "import json,sys; print(json.load(sys.stdin)['resources']['pipelines']['resilience_pipeline']['id'])" 2>/dev/null)
if [ -n "$PIPELINE_ID" ]; then
    STATE=$(databricks pipelines get $PIPELINE_ID --output json | python3 -c "import json,sys; print(json.load(sys.stdin).get('state','UNKNOWN'))")
    echo "Pipeline $PIPELINE_ID: $STATE"
else
    echo "⚠️ Pipeline not yet deployed"
fi

# 3. Job
echo "Job: check schedule and last run status via UI or CLI"

# 4. Serving endpoint
databricks serving-endpoints get provable-resilience-span-risk 2>/dev/null && echo "✅ Endpoint exists" || echo "⚠️ Endpoint not found"

echo "=== Done ==="
```

## 8. Tagging & Governance

| Tag | Value | Applied to |
| --- | --- | --- |
| `telco_project` | `provable_resilience_intelligence` | All assets (CEO mandate) |
| `team` | `resilience-engineering` | Job |
| `dev` | `<username>` | Dev target resources (auto) |

## 9. Troubleshooting

| Issue | Cause | Fix |
| --- | --- | --- |
| `bundle validate` fails with warehouse error | Warehouse name mismatch | Update `warehouse` lookup name or use `--var` override |
| Pipeline FAILED | Check pipeline UI for error details | Fix source notebook, redeploy |
| App deploy fails | Source path not found | Verify `source_code_path` resolves from `bundle/resources/` |
| Model endpoint FAILED | Model version not registered | Register model in UC first, then deploy |
| CI fails on PR | Lint/test errors | Fix code, push again |
| `/Shared root_path` warning (prod) | Expected until SP configured | Ignore for now; fix when SP is created |

## 10. Contacts & Escalation

| Role | Responsibility |
| --- | --- |
| @devops | DAB config, CI/CD, deployment issues |
| @data-engineer | Pipeline source code, table schemas |
| @ml-engineer | Model training, serving config |
| @app-developer | App source code, UI issues |
| @pm | Prioritization, blockers, CEO escalation |
| CEO (human) | Infrastructure creation (repos, endpoints, SPs) |
