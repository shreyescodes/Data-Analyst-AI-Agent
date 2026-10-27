from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sales() -> pd.DataFrame:
    """A small, clean dataset with numeric, text and date columns."""
    return pd.DataFrame(
        {
            "order_date": pd.to_datetime(
                ["2024-01-01", "2024-01-02", "2024-01-02", "2024-01-03", "2024-01-04"]
            ),
            "region": ["North", "South", "North", "East", "South"],
            "units": [10, 3, 7, 1, 5],
            "unit_price": [2.5, 10.0, 2.5, 99.0, 10.0],
        }
    )


@pytest.fixture
def messy() -> pd.DataFrame:
    """Covers every cleaning step: whitespace, blanks, dates, numeric text, dupes."""
    return pd.DataFrame(
        {
            "name": ["  Alice ", "Bob", "Bob", "   ", None, "Eve  Smith"],
            "joined": ["2024-01-05", "2024-02-10", "2024-02-10", None, "2024-03-01", "2024-04-01"],
            "score": [" 42 ", "17", "17", "8", "n/a", "3"],
            "age": [30.0, 25.0, 25.0, np.nan, 40.0, 35.0],
        }
    )
