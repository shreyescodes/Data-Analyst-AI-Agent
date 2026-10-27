"""Exercise the installed package inside the production Docker image.

CI pipes this file into the container (`docker run -i ... python - < this`) to
prove the image has every runtime dependency and the core features work
there: loading, cleaning, read-only SQL, profiling and snapshots.
"""

from __future__ import annotations

import os
from importlib import resources
from pathlib import Path

from data_analyst_agent.assistant import rule_based_sql
from data_analyst_agent.cleaning import assess_quality, clean
from data_analyst_agent.exceptions import UnsafeQueryError
from data_analyst_agent.ingestion import load_file
from data_analyst_agent.profiling import build_profile_html
from data_analyst_agent.schema import Schema
from data_analyst_agent.storage import SQLiteStore
from data_analyst_agent.versioning import VersionStore


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"FAILED: {message}")
    print(f"ok  {message}")


def main() -> None:
    sample = resources.files("data_analyst_agent") / "data" / "sample_sales.csv"
    with sample.open("rb") as fh:
        raw = load_file(fh, "sample_sales.csv")
    check(raw.shape == (248, 7), f"bundled sample loads ({raw.shape})")

    quality = assess_quality(raw)
    cleaned, report = clean(raw)
    check(quality.duplicate_rows == 8, "quality assessment finds duplicates")
    check(len(cleaned) == 222 and len(report.steps) == 5, "cleaning pipeline runs")

    with SQLiteStore() as store:
        store.load(cleaned)
        result = store.query(rule_based_sql("total units by region", Schema.from_frame(cleaned)))
        check(len(result.frame) == 4, "grouped query returns one row per region")
        try:
            store.query('DELETE FROM "dataset"')
        except UnsafeQueryError:
            check(True, "write query is refused")
        else:
            check(False, "write query is refused")

    html = build_profile_html(cleaned, minimal=True)
    check("<html" in html.lower(), f"profiling report renders ({len(html):,} bytes)")

    versions = VersionStore(Path(os.environ["DATA_VERSIONS_DIR"]))
    saved = versions.save(cleaned, "container smoke test")
    check(versions.load(saved.version_id).shape == cleaned.shape, "snapshot round-trips")

    print("container smoke test passed")


if __name__ == "__main__":
    main()
