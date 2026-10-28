"""Measure natural-language-to-SQL accuracy on a fixed question set.

For each case the assistant answers the question as the app does (writing SQL,
running it and repairing it on errors), and the reference query is run on
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

from data_analyst_agent.assistant import Assistant, GeneratedSQL, Source
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

    passed = self_corrected = 0
    latencies: list[float] = []
    print(f"Mode: {mode}\n")
    with SQLiteStore(row_limit=100_000, timeout_seconds=30) as store:
        store.load(df)
        for i, case in enumerate(spec["cases"], 1):
            started = time.perf_counter()
            try:
                generated, result = assistant.answer(case["question"], schema, store.query)
            except DataAgentError as exc:
                latencies.append(time.perf_counter() - started)
                print(f"FAIL  {i:>2}. {case['question']} ({exc})")
                continue
            latencies.append(time.perf_counter() - started)
            ok = results_match(store.query(case["sql"]).frame, result.frame)
            passed += ok
            self_corrected += (
                ok and generated.source is Source.LLM and bool(generated.failed_attempts)
            )
            print(f"{'PASS' if ok else 'FAIL'}  {i:>2}. {case['question']}{_tags(generated)}")
            if not ok:
                print(f"        generated: {generated.sql}")

    total = len(spec["cases"])
    latencies.sort()
    print(
        f"\nExecution accuracy: {passed}/{total} ({passed / total:.0%})"
        f" | passed after self-correction: {self_corrected}"
        f" | median time to answer: {latencies[len(latencies) // 2]:.1f}s"
    )


def _tags(generated: GeneratedSQL) -> str:
    tags = []
    if generated.failed_attempts:
        tags.append(f"{len(generated.failed_attempts)} failed attempt(s)")
    if generated.source is Source.RULES and generated.note:
        tags.append("fell back to rules")
    return f" ({', '.join(tags)})" if tags else ""


if __name__ == "__main__":
    main()
