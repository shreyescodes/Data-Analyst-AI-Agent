from dataclasses import dataclass, field

import pandas as pd
import pytest

from data_analyst_agent.assistant import (
    MAX_SQL_ATTEMPTS,
    Assistant,
    FailedQuery,
    Source,
    extract_sql,
    rule_based_sql,
    rule_based_summary,
)
from data_analyst_agent.exceptions import LLMError, QueryTimeoutError, StorageError
from data_analyst_agent.schema import Schema
from data_analyst_agent.storage import SQLiteStore


@dataclass
class FakeClient:
    """Records prompts and replays canned replies (or raises them if exceptions)."""

    replies: list[str | Exception]
    model: str = "fake-model"
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system, user, *, max_tokens=512, temperature=0.2):
        self.prompts.append((system, user))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


@pytest.fixture
def schema(sales):
    return Schema.from_frame(sales)


@pytest.fixture
def store(sales):
    with SQLiteStore() as store:
        store.load(sales)
        yield store


COUNT_SQL = 'SELECT COUNT(*) AS "row_count" FROM "dataset"'


class TestRuleBasedSQL:
    @pytest.mark.parametrize(
        ("question", "expected"),
        [
            (
                "What is the average unit price?",
                'SELECT ROUND(AVG("unit_price"), 2) AS "avg_unit_price" FROM "dataset"',
            ),
            ("total units", 'SELECT SUM("units") AS "sum_units" FROM "dataset"'),
            ("highest units", 'SELECT MAX("units") AS "max_units" FROM "dataset"'),
            ("How many orders are there?", 'SELECT COUNT(*) AS "row_count" FROM "dataset"'),
            (
                "total units by region",
                'SELECT "region", SUM("units") AS "sum_units" FROM "dataset" '
                'GROUP BY "region" ORDER BY 2 DESC LIMIT 50',
            ),
            (
                "number of orders per region",
                'SELECT "region", COUNT(*) AS "row_count" FROM "dataset" '
                'GROUP BY "region" ORDER BY 2 DESC LIMIT 50',
            ),
            ("show me the data", 'SELECT * FROM "dataset" LIMIT 100'),
        ],
    )
    def test_question_shapes(self, schema, question, expected):
        assert rule_based_sql(question, schema) == expected

    def test_by_must_be_a_whole_word(self, schema):
        # Regression: a substring check matched "by" inside words like "maybe".
        assert "GROUP BY" not in rule_based_sql("maybe the average units", schema)

    def test_quotes_columns_with_spaces(self):
        schema = Schema.from_frame(pd.DataFrame({"Unit Price": [1.0], "Store Name": ["a"]}))

        sql = rule_based_sql("average unit price by store name", schema)

        assert sql.startswith('SELECT "Store Name", ROUND(AVG("Unit Price"), 2)')

    def test_generated_sql_runs(self, schema, store):
        result = store.query(rule_based_sql("average units by region", schema))

        assert result.frame.iloc[0].tolist() == ["North", 8.5]


class TestExtractSQL:
    @pytest.mark.parametrize(
        "reply",
        [
            'SELECT * FROM "dataset"',
            '```sql\nSELECT * FROM "dataset";\n```',
            'Here is the query:\n\nSELECT * FROM "dataset";\n\nIt returns all rows.',
            '```\nSELECT * FROM "dataset"\n```',
        ],
    )
    def test_extracts_statement(self, reply):
        assert extract_sql(reply) == 'SELECT * FROM "dataset"'

    def test_keeps_only_first_statement(self):
        assert extract_sql("SELECT 1; DROP TABLE dataset") == "SELECT 1"

    def test_rejects_replies_without_sql(self):
        with pytest.raises(LLMError):
            extract_sql("I cannot answer that.")


class TestAssistant:
    def test_without_client_uses_rules(self, schema, store):
        generated, result = Assistant(None).answer("how many rows", schema, store.query)

        assert generated.source is Source.RULES
        assert generated.note is None
        assert result.frame.iat[0, 0] == 5

    def test_llm_sql_and_prompt_contents(self, schema, store):
        client = FakeClient(['```sql\nSELECT "region" FROM "dataset"\n```'])

        generated, result = Assistant(client).answer("list regions", schema, store.query)

        assert generated.sql == 'SELECT "region" FROM "dataset"'
        assert generated.source is Source.LLM
        assert generated.failed_attempts == ()
        assert len(result.frame) == 5
        _, user_prompt = client.prompts[0]
        assert "- unit_price (numeric)" in user_prompt
        assert "list regions" in user_prompt
        assert "previous queries failed" not in user_prompt

    def test_schema_only_is_sent_for_sql(self, schema, store):
        client = FakeClient(["SELECT 1"])

        Assistant(client).answer("anything", schema, store.query)

        assert "North" not in client.prompts[0][1]

    def test_provider_failure_falls_back_to_rules(self, schema, store):
        client = FakeClient([LLMError("provider down")])

        generated, _ = Assistant(client).answer("how many rows", schema, store.query)

        assert generated.source is Source.RULES
        assert generated.sql == COUNT_SQL
        assert "provider down" in (generated.note or "")
        assert len(client.prompts) == 1  # provider errors are not retried

    @pytest.mark.parametrize(
        ("bad_reply", "error"),
        [
            ('SELECT "region" FROM "dataset" WHERE colour = 1', "no such column: colour"),
            ("WITH t AS (SELECT 1) DELETE FROM dataset", "tried to modify data"),
            ("DROP TABLE dataset", "did not contain a SELECT"),
        ],
    )
    def test_repairs_a_failed_query(self, schema, store, bad_reply, error):
        client = FakeClient([bad_reply, COUNT_SQL])

        generated, result = Assistant(client).answer("how many rows", schema, store.query)

        assert generated.source is Source.LLM
        assert generated.sql == COUNT_SQL
        assert result.frame.iat[0, 0] == 5
        [failed] = generated.failed_attempts
        assert error in failed.error
        # The second prompt shows the model its own query and the error.
        retry_prompt = client.prompts[1][1]
        assert "Your previous queries failed" in retry_prompt
        assert failed.sql in retry_prompt
        assert error in retry_prompt

    def test_falls_back_to_rules_after_max_attempts(self, schema, store):
        bad = 'SELECT missing FROM "dataset"'
        client = FakeClient([bad] * MAX_SQL_ATTEMPTS)

        generated, result = Assistant(client).answer("how many rows", schema, store.query)

        assert generated.source is Source.RULES
        assert generated.sql == COUNT_SQL
        assert len(generated.failed_attempts) == MAX_SQL_ATTEMPTS
        assert f"failed {MAX_SQL_ATTEMPTS} times" in (generated.note or "")
        assert "no such column: missing" in (generated.note or "")
        assert result.frame.iat[0, 0] == 5

    def test_every_failure_is_shown_on_later_attempts(self, schema, store):
        client = FakeClient(["SELECT a FROM dataset", "SELECT b FROM dataset", COUNT_SQL])

        generated, _ = Assistant(client).answer("how many rows", schema, store.query)

        assert [f.sql for f in generated.failed_attempts] == [
            "SELECT a FROM dataset",
            "SELECT b FROM dataset",
        ]
        last_prompt = client.prompts[2][1]
        assert "Attempt 1:\nSELECT a FROM dataset" in last_prompt
        assert "Attempt 2:\nSELECT b FROM dataset" in last_prompt

    def test_timeouts_are_not_retried(self, schema):
        client = FakeClient(["SELECT 1", "SELECT 2"])

        def run(sql):
            raise QueryTimeoutError("too slow")

        with pytest.raises(QueryTimeoutError):
            Assistant(client).answer("q", schema, run)
        assert len(client.prompts) == 1

    def test_rule_based_query_errors_propagate(self, schema):
        def run(sql):
            raise StorageError("store unavailable")

        with pytest.raises(StorageError, match="store unavailable"):
            Assistant(None).answer("how many rows", schema, run)

    def test_long_non_sql_replies_are_truncated(self, schema, store):
        client = FakeClient(["x" * 5_000, COUNT_SQL])

        generated, _ = Assistant(client).answer("how many rows", schema, store.query)

        assert generated.failed_attempts == (
            FailedQuery("x" * 1_000, "The model reply did not contain a SELECT query."),
        )

    def test_summary_with_llm(self, sales):
        client = FakeClient(["North sells the most."])

        insight = Assistant(client).summarise("who sells most?", "SELECT 1", sales)

        assert insight.text == "North sells the most."
        assert insight.source is Source.LLM
        assert "North" in client.prompts[0][1]

    def test_summary_prompt_includes_verified_facts(self, sales):
        # Regression: a small model named the wrong region as the top seller
        # when it had to read the maximum off the CSV itself.
        client = FakeClient(["North."])
        totals = sales.groupby("region", as_index=False)["units"].sum()

        Assistant(client).summarise("Which region sold the most?", "SELECT 1", totals)

        prompt = client.prompts[0][1]
        assert "Verified facts:" in prompt
        assert "- Highest **units**: North (17)" in prompt

    def test_summary_falls_back(self, sales):
        insight = Assistant(FakeClient([LLMError("down")])).summarise("q", "SELECT 1", sales)

        assert insight.source is Source.RULES
        assert insight.note

    def test_summary_skips_llm_for_empty_results(self):
        client = FakeClient([])

        insight = Assistant(client).summarise("q", "SELECT 1", pd.DataFrame())

        assert insight.text == "The query returned no rows."
        assert client.prompts == []

    def test_check_connection(self):
        Assistant(FakeClient(["OK"])).check_connection()

        with pytest.raises(LLMError, match="No LLM API key"):
            Assistant(None).check_connection()


class TestRuleBasedSummary:
    def test_single_value(self):
        assert rule_based_summary(pd.DataFrame({"total": [1234567]})) == "**total**: 1,234,567"

    def test_single_float(self):
        assert rule_based_summary(pd.DataFrame({"avg": [2.0 / 3]})) == "**avg**: 0.67"

    def test_table(self, sales):
        summary = rule_based_summary(sales)

        assert summary.startswith("The query returned 5 rows and 4 columns.")
        assert "**units**: mean 5.20, range 1 to 10" in summary

    def test_grouped_result_names_extremes(self):
        result = pd.DataFrame(
            {"species": ["Gentoo", "Adelie", "Chinstrap"], "mass": [5092.4, 3706.2, 3733.1]}
        )

        summary = rule_based_summary(result)

        assert "- Highest **mass**: Gentoo (5,092.40)" in summary
        assert "- Lowest **mass**: Adelie (3,706.20)" in summary
