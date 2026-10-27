"""HTML profiling reports via fg-data-profiling (formerly ydata-profiling)."""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

# Above this many cells the full report (correlations, interactions) gets slow,
# so callers should default to the minimal report.
LARGE_DATASET_CELLS = 2_000_000


def is_large(df: pd.DataFrame) -> bool:
    return df.size > LARGE_DATASET_CELLS


def build_profile_html(
    df: pd.DataFrame, *, title: str = "Dataset profile", minimal: bool = False
) -> str:
    """Return a self-contained HTML profiling report for ``df``."""
    # Imported lazily: the profiling library takes several seconds to import and is
    # only needed when a report is actually requested.
    from data_profiling import ProfileReport

    logger.info(
        "Building %s profile for %d x %d frame", "minimal" if minimal else "full", *df.shape
    )
    report = ProfileReport(df, title=title, minimal=minimal, progress_bar=False)
    html: str = report.to_html()
    return html
