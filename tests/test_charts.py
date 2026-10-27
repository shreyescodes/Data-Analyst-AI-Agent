import pandas as pd
import plotly.graph_objects as go
import pytest

from data_analyst_agent.charts import (
    ChartSpec,
    ChartType,
    correlation_heatmap,
    distribution_plot,
    render_chart,
    suggest_chart,
)
from data_analyst_agent.exceptions import ChartError


class TestSuggestChart:
    @pytest.mark.parametrize(
        ("request_text", "chart_type", "x", "y"),
        [
            ("units over time", ChartType.LINE, "order_date", "units"),
            ("unit price trend", ChartType.LINE, "order_date", "unit_price"),
            ("distribution of unit price", ChartType.HISTOGRAM, "unit_price", None),
            ("unit price vs units", ChartType.SCATTER, "units", "unit_price"),
            ("compare units by region", ChartType.BAR, "region", "units"),
            ("share of units per region", ChartType.PIE, "region", "units"),
            ("outliers in unit price", ChartType.BOX, "region", "unit_price"),
        ],
    )
    def test_keywords_and_mentioned_columns(self, sales, request_text, chart_type, x, y):
        spec = suggest_chart(request_text, sales)

        assert (spec.chart_type, spec.x, spec.y) == (chart_type, x, y)
        assert spec.rationale

    def test_infers_column_types_from_data(self, sales):
        # Regression: types used to be read from head().to_dict(), which always
        # yielded dicts, so every request fell through to a broken default.
        spec = suggest_chart("", sales)

        assert spec.chart_type is ChartType.LINE
        assert spec.x == "order_date"

    def test_falls_back_when_requested_type_impossible(self):
        df = pd.DataFrame({"city": ["a", "b", "a"]})

        spec = suggest_chart("scatter plot", df)

        assert spec.chart_type is ChartType.BAR
        assert spec.y is None

    def test_no_usable_columns(self):
        df = pd.DataFrame({"when": pd.to_datetime(["2024-01-01"])})

        with pytest.raises(ChartError):
            suggest_chart("anything", df)


class TestRenderChart:
    @pytest.mark.parametrize(
        "request_text",
        [
            "units over time",
            "distribution of units",
            "units vs unit price",
            "units by region",
            "share of units by region",
            "box plot of units",
            "how often does each region appear",
        ],
    )
    def test_every_suggestion_renders(self, sales, request_text):
        figure = render_chart(sales, suggest_chart(request_text, sales))

        assert isinstance(figure, go.Figure)
        assert figure.data

    def test_bar_aggregates_by_category(self, sales):
        figure = render_chart(sales, ChartSpec(ChartType.BAR, "region", "units"))

        bars = dict(zip(figure.data[0].x, figure.data[0].y, strict=True))
        assert bars == {"North": 8.5, "South": 4.0, "East": 1.0}

    def test_bar_counts_without_measure(self, sales):
        figure = render_chart(sales, ChartSpec(ChartType.BAR, "region"))

        assert dict(zip(figure.data[0].x, figure.data[0].y, strict=True))["North"] == 2

    def test_unknown_column(self, sales):
        with pytest.raises(ChartError, match="nope"):
            render_chart(sales, ChartSpec(ChartType.HISTOGRAM, "nope"))


def test_correlation_heatmap(sales):
    figure = correlation_heatmap(sales)

    assert list(figure.data[0].x) == ["units", "unit_price"]


def test_correlation_heatmap_needs_two_numeric_columns():
    with pytest.raises(ChartError):
        correlation_heatmap(pd.DataFrame({"a": [1, 2]}))


def test_distribution_plot(sales):
    figure = distribution_plot(sales, "units")

    assert [trace.type for trace in figure.data] == ["histogram", "box"]
