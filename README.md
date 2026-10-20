# Provable Resilience Intelligence

Governed, continuously updated resilience scoring for every **Lakelink Fiber** enterprise service.

Joins physical path (conduit, SRLGs, COs) with live network health and outside hazard signals (wildfire, flood, weather, 811 dig tickets). Turns "redundancy on paper" into proof.

## Architecture

| Layer | Description |
|-------|-------------|
| **Bronze** | Raw ingestion from geographic, resource, service, and hazard sources |
| **Silver** | SID/TMForum-aligned entities (geographic_site, physical_resource_span, etc.) |
| **Gold** | Resilience scores, risk models, proactive actions |
| **App** | React/FastAPI scorecard + Genie agent |

## Key Data Model (SID-aligned)

`geographic_site` • `physical_resource_span` • `physical_resource_conduit` • `shared_risk_group` • `customer` • `service_inventory` • `service_path` • `resource_alarm` • `resource_performance_measure` • `geographic_hazard_event` • `resilience_score_snapshot` • `proactive_action`

## Project Structure

```
provable-resilience-intelligence/
├── bundle/                  # DAB config (databricks.yml + resources/)
├── src/                     # Source notebooks and Python modules
├── pipeline/                # SDP pipeline notebooks (bronze/silver/gold)
├── apps/                    # Databricks App (resilience-scorecard)
├── data/                    # Synthetic data scripts
├── resources/               # Static resources
└── tests/                   # Unit and integration tests
```

## Deployment

```bash
# Validate
cd bundle && databricks bundle validate --target dev

# Deploy to dev
databricks bundle deploy --target dev

# Deploy to prod
databricks bundle deploy --target prod
```

## Branch Strategy

| Branch | Purpose |
|--------|---------|
| `main` | Production-ready, protected |
| `develop` | Integration branch for features |
| `feature/*` | Individual feature work |
| `hotfix/*` | Emergency production fixes |

## Catalog

**Target:** `cdm_tmforum.provable_resilience_intelligence`

## License

MIT
