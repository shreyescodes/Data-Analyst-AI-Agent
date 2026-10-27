import pandas as pd
import pytest

from data_analyst_agent.schema import ColumnKind, Schema, classify


def test_classify():
    df = pd.DataFrame(
        {
            "n": [1.5],
            "flag": [True],
            "when": pd.to_datetime(["2024-01-01"]),
            "label": ["x"],
            "s": pd.Series(["y"], dtype="string"),
        }
    )

    kinds = [classify(df[c]) for c in df.columns]

    assert kinds == [
        ColumnKind.NUMERIC,
        ColumnKind.BOOLEAN,
        ColumnKind.DATETIME,
        ColumnKind.TEXT,
        ColumnKind.TEXT,
    ]


@pytest.fixture
def penguins_schema():
    columns = ["species", "bill_length_mm", "body_mass_g", "sex", "year", "unit_price", "units"]
    return Schema.from_frame(pd.DataFrame({c: [1] for c in columns}))


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("average body mass by species", ["body_mass_g", "species"]),
        ("Body-Mass (g) per SPECIES?", ["body_mass_g", "species"]),
        ("bill length mm", ["bill_length_mm"]),
        ("count by sexes", ["sex"]),
        ("total units", ["units"]),
        ("units vs unit price", ["units", "unit_price"]),
        ("mass of the birds", []),
        ("", []),
    ],
)
def test_mentioned_in(penguins_schema, question, expected):
    assert penguins_schema.mentioned_in(question, penguins_schema.names()) == expected
