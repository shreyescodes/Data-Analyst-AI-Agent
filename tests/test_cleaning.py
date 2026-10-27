import numpy as np
import pandas as pd
import pytest

from data_analyst_agent.cleaning import (
    CleaningOptions,
    MissingValueStrategy,
    assess_quality,
    clean,
)

ONLY = dict.fromkeys(
    [
        "normalise_text",
        "parse_dates",
        "convert_numeric_text",
        "remove_duplicates",
        "handle_missing",
        "remove_outliers",
    ],
    False,
)


def only(**enabled: object) -> CleaningOptions:
    """Options with every step disabled except those passed in."""
    return CleaningOptions(**{**ONLY, **enabled})  # type: ignore[arg-type]


class TestAssessQuality:
    def test_counts_issues(self, messy):
        quality = assess_quality(messy)

        assert quality.n_rows == 6
        assert quality.duplicate_rows == 1
        # Two None, one NaN and one whitespace-only name.
        assert quality.missing_cells == 4
        assert quality.missing_ratio == pytest.approx(4 / 24)
        assert set(quality.columns_with_missing) == {"name", "joined", "age"}
        # "score" contains "n/a", so it is not purely numeric.
        assert quality.numeric_text_columns == ()

    def test_detects_numeric_text(self):
        df = pd.DataFrame({"a": ["1", "2.5", None], "b": ["x", "1", "2"]})

        assert assess_quality(df).numeric_text_columns == ("a",)

    def test_blank_cells_count_as_missing(self):
        # A whitespace-only cell makes pandas read a numeric column as text.
        df = pd.DataFrame({"rating": ["4", "  ", "5"]})

        quality = assess_quality(df)

        assert quality.missing_cells == 1
        assert quality.numeric_text_columns == ("rating",)

    def test_empty_frame(self):
        quality = assess_quality(pd.DataFrame())

        assert quality.missing_ratio == 0.0


class TestPipeline:
    def test_full_run(self, messy):
        cleaned, report = clean(messy)

        assert cleaned["name"].tolist() == ["Alice", "Bob", "Eve Smith"]
        assert pd.api.types.is_datetime64_any_dtype(cleaned["joined"])
        assert [s.name for s in report.steps] == [
            "Normalise text",
            "Parse dates",
            "Convert numeric text",
            "Remove duplicates",
            "Handle missing values",
        ]
        assert report.rows_removed == 3
        assert cleaned.index.tolist() == [0, 1, 2]

    def test_does_not_mutate_input(self, messy):
        snapshot = messy.copy()

        clean(messy)

        pd.testing.assert_frame_equal(messy, snapshot)

    def test_disabled_steps_do_not_run(self, messy):
        cleaned, report = clean(messy, only())

        assert report.steps == []
        pd.testing.assert_frame_equal(cleaned, messy)


class TestNormaliseText:
    def test_trims_collapses_and_blanks(self, messy):
        cleaned, report = clean(messy, only(normalise_text=True))

        assert cleaned["name"].tolist()[:3] == ["Alice", "Bob", "Bob"]
        assert cleaned["name"].iloc[5] == "Eve Smith"
        assert pd.isna(cleaned["name"].iloc[3])
        assert "1 blank values" in report.steps[0].detail

    def test_preserves_missing_values(self):
        # Regression: astype(str) used to turn NaN into the string "nan".
        df = pd.DataFrame({"city": ["Paris", None, np.nan]})

        cleaned, _ = clean(df, only(normalise_text=True))

        assert cleaned["city"].isna().tolist() == [False, True, True]

    def test_leaves_non_string_values_in_mixed_columns(self):
        df = pd.DataFrame({"mixed": [" a ", 7, 3.5]})

        cleaned, _ = clean(df, only(normalise_text=True))

        assert cleaned["mixed"].tolist() == ["a", 7, 3.5]


class TestParseDates:
    def test_parses_iso_and_us_formats(self):
        df = pd.DataFrame({"iso": ["2024-01-31", "2024-02-01"], "us": ["01/31/2024", "02/01/2024"]})

        cleaned, _ = clean(df, only(parse_dates=True))

        assert cleaned["iso"].dt.day.tolist() == [31, 1]
        assert cleaned["us"].dt.month.tolist() == [1, 2]

    def test_skips_columns_with_unparseable_values(self):
        df = pd.DataFrame({"d": ["2024-01-01", "2024-13-45"]})

        cleaned, report = clean(df, only(parse_dates=True))

        assert cleaned["d"].tolist() == ["2024-01-01", "2024-13-45"]
        assert "0 columns" in report.steps[0].detail

    def test_ignores_non_date_text(self):
        df = pd.DataFrame({"code": ["A-1", "B-2"]})

        cleaned, _ = clean(df, only(parse_dates=True))

        assert cleaned["code"].dtype == object


class TestConvertNumericText:
    def test_converts_after_whitespace_normalisation(self):
        df = pd.DataFrame({"n": [" 1 ", "2", None]})

        cleaned, _ = clean(df, only(normalise_text=True, convert_numeric_text=True))

        assert pd.api.types.is_numeric_dtype(cleaned["n"])
        assert cleaned["n"].iloc[:2].tolist() == [1, 2]

    def test_does_not_coerce_partially_numeric_columns(self, messy):
        cleaned, _ = clean(messy, only(normalise_text=True, convert_numeric_text=True))

        assert "n/a" in cleaned["score"].tolist()


class TestMissingValues:
    @pytest.fixture
    def frame(self):
        return pd.DataFrame({"x": [1.0, np.nan, 3.0, 10.0], "c": ["a", "b", None, "b"]})

    @pytest.mark.parametrize(
        ("strategy", "expected_x", "expected_c"),
        [
            (MissingValueStrategy.MEAN, [1.0, 14 / 3, 3.0, 10.0], ["a", "b", None, "b"]),
            (MissingValueStrategy.MEDIAN, [1.0, 3.0, 3.0, 10.0], ["a", "b", None, "b"]),
            (MissingValueStrategy.MODE, [1.0, 1.0, 3.0, 10.0], ["a", "b", "b", "b"]),
            (MissingValueStrategy.FORWARD_FILL, [1.0, 1.0, 3.0, 10.0], ["a", "b", "b", "b"]),
            (MissingValueStrategy.BACKWARD_FILL, [1.0, 3.0, 3.0, 10.0], ["a", "b", "b", "b"]),
        ],
    )
    def test_fill_strategies(self, frame, strategy, expected_x, expected_c):
        cleaned, _ = clean(frame, only(handle_missing=True, missing_strategy=strategy))

        assert cleaned["x"].tolist() == pytest.approx(expected_x)
        assert [None if pd.isna(v) else v for v in cleaned["c"]] == expected_c

    def test_drop_rows(self, frame):
        cleaned, report = clean(frame, only(handle_missing=True))

        assert cleaned["x"].tolist() == [1.0, 10.0]
        assert report.steps[0].rows_removed == 2


class TestOutliers:
    def test_removes_extreme_rows(self):
        df = pd.DataFrame({"v": [10, 11, 12, 13, 12, 11, 1000]})

        cleaned, report = clean(df, only(remove_outliers=True))

        assert 1000 not in cleaned["v"].tolist()
        assert report.rows_removed == 1

    def test_keeps_rows_with_missing_values(self):
        # Regression: comparisons against NaN used to drop these rows silently.
        df = pd.DataFrame({"v": [10.0, 11.0, 12.0, np.nan, 13.0, 1000.0]})

        cleaned, _ = clean(df, only(remove_outliers=True))

        assert cleaned["v"].isna().sum() == 1

    def test_skips_columns_without_spread(self):
        flags = pd.DataFrame({"flag": [0] * 9 + [1]})

        cleaned, _ = clean(flags, only(remove_outliers=True))

        assert len(cleaned) == 10

    def test_result_does_not_depend_on_column_order(self):
        df = pd.DataFrame({"a": [1, 2, 3, 4, 5, 100, 3, 2], "b": [5, 6, 7, 8, 9, 7, -90, 6]})

        first, _ = clean(df, only(remove_outliers=True))
        second, _ = clean(df[["b", "a"]], only(remove_outliers=True))

        pd.testing.assert_frame_equal(first, second[["a", "b"]])
