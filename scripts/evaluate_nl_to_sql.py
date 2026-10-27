"""Measure natural-language-to-SQL accuracy on a fixed question set.

For each case the generated query and the reference query are both run on
the read-only store. A case passes when the results match: same number of
rows, and every reference row's values appear in a distinct generated row
(extra columns, column order, row order and float noise are ignored).

Uses whatever LLM the environment configures (see .env.example); with no
LLM configured it measures the rule-based fallback.

    uv run python scripts/evaluate_nl_to_sql.py [--cases evals/nl_to_sql_penguins.json]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import pandas as pd

from data_analyst_agent.assistant import Assistant, Source
from data_analyst_agent.config import Settings
from data_analyst_agent.exceptions import DataAgentError
from data_analyst_agent.llm import build_client
from data_analyst_agent.schema import Schema
from data_analyst_agent.storage import SQLiteStore

ROOT = Path(__file__).resolve().parents[1]
Row = Counter[object]


def normalise(frame: pd.DataFrame) -> list[Row]:
    def value(v: object) -> object:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        if isinstance(v, int | float):
            return round(float(v), 1)
        return str(v).strip().lower()

    return [Counter(value(v) for v in row) for row in frame.itertuples(index=False)]


def results_match(expected: pd.DataFrame, actual: pd.DataFrame) -> bool:
    expected_rows, actual_rows = normalise(expected), normalise(actual)
    if len(expected_rows) != len(actual_rows):
        return False
    unused = list(actual_rows)
    for row in expected_rows:
        match = next((c for c in unused if not row - c), None)
        if match is None:
            return False
        unused.remove(match)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=ROOT / "evals" / "nl_to_sql_penguins.json")
    args = parser.parse_args()

    spec = json.loads(args.cases.read_text(encoding="utf-8"))
    df = pd.read_csv(ROOT / spec["dataset"])
    schema = Schema.from_frame(df)
    settings = Settings.from_env()
    assistant = Assistant(build_client(settings))
    mode = f"LLM {settings.llm_model} @ {settings.llm_base_url}" if assistant.uses_llm else "rules"

    passed = 0
    latencies: list[float] = []
    print(f"Mode: {mode}\n")
    with SQLiteStore(row_limit=100_000, timeout_seconds=30) as store:
        store.load(df)
        for i, case in enumerate(spec["cases"], 1):
            started = time.perf_counter()
            generated = assistant.generate_sql(case["question"], schema)
            latencies.append(time.perf_counter() - started)
            try:
                ok = results_match(store.query(case["sql"]).frame, store.query(generated.sql).frame)
            except DataAgentError:
                ok = False
            fallback = (
                " (fell back to rules)"
                if generated.source is Source.RULES and assistant.uses_llm
                else ""
            )
            passed += ok
            print(f"{'PASS' if ok else 'FAIL'}  {i:>2}. {case['question']}{fallback}")
            if not ok:
                print(f"        generated: {generated.sql}")

    total = len(spec["cases"])
    latencies.sort()
    print(
        f"\nExecution accuracy: {passed}/{total} ({passed / total:.0%})"
        f" | median SQL generation latency: {latencies[len(latencies) // 2]:.1f}s"
    )


if __name__ == "__main__":
    main()
