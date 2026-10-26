"""P35-DEVOPS-V4-FROZEN-WRITE-GUARD: v4 shadow-build code must never write to v3 FROZEN objects.

Decision DEC-PRI-V4-SHADOW-BUILD opens a shadow-build window: agents may create and
write *_v4_candidate tables and metric views, but must never ALTER/UPDATE/RESTORE
(or otherwise write) an object that is FROZEN in PRI-DEMO-FREEZE-v3. Promotion to live
needs a FREEZE-v4 manifest from @data-planner, @qa sign-off and a @pm cutover decision.

This is a static CI gate (no Spark needed):

* Scope: every .py / .sql / .ipynb / .yml / .yaml file outside tests/, .git/ and .github/
  whose path contains "v4" or whose content references v4 shadow work
  ("_v4_candidate", "FREEZE-v4", "v4_shadow").
* Detection: SQL DML/DDL (INSERT, MERGE, UPDATE ... SET, DELETE FROM, TRUNCATE, ALTER,
  RESTORE TABLE, CREATE [OR REPLACE|OR REFRESH], REPLACE TABLE, DROP, COMMENT ON) and
  PySpark / pipeline writers (saveAsTable, insertInto, toTable, DeltaTable.forName,
  @dlt/@dp table decorators with name=...).
* Rule: the write target (last identifier segment, catalog/schema/backticks stripped)
  must not be in tests/frozen_v3_objects.json. *_v4_candidate targets always pass.
  Reads of FROZEN tables (SELECT ... FROM, VERSION AS OF) are allowed.

Simple string constants in the same file (OUTPUT_TABLE = f"{SCHEMA}.x_v4_candidate") are
resolved, so saveAsTable(OUTPUT_TABLE) and f"... {OUTPUT_TABLE} ..." are checked too.
Known limit: other dynamic targets (loop variables, IDENTIFIER(:t)) cannot be resolved
statically; they are reported as warnings. ml_freeze_guard.assert_writable() is the
runtime companion for those cases.

Refresh tests/frozen_v3_objects.json only when a new freeze manifest is captured.
"""
import json
import pathlib
import re
import warnings

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
SNAPSHOT_PATH = pathlib.Path(__file__).with_name("frozen_v3_objects.json")
CATALOG_SCHEMA = "cdm_tmforum.provable_resilience_intelligence"

SHADOW_SUFFIX = "_v4_candidate"
SCAN_SUFFIXES = {".py", ".sql", ".ipynb", ".yml", ".yaml"}
EXCLUDE_DIRS = {
    ".git", ".github", "tests", "node_modules", "__pycache__", ".ruff_cache",
    ".databricks", "__dist__", ".ipynb_checkpoints", ".venv",
}
V4_CONTENT_MARKER = re.compile(r"_v4_candidate|freeze[-_ ]?v4|v4[-_]shadow", re.IGNORECASE)
V4_PATH_MARKER = re.compile(r"v4", re.IGNORECASE)

# Identifier: optional quote/backtick, then word chars, dots, braces (f-strings), $ and -.
_IDENT = r"[`\"']?(?P<target>[\w{}$.`\-]+)[`\"']?"
_OBJ = r"(?:TABLE|VIEW|MATERIALIZED\s+VIEW|STREAMING\s+TABLE)"

WRITE_PATTERNS = [
    ("INSERT", rf"\bINSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?{_IDENT}"),
    ("MERGE", rf"\bMERGE\s+INTO\s+{_IDENT}"),
    ("UPDATE", rf"\bUPDATE\s+{_IDENT}\s+SET\b"),
    ("DELETE", rf"\bDELETE\s+FROM\s+{_IDENT}"),
    ("TRUNCATE", rf"\bTRUNCATE\s+TABLE\s+{_IDENT}"),
    ("ALTER", rf"\bALTER\s+{_OBJ}\s+{_IDENT}"),
    ("RESTORE", rf"\bRESTORE\s+TABLE\s+{_IDENT}"),
    ("CREATE", rf"\bCREATE\s+(?:OR\s+(?:REPLACE|REFRESH)\s+)?{_OBJ}\s+(?:IF\s+NOT\s+EXISTS\s+)?{_IDENT}"),
    ("REPLACE", rf"\bREPLACE\s+TABLE\s+{_IDENT}"),
    ("DROP", rf"\bDROP\s+{_OBJ}\s+(?:IF\s+EXISTS\s+)?{_IDENT}"),
    ("COMMENT", rf"\bCOMMENT\s+ON\s+(?:TABLE|VIEW)\s+{_IDENT}"),
    ("COMMENT_COLUMN", rf"\bCOMMENT\s+ON\s+COLUMN\s+{_IDENT}"),
    ("saveAsTable", rf"\.saveAsTable\(\s*f?{_IDENT}"),
    ("insertInto", rf"\.insertInto\(\s*f?{_IDENT}"),
    ("toTable", rf"\.toTable\(\s*f?{_IDENT}"),
    ("DeltaTable.forName", rf"DeltaTable\.forName\(\s*\w+\s*,\s*f?{_IDENT}"),
    ("pipeline_decorator", rf"@(?:dlt|dp)\.(?:table|materialized_view|streaming_table)\([^)]*?\bname\s*=\s*f?{_IDENT}"),
    ("create_streaming_table", rf"\.create_streaming_table\([^)]*?\bname\s*=\s*f?{_IDENT}"),
]
COMPILED = [(kind, re.compile(p, re.IGNORECASE | re.DOTALL)) for kind, p in WRITE_PATTERNS]


def load_frozen():
    data = json.loads(SNAPSHOT_PATH.read_text())
    return data["manifest_version"], {o.lower() for o in data["frozen_objects"]}


_CONST_RX = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*f?[\"']([^\"'\n]+)[\"']\s*$", re.MULTILINE)
_PLACEHOLDER_RX = re.compile(r"\{([A-Za-z_]\w*)\}")


def collect_constants(code: str) -> dict:
    """Map simple NAME = "..." / f"..." assignments to their string value."""
    return {m.group(1): m.group(2) for m in _CONST_RX.finditer(code)}


def resolve(raw: str, consts: dict) -> str:
    """Substitute a bare constant name or {NAME} placeholders (two passes for nesting)."""
    if raw in consts:
        raw = consts[raw]
    for _ in range(2):
        raw = _PLACEHOLDER_RX.sub(lambda m: consts.get(m.group(1), m.group(0)), raw)
    return raw


def normalize_target(raw: str, kind: str):
    """Return the bare object name, or None if the target is fully dynamic."""
    t = raw.replace("`", "").strip("\"' ").lower()
    parts = [p for p in t.split(".") if p]
    if kind == "COMMENT_COLUMN" and len(parts) >= 2:
        parts = parts[:-1]  # drop the column segment
    if not parts:
        return None
    name = parts[-1]
    if "{" in name or "}" in name or name.startswith("$") or name.startswith(":"):
        return None
    return name


def _blank_comments(text: str, suffix: str) -> str:
    """Blank out full-line comments (keeps line numbers stable)."""
    out = []
    for line in text.splitlines():
        s = line.lstrip()
        if s.startswith("#") and not s.startswith("#!") or s.startswith("--"):
            out.append("")
        elif suffix == ".sql" and "--" in line:
            out.append(line.split("--", 1)[0])
        else:
            out.append(line)
    return "\n".join(out)


def iter_code_chunks(path: pathlib.Path):
    """Yield (label, code_text) for a file; notebooks yield one chunk per code cell."""
    if path.suffix == ".ipynb":
        try:
            nb = json.loads(path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        for i, cell in enumerate(nb.get("cells", []), start=1):
            if cell.get("cell_type") != "code":
                continue
            src = cell.get("source", "")
            src = "".join(src) if isinstance(src, list) else src
            if src.lstrip().startswith("%md"):
                continue
            yield f"cell {i}", _blank_comments(src, ".py")
    else:
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            return
        yield "", _blank_comments(text, path.suffix)


def find_frozen_writes(code: str, frozen: set, consts: dict = None):
    """Return (violations, dynamic) for one code chunk.

    violations: list of (line_no, kind, target) writes to FROZEN objects.
    dynamic: list of (line_no, kind, raw_target) writes whose target is unresolvable.
    """
    violations, dynamic = [], []
    consts = collect_constants(code) if consts is None else consts
    for kind, rx in COMPILED:
        for m in rx.finditer(code):
            raw = resolve(m.group("target"), consts)
            line_no = code.count("\n", 0, m.start()) + 1
            name = normalize_target(raw, kind)
            if name is None:
                dynamic.append((line_no, kind, raw))
                continue
            if name.endswith(SHADOW_SUFFIX):
                continue
            if name in frozen:
                violations.append((line_no, kind, name))
    return violations, dynamic


def iter_v4_files(root: pathlib.Path = PROJECT_ROOT):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(root)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if V4_PATH_MARKER.search(str(rel)) or V4_CONTENT_MARKER.search(text):
            yield path


# ---------------------------------------------------------------------------
# Snapshot sanity
# ---------------------------------------------------------------------------

def test_snapshot_well_formed():
    version, frozen = load_frozen()
    assert version.startswith("PRI-DEMO-FREEZE-v"), version
    assert len(frozen) >= 40, f"Suspiciously small FROZEN set ({len(frozen)})"
    assert not any(o.endswith(SHADOW_SUFFIX) for o in frozen), "Shadow objects must never be FROZEN v3"


# ---------------------------------------------------------------------------
# Detector self-tests (keep the gate from going vacuous)
# ---------------------------------------------------------------------------

POSITIVE_CASES = [
    "INSERT INTO cdm_tmforum.provable_resilience_intelligence.hazard_span_intersection SELECT 1",
    "insert overwrite table span_risk_predictions select * from x",
    "MERGE INTO `cdm_tmforum`.`provable_resilience_intelligence`.`physical_resource_conduit` t USING s ON t.id = s.id",
    "UPDATE physical_resource_span SET length_km = 1",
    "DELETE FROM resource_alarm WHERE 1=1",
    "TRUNCATE TABLE service_path",
    "ALTER TABLE hazard_span_intersection ADD COLUMN x INT",
    "RESTORE TABLE resilience_score_snapshot TO VERSION AS OF 21",
    "CREATE OR REPLACE TABLE physical_resource_span AS SELECT * FROM x",
    "CREATE OR REPLACE VIEW revenue_at_risk AS SELECT 1",
    "CREATE OR REFRESH MATERIALIZED VIEW resilience_score AS SELECT 1",
    "DROP TABLE IF EXISTS shared_risk_group",
    "COMMENT ON TABLE physical_resource_conduit IS 'x'",
    "COMMENT ON COLUMN physical_resource_span.site_a_id IS 'x'",
    'df.write.mode("overwrite").saveAsTable("cdm_tmforum.provable_resilience_intelligence.span_risk_predictions")',
    'df.write.saveAsTable(f"{CATALOG_SCHEMA}.hazard_span_intersection")',
    'df.write.insertInto("resource_performance_measure")',
    'q = df.writeStream.toTable("span_risk_inference_log")',
    'DeltaTable.forName(spark, "physical_resource_conduit").update(set={"a": "1"})',
    '@dlt.table(name="hazard_span_intersection")',
]

NEGATIVE_CASES = [
    "CREATE OR REPLACE TABLE hazard_span_intersection_v4_candidate AS SELECT * FROM hazard_span_intersection VERSION AS OF 22",
    "INSERT INTO physical_resource_conduit_v4_candidate SELECT * FROM physical_resource_conduit",
    "MERGE INTO span_risk_predictions_v4_candidate t USING span_risk_predictions s ON t.id = s.id",
    'df.write.saveAsTable(f"{CATALOG_SCHEMA}.physical_resource_span_v4_candidate")',
    "SELECT * FROM resilience_score_snapshot",
    'spark.table("hazard_span_intersection").count()',
    "CREATE OR REPLACE TEMPORARY VIEW customer AS SELECT 1",
    "UPDATE agent_tasks SET status = 'completed' WHERE task_code = 'X'",
    "# MERGE INTO hazard_span_intersection -- commented out",
    "-- DELETE FROM resource_alarm",
]


@pytest.mark.parametrize("snippet", POSITIVE_CASES)
def test_detector_flags_frozen_writes(snippet):
    _, frozen = load_frozen()
    violations, _ = find_frozen_writes(_blank_comments(snippet, ".sql"), frozen)
    assert violations, f"Guard failed to flag a FROZEN write: {snippet}"


@pytest.mark.parametrize("snippet", NEGATIVE_CASES)
def test_detector_allows_shadow_writes_and_reads(snippet):
    _, frozen = load_frozen()
    violations, _ = find_frozen_writes(_blank_comments(snippet, ".sql"), frozen)
    assert not violations, f"False positive on allowed statement: {snippet} -> {violations}"


def test_constant_targets_are_resolved():
    _, frozen = load_frozen()
    bad = 'SCHEMA = "cdm_tmforum.provable_resilience_intelligence"\nOUT = f"{SCHEMA}.span_risk_predictions"\ndf.write.saveAsTable(OUT)\nspark.sql(f"COMMENT ON TABLE {OUT} IS \'x\'")'
    good = bad.replace("span_risk_predictions", "span_risk_predictions_v4_candidate")
    assert len(find_frozen_writes(bad, frozen)[0]) == 2
    assert find_frozen_writes(good, frozen) == ([], [])


def test_dynamic_target_is_reported():
    _, frozen = load_frozen()
    violations, dynamic = find_frozen_writes('df.write.saveAsTable(f"{tbl}")', frozen)
    assert not violations and dynamic


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_v4_shadow_code_never_writes_frozen_v3():
    version, frozen = load_frozen()
    failures, dynamic_all, scanned = [], [], []
    for path in iter_v4_files():
        rel = path.relative_to(PROJECT_ROOT)
        scanned.append(str(rel))
        chunks = list(iter_code_chunks(path))
        consts = collect_constants("\n".join(code for _, code in chunks))
        for label, code in chunks:
            violations, dynamic = find_frozen_writes(code, frozen, consts)
            loc = f"{rel}{' ' + label if label else ''}"
            failures += [f"{loc} line {ln}: {kind} -> {tgt}" for ln, kind, tgt in violations]
            dynamic_all += [f"{loc} line {ln}: {kind} -> {raw}" for ln, kind, raw in dynamic]
    if dynamic_all:
        warnings.warn(
            "v4 freeze guard: unresolvable dynamic write targets (verify they end in "
            f"{SHADOW_SUFFIX} or use ml_freeze_guard.assert_writable):\n  " + "\n  ".join(dynamic_all)
        )
    assert not failures, (
        f"DEC-PRI-V4-SHADOW-BUILD violation: v4 shadow-build code writes to objects FROZEN in "
        f"{version}. Only *{SHADOW_SUFFIX} targets are allowed until the @pm v4 cutover.\n  "
        + "\n  ".join(failures)
        + f"\nScanned {len(scanned)} v4-scoped file(s)."
    )


# ---------------------------------------------------------------------------
# v4 candidate writer coverage (P37-DEVOPS-V4-PR-READINESS)
# ---------------------------------------------------------------------------
# Every live *_v4_candidate object must have a versioned writer in this repo, so the
# freeze guard above can actually inspect the code that builds it. Objects built only
# from ad-hoc agent sessions are reported. The check is advisory (warning) until the
# writers are checked in; set PRI_V4_COVERAGE_STRICT=1 to make it blocking.

CANDIDATES_PATH = pathlib.Path(__file__).with_name("v4_candidate_objects.json")


def load_v4_candidates():
    data = json.loads(CANDIDATES_PATH.read_text())
    return {o.lower() for o in data["v4_candidate_objects"]}


def load_v4_writers():
    """P39: object -> {expected_writer, owner_role, owner_task, status}."""
    data = json.loads(CANDIDATES_PATH.read_text())
    return {k.lower(): v for k, v in data.get("writers", {}).items()}


def v4_writer_index(root: pathlib.Path = PROJECT_ROOT):
    """Map each resolved write target in v4-scoped files to the files that write it."""
    index = {}
    for path in iter_v4_files(root):
        rel = str(path.relative_to(root))
        chunks = list(iter_code_chunks(path))
        consts = collect_constants("\n".join(code for _, code in chunks))
        for _, code in chunks:
            for kind, rx in COMPILED:
                for m in rx.finditer(code):
                    name = normalize_target(resolve(m.group("target"), consts), kind)
                    if name:
                        index.setdefault(name, set()).add(rel)
    return index


def test_v4_candidate_registry_well_formed():
    _, frozen = load_frozen()
    cands = load_v4_candidates()
    assert cands, "v4 candidate registry is empty"
    assert all(c.endswith(SHADOW_SUFFIX) for c in cands), cands
    assert not (cands & frozen), f"v4 candidates overlap FROZEN v3: {cands & frozen}"


def test_v4_candidate_writers_mapped():
    """P39: every candidate records an expected writer path and an owning Lakebase task."""
    cands, writers = load_v4_candidates(), load_v4_writers()
    assert set(writers) == cands, (
        f"writers map drift: unmapped={sorted(cands - set(writers))}, extra={sorted(set(writers) - cands)}"
    )
    for obj, meta in writers.items():
        for key in ("expected_writer", "owner_role", "owner_task"):
            assert meta.get(key), f"{obj}: missing {key}"
        assert meta["owner_role"].startswith("@"), f"{obj}: owner_role must be an @role"
        assert not pathlib.PurePosixPath(meta["expected_writer"]).is_absolute(), (
            f"{obj}: expected_writer must be repo-relative"
        )


def test_v4_candidates_have_versioned_writer():
    import os

    index = v4_writer_index()
    missing = sorted(c for c in load_v4_candidates() if c not in index)
    if not missing:
        return
    writers = load_v4_writers()

    def _describe(obj):
        m = writers.get(obj, {})
        return f"{obj} -> expected {m.get('expected_writer', '?')} (owner {m.get('owner_role', '?')}, {m.get('owner_task', '?')})"

    msg = (
        f"{len(missing)} v4 candidate object(s) with no versioned writer in the repo (built from "
        "ad-hoc agent sessions; the freeze guard cannot inspect them):\n  "
        + "\n  ".join(_describe(o) for o in missing)
    )
    if os.environ.get("PRI_V4_COVERAGE_STRICT") == "1":
        pytest.fail(msg)
    warnings.warn(msg)


def test_v4_candidate_registry_matches_live():
    pyspark_sql = pytest.importorskip("pyspark.sql")
    spark = pyspark_sql.SparkSession.getActiveSession()
    if spark is None:
        pytest.skip("No active Spark session (CI runner); live v4 registry check skipped")
    catalog, schema = CATALOG_SCHEMA.split(".")
    rows = spark.sql(
        f"SELECT lower(table_name) AS o FROM {catalog}.information_schema.tables "
        "WHERE table_schema = :s AND lower(table_name) LIKE '%\\_v4\\_candidate'",
        args={"s": schema},
    ).collect()
    live = {r.o for r in rows}
    cands = load_v4_candidates()
    assert live == cands, f"v4 registry drift: unregistered={live - cands}, dropped={cands - live}"


# ---------------------------------------------------------------------------
# Drift check vs live manifest (runs only where a Spark session exists)
# ---------------------------------------------------------------------------

def test_snapshot_matches_live_manifest():
    pyspark_sql = pytest.importorskip("pyspark.sql")
    spark = pyspark_sql.SparkSession.getActiveSession()
    if spark is None:
        pytest.skip("No active Spark session (CI runner); live manifest check skipped")
    version, frozen = load_frozen()
    rows = spark.sql(
        f"SELECT lower(object_name) AS o FROM {CATALOG_SCHEMA}.demo_freeze_manifest "
        "WHERE manifest_version = :v AND freeze_status = 'FROZEN'",
        args={"v": version},
    ).collect()
    live = {r.o for r in rows}
    assert live == frozen, f"Snapshot drift vs {version}: missing={live - frozen}, extra={frozen - live}"
