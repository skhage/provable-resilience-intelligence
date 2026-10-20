"""Branding compliance tests for Lakelink Fiber mandate.

CEO Directive: All produced assets must use 'Lakelink Fiber'.
'Lumen' or 'Lumen Technologies' must not appear in any produced asset.
The only exceptions are meta-documents that explain the branding rule itself.

Project: Lakelink Fiber — Provable Resilience Intelligence
"""

import os
import re
import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)

# Extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".sql", ".md", ".yml", ".yaml", ".json",
    ".tsx", ".ts", ".jsx", ".css", ".toml", ".html",
}

# Meta-files where 'Lumen' may appear (explaining the rule, not using the brand)
META_EXCEPTIONS = {
    ".assistant_instructions.md",
    "BRAND-GUIDE.md",
    "UX-DESIGN-SPEC.md",
    "CONTRIBUTING.md",
}

# CSS variable branding pattern: no 'lumen' in CSS custom property names (BUG-QA-013 resolved)
CSS_VAR_VIOLATION_PATTERN = re.compile(r"--lf-lumen-")


def _collect_project_files():
    """Walk project tree and yield (relative_path, full_path) for scannable files."""
    for root, _dirs, files in os.walk(PROJECT_ROOT):
        # Skip hidden dirs and tests themselves
        if any(part.startswith(".") for part in root.split(os.sep)):
            continue
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SCAN_EXTENSIONS:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, PROJECT_ROOT)
                yield rel, full


class TestBrandingCompliance:
    """No produced asset may contain 'Lumen Technologies' or use 'Lumen' as a brand name."""

    def test_no_lumen_technologies(self):
        """'Lumen Technologies' (case-insensitive) must never appear in produced assets."""
        violations = []
        for rel, full in _collect_project_files():
            if os.path.basename(rel) in META_EXCEPTIONS:
                continue
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if re.search(r"lumen\s+technologies", line, re.IGNORECASE):
                            violations.append(f"{rel}:{i}: {line.strip()[:80]}")
            except OSError:
                pass
        assert not violations, (
            f"Branding violation — 'Lumen Technologies' found in:\n"
            + "\n".join(violations)
        )

    def test_css_variable_names_no_lumen(self):
        """CSS custom properties must not contain 'lumen' (use 'lf-accent' instead).

        BUG-QA-013 resolved: --lf-lumen-orange renamed to --lf-accent-orange.
        This test now enforces the fix as a regression guard.
        """
        violations = []
        for rel, full in _collect_project_files():
            if not rel.endswith(".css"):
                continue
            try:
                with open(full, encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if CSS_VAR_VIOLATION_PATTERN.search(line):
                            violations.append(f"{rel}:{i}: {line.strip()[:80]}")
            except OSError:
                pass
        assert not violations, (
            f"Branding violation — CSS variables containing 'lumen' found in:\n"
            + "\n".join(violations)
        )

    def test_column_comments_no_lumen(self):
        """Table/column COMMENT strings must use 'Lakelink Fiber', not 'Lumen'."""
        try:
            from pyspark.sql import SparkSession
            spark = SparkSession.builder.getOrCreate()
        except Exception:
            pytest.skip("Spark not available")

        rows = spark.sql("""
            SELECT table_name, column_name, comment
            FROM cdm_tmforum.information_schema.columns
            WHERE table_schema = 'provable_resilience_intelligence'
              AND comment ILIKE '%lumen%'
        """).collect()
        violations = [(r["table_name"], r["column_name"], r["comment"]) for r in rows]
        assert not violations, (
            f"Branding violation in column comments: {violations}"
        )

    def test_table_comments_no_lumen(self):
        """Table-level COMMENTs must use 'Lakelink Fiber'."""
        try:
            from pyspark.sql import SparkSession
            spark = SparkSession.builder.getOrCreate()
        except Exception:
            pytest.skip("Spark not available")

        rows = spark.sql("""
            SELECT table_name, comment
            FROM cdm_tmforum.information_schema.tables
            WHERE table_schema = 'provable_resilience_intelligence'
              AND comment ILIKE '%lumen%'
        """).collect()
        violations = [(r["table_name"], r["comment"]) for r in rows]
        assert not violations, (
            f"Branding violation in table comments: {violations}"
        )
