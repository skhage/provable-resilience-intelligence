"""Mock data for the resilience scorecard.

Used until gold tables (resilience_score_snapshot, proactive_action) are
populated by the data pipeline. Every mock record matches the target schema
so the UI needs zero changes when real data lands.

Branding: Lakelink Fiber (never Lumen).
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import random

# Fixed base timestamp for deterministic mock data (BUG-QA-014)
_FIXED_BASE = datetime(2026, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Lakelink Fiber mock customers and services
# ---------------------------------------------------------------------------

_CUSTOMERS = [
    ("CUST-001", "Apex Healthcare Systems"),
    ("CUST-002", "Meridian Financial Group"),
    ("CUST-003", "Cascade Energy Partners"),
    ("CUST-004", "Pinnacle Manufacturing Corp"),
    ("CUST-005", "Summit Logistics Inc"),
    ("CUST-006", "Ironwood Data Centers"),
    ("CUST-007", "Crestline Retail Holdings"),
    ("CUST-008", "Broadleaf Education Network"),
]

_SERVICES = [
    ("SVC-1001", "Chicago-Denver MPLS Ring", "CUST-001"),
    ("SVC-1002", "Dallas-Houston Metro Ethernet", "CUST-002"),
    ("SVC-1003", "Seattle-Portland Dark Fiber", "CUST-003"),
    ("SVC-1004", "Atlanta-Miami Wavelength", "CUST-004"),
    ("SVC-1005", "NYC-DC Protected Span", "CUST-005"),
    ("SVC-1006", "Denver-Phoenix Long Haul", "CUST-006"),
    ("SVC-1007", "Minneapolis-Chicago SD-WAN", "CUST-007"),
    ("SVC-1008", "Boston-NYC Metro Ring", "CUST-008"),
    ("SVC-1009", "LA-San Jose Backbone", "CUST-001"),
    ("SVC-1010", "Tampa-Jacksonville Direct", "CUST-002"),
    ("SVC-1011", "Salt Lake City-Boise Span", "CUST-003"),
    ("SVC-1012", "Omaha-Kansas City Ring", "CUST-004"),
    ("SVC-1013", "Phoenix-Tucson Metro", "CUST-005"),
    ("SVC-1014", "Raleigh-Charlotte DWDM", "CUST-006"),
    ("SVC-1015", "Cleveland-Pittsburgh Express", "CUST-007"),
    ("SVC-1016", "Nashville-Memphis Backbone", "CUST-008"),
]

_RATING_MAP = {
    (85, 100): "A",
    (70, 85): "B",
    (55, 70): "C",
    (40, 55): "D",
    (0, 40): "F",
}


def _score_to_rating(score: float) -> str:
    for (lo, hi), rating in _RATING_MAP.items():
        if lo <= score < hi:
            return rating
    return "A" if score >= 85 else "F"


def _risk_level(score: float) -> str:
    if score < 40:
        return "critical"
    if score < 60:
        return "high"
    if score < 75:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Mock score generator
# ---------------------------------------------------------------------------

def generate_mock_scores() -> list[dict]:
    """Generate 16 mock resilience score snapshots."""
    random.seed(42)  # deterministic for demo consistency
    now = _FIXED_BASE
    cust_map = {c[0]: c[1] for c in _CUSTOMERS}
    scores = []

    for svc_id, svc_name, cust_id in _SERVICES:
        phys = round(random.uniform(20, 98), 1)
        net = round(random.uniform(30, 99), 1)
        env = round(random.uniform(15, 95), 1)
        overall = round(phys * 0.4 + net * 0.35 + env * 0.25, 1)
        srlg = random.randint(1, 8)
        spf = random.randint(0, 4)

        scores.append({
            "service_id": svc_id,
            "service_name": svc_name,
            "customer_id": cust_id,
            "customer_name": cust_map[cust_id],
            "resilience_score": overall,
            "physical_redundancy_score": phys,
            "network_health_score": net,
            "environmental_risk_score": env,
            "path_diversity_rating": _score_to_rating(overall),
            "srlg_count": srlg,
            "single_point_failures": spf,
            "snapshot_timestamp": (now - timedelta(minutes=random.randint(0, 120))).isoformat(),
            "revenue_at_risk_usd": round(random.uniform(50_000, 800_000), 2),
        })

    return scores


def generate_mock_summary(scores: list[dict]) -> dict:
    """Derive summary stats from mock scores."""
    levels = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    total_spf = 0
    for s in scores:
        level = _risk_level(s["resilience_score"])
        levels[level] += 1
        total_spf += s["single_point_failures"]

    return {
        "total_services": len(scores),
        "avg_resilience_score": round(sum(s["resilience_score"] for s in scores) / len(scores), 1),
        "critical_count": levels["critical"],
        "high_risk_count": levels["high"],
        "medium_risk_count": levels["medium"],
        "low_risk_count": levels["low"],
        "total_single_point_failures": total_spf,
        "total_srlg_groups": 809,  # BUG-DW-031: realistic mock matching shared_risk_group table count
        "total_revenue_at_risk_usd": round(sum(s.get("revenue_at_risk_usd", 0) for s in scores), 2),
    }


# ---------------------------------------------------------------------------
# Mock action generator
# ---------------------------------------------------------------------------

_RISK_TRIGGERS = [
    "Wildfire proximity < 5 mi (NIFC alert)",
    "Flood zone overlap (FEMA Zone A)",
    "811 dig ticket within 500 ft",
    "Conduit SRLG single-point failure",
    "Severe weather (NWS tornado warning)",
    "Fiber cut — adjacent span alarm",
    "CO power backup < 4 hrs",
    "Optical degradation (BER > 1e-6)",
]


def generate_mock_actions() -> list[dict]:
    """Generate 12 mock proactive actions."""
    random.seed(99)
    now = _FIXED_BASE
    actions = []
    action_types = ["reroute", "dispatch", "notify"]
    statuses = ["pending", "pending", "pending", "in_progress", "in_progress", "completed"]
    priorities = ["critical", "critical", "high", "high", "medium", "medium", "low"]

    for i in range(12):
        svc = _SERVICES[i % len(_SERVICES)]
        act_type = random.choice(action_types)
        priority = random.choice(priorities)
        status = random.choice(statuses)
        trigger = random.choice(_RISK_TRIGGERS)

        desc_map = {
            "reroute": f"Reroute traffic for {svc[1]} via alternate path to avoid {trigger.split('(')[0].strip()}",
            "dispatch": f"Dispatch field crew to inspect {svc[1]} span near {trigger.split('(')[0].strip()}",
            "notify": f"Notify customer about potential service impact on {svc[1]} due to {trigger.split('(')[0].strip()}",
        }

        # Hazard context for hazard-triggered actions (HAZARD-VIS-SPEC §5)
        hazard_context = {}
        if "Wildfire" in trigger or "Flood" in trigger or "811" in trigger or "Severe weather" in trigger:
            hazard_types_map = {
                "Wildfire": ("wildfire", "Park Fire", 39.8, -121.6),
                "Flood": ("flood", "Flood Warning #2456", 29.76, -95.37),
                "811": ("dig_ticket", "DT-2026-4421", 32.78, -96.80),
                "Severe weather": ("severe_weather", "NWS Tornado Watch #384", 35.22, -97.44),
            }
            for key, (htype, hname, lat, lng) in hazard_types_map.items():
                if key in trigger:
                    hazard_context = {
                        "hazard_type": htype,
                        "hazard_name": hname,
                        "hazard_severity": priority,
                        "hazard_spans_affected": random.randint(2, 15),
                        "hazard_latitude": lat,
                        "hazard_longitude": lng,
                        "hazard_containment_pct": round(random.uniform(5, 85), 1) if htype == "wildfire" else None,
                        "hazard_last_update": (now - timedelta(minutes=random.randint(10, 240))).isoformat(),
                    }
                    break

        actions.append({
            "action_id": f"ACT-{1000 + i}",
            "action_type": act_type,
            "service_id": svc[0],
            "service_name": svc[1],
            "risk_trigger": trigger,
            "priority": priority,
            "status": status,
            "assigned_to": random.choice(["NOC Team A", "Field Ops West", "Field Ops East", "Customer Success", None]),
            "description": desc_map[act_type],
            "resolution_notes": "Traffic rerouted successfully via backup path" if status == "completed" else None,
            "created_at": (now - timedelta(hours=random.randint(1, 48))).isoformat(),
            "updated_at": (now - timedelta(minutes=random.randint(0, 120))).isoformat(),
            **hazard_context,
        })

    return actions


def generate_mock_hazard_list() -> list[dict]:
    """Mock hazard list for the summary table."""
    now = _FIXED_BASE
    return [
        {"hazard_id": "HZ-001", "hazard_type": "wildfire", "name": "Park Fire — Butte County", "severity": "critical", "location": "39.80\u00b0N, 121.60\u00b0W", "spans_affected": 12, "is_active": True, "last_update": (now - timedelta(hours=2)).isoformat()},
        {"hazard_id": "HZ-002", "hazard_type": "severe_weather", "name": "NWS Tornado Watch #384", "severity": "critical", "location": "35.22\u00b0N, 97.44\u00b0W", "spans_affected": 8, "is_active": True, "last_update": (now - timedelta(hours=1)).isoformat()},
        {"hazard_id": "HZ-003", "hazard_type": "flood", "name": "Flood Warning #2456", "severity": "medium", "location": "29.76\u00b0N, 95.37\u00b0W", "spans_affected": 6, "is_active": True, "last_update": (now - timedelta(hours=4)).isoformat()},
        {"hazard_id": "HZ-004", "hazard_type": "dig_ticket", "name": "DT-2026-4421", "severity": "low", "location": "32.78\u00b0N, 96.80\u00b0W", "spans_affected": 2, "is_active": True, "last_update": (now - timedelta(hours=8)).isoformat()},
        {"hazard_id": "HZ-005", "hazard_type": "earthquake", "name": "M3.2 — Central Oklahoma", "severity": "low", "location": "35.50\u00b0N, 97.30\u00b0W", "spans_affected": 3, "is_active": True, "last_update": (now - timedelta(hours=12)).isoformat()},
    ]


def generate_mock_hazard_summary() -> dict:
    """Mock hazard summary for fallback when hazard tables are unavailable."""
    return {
        "active_hazards": 7554,
        "spans_at_risk": 562,
        "services_impacted": 214,
        "revenue_exposed_usd": 18_742_800.00,
    }


def generate_mock_product_offerings() -> list[dict]:
    """Mock Lakelink Fiber product offerings (5 products matching UC table)."""
    return [
        {"product_offering_id": "PROD-WL-001", "service_type": "wavelength", "product_name": "Lakelink Fiber WaveConnect", "product_category": "optical_transport", "network_technology": "DWDM", "technology_domain": "optical", "sla_tier_default": "premium_plus", "bandwidth_options": "10G,40G,100G,400G", "is_diverse_eligible": True, "mrc_range_usd": "2000-15000"},
        {"product_offering_id": "PROD-ETH-001", "service_type": "ethernet", "product_name": "Lakelink Fiber EtherLink", "product_category": "packet_services", "network_technology": "Carrier_Ethernet", "technology_domain": "packet", "sla_tier_default": "premium", "bandwidth_options": "100M,1G,10G,100G", "is_diverse_eligible": True, "mrc_range_usd": "500-8000"},
        {"product_offering_id": "PROD-DF-001", "service_type": "dark_fiber", "product_name": "Lakelink Fiber DarkPath", "product_category": "physical_infrastructure", "network_technology": "Dark_Fiber", "technology_domain": "physical", "sla_tier_default": "standard", "bandwidth_options": "unlimited", "is_diverse_eligible": True, "mrc_range_usd": "1500-12000"},
        {"product_offering_id": "PROD-VPN-001", "service_type": "ip_vpn", "product_name": "Lakelink Fiber CloudVPN", "product_category": "ip_services", "network_technology": "MPLS_IP", "technology_domain": "ip", "sla_tier_default": "premium", "bandwidth_options": "50M,100M,1G,10G", "is_diverse_eligible": True, "mrc_range_usd": "800-6000"},
        {"product_offering_id": "PROD-SEC-001", "service_type": "managed_security", "product_name": "Lakelink Fiber SecureEdge", "product_category": "security_services", "network_technology": "SD_WAN_SASE", "technology_domain": "security", "sla_tier_default": "premium_plus", "bandwidth_options": "100M,1G,10G", "is_diverse_eligible": False, "mrc_range_usd": "1200-10000"},
    ]


def generate_mock_crosswalk() -> list[dict]:
    """Mock hazard×span crosswalk data (aggregated by type × proximity band)."""
    return [
        {"hazard_type": "dig_ticket", "proximity_band": "direct_impact", "intersection_count": 74, "distinct_spans": 73, "avg_services_per_span": 69.8, "avg_distance_km": 0.62},
        {"hazard_type": "dig_ticket", "proximity_band": "near_field", "intersection_count": 84, "distinct_spans": 83, "avg_services_per_span": 14.8, "avg_distance_km": 1.37},
        {"hazard_type": "earthquake", "proximity_band": "direct_impact", "intersection_count": 10, "distinct_spans": 10, "avg_services_per_span": 4.3, "avg_distance_km": 0.65},
        {"hazard_type": "earthquake", "proximity_band": "near_field", "intersection_count": 189, "distinct_spans": 188, "avg_services_per_span": 9.2, "avg_distance_km": 3.45},
        {"hazard_type": "earthquake", "proximity_band": "buffer_zone", "intersection_count": 33722, "distinct_spans": 9656, "avg_services_per_span": 6.3, "avg_distance_km": 50.73},
        {"hazard_type": "flood", "proximity_band": "direct_impact", "intersection_count": 12, "distinct_spans": 12, "avg_services_per_span": 4.2, "avg_distance_km": 0.64},
        {"hazard_type": "flood", "proximity_band": "near_field", "intersection_count": 296, "distinct_spans": 290, "avg_services_per_span": 19.9, "avg_distance_km": 3.3},
        {"hazard_type": "flood", "proximity_band": "buffer_zone", "intersection_count": 5235, "distinct_spans": 4005, "avg_services_per_span": 7.0, "avg_distance_km": 17.35},
        {"hazard_type": "severe_weather", "proximity_band": "direct_impact", "intersection_count": 27, "distinct_spans": 27, "avg_services_per_span": 3.4, "avg_distance_km": 0.62},
        {"hazard_type": "severe_weather", "proximity_band": "near_field", "intersection_count": 555, "distinct_spans": 520, "avg_services_per_span": 5.7, "avg_distance_km": 3.53},
        {"hazard_type": "severe_weather", "proximity_band": "buffer_zone", "intersection_count": 24429, "distinct_spans": 9172, "avg_services_per_span": 7.4, "avg_distance_km": 25.63},
        {"hazard_type": "wildfire", "proximity_band": "direct_impact", "intersection_count": 9, "distinct_spans": 9, "avg_services_per_span": 1.8, "avg_distance_km": 0.59},
        {"hazard_type": "wildfire", "proximity_band": "near_field", "intersection_count": 386, "distinct_spans": 379, "avg_services_per_span": 6.5, "avg_distance_km": 3.48},
        {"hazard_type": "wildfire", "proximity_band": "buffer_zone", "intersection_count": 14088, "distinct_spans": 7517, "avg_services_per_span": 7.4, "avg_distance_km": 25.57},
    ]


def generate_mock_crosswalk_summary() -> dict:
    """Mock KPI summary for the hazard crosswalk view."""
    return {
        "total_intersections": 79116,
        "distinct_spans_exposed": 10074,
        "total_spans": 10092,
        "exposure_pct": 99.8,
        "hazard_types": 5,
        "direct_impact_count": 132,
        "near_field_count": 1510,
        "buffer_zone_count": 77474,
    }


def generate_mock_action_summary(actions: list[dict]) -> dict:
    """Derive action queue summary from mock actions."""
    counts = {"pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
    crit_pending = 0
    for a in actions:
        counts[a["status"]] = counts.get(a["status"], 0) + 1
        if a["status"] == "pending" and a["priority"] == "critical":
            crit_pending += 1

    return {
        "total_actions": len(actions),
        "pending_count": counts["pending"],
        "in_progress_count": counts["in_progress"],
        "completed_count": counts["completed"],
        "cancelled_count": counts["cancelled"],
        "critical_pending": crit_pending,
    }


# ---------------------------------------------------------------------------
# Conduit coverage (P35-APP-CONDUIT-COVERAGE-BADGE) — small deterministic sample
# Live v4 (post BUG-DP-068 B2): 55 REAL_SEGMENTED / 92 BB_SEGMENTED / 1,914 INVENTORY_ONLY.
# ---------------------------------------------------------------------------

_MOCK_CONDUITS = [
    # id, name, corridor, type, region, km, class, seg_km, latA, lonA, latZ, lonZ
    ("CDT-BB-0005", "Backbone St. Louis-Indianapolis", "I-70", "underground", "Central", 372.9, "REAL_SEGMENTED", 372.9, 38.62, -90.21, 39.79, -86.15),
    ("CDT-BB-0012", "Backbone Denver-Kansas City", "I-70", "underground", "Central", 905.2, "REAL_SEGMENTED", 905.2, 39.74, -104.99, 39.10, -94.58),
    ("CDT-BB-0009", "Backbone New York-New York", "I-10", "aerial", "East", 3.5, "REAL_SEGMENTED", 3.2, 40.71, -74.02, 40.71, -73.98),
    ("CDT-BBR-0061", "Backbone Route Phoenix-Los Angeles #1", "I-10", "underground", "West", 598.4, "BB_SEGMENTED", 598.4, 33.45, -112.07, 34.05, -118.24),
    ("CDT-BBR-0077", "Backbone Route Atlanta-Charlotte #1", "I-85", "aerial", "Southeast", 365.0, "BB_SEGMENTED", 365.0, 33.75, -84.39, 35.23, -80.84),
    ("CDT-0412", "Metro Dallas Ring 4", None, "direct_buried", "Central", 18.6, "INVENTORY_ONLY", 0.0, 32.78, -96.80, 32.90, -96.70),
    ("CDT-0988", "Metro Seattle Lateral 2", None, "underground", "West", 9.1, "INVENTORY_ONLY", 0.0, 47.61, -122.33, 47.67, -122.30),
]


def generate_mock_conduit_coverage() -> list[dict]:
    """Mock conduit coverage rows (schema matches ConduitCoverageOut)."""
    rows = []
    for (cid, name, corr, ctype, region, km, cls, seg, la, loa, lz, loz) in _MOCK_CONDUITS:
        rows.append({
            "conduit_id": cid, "conduit_name": name, "corridor": corr,
            "conduit_type": ctype, "owner": "lakelink_fiber", "region": region,
            "length_km": km, "span_coverage_class": cls, "segmented_km": seg,
            "coverage_pct": round(min(100.0, 100.0 * seg / km), 2) if km else 0.0,
            "site_a_id": None, "site_z_id": None,
            "lat_a": la, "lon_a": loa, "lat_z": lz, "lon_z": loz,
        })
    return rows


def generate_mock_conduit_coverage_summary() -> dict:
    """Mock legend counts mirroring the live v4 distribution."""
    classes = [
        {"span_coverage_class": "REAL_SEGMENTED", "conduit_count": 55, "length_km": 76582.7, "segmented_km": 76594.4},
        {"span_coverage_class": "BB_SEGMENTED", "conduit_count": 92, "length_km": 131324.2, "segmented_km": 131324.9},
        {"span_coverage_class": "INVENTORY_ONLY", "conduit_count": 1914, "length_km": 1933666.1, "segmented_km": 0.0},
    ]
    return {
        "total_conduits": sum(c["conduit_count"] for c in classes),
        "classes": classes,
        "source_table": "physical_resource_conduit_v4_candidate",
    }
