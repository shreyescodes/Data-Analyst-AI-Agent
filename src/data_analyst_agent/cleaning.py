"""Rule-based data-quality assessment and cleaning pipeline.

Steps run in a fixed order chosen so each one sees the output it needs:
text is normalised before type inference (``" 42 "`` becomes numeric) and
before de-duplication (``"a "`` and ``"a"`` are treated as equal).

No step converts a value it cannot parse: a column is only re-typed when
every non-missing value converts cleanly.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

import pandas as pd

from data_analyst_agent.schema import ColumnKind, Schema, is_text_dtype

logger = logging.getLogger(__name__)

_DATE_PATTERN = re.compile(
    r"^\s*(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})([ T]\d{1,2}:\d{2}.*)?$"
)
_DATE_SAMPLE_SIZE = 200
_DATE_MATCH_THRESHOLD = 0.9


class MissingValueStrategy(StrEnum):
    DROP_ROWS = "drop_rows"
    MEAN = "mean"
    MEDIAN = "median"
    MODE = "mode"
    FORWARD_FILL = "forward_fill"
    BACKWARD_FILL = "backward_fill"


@dataclass(frozen=True, slots=True)
class CleaningOptions:
    normalise_text: bool = True
    parse_dates: bool = True
    convert_numeric_text: bool = True
    remove_duplicates: bool = True
    handle_missing: bool = True
    missing_strategy: MissingValueStrategy = MissingValueStrategy.DROP_ROWS
    remove_outliers: bool = False
    outlier_iqr_multiplier: float = 1.5


@dataclass(frozen=True, slots=True)
class CleaningStep:
    name: str
    detail: str
    rows_before: int
    rows_after: int

    @property
    def rows_removed(self) -> int:
        return self.rows_before - self.rows_after


@dataclass(slots=True)
class CleaningReport:
    steps: list[CleaningStep] = field(default_factory=list)

    @property
    def rows_removed(self) -> int:
        return sum(step.rows_removed for step in self.steps)


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    n_rows: int
    n_columns: int
    missing_cells: int
    duplicate_rows: int
    numeric_text_columns: tuple[str, ...]
    columns_with_missing: tuple[str, ...]

    @property
    def missing_ratio(self) -> float:
        total = self.n_rows * self.n_columns
        return self.missing_cells / total if total else 0.0


def assess_quality(df: pd.DataFrame) -> QualityAssessment:
    """Summarise data-quality issues.

    Whitespace-only strings count as missing, since that is how the cleaning
    pipeline treats them.
    """
    missing = df.isna() | df.apply(_is_blank_string)
    return QualityAssessment(
        n_rows=len(df),
        n_columns=df.shape[1],
        missing_cells=int(missing.to_numpy().sum()),
        duplicate_rows=int(df.duplicated().sum()),
        numeric_text_columns=tuple(
            str(col) for col in df.columns if _is_numeric_text(df[col].mask(missing[col]))
        ),
        columns_with_missing=tuple(str(col) for col in df.columns[missing.any()]),
    )


StepFn = Callable[[pd.DataFrame, CleaningOptions], tuple[pd.DataFrame, str]]


def clean(
    df: pd.DataFrame, options: CleaningOptions | None = None
) -> tuple[pd.DataFrame, CleaningReport]:
    """Run the enabled cleaning steps and return the result with a report.

    The input frame is never mutated.
    """
    options = options or CleaningOptions()
    pipeline: list[tuple[bool, str, StepFn]] = [
        (options.normalise_text, "Normalise text", _normalise_text),
        (options.parse_dates, "Parse dates", _parse_dates),
        (options.convert_numeric_text, "Convert numeric text", _convert_numeric),
        (options.remove_duplicates, "Remove duplicates", _remove_duplicates),
        (options.handle_missing, "Handle missing values", _handle_missing),
        (options.remove_outliers, "Remove outliers", _remove_outliers),
    ]

    result = df.copy()
    report = CleaningReport()
    for enabled, name, step in pipeline:
        if not enabled:
            continue
        rows_before = len(result)
        result, detail = step(result, options)
        report.steps.append(CleaningStep(name, detail, rows_before, len(result)))
        logger.debug("%s: %s", name, detail)

    return result.reset_index(drop=True), report


# --- Steps -------------------------------------------------------------------


def _normalise_text(df: pd.DataFrame, _: CleaningOptions) -> tuple[pd.DataFrame, str]:
    """Trim and collapse whitespace; turn blank strings into missing values."""
    changed_cells = 0
    blanks = 0
    for col in df.columns:
        series = df[col]
        if not is_text_dtype(series):
            continue
        is_str = series.map(lambda v: isinstance(v, str)).astype(bool)
        if not is_str.any():
            continue
        original = series[is_str]
        normalised = original.str.strip().str.replace(r"\s+", " ", regex=True)
        changed_cells += int((normalised != original).sum())
        blank = normalised == ""
        blanks += int(blank.sum())
        updated = series.copy()
        updated[is_str] = normalised.mask(blank)
        df[col] = updated
    return df, f"Normalised {changed_cells} cells; {blanks} blank values set to missing"


def _parse_dates(df: pd.DataFrame, _: CleaningOptions) -> tuple[pd.DataFrame, str]:
    converted: list[str] = []
    for col in df.columns:
        series = df[col]
        if not is_text_dtype(series):
            continue
        values = series.dropna()
        if values.empty or not values.map(lambda v: isinstance(v, str)).all():
            continue
        sample = values.head(_DATE_SAMPLE_SIZE)
        if sample.str.match(_DATE_PATTERN).mean() < _DATE_MATCH_THRESHOLD:
            continue
        parsed = _to_datetime(series, expected=len(values))
        if parsed is not None:
            df[col] = parsed
            converted.append(str(col))
    return df, _describe_columns("Parsed dates in", converted)


def _convert_numeric(df: pd.DataFrame, _: CleaningOptions) -> tuple[pd.DataFrame, str]:
    converted: list[str] = []
    for col in df.columns:
        if _is_numeric_text(df[col]):
            df[col] = pd.to_numeric(df[col])
            converted.append(str(col))
    return df, _describe_columns("Converted numeric text in", converted)


def _remove_duplicates(df: pd.DataFrame, _: CleaningOptions) -> tuple[pd.DataFrame, str]:
    deduplicated = df.drop_duplicates()
    return deduplicated, f"Removed {len(df) - len(deduplicated)} duplicate rows"


def _handle_missing(df: pd.DataFrame, options: CleaningOptions) -> tuple[pd.DataFrame, str]:
    strategy = options.missing_strategy
    missing_before = int(df.isna().to_numpy().sum())

    if strategy is MissingValueStrategy.DROP_ROWS:
        result = df.dropna()
        return result, f"Dropped {len(df) - len(result)} rows with missing values"

    if strategy in (MissingValueStrategy.MEAN, MissingValueStrategy.MEDIAN):
        numeric = Schema.from_frame(df).names(ColumnKind.NUMERIC)
        fill = df[numeric].mean() if strategy is MissingValueStrategy.MEAN else df[numeric].median()
        result = df.copy()
        result[numeric] = df[numeric].fillna(fill)
    elif strategy is MissingValueStrategy.MODE:
        modes = {col: df[col].mode(dropna=True) for col in df.columns}
        result = df.fillna({col: m.iloc[0] for col, m in modes.items() if not m.empty})
    elif strategy is MissingValueStrategy.FORWARD_FILL:
        result = df.ffill()
    else:
        result = df.bfill()

    filled = missing_before - int(result.isna().to_numpy().sum())
    return result, f"Filled {filled} missing values using {strategy.value}"


def _remove_outliers(df: pd.DataFrame, options: CleaningOptions) -> tuple[pd.DataFrame, str]:
    """Drop rows outside Tukey fences on any numeric column.

    Fences are computed on the step's input so the result does not depend on
    column order. Missing values are never treated as outliers, and columns
    with zero spread (e.g. mostly-constant flags) are skipped.
    """
    k = options.outlier_iqr_multiplier
    is_outlier = pd.Series(False, index=df.index)
    checked = 0
    for col in Schema.from_frame(df).numeric:
        q1, q3 = df[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        if pd.isna(iqr) or iqr == 0:
            continue
        checked += 1
        outside = (df[col] < q1 - k * iqr) | (df[col] > q3 + k * iqr)
        is_outlier |= outside.fillna(False)
    result = df[~is_outlier]
    return result, f"Removed {int(is_outlier.sum())} rows across {checked} columns"


# --- Helpers -----------------------------------------------------------------


def _is_blank_string(series: pd.Series) -> pd.Series:
    if not is_text_dtype(series):
        return pd.Series(False, index=series.index)
    return series.map(lambda v: isinstance(v, str) and not v.strip()).astype(bool)


def _is_numeric_text(series: pd.Series) -> bool:
    """True when a text column holds only values that parse as numbers."""
    if not is_text_dtype(series):
        return False
    values = series.dropna()
    if values.empty:
        return False
    return bool(pd.to_numeric(values, errors="coerce").notna().all())


def _to_datetime(series: pd.Series, expected: int) -> pd.Series | None:
    """Parse with the strictest format that converts all ``expected`` values.

    Returns ``None`` if no format parses every value, so a column is never
    partially converted (which would silently replace values with NaT).
    """
    for fmt in ("ISO8601", "mixed"):
        try:
            parsed = pd.to_datetime(series, errors="coerce", format=fmt)
        except (ValueError, TypeError):
            continue
        if parsed.notna().sum() == expected:
            return parsed
    return None


def _describe_columns(prefix: str, columns: list[str]) -> str:
    if not columns:
        return f"{prefix} 0 columns"
    return f"{prefix} {', '.join(columns)}"


__all__ = [
    "CleaningOptions",
    "CleaningReport",
    "CleaningStep",
    "MissingValueStrategy",
    "QualityAssessment",
    "assess_quality",
    "clean",
]
