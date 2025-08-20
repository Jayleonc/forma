"""Deprecated orchestration module.

The heavy business logic has moved to `forma.workflows` sub-package.
This thin wrapper keeps backward compatibility for external imports.
"""

from __future__ import annotations

from pathlib import Path

from .workflows.conversion import run_conversion
from .workflows.qa_pipeline import generate_qa_pipeline as _generate_qa_pipeline

__all__ = ["run_conversion", "Controller"]


class Controller:
    """Backward-compat thin wrapper for QA pipeline."""

    def generate_qa_pipeline(self, input_path: Path, output_dir: Path) -> None:  # noqa: D102
        """Runs the full QA generation pipeline."""
        _generate_qa_pipeline(input_path, output_dir)
