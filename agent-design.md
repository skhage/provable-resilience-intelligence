# Lakelink Fiber Resilience Intelligence Agent — Architecture Design

## Overview

The Resilience Intelligence Agent is a **Supervisor Agent** (Agent Bricks MAS pattern) that orchestrates
specialized sub-agents to deliver three core capabilities:
1. **Reroute Proposals** — Identify at-risk services and recommend network path changes
2. **Dispatch Prioritization** — Triage hazard events, correlate alarms, prioritize field crew dispatch
3. **Customer Resilience Reports** — Generate customer-ready service health summaries

**Supervisor Agent ID:** `bc01d3ea-8c78-4bd2-8aba-bbceff772418`
**Endpoint:** `mas-bc01d3ea-endpoint`
**AI Gateway:** `resilience-agent-gateway` (Claude Sonnet 4.5 + PII filtering + rate limits)

---

## Architecture Diagram

```
                        ┌──────────────────────────────────────────┐
                        │   Lakelink Fiber Resilience Agent        │
                        │   (Supervisor — Agent Bricks MAS)        │
                        │   Endpoint: mas-bc01d3ea-endpoint        │
                        └──────────────┬───────────────────────────┘
                                       │ Routes by intent
          ┌───────────────┬────────────┼────────────┬──────────────┐
          │               │            │            │              │
    ┌─────▼─────┐  ┌──────▼──────┐ ┌───▼────┐ ┌────▼─────┐  ┌────▼─────────┐
    │ Genie     │  │ Hazard      │ │Reroute │ │Customer  │  │ PII Guard    │
    │ Space     │  │ Intelligence│ │Advisor │ │Report    │  │ (AI Gateway) │
    │ (SQL)     │  │ (UC Func)   │ │(UC Func)│ │(UC Func) │  │ (guardrails) │
    └─────┬─────┘  └──────┬──────┘ └───┬────┘ └────┬─────┘  └──────────────┘
          │               │            │            │
    ┌─────▼───────────────▼────────────▼────────────▼──────────────────────┐
    │                  Unity Catalog Tables (54 objects)                    │
    │  cdm_tmforum.provable_resilience_intelligence                        │
    │  ┌────────────────┐ ┌───────────────┐ ┌─────────────────────────┐    │
    │  │ resilience_    │ │ geographic_   │ │ span_risk_predictions   │    │
    │  │ score_snapshot │ │ hazard_event  │ │ optical_anomaly_detect  │    │
    │  │ service_inv    │ │ hazard_span_  │ │ proactive_action        │    │
    │  │ customer       │ │ proximity     │ │ derived_shared_risk_grp │    │
    │  │ service_path   │ │ hazard_alarm_ │ │ physical_resource_span  │    │
    │  │                │ │ correlation   │ │                         │    │
    │  └────────────────┘ └───────────────┘ └─────────────────────────┘    │
    └──────────────────────────────────────────────────────────────────────┘
    ┌──────────────────────────────────────────────────────────────────────┐
    │                  ML Model Endpoints                                  │
    │  span-risk-classifier-v2 (XGBoost v4, UC registered)                │
    │  resilience-agent-gateway (Claude Sonnet 4.5, PII filter, rate lim) │
    └──────────────────────────────────────────────────────────────────────┘
```

---

## Tool Definitions

### Tool 1: `resilience_data` (Genie Space)
- **Type:** `genie_space`
- **Genie Space ID:** `01f1cd30d49118b38fabfb0cbacd966d`
- **Purpose:** Free-form SQL analytics on all 54 PRI tables. Handles data grounding queries,
  ad-hoc analysis, network-wide statistics, trend queries, and any question not handled
  by the specialized UC function tools.
- **Tables:** Full PRI schema (resilience_score_snapshot, service_inventory, customer,
  resource_alarm, resource_performance_measure, span_risk_predictions, optical_anomaly_detection,
  proactive_action, service_path, physical_resource_span, geographic_hazard_event, etc.)
- **Routes to:** General data questions, "how many", "show distribution", "compare", trends

### Tool 2: `hazard_lookup` (UC Function)
- **Type:** `uc_function`
- **Function:** `cdm_tmforum.provable_resilience_intelligence.hazard_intelligence`
- **Purpose:** Specialized hazard event intelligence with alarm correlation, service impact,
  and revenue at risk. Returns prioritized hazard exposure with recommended actions.
- **Parameters:**
  - `span_id_filter` (STRING) — Optional span filter. NULL for all spans.
  - `hazard_type_filter` (STRING) — earthquake, severe_weather, wildfire, flood, dig_ticket. NULL for all.
  - `severity_min` (STRING) — low, medium, high, critical. NULL for all.
  - `top_n` (INT) — Result limit. Default 20.
- **Returns:** span_id, hazard_id, hazard_type, severity, event_start, event_end,
  distance_km, affected_services, annual_revenue_at_risk_usd, correlated_alarm_count,
  recommended_action
- **Routes to:** "hazard exposure", "dispatch", "earthquake/wildfire/flood impact",
  "which spans are threatened", "crew dispatch priority"

### Tool 3: `reroute_advisor` (UC Function)
- **Type:** `uc_function`
- **Function:** `cdm_tmforum.provable_resilience_intelligence.reroute_recommender`
- **Purpose:** Identifies services needing rerouting based on composite risk factors:
  resilience score, span risk predictions, SRLG-based false diversity, and active hazard
  exposure. Returns prioritized recommendations with reroute urgency classification.
- **Parameters:**
  - `service_id_filter` (STRING) — Optional service ID. NULL for top at-risk.
  - `risk_band_filter` (STRING) — Excellent, Good, Moderate, At-Risk, Critical. NULL for Critical+At-Risk.
  - `customer_id_filter` (STRING) — Optional customer filter. NULL for all.
  - `top_n` (INT) — Result limit. Default 25.
- **Returns:** service_id, customer_id, customer_name, service_type, sla_tier, mrc_usd,
  overall_score, risk_band, sold_as_diverse, has_protect_path, shared_srlg_count,
  false_diversity, critical_span_count, active_hazard_count, reroute_priority,
  recommended_action
- **Priority Levels:**
  - P1-EMERGENCY: Critical risk + premium SLA
  - P2-URGENT: Critical risk OR false diversity
  - P3-HIGH: At-Risk + premium SLA
  - P4-MEDIUM: At-Risk + standard SLA
  - P5-ROUTINE: Moderate with risk factors
- **Routes to:** "reroute", "which services need path change", "false diversity",
  "SRLG overlap", "at-risk services", "priority reroute list"

### Tool 4: `customer_report` (UC Function)
- **Type:** `uc_function`
- **Function:** `cdm_tmforum.provable_resilience_intelligence.customer_resilience_report`
- **Purpose:** Generates a comprehensive per-service resilience summary for a specific
  customer. Includes all four score components, diversity analysis, and latest proactive
  actions. Designed for customer-facing reports.
- **Parameters:**
  - `customer_id_filter` (STRING) — Required. Example: CUST-0001.
  - `include_actions` (BOOLEAN) — Include proactive actions. Default TRUE.
- **Returns:** customer_id, customer_name, service_id, service_type, sla_tier, mrc_usd,
  overall_score, risk_band, path_diversity_score, hazard_exposure_score,
  telemetry_health_score, sold_as_diverse, shared_srlg_count, active_hazards,
  active_alarms, latest_action_type, latest_action_priority, latest_action_status,
  latest_action_trigger
- **Routes to:** "customer report", "generate resilience report for", "account review",
  "SLA compliance", "customer health summary"

---

## Routing Examples (7 total)

| # | Example Question | Routed Tool | Key Guidelines |
|---|---|---|---|
| 1 | Which spans need immediate rerouting? | reroute_advisor | Query critical risk, join service paths, prioritize by SLA |
| 2 | Show optical degradation anomalies | resilience_data | Query optical_anomaly_detection, cross-ref span risk |
| 3 | Generate customer resilience report for premium_plus | customer_report | Include all score components, format as exec report |
| 4 | Active hazard events needing crew dispatch? | hazard_lookup | severity_min=high, include alarm correlation |
| 5 | Services with false diversity (shared SRLGs) | reroute_advisor | Focus false_diversity=true, show shared SRLG count |
| 6 | Generate resilience report for CUST-0001 | customer_report | Format as exec report with Lakelink Fiber branding |
| 7 | Contact details for customers (PII) | REFUSED | Privacy-controlled data, offer anonymized metrics |

---

## AI Gateway Configuration

**Endpoint:** `resilience-agent-gateway`

| Setting | Value |
|---|---|
| Primary model | Claude Sonnet 4.5 (pay-per-token) |
| Fallback model | GPT-5 Mini (pay-per-token) |
| User rate limit | 30 req/min, 50K tokens/min |
| Service rate limit | 1,000 req/hr, 2M tokens/hr |
| PII filtering | Enabled (guardrails) |
| Inference table | cdm_tmforum.provable_resilience_intelligence.resilience_agent_* |

### Guardrails
- **Input guardrail:** PII detection — blocks requests containing SSN, credit card, phone numbers
- **Output guardrail:** PII filtering — redacts any PII that may appear in model responses
- **Safety:** Adversarial prompt detection, refusal of off-topic requests

---

## ML Model Dependencies

### Span Risk Classifier
- **Endpoint:** `span-risk-classifier-v2`
- **Model:** `cdm_tmforum.provable_resilience_intelligence.span_risk_classifier` v2
- **Algorithm:** XGBoost v4 (4-class: low/moderate/high/critical)
- **Training data:** 10,092 spans with 22 features (alarm counts, OSNR stats, BER stats,
  hazard proximity, SRLG membership, connectivity degree)
- **Predictions stored:** `span_risk_predictions` (10,092 rows)
- **Drift monitoring:** Active — last check PASSED, 0/22 features drifted

### Optical Anomaly Detection
- **Algorithm:** Isolation Forest (unsupervised)
- **Features:** OSNR (avg, min, p5), BER (avg, max, p95), power (avg, std), CD, PMD
- **Predictions stored:** `optical_anomaly_detection` (10,000 spans)
- **Severity bands:** info/warning/minor/major/critical (from anomaly_score quantiles)
- **Key finding:** OSNR cliff at 20 dB — spans below this threshold require immediate attention

### Resilience Score V2
- **Formula:** 0.4 × path_diversity + 0.3 × hazard_exposure + 0.3 × telemetry_health + SLA boost
- **SLA boost:** premium_plus +5, premium +2
- **Distribution:** 8,000 services scored (Excellent: 437, Good: 3,519, Moderate: 2,509,
  At-Risk: 1,524, Critical: 11)

---

## Evaluation Dataset

**Table:** `resilience_agent_eval_dataset` (12 scenarios)

| Category | Count | Difficulty |
|---|---|---|
| reroute_proposal | 3 | standard, complex, standard |
| dispatch_request | 3 | standard, complex, standard |
| customer_report | 3 | standard, complex, standard |
| data_grounding | 2 | standard, standard |
| safety_pii | 1 | adversarial |

**Evaluation experiment:** `resilience_agent_evaluation` (MLflow)

---

## Genie Spaces

| Space | ID | Tables | Purpose |
|---|---|---|---|
| Service Assurance | 01f1cc02b4c7110aaa64d6bccad5d95f | 22 | NOC/SA team analytics |
| Sales | 01f1cc02b7061b9bab644383b5cd0bfa | 16 | Customer-facing sales analytics |
| Data Lineage | 01f1cc01d05b10ecb56d3addec7b32ad | PRI schema | Schema health monitoring |
| Resilience Intelligence | 01f1cd30d49118b38fabfb0cbacd966d | PRI schema | Supervisor agent backend |

---

## Data Flow

```
User Query → Supervisor Agent → Intent Classification → Tool Selection
                                                            │
         ┌──────────────────────────────────────────────────┤
         │                                                  │
    General data question                         Specialized query
         │                                                  │
    Genie Space (SQL)                    UC Function (parameterized)
         │                                                  │
    Free-form SQL on                   hazard_intelligence()
    54 PRI tables                      reroute_recommender()
         │                             customer_resilience_report()
         │                                                  │
         └──────────────────┬───────────────────────────────┘
                            │
                    Response Generation
                    (Claude Sonnet 4.5)
                            │
                    PII Guardrail Check
                            │
                    User Response
```

---

## Key Metrics

| Metric | Value |
|---|---|
| Total PRI tables | 54 objects (managed, views, metric views) |
| Services scored | 8,000 |
| Spans classified | 10,092 |
| Proactive actions | 10,801 |
| Hazard events | 57,399 |
| Alarm-hazard correlations | 20,702 |
| Resource alarms | 2,000,000 |
| Performance measurements | 5,000,000 |
| False diversity rate | 29.2% (2,332/8,000 services) |
| Revenue at risk (false diversity) | $438M annual |
| Eval scenarios | 12 |

---

## Known Blockers

1. **Governed tag value** — `provable_resilience_intelligence` not yet in allowed tag
   values for `telco_project` policy. CEO action required to add. All 3 new UC functions
   remain untagged until resolved.
2. **Inference table backfill** — `resilience_agent_payload` has 75 rows,
   `resilience_gateway_payload` and `span_risk_classifier_payload` at 0. Waiting on
   @data-engineer to route live traffic.

---

## Version History

| Date | Change | Author |
|---|---|---|
| 2026-10-23 | Initial architecture: 4-tool supervisor (Genie + 3 UC functions), 7 examples, AI Gateway config documented | @ml-engineer |
| 2026-10-20 | Supervisor agent created with 1 Genie tool, 3 examples | @ml-engineer |
| 2026-10-19 | AI Gateway endpoint deployed (Claude Sonnet 4.5 + PII + rate limits) | @ml-engineer |
