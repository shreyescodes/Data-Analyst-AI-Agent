"""Chart selection and rendering with Plotly.

:func:`suggest_chart` picks a chart type and columns from a free-text request
using keywords, column names mentioned in the request, and column types.
:func:`render_chart` turns that specification into a Plotly figure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from data_analyst_agent.exceptions import ChartError
from data_analyst_agent.schema import Schema, normalise_text

TEMPLATE = "plotly_white"
_MAX_CATEGORIES = 20
_MAX_PIE_SLICES = 10


class ChartType(StrEnum):
    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    BOX = "box"
    PIE = "pie"


@dataclass(frozen=True, slots=True)
class ChartSpec:
    chart_type: ChartType
    x: str
    y: str | None = None
    color: str | None = None
    title: str = ""
    rationale: str = ""


_KEYWORDS: tuple[tuple[ChartType, tuple[str, ...]], ...] = (
    (ChartType.LINE, ("trend", "over time", "time series", "timeline", "evolution")),
    (ChartType.HISTOGRAM, ("distribution", "histogram", "spread", "frequency")),
    (ChartType.BOX, ("box", "boxplot", "outlier", "outliers", "quartile")),
    (ChartType.SCATTER, ("correlation", "relationship", "scatter", "versus", "vs")),
    (ChartType.PIE, ("proportion", "share", "percentage", "composition", "pie")),
    (ChartType.BAR, ("compare", "comparison", "by", "per", "bar", "rank", "top")),
)


def suggest_chart(request: str, df: pd.DataFrame) -> ChartSpec:
    """Choose a chart for ``request``, preferring columns it mentions by name."""
    schema = Schema.from_frame(df)
    text = normalise_text(request)
    mentioned = schema.mentioned_in(text, schema.names())
    numeric = _prefer(mentioned, schema.numeric)
    categorical = _prefer(mentioned, schema.text)
    dates = _prefer(mentioned, schema.datetime)

    requested = next(
        (
            chart
            for chart, words in _KEYWORDS
            if re.search(rf"\b({'|'.join(map(re.escape, words))})\b", text)
        ),
        None,
    )

    for chart in _candidates(requested):
        spec = _build(chart, numeric, categorical, dates)
        if spec is not None:
            return spec

    raise ChartError(
        "Could not find suitable columns for a chart. "
        "Make sure the dataset has at least one numeric or text column."
    )


def render_chart(df: pd.DataFrame, spec: ChartSpec) -> go.Figure:
    for column in (spec.x, spec.y, spec.color):
        if column is not None and column not in df.columns:
            raise ChartError(f"Column '{column}' is not in the dataset.")

    title = spec.title or None
    match spec.chart_type:
        case ChartType.HISTOGRAM:
            fig = px.histogram(df, x=spec.x, nbins=30, title=title, template=TEMPLATE)
        case ChartType.BOX:
            fig = px.box(
                df, x=spec.x if spec.y else None, y=spec.y or spec.x, title=title, template=TEMPLATE
            )
        case ChartType.SCATTER:
            fig = px.scatter(
                df,
                x=spec.x,
                y=spec.y,
                color=spec.color,
                opacity=0.7,
                title=title,
                template=TEMPLATE,
            )
        case ChartType.LINE:
            data = _mean_by(df, spec.x, spec.y).sort_values(spec.x)
            fig = px.line(data, x=spec.x, y=spec.y, markers=True, title=title, template=TEMPLATE)
        case ChartType.BAR:
            data = _mean_by(df, spec.x, spec.y) if spec.y else _counts(df, spec.x)
            y = spec.y or "count"
            data = data.nlargest(_MAX_CATEGORIES, y)
            fig = px.bar(data, x=spec.x, y=y, title=title, template=TEMPLATE)
        case ChartType.PIE:
            if spec.y:
                data = df.groupby(spec.x, observed=True)[spec.y].sum().reset_index()
            else:
                data = _counts(df, spec.x)
            values = spec.y or "count"
            data = data.nlargest(_MAX_PIE_SLICES, values)
            fig = px.pie(data, names=spec.x, values=values, title=title, template=TEMPLATE)
    return fig


def correlation_heatmap(df: pd.DataFrame) -> go.Figure:
    numeric = df[Schema.from_frame(df).numeric]
    if numeric.shape[1] < 2:
        raise ChartError("A correlation heatmap needs at least two numeric columns.")
    corr = numeric.corr().round(2)
    return px.imshow(
        corr,
        text_auto=True,
        zmin=-1,
        zmax=1,
        color_continuous_scale="RdBu_r",
        aspect="auto",
        title="Correlation matrix",
        template=TEMPLATE,
    )


def distribution_plot(df: pd.DataFrame, column: str) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, row_heights=[0.75, 0.25], shared_xaxes=True, vertical_spacing=0.05
    )
    fig.add_trace(go.Histogram(x=df[column], nbinsx=30, name=column), row=1, col=1)
    fig.add_trace(go.Box(x=df[column], name=column, orientation="h"), row=2, col=1)
    fig.update_layout(title=f"Distribution of {column}", template=TEMPLATE, showlegend=False)
    return fig


# --- Helpers -----------------------------------------------------------------


def _candidates(requested: ChartType | None) -> list[ChartType]:
    """Requested type first, then sensible defaults in order of usefulness."""
    defaults = [ChartType.BAR, ChartType.SCATTER, ChartType.HISTOGRAM, ChartType.PIE]
    if requested is None:
        return [ChartType.LINE, *defaults]
    return [requested, *(c for c in defaults if c is not requested)]


def _build(
    chart: ChartType, numeric: list[str], categorical: list[str], dates: list[str]
) -> ChartSpec | None:
    match chart:
        case ChartType.LINE if numeric and dates:
            x, y = dates[0], numeric[0]
            return ChartSpec(
                chart,
                x,
                y,
                title=f"{y} over {x}",
                rationale=f"Line chart of average {y} over time ({x}).",
            )
        case ChartType.LINE if numeric and categorical:
            # No date column: a trend over an ordered category is the best we can do.
            x, y = categorical[0], numeric[0]
            return ChartSpec(
                chart,
                x,
                y,
                title=f"{y} by {x}",
                rationale=f"No date column found; average {y} across {x}.",
            )
        case ChartType.BAR if categorical:
            x = categorical[0]
            if numeric:
                y = numeric[0]
                return ChartSpec(
                    chart,
                    x,
                    y,
                    title=f"Average {y} by {x}",
                    rationale=f"Bar chart comparing average {y} across {x}.",
                )
            return ChartSpec(
                chart,
                x,
                title=f"Rows per {x}",
                rationale=f"Bar chart of how often each {x} appears.",
            )
        case ChartType.SCATTER if len(numeric) >= 2:
            # "A vs B" reads as A plotted against B, so A goes on the y-axis.
            y, x = numeric[0], numeric[1]
            color = categorical[0] if categorical else None
            return ChartSpec(
                chart,
                x,
                y,
                color=color,
                title=f"{y} vs {x}",
                rationale=f"Scatter plot showing how {y} relates to {x}.",
            )
        case ChartType.HISTOGRAM if numeric:
            x = numeric[0]
            return ChartSpec(
                chart,
                x,
                title=f"Distribution of {x}",
                rationale=f"Histogram of how {x} values are distributed.",
            )
        case ChartType.BOX if numeric:
            y = numeric[0]
            x = categorical[0] if categorical else y
            return ChartSpec(
                chart,
                x,
                y if categorical else None,
                title=f"Spread of {y}",
                rationale=f"Box plot showing median, quartiles and outliers of {y}.",
            )
        case ChartType.PIE if categorical:
            x = categorical[0]
            measure = numeric[0] if numeric else None
            label = f"total {measure}" if measure else "rows"
            return ChartSpec(
                chart,
                x,
                measure,
                title=f"Share of {label} by {x}",
                rationale=f"Pie chart of each {x}'s share of {label}.",
            )
    return None


def _prefer(mentioned: list[str], columns: list[str]) -> list[str]:
    """Columns mentioned in the request first, then the rest in original order."""
    first = [c for c in mentioned if c in columns]
    return first + [c for c in columns if c not in first]


def _mean_by(df: pd.DataFrame, x: str, y: str | None) -> pd.DataFrame:
    if y is None:
        return _counts(df, x)
    return df.groupby(x, observed=True, dropna=True)[y].mean().reset_index()


def _counts(df: pd.DataFrame, x: str) -> pd.DataFrame:
    counts = df[x].value_counts(dropna=True)
    return pd.DataFrame({x: counts.index, "count": counts.to_numpy()})
