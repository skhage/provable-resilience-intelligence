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
