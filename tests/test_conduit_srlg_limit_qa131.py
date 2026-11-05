"""BUG-QA-131: _CONDUIT_SRLGS_SQL LIMIT is derived from CONDUIT_SRLG_LIST_CAP (single source of truth).

Before: the SQL text had a literal 'LIMIT 500' while _execute got row_limit=CONDUIT_SRLG_LIST_CAP.
Changing one without the other would make the cap and the UI 'Showing N of M' logic diverge.
Now the LIMIT is rendered from the int constant via _sql_limit(). The rendered SQL is byte-identical
to the previous text (sha pinned), so live behaviour is unchanged. The v3 _SRLG_BY_REGION_SQL stays
frozen (sha c24ace6c).
Project: Lakelink Fiber - Provable Resilience Intelligence.
"""

import ast
import hashlib
import os
import re
import sys
import types

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..")
APP_SRC = os.path.join(ROOT, "apps", "resilience-scorecard", "src")
if APP_SRC not in sys.path:
    sys.path.insert(0, APP_SRC)

from resilience_scorecard.backend.services import catalog_sql as cs  # noqa: E402

CS_PATH = os.path.join(
    APP_SRC, "resilience_scorecard", "backend", "services", "catalog_sql.py"
)

# sha256 of the SQL text at 5ed3011 (literal LIMIT 500). Rendering must not change a byte.
CONDUIT_SRLGS_SHA = "b89c86c2cced503e031b65863049b4c3c7f98ebe8bf9c4a80cef213dfb444206"
CONDUIT_SRLGS_V4_SHA = "402fed4d8cd5b4cb57f5409e91aa3baa6cb0e8e643d8ca8ef7540cbaf13b01a2"
SRLG_BY_REGION_V3_SHA = "c24ace6cb54b7d28d818043fbc414130d323bd1d34077c2e5ca91f6f7be92b5f"


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _assignment_node(tree: ast.Module, name: str) -> ast.AST:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise AssertionError(f"{name} assignment not found")


def _load_with_cap(cap_src: str) -> types.ModuleType:
    """Exec catalog_sql source with a different cap literal, in an isolated module."""
    src = open(CS_PATH, encoding="utf-8").read()
    assert src.count("CONDUIT_SRLG_LIST_CAP = 500\n") == 1
    src = src.replace("CONDUIT_SRLG_LIST_CAP = 500\n", f"CONDUIT_SRLG_LIST_CAP = {cap_src}\n")
    mod = types.ModuleType("resilience_scorecard.backend.services._qa131_probe")
    mod.__package__ = "resilience_scorecard.backend.services"
    mod.__file__ = CS_PATH
    exec(compile(src, CS_PATH, "exec"), mod.__dict__)
    return mod


def test_sql_limit_equals_cap():
    for sql in (cs._CONDUIT_SRLGS_SQL, cs._CONDUIT_SRLGS_V4_SQL):
        assert re.findall(r"LIMIT\s+(\d+)", sql) == [str(cs.CONDUIT_SRLG_LIST_CAP)]
        assert sql.rstrip().endswith(f"LIMIT {cs.CONDUIT_SRLG_LIST_CAP}")


def test_rendered_sql_is_byte_identical_to_previous_text():
    assert _sha(cs._CONDUIT_SRLGS_SQL) == CONDUIT_SRLGS_SHA
    assert _sha(cs._CONDUIT_SRLGS_V4_SQL) == CONDUIT_SRLGS_V4_SHA


def test_v3_srlg_by_region_sql_still_frozen():
    assert _sha(cs._SRLG_BY_REGION_SQL) == SRLG_BY_REGION_V3_SHA


def test_no_literal_limit_in_conduit_srlgs_assignment():
    tree = ast.parse(open(CS_PATH, encoding="utf-8").read())
    value = _assignment_node(tree, "_CONDUIT_SRLGS_SQL")
    literals = [n.value for n in ast.walk(value) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any(re.search(r"LIMIT\s+\d", s) for s in literals), "literal LIMIT N in SQL text"
    names = {n.id for n in ast.walk(value) if isinstance(n, ast.Name)}
    assert "CONDUIT_SRLG_LIST_CAP" in names


def test_cap_change_propagates_to_sql_and_v4():
    mod = _load_with_cap("37")
    assert mod.CONDUIT_SRLG_LIST_CAP == 37
    for sql in (mod._CONDUIT_SRLGS_SQL, mod._CONDUIT_SRLGS_V4_SQL):
        assert re.findall(r"LIMIT\s+(\d+)", sql) == ["37"]
    # Everything except the LIMIT number is unchanged.
    assert mod._CONDUIT_SRLGS_SQL.replace("LIMIT 37", "LIMIT 500") == cs._CONDUIT_SRLGS_SQL


@pytest.mark.parametrize("bad", [0, -1, True, False, 2.5, "500", "500; DROP TABLE x", None])
def test_sql_limit_rejects_non_positive_int(bad):
    with pytest.raises(ValueError):
        cs._sql_limit(bad)


def test_sql_limit_renders_positive_int():
    assert cs._sql_limit(1) == "LIMIT 1"
    assert cs._sql_limit(500) == "LIMIT 500"


def test_bad_cap_fails_at_import():
    with pytest.raises(ValueError):
        _load_with_cap("'500 OR 1=1'")


def test_execute_row_limit_uses_same_constant():
    src = open(CS_PATH, encoding="utf-8").read()
    assert re.search(r"sql, row_limit=CONDUIT_SRLG_LIST_CAP, params=", src)
