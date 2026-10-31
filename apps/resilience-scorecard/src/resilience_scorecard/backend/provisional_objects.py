"""Lakelink Fiber PRI: PROVISIONAL object set for the DEC-41 partial cutover (BUG-QA-100).

Pure module (no SDK import) shared by the router fallback and CatalogSqlService.

Source of truth: ops/v4_cutover_runbook.py PARTIAL_KEEP_V3 (DEC id 41 + DEC id 42 expansion +
DEC id 44 FK consumers). In partial mode, each of those objects gets one of two verdicts:
  * KEPT_V3_PROVISIONAL: the v3 live object stays the source, so the UI must show the PROVISIONAL label (DEC-42).
  * DEFERRED_V4_1: a v4-only object (no v3 live object and not in the v3 manifest). Nothing is
    kept, so there is no PROVISIONAL label.
tests/test_provisional_objects_qa100.py checks that this module stays in sync with the runbook.
"""
from __future__ import annotations

import re

V3_MANIFEST_VERSION = "PRI-DEMO-FREEZE-v3"

# Mirror of ops/v4_cutover_runbook.PARTIAL_KEEP_V3 (same order). The sync test enforces equality.
PARTIAL_KEEP_V3_CANDIDATES: tuple[str, ...] = (
    "hazard_span_intersection", "span_risk_predictions", "resilience_score_snapshot",
    "hazard_span_proximity", "span_hazard_features", "hazard_proximity_count",
    "proactive_action",
    "path_diversity_conduit",
    "diversity_coverage",
    "revenue_at_risk", "mv_mrc_protected",
    # DEC id 44 FK consumers (non-runbook items)
    "optical_anomaly_detection", "span_risk_inference_log",
)

# v4-only candidates. They have no v3 live object and are not in the v3 manifest, so the runbook
# verdict is DEFERRED_V4_1 (confirmed live on 2026-10-31).
DEFERRED_V4_1_OBJECTS: frozenset[str] = frozenset(
    {"span_hazard_features", "path_diversity_conduit", "mv_mrc_protected"}
)

# Fallback for when the live manifest query is unavailable: every KEEP_V3 candidate except the deferred ones.
DEFAULT_PROVISIONAL_OBJECTS: tuple[str, ...] = tuple(
    o for o in PARTIAL_KEEP_V3_CANDIDATES if o not in DEFERRED_V4_1_OBJECTS
)

# P73 / DEC-PRI-V4-BRIDGE-RETAIN-BOTH-MODES (id 45): in a FULL cutover these 2 historical ML output/log tables
# still stay on v3 (re-keying is v4.1 ML scope), so the manifest labels them PROVISIONAL in FULL mode too.
# Mirror of ops/v4_cutover_runbook.FULL_MODE_PROVISIONAL (the sync test enforces equality).
FULL_MODE_PROVISIONAL_OBJECTS: tuple[str, ...] = ("optical_anomaly_detection", "span_risk_inference_log")

_IDENT = re.compile(r"^[a-z0-9_]+$")
if not all(_IDENT.match(o) for o in PARTIAL_KEEP_V3_CANDIDATES + (V3_MANIFEST_VERSION.lower().replace("-", "_"),)):
    raise ValueError("provisional object names must be plain lower-case identifiers")  # pragma: no cover

# Live derivation. This mirrors runbook partial_keep_verdict(): a candidate is KEPT_V3_PROVISIONAL only when
# it is in the v3 manifest AND a live object exists. Otherwise it is DEFERRED_V4_1 (or fails closed in the
# runbook). The v3 fingerprint gate is enforced by the runbook at cutover time, not here.
# The names are compile-time constants checked against _IDENT above, so they are not user input.
_IN_LIST = ", ".join("'" + o + "'" for o in PARTIAL_KEEP_V3_CANDIDATES)
PROVISIONAL_OBJECTS_SQL = f"""
SELECT m.object_name
FROM demo_freeze_manifest m
WHERE m.manifest_version = '{V3_MANIFEST_VERSION}'
  AND m.object_name IN ({_IN_LIST})
  AND EXISTS (
    SELECT 1 FROM information_schema.tables t
    WHERE t.table_schema = current_schema() AND t.table_name = m.object_name
  )
GROUP BY m.object_name
ORDER BY m.object_name
"""
