"""Natural-language question answering over the active dataset.

Two capabilities, each with an LLM path and a deterministic fallback:

* :meth:`Assistant.answer` turns a question into a SQLite query and runs it.
  When the model's query is rejected or fails, the error is sent back to the
  model so it can correct the query, up to ``MAX_SQL_ATTEMPTS`` tries.
  Only the schema (column names and types) and the model's own failed SQL
  and error messages are sent to the LLM, never rows.
* :meth:`Assistant.summarise` explains a query result in plain English.
  This sends up to ``_MAX_RESULT_ROWS`` result rows to the LLM.

The fallbacks keep the app fully usable without an API key and are used
automatically when the provider fails.
"""

from __future__ import annotations

import logging
import numbers
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from data_analyst_agent.exceptions import LLMError, QueryTimeoutError, StorageError
from data_analyst_agent.llm import ChatClient
from data_analyst_agent.schema import Schema, normalise_text
from data_analyst_agent.storage import (
    TABLE_NAME,
    QueryResult,
    quote_identifier,
    validate_read_only,
)

logger = logging.getLogger(__name__)

MAX_SQL_ATTEMPTS = 3
_MAX_RESULT_ROWS = 50
_MAX_RESULT_CHARS = 6_000
_MAX_FAILED_REPLY_CHARS = 1_000

RunQuery = Callable[[str], QueryResult]

SQL_SYSTEM_PROMPT = f"""\
You translate questions about a dataset into a single SQLite query.
Rules:
- The only table is "{TABLE_NAME}".
- Use only the columns listed by the user and wrap every column name in double quotes.
- Return exactly one SELECT statement (a WITH clause is allowed).
- Add LIMIT 100 unless the query aggregates to a small number of rows.
- Reply with the SQL only: no explanation and no markdown."""

INSIGHT_SYSTEM_PROMPT = """\
You are a careful data analyst. Answer the user's question using only the query
result provided. Be concise: two to four sentences or a short bullet list.
The "Verified facts" were computed exactly from the full result: rely on them
over your own reading of the table, and never contradict them.
Quote the numbers you rely on and never invent values that are not in the result.
If the result does not answer the question, say so."""


class Source(StrEnum):
    LLM = "llm"
    RULES = "rules"


@dataclass(frozen=True, slots=True)
class FailedQuery:
    """A model-written query that was rejected or failed, and why."""

    sql: str
    error: str


@dataclass(frozen=True, slots=True)
class GeneratedSQL:
    sql: str
    source: Source
    note: str | None = None
    # Earlier model attempts that failed before ``sql`` was produced.
    failed_attempts: tuple[FailedQuery, ...] = ()


@dataclass(frozen=True, slots=True)
class Insight:
    text: str
    source: Source
    note: str | None = None


class Assistant:
    def __init__(self, client: ChatClient | None) -> None:
        self._client = client

    @property
    def uses_llm(self) -> bool:
        return self._client is not None

    @property
    def model(self) -> str | None:
        return self._client.model if self._client else None

    def check_connection(self) -> None:
        """Make a tiny request to confirm the provider, model and key all work."""
        if self._client is None:
            raise LLMError("No LLM API key is configured.")
        self._client.complete(
            "Reply with the single word OK.", "ping", max_tokens=10, temperature=0.0
        )

    def answer(
        self,
        question: str,
        schema: Schema,
        run: RunQuery,
        *,
        max_attempts: int = MAX_SQL_ATTEMPTS,
    ) -> tuple[GeneratedSQL, QueryResult]:
        """Write SQL for ``question``, run it with ``run``, and repair it if it fails.

        A model reply without a usable query, a rejected statement, or a SQL
        error is fed back to the model for another attempt. Timeouts are
        raised rather than retried. If the provider fails or every attempt
        fails, the keyword rules answer instead and the result says why.
        """
        if self._client is None:
            return self._answer_with_rules(question, schema, run)

        failures: list[FailedQuery] = []
        while len(failures) < max_attempts:
            try:
                reply = self._client.complete(
                    SQL_SYSTEM_PROMPT,
                    _sql_prompt(question, schema, failures),
                    max_tokens=400,
                    temperature=0.0,
                )
            except LLMError as exc:
                logger.warning("LLM SQL generation failed, using rules: %s", exc)
                return self._answer_with_rules(
                    question,
                    schema,
                    run,
                    note=f"AI query generation failed ({exc}); used keyword rules instead.",
                    failures=failures,
                )

            sql = reply.strip()[:_MAX_FAILED_REPLY_CHARS]
            try:
                sql = validate_read_only(extract_sql(reply))
                result = run(sql)
            except QueryTimeoutError:
                raise
            except (LLMError, StorageError) as exc:
                logger.info("Model query failed (attempt %d): %s", len(failures) + 1, exc)
                failures.append(FailedQuery(sql, str(exc)))
                continue
            return GeneratedSQL(sql, Source.LLM, failed_attempts=tuple(failures)), result

        logger.warning("Model query failed %d times, using rules", len(failures))
        return self._answer_with_rules(
            question,
            schema,
            run,
            note=(
                f"The AI query failed {len(failures)} times (last error: "
                f"{failures[-1].error}); used keyword rules instead."
            ),
            failures=failures,
        )

    @staticmethod
    def _answer_with_rules(
        question: str,
        schema: Schema,
        run: RunQuery,
        *,
        note: str | None = None,
        failures: list[FailedQuery] | None = None,
    ) -> tuple[GeneratedSQL, QueryResult]:
        sql = rule_based_sql(question, schema)
        generated = GeneratedSQL(sql, Source.RULES, note, tuple(failures or ()))
        return generated, run(sql)

    def summarise(self, question: str, sql: str, result: pd.DataFrame) -> Insight:
        if self._client is None or result.empty:
            return Insight(rule_based_summary(result), Source.RULES)

        # Small models misread tables (e.g. naming the wrong maximum), so the
        # facts that matter are computed in code and passed in as ground truth.
        table = result.head(_MAX_RESULT_ROWS).to_csv(index=False)[:_MAX_RESULT_CHARS]
        prompt = (
            f"Question: {question}\n\nSQL:\n{sql}\n\n"
            f"Verified facts:\n{rule_based_summary(result)}\n\n"
            f"Result ({len(result)} rows; first {min(len(result), _MAX_RESULT_ROWS)} "
            f"shown as CSV):\n{table}"
        )
        try:
            text = self._client.complete(
                INSIGHT_SYSTEM_PROMPT, prompt, max_tokens=500, temperature=0.3
            )
        except LLMError as exc:
            logger.warning("LLM summary failed, using rules: %s", exc)
            return Insight(
                rule_based_summary(result),
                Source.RULES,
                note=f"AI summary failed ({exc}); showing a statistical summary.",
            )
        return Insight(text, Source.LLM)


# --- Prompting and SQL extraction --------------------------------------------


def _sql_prompt(question: str, schema: Schema, failures: list[FailedQuery]) -> str:
    columns = "\n".join(f"- {c.name} ({c.kind.value})" for c in schema.columns)
    prompt = f"Columns:\n{columns}\n\nQuestion: {question}"
    if failures:
        attempts = "\n\n".join(
            f"Attempt {i}:\n{f.sql}\nError: {f.error}" for i, f in enumerate(failures, 1)
        )
        prompt += (
            f"\n\nYour previous queries failed:\n\n{attempts}\n\n"
            "Write a corrected query that avoids these errors."
        )
    return prompt


_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_QUERY_START = re.compile(r"\b(with|select)\b", re.IGNORECASE)


def extract_sql(reply: str) -> str:
    """Pull the first SQL statement out of a model reply."""
    fence = _FENCE.search(reply)
    text = fence.group(1) if fence else reply
    start = _QUERY_START.search(text)
    if not start:
        raise LLMError("The model reply did not contain a SELECT query.")
    return text[start.start() :].split(";", 1)[0].strip()


# --- Rule-based fallbacks ----------------------------------------------------

_AGGREGATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("AVG", ("average", "avg", "mean")),
    ("SUM", ("total", "sum")),
    ("MAX", ("max", "maximum", "highest", "largest", "most")),
    ("MIN", ("min", "minimum", "lowest", "smallest", "least")),
)
_GROUP_BY = re.compile(r"\b(by|per|for each|each|across)\b")
_COUNT = re.compile(r"\b(count|how many|number of)\b")


def rule_based_sql(question: str, schema: Schema) -> str:
    """Map common question shapes to SQL using keywords and column names.

    Supported shapes: aggregates ("average price"), counts ("how many rows"),
    and grouped versions of both ("total revenue by region").
    """
    text = normalise_text(question)
    table = quote_identifier(TABLE_NAME)
    aggregate = next(
        (fn for fn, words in _AGGREGATES if re.search(rf"\b({'|'.join(words)})\b", text)),
        None,
    )

    group_match = _GROUP_BY.search(text)
    head = text[: group_match.start()] if group_match else text
    tail = text[group_match.end() :] if group_match else ""

    group_col = None
    if group_match:
        all_columns = schema.names()
        group_col = next(iter(schema.mentioned_in(tail, all_columns)), None) or next(
            iter(schema.text), None
        )

    numeric = [c for c in schema.numeric if c != group_col]
    value_col = next(iter(schema.mentioned_in(head, numeric)), None) or next(iter(numeric), None)

    if group_col is not None:
        group = quote_identifier(group_col)
        if aggregate and value_col:
            measure = _aggregate_expr(aggregate, value_col)
        else:
            measure = 'COUNT(*) AS "row_count"'
        return f"SELECT {group}, {measure} FROM {table} GROUP BY {group} ORDER BY 2 DESC LIMIT 50"

    if aggregate and value_col:
        return f"SELECT {_aggregate_expr(aggregate, value_col)} FROM {table}"

    if _COUNT.search(text):
        return f'SELECT COUNT(*) AS "row_count" FROM {table}'

    return f"SELECT * FROM {table} LIMIT 100"


def _aggregate_expr(function: str, column: str) -> str:
    expr = f"{function}({quote_identifier(column)})"
    if function == "AVG":
        expr = f"ROUND({expr}, 2)"
    return f"{expr} AS {quote_identifier(f'{function.lower()}_{column}')}"


def rule_based_summary(result: pd.DataFrame) -> str:
    if result.empty:
        return "The query returned no rows."

    if result.shape == (1, 1):
        column = result.columns[0]
        return f"**{column}**: {_format_value(result.iat[0, 0])}"

    schema = Schema.from_frame(result)
    lines = [f"The query returned {len(result):,} rows and {result.shape[1]} columns."]

    # A label column plus one measure (a GROUP BY result): name the extremes.
    if len(schema.text) == 1 and len(schema.numeric) == 1 and len(result) > 1:
        label, measure = schema.text[0], schema.numeric[0]
        ranked = result.dropna(subset=[measure]).sort_values(measure)
        if not ranked.empty:
            top, bottom = ranked.iloc[-1], ranked.iloc[0]
            lines.append(f"- Highest **{measure}**: {top[label]} ({_format_value(top[measure])})")
            lines.append(
                f"- Lowest **{measure}**: {bottom[label]} ({_format_value(bottom[measure])})"
            )
            return "\n".join(lines)

    for column in schema.numeric[:3]:
        values = result[column].dropna()
        if values.empty:
            continue
        lines.append(
            f"- **{column}**: mean {_format_value(values.mean())}, "
            f"range {_format_value(values.min())} to {_format_value(values.max())}"
        )
    return "\n".join(lines)


def _format_value(value: object) -> str:
    # numbers.* ABCs also cover NumPy scalars such as np.int64.
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, numbers.Integral):
        return f"{int(value):,}"
    if isinstance(value, numbers.Real):
        return f"{float(value):,.2f}"
    return str(value)
