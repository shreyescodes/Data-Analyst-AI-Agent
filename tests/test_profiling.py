import pandas as pd
import pytest

from data_analyst_agent.profiling import LARGE_DATASET_CELLS, build_profile_html, is_large


def test_is_large():
    assert not is_large(pd.DataFrame({"a": range(10)}))
    assert is_large(pd.DataFrame({"a": range(LARGE_DATASET_CELLS + 1)}))


@pytest.mark.slow
def test_build_minimal_report(sales):
    html = build_profile_html(sales, title="Sales", minimal=True)

    assert html.lstrip().lower().startswith("<!doctype html")
    assert "Sales" in html
