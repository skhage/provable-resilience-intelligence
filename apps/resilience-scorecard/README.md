# Lakelink Fiber — Provable Resilience Intelligence App

React/TypeScript + FastAPI Databricks App providing a resilience scorecard and
proactive action queue for enterprise network services.

## Architecture

```
Frontend (React + TypeScript)          Backend (FastAPI)
├─ / Scorecard Dashboard         ───▸  GET  /api/scores
│   └─ KPI header + service table       GET  /api/scores/summary
│                                       GET  /api/scores/risk-distribution
├─ /actions Action Queue          ───▸  GET  /api/actions
│   └─ Filter/sort + status buttons     PATCH /api/actions/{id}
│                                       GET  /api/actions/summary
└─ Health                         ───▸  GET  /api/health
     └─ Lakebase connectivity check
```

**State management:** Action queue state lives in Lakebase Postgres
(`proactive_actions` table) for durability across restarts.

**Data sources (3-tier fallback):**
- **Scorecard:** Live from Unity Catalog gold tables (8,000 services, $62.88M revenue at risk) via Statement Execution API. Falls back to mock if warehouse unavailable.
- **Action queue reads:** Lakebase `proactive_actions` → UC `proactive_action` (10,801 actions) → mock
- **Action queue writes:** Lakebase `proactive_actions` (status updates persist across restarts)

## Lakelink Fiber Brand

| Token | Value |
|-------|-------|
| Dark Teal | `#006272` |
| Platinum | `#E8E8E8` |
| Iron | `#4D4D4D` |
| Orange | `#F26522` |

## Project Structure

```
apps/resilience-scorecard/
├─ pyproject.toml              # Python dependencies
├─ app.yaml                    # Databricks App config
├─ README.md
└─ src/resilience_scorecard/
   ├─ backend/
   │  ├─ app.py                 # FastAPI entry point
   │  ├─ core.py                # Config, DI, app factory
   │  ├─ models.py              # Pydantic models
   │  ├─ router.py              # API routes
   │  └─ services/
   │     ├─ catalog_sql.py       # Unity Catalog SQL service (live data)
    │     ├─ lakebase.py          # Lakebase Postgres client (action state)
    │     └─ mock_data.py         # Mock data fallback
   └─ ui/
      ├─ routes/
      │  ├─ index.tsx            # Scorecard dashboard
      │  └─ actions.tsx          # Action queue
      ├─ components/
      │  ├─ dashboard/
      │  │  ├─ scorecard-header.tsx
      │  │  └─ service-table.tsx
      │  └─ actions/
      │     └─ action-queue-table.tsx
      └─ styles/
         └─ lakelink-theme.css   # Brand CSS variables
```

## API Endpoints

| Method | Path | operation_id | Description |
|--------|------|-------------|-------------|
| GET | `/api/health` | `getHealth` | Readiness + Lakebase status |
| GET | `/api/scores` | `listResilienceScores` | All service scores |
| GET | `/api/scores/summary` | `getResilienceSummary` | Aggregate KPIs |
| GET | `/api/scores/risk-distribution` | `getRiskDistribution` | Risk by category |
| GET | `/api/scores/{service_id}` | `getServiceScore` | Single service |
| GET | `/api/actions` | `listActions` | Action queue (Lakebase) |
| GET | `/api/actions/summary` | `getActionSummary` | Queue counts |
| PATCH | `/api/actions/{action_id}` | `updateActionStatus` | Update status |
| GET | `/api/actions/{action_id}` | `getAction` | Single action |

## Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `RESILIENCE_SCORECARD_LAKEBASE_HOST` | `ep-summer-hill-...` | Lakebase Postgres host |
| `RESILIENCE_SCORECARD_LAKEBASE_ENDPOINT` | `projects/telco-...` | Lakebase endpoint path |
| `RESILIENCE_SCORECARD_CATALOG` | `cdm_tmforum` | Unity Catalog name |
| `RESILIENCE_SCORECARD_SCHEMA` | `provable_resilience_intelligence` | Schema with gold tables |
| `RESILIENCE_SCORECARD_WAREHOUSE_ID` | `9cd919d96b11bf1c` | SQL warehouse for live queries |

## Prerequisites

1. **SQL Warehouse:** A serverless SQL warehouse (default: Serverless Starter Warehouse). Must have access to `cdm_tmforum.provable_resilience_intelligence`.
2. **Lakebase Project:** `telco-provable-resilience-intelligence-project` with `proactive_actions` table.
3. **Gold Tables:** `resilience_score_snapshot`, `service_inventory`, `customer`, `geographic_site`, `proactive_action` — all populated by the data pipeline.

## Setup

```bash
# Initialize with apx
apx init --as-member=apps/resilience-scorecard
apx dev apply lakebase

# Start dev servers
apx dev start

# Deploy to Databricks Apps
apx build
databricks apps deploy resilience-scorecard
```

## Demo Walkthrough

See `demo-flow-guide.md` in the project root for the full 3-act demo structure. This app covers:

- **Scene 4 (App Action Queue):** Navigate to `/actions` — NOC manager reviews pending reroutes, dispatches, escalations. Filter by status/priority. Update action status (Lakebase write).
- **Scene 5 (Sales Genie):** Return to `/` — Sales AE views customer portfolio resilience scores sorted by risk. Identify false-diversity services where working/protect paths share SRLGs.

## Live Data Integration

The app uses the Databricks SDK Statement Execution API to query gold tables directly. On startup, `CatalogSqlService` runs a connectivity test — if the warehouse responds, all scorecard endpoints serve live data. The health endpoint at `/api/health` reports `data_source: "live"` or `"mock"`.

**Key metrics (live):**
- 8,000 monitored services across 1,200 enterprise customers
- Avg resilience score: 50.0 (calibrated: 0.40×diversity + 0.30×hazard + 0.30×telemetry)
- 1,614 critical / 4,657 high / 1,728 medium / 1 low
- $62.88M total monthly revenue at risk
- 10,801 proactive actions (2,646 pending, 5,798 completed)

## Status

- [x] Live scorecard data from UC gold tables (P8-LIVE-DATA-SCORECARD)
- [x] Lakebase action state management
- [x] WCAG 2.1 AA accessibility (37 verified items)
- [x] Lakelink Fiber brand compliance (0 violations)
- [x] Responsive layout with mobile touch targets
- [ ] Seed Lakebase action queue from UC (P8-ACTION-QUEUE-UC-SYNC)
- [ ] Tag deployed app with `telco_project: provable_resilience_intelligence`
- [ ] Geospatial map view for at-risk spans (future)
