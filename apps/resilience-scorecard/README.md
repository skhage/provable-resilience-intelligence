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

**Data sources:**
- **Scorecard:** Mock data until `cdm_tmforum.provable_resilience_intelligence.resilience_score_snapshot` is populated (P2-GOLD-RESILIENCE-SCORE)
- **Action queue:** Lakebase `proactive_actions` table (live), mock fallback

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
   │     ├─ lakebase.py          # Lakebase Postgres client
   │     └─ mock_data.py         # Mock data generator
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

## TODO (blocked on upstream)

- [ ] Wire scorecard to live gold tables when P2-GOLD-RESILIENCE-SCORE completes
- [ ] Wire action queue creation to resilience agent (P3-RESILIENCE-AGENT)
- [ ] Add geospatial map view for at-risk spans
- [ ] Submit to @designer for UX/brand review
- [ ] Tag deployed app with `telco_project: provable_resilience_intelligence`
