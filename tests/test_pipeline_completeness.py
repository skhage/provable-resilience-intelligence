"""BUG-QA-070: Verify the bundled pipeline notebook contains full scoring logic.

The DAB pipeline resource (bundle/resources/resilience_pipeline.pipeline.yml)
references a notebook in bundle/pipeline/. That notebook must define the same
materialized views as the canonical pipeline in pipelines/, including the
gold-layer scoring tables. A bronze-only stub would pass bundle validate but
deploy a pipeline with no silver/gold output.

This test catches content drift between the bundled stub and the canonical
pipeline without requiring a Spark session or pipeline dry-run.
"""
import json
import pathlib
import re

import pytest

# Project root = two levels up from tests/
PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent

# The canonical pipeline notebook (the 'real' source of truth)
CANONICAL_PIPELINE = PROJECT_ROOT / "pipelines" / "resilience_scoring_pipeline.ipynb"

# The DAB-bundled pipeline notebook (what gets deployed)
BUNDLED_PIPELINE = PROJECT_ROOT / "bundle" / "pipeline" / "resilience_scoring_pipeline.ipynb"

# Gold-layer materialized views that MUST exist in the deployed pipeline
REQUIRED_GOLD_VIEWS = [
    "gold_resilience_score",
    "gold_revenue_at_risk",
    "gold_proactive_action",
]

# Silver-layer materialized views that MUST exist in the deployed pipeline
REQUIRED_SILVER_VIEWS = [
    "silver_hazard_span_intersection",
    "silver_srlg_diversity_analysis",
]


def _read_notebook_source(nb_path: pathlib.Path) -> str:
    """Extract all cell source code from a Jupyter .ipynb notebook."""
    if not nb_path.exists():
        pytest.skip(f"Notebook not found: {nb_path}")
    with open(nb_path) as f:
        nb = json.load(f)
    sources = []
    for cell in nb.get("cells", []):
        src = "".join(cell.get("source", []))
        sources.append(src)
    return "\n".join(sources)


def _read_notebook_workspace_format(nb_dir: pathlib.Path) -> str:
    """Read a Databricks workspace-format notebook directory/file.

    Workspace notebooks may be stored as .py files or as directories.
    Try both .ipynb (Jupyter) and raw .py content.
    """
    # Try .ipynb first
    ipynb = nb_dir.with_suffix(".ipynb")
    if ipynb.exists():
        return _read_notebook_source(ipynb)

    # Try bare .py
    py_file = nb_dir.with_suffix(".py")
    if py_file.exists():
        return py_file.read_text()

    # Try directory with cell files (Databricks source format)
    if nb_dir.is_dir():
        content_parts = []
        for f in sorted(nb_dir.iterdir()):
            if f.suffix in (".py", ".sql"):
                content_parts.append(f.read_text())
        if content_parts:
            return "\n".join(content_parts)

    # Nothing found
    pytest.skip(f"No readable notebook at {nb_dir} (.ipynb, .py, or dir)")
    return ""


class TestPipelineCompleteness:
    """BUG-QA-070: the bundled pipeline must contain full scoring logic."""

    def _get_bundled_content(self) -> str:
        return _read_notebook_workspace_format(BUNDLED_PIPELINE.with_suffix(""))

    @pytest.mark.parametrize("view_name", REQUIRED_GOLD_VIEWS)
    def test_bundled_pipeline_has_gold_view(self, view_name):
        """The bundled pipeline notebook must define each gold MV."""
        content = self._get_bundled_content()
        pattern = re.compile(rf"\b{re.escape(view_name)}\b", re.IGNORECASE)
        assert pattern.search(content), (
            f"BUG-QA-070: bundled pipeline is missing gold view '{view_name}'. "
            f"Sync the canonical pipeline into bundle/pipeline/ before deploying."
        )

    @pytest.mark.parametrize("view_name", REQUIRED_SILVER_VIEWS)
    def test_bundled_pipeline_has_silver_view(self, view_name):
        """The bundled pipeline notebook must define each silver MV."""
        content = self._get_bundled_content()
        pattern = re.compile(rf"\b{re.escape(view_name)}\b", re.IGNORECASE)
        assert pattern.search(content), (
            f"BUG-QA-070: bundled pipeline is missing silver view '{view_name}'. "
            f"Sync the canonical pipeline into bundle/pipeline/ before deploying."
        )

    def test_canonical_pipeline_exists(self):
        """The canonical pipeline notebook must exist at pipelines/."""
        exists = (
            CANONICAL_PIPELINE.exists()
            or CANONICAL_PIPELINE.with_suffix("").exists()
            or CANONICAL_PIPELINE.with_suffix(".py").exists()
        )
        assert exists, (
            f"Canonical pipeline not found at {CANONICAL_PIPELINE}. "
            f"Expected the real scoring pipeline in pipelines/."
        )

    def test_no_stub_header_in_bundled(self):
        """The bundled pipeline must not contain the placeholder stub header."""
        content = self._get_bundled_content()
        assert "replace this stub" not in content.lower(), (
            "BUG-QA-070: bundled pipeline still contains the placeholder stub header. "
            "Sync the canonical pipeline content before deploying."
        )
