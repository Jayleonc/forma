"""Deprecated orchestration module.

The heavy business logic has moved to `forma.workflows` sub-package.
This thin wrapper keeps backward compatibility for external imports.
"""

from __future__ import annotations

from pathlib import Path

from .workflows.conversion import run_conversion
from .workflows.knowledge_pipeline import run_knowledge_pipeline as _run_knowledge_pipeline

__all__ = ["run_conversion", "Controller"]


class Controller:
    """Backward-compat thin wrapper for knowledge pipeline."""

    def run_knowledge_pipeline(self, input_path: Path, output_dir: Path) -> None:  # noqa: D102
        """Runs the full knowledge building pipeline."""
        _run_knowledge_pipeline(input_path, output_dir)

    # Backwards compatibility with previous API
    generate_qa_pipeline = run_knowledge_pipeline
