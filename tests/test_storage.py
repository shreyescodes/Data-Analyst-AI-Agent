import pandas as pd
import pytest

from data_analyst_agent.exceptions import StorageError, UnsafeQueryError
from data_analyst_agent.storage import (
    TABLE_NAME,
    SQLiteStore,
    quote_identifier,
    validate_read_only,
)


@pytest.fixture
def store(sales):
    with SQLiteStore(row_limit=3, timeout_seconds=1.0) as s:
        s.load(sales)
        yield s


class TestValidateReadOnly:
    @pytest.mark.parametrize(
        "sql",
        [
            "SELECT 1",
            "  select * from dataset;  ",
            "WITH t AS (SELECT 1) SELECT * FROM t",
            "-- comment\nSELECT 1",
            "/* block */ SELECT 1",
        ],
    )
    def test_accepts_queries(self, sql):
        assert validate_read_only(sql).lower().rstrip().endswith(("1", "dataset", "t"))

    @pytest.mark.parametrize(
        "sql",
        [
            "",
            "   ;",
            "DROP TABLE dataset",
            "DELETE FROM dataset",
            "PRAGMA table_info(x)",
            "ATTACH DATABASE 'x' AS y",
            "-- SELECT\nDELETE FROM dataset",
        ],
    )
    def test_rejects_non_select(self, sql):
        with pytest.raises(UnsafeQueryError):
            validate_read_only(sql)

    def test_does_not_reject_keywords_inside_identifiers(self):
        # A naive blocklist would reject the column name "last_updated".
        assert validate_read_only('SELECT "last_updated" FROM dataset')


class TestSQLiteStore:
    def test_query_returns_frame(self, store):
        result = store.query(
            f"SELECT region, SUM(units) AS total FROM {TABLE_NAME} "
            "GROUP BY region ORDER BY total DESC"
        )

        assert result.frame.to_dict("records") == [
            {"region": "North", "total": 17},
            {"region": "South", "total": 8},
            {"region": "East", "total": 1},
        ]
        assert not result.truncated

    def test_truncates_to_row_limit(self, store):
        result = store.query(f"SELECT * FROM {TABLE_NAME}")

        assert len(result.frame) == 3
        assert result.truncated

    def test_dates_are_queryable(self, store):
        result = store.query(
            f"SELECT COUNT(*) AS n FROM {TABLE_NAME} WHERE order_date >= '2024-01-03'"
        )

        assert result.frame.iat[0, 0] == 2

    def test_load_replaces_previous_data(self, store):
        store.load(pd.DataFrame({"x": [1]}))

        assert store.query(f"SELECT * FROM {TABLE_NAME}").frame.columns.tolist() == ["x"]

    @pytest.mark.parametrize(
        "sql",
        [
            # Writes hidden behind a SELECT-looking prefix are still refused,
            # because the connection itself is read-only.
            f"WITH x AS (SELECT 1) DELETE FROM {TABLE_NAME}",
            f"SELECT 1; DROP TABLE {TABLE_NAME}",
        ],
    )
    def test_writes_are_impossible(self, store, sql):
        with pytest.raises(StorageError):
            store.query(sql)

        assert len(store.query(f"SELECT * FROM {TABLE_NAME}").frame) == 3

    def test_sql_errors_are_wrapped(self, store):
        with pytest.raises(StorageError, match="no such column"):
            store.query(f"SELECT missing FROM {TABLE_NAME}")

    def test_long_queries_time_out(self, sales):
        with SQLiteStore(timeout_seconds=0.05) as slow:
            slow.load(sales)
            endless = (
                "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) "
                "SELECT COUNT(*) FROM n"
            )
            with pytest.raises(StorageError, match="time limit"):
                slow.query(endless)

    def test_query_before_load(self):
        with SQLiteStore() as empty, pytest.raises(StorageError, match="No data"):
            empty.query("SELECT 1")

    def test_close_removes_files(self, sales):
        store = SQLiteStore()
        store.load(sales)
        directory = store._dir

        store.close()

        assert not directory.exists()


@pytest.mark.parametrize(
    ("name", "quoted"),
    [("region", '"region"'), ("unit price", '"unit price"'), ('a"b', '"a""b"')],
)
def test_quote_identifier(name, quoted):
    assert quote_identifier(name) == quoted
