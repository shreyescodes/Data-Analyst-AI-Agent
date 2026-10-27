from dataclasses import dataclass, field

import pandas as pd
import pytest

from data_analyst_agent.assistant import (
    Assistant,
    Source,
    extract_sql,
    rule_based_sql,
    rule_based_summary,
)
from data_analyst_agent.exceptions import LLMError
from data_analyst_agent.schema import Schema


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

    def test_generated_sql_runs(self, sales, schema):
        from data_analyst_agent.storage import SQLiteStore

        with SQLiteStore() as store:
            store.load(sales)
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
    def test_without_client_uses_rules(self, schema):
        generated = Assistant(None).generate_sql("how many rows", schema)

        assert generated.source is Source.RULES
        assert generated.note is None

    def test_llm_sql_and_prompt_contents(self, schema):
        client = FakeClient(['```sql\nSELECT "region" FROM "dataset"\n```'])

        generated = Assistant(client).generate_sql("list regions", schema)

        assert generated == generated.__class__('SELECT "region" FROM "dataset"', Source.LLM)
        _, user_prompt = client.prompts[0]
        assert "- unit_price (numeric)" in user_prompt
        assert "list regions" in user_prompt

    def test_schema_only_is_sent_for_sql(self, sales, schema):
        client = FakeClient(["SELECT 1"])

        Assistant(client).generate_sql("anything", schema)

        assert "North" not in client.prompts[0][1]

    @pytest.mark.parametrize(
        "reply", [LLMError("provider down"), "DELETE FROM dataset", "no sql here"]
    )
    def test_falls_back_to_rules(self, schema, reply):
        generated = Assistant(FakeClient([reply])).generate_sql("how many rows", schema)

        assert generated.source is Source.RULES
        assert generated.sql == 'SELECT COUNT(*) AS "row_count" FROM "dataset"'
        assert generated.note

    def test_summary_with_llm(self, sales):
        client = FakeClient(["North sells the most."])

        insight = Assistant(client).summarise("who sells most?", "SELECT 1", sales)

        assert insight.text == "North sells the most."
        assert insight.source is Source.LLM
        assert "North" in client.prompts[0][1]

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
