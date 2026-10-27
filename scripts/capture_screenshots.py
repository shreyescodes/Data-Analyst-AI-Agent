"""Regenerate the README screenshots by driving the real app in a browser.

Starts the Streamlit app, loads the Palmer Penguins dataset from
``docs/data/penguins.csv``, walks through every tab and saves PNGs to
``docs/images/``. Uses the locally installed Google Chrome via Playwright.

    uv run --group screenshots python scripts/capture_screenshots.py
    uv run --group screenshots python scripts/capture_screenshots.py --llm  # needs an LLM
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import FloatRect, Locator, Page, sync_playwright

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "docs" / "data" / "penguins.csv"
OUTPUT = ROOT / "docs" / "images"
PORT = 8599
URL = f"http://localhost:{PORT}"
VIEWPORT = {"width": 1440, "height": 2600}


LLM_VARIABLES = {"LLM_API_KEY", "HF_TOKEN", "HF_API_KEY", "LLM_BASE_URL", "LLM_MODEL"}


@contextmanager
def running_app(*, use_llm: bool) -> Iterator[None]:
    """Start the app; without ``use_llm`` all LLM settings are removed (rule-based mode)."""
    env = {k: v for k, v in os.environ.items() if use_llm or k not in LLM_VARIABLES}
    env["DATA_VERSIONS_DIR"] = tempfile.mkdtemp(prefix="screenshots-")
    process = subprocess.Popen(  # noqa: S603 - fixed argument list
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(ROOT / "app.py"),
            f"--server.port={PORT}",
            "--server.headless=true",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_health()
        yield
    finally:
        process.terminate()
        process.wait(timeout=10)


def _wait_for_health(timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}/_stcore/health", timeout=2):  # noqa: S310
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Streamlit did not start in time")


def panel(page: Page) -> Locator:
    """The currently visible tab panel."""
    return page.locator('[role="tabpanel"]:visible')


def open_tab(page: Page, name: str) -> Locator:
    page.get_by_role("tab", name=name).click()
    page.wait_for_timeout(500)
    return panel(page)


def wait_idle(page: Page) -> None:
    """Wait until Streamlit has finished rerunning the script."""
    page.wait_for_timeout(400)
    page.locator('[data-testid="stStatusWidget"]').wait_for(state="hidden", timeout=120_000)
    page.wait_for_timeout(600)


def shot(page: Page, name: str, top: Locator, bottom: Locator, *, sidebar: bool = False) -> None:
    """Save the region from ``top`` to ``bottom`` (inclusive) of the main area."""
    main = page.locator('[data-testid="stMain"]').bounding_box()
    first, last = top.bounding_box(), bottom.bounding_box()
    if not (main and first and last):
        raise RuntimeError(f"{name}: element not visible")
    x = 0.0 if sidebar else main["x"]
    y = max(first["y"] - 12, 0)
    clip: FloatRect = {
        "x": x,
        "y": y,
        "width": main["x"] + main["width"] - x,
        "height": last["y"] + last["height"] + 24 - y,
    }
    path = OUTPUT / f"{name}.png"
    page.screenshot(path=path, clip=clip)
    print(f"saved {path.relative_to(ROOT)}")


def commit_text_area(page: Page, field: Locator, text: str) -> None:
    field.fill(text)
    field.press("Control+Enter")
    wait_idle(page)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Use the LLM configured in the environment and capture only the AI screenshots.",
    )
    args = parser.parse_args()

    OUTPUT.mkdir(parents=True, exist_ok=True)
    with running_app(use_llm=args.llm), sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=VIEWPORT)  # type: ignore[arg-type]
        page.goto(URL)
        page.get_by_role("tab", name="Load data").wait_for()
        wait_idle(page)

        load_dataset(page, screenshot=not args.llm)
        if args.llm:
            capture_llm(page)
        else:
            capture_workflow(page)
        browser.close()


def load_dataset(page: Page, *, screenshot: bool) -> None:
    tab = panel(page)
    tab.locator('input[type="file"]').set_input_files(DATASET)
    tab.get_by_text("Loaded: penguins.csv").wait_for(timeout=60_000)
    wait_idle(page)
    if screenshot:
        shot(
            page,
            "01-load-data",
            page.get_by_role("heading", name="Data Analyst AI Agent"),
            tab.locator('[data-testid="stDataFrame"]'),
            sidebar=True,
        )


def capture_workflow(page: Page) -> None:
    # 2. Clean it.
    tab = open_tab(page, "Clean")
    tab.get_by_role("button", name="Run cleaning").click()
    tab.get_by_role("heading", name="Result").wait_for()
    wait_idle(page)
    shot(
        page,
        "02-clean",
        tab.get_by_role("heading", name="Clean"),
        tab.locator('[data-testid="stDataFrame"]').nth(1),
    )

    # 3. Snapshot the cleaned data.
    tab.get_by_role("textbox", name="Description", exact=True).fill(
        "Penguins: dropped rows with missing values"
    )
    tab.get_by_role("button", name="Save snapshot").click()
    tab.get_by_text("Saved snapshot").wait_for()
    wait_idle(page)
    shot(
        page,
        "03-snapshots",
        tab.get_by_role("heading", name="Snapshots"),
        tab.get_by_role("button", name="Restore").last,
    )

    # 4. Ask a question in plain English.
    tab = open_tab(page, "Ask & query")
    tab.get_by_role("textbox", name="Question", exact=True).fill("average body mass by species")
    tab.get_by_role("button", name="Ask").click()
    tab.get_by_text("Rule-based SQL").wait_for()
    wait_idle(page)
    shot(
        page,
        "04-ask",
        tab.get_by_role("heading", name="Ask a question"),
        tab.get_by_role("button", name="Download result as CSV").first,
    )

    # 5. Hand-written SQL, then a write attempt that must be refused.
    editor = tab.get_by_role("textbox", name="SQL", exact=True)
    commit_text_area(
        page,
        editor,
        "SELECT species, sex,\n"
        "       ROUND(AVG(flipper_length_mm), 1) AS avg_flipper_mm,\n"
        "       ROUND(AVG(body_mass_g)) AS avg_mass_g,\n"
        "       COUNT(*) AS penguins\n"
        "FROM dataset\nGROUP BY species, sex\nORDER BY avg_mass_g DESC",
    )
    tab.get_by_role("button", name="Run SQL").click()
    wait_idle(page)
    shot(
        page,
        "05-sql",
        tab.get_by_role("heading", name="Run SQL"),
        tab.get_by_role("button", name="Download result as CSV").last,
    )

    commit_text_area(page, editor, "DELETE FROM dataset WHERE species = 'Adelie'")
    tab.get_by_role("button", name="Run SQL").click()
    tab.get_by_text("Only SELECT queries").wait_for()
    wait_idle(page)
    shot(
        page,
        "06-sql-blocked",
        tab.get_by_role("heading", name="Run SQL"),
        tab.get_by_text("Only SELECT queries"),
    )

    # 6. Charts from a plain-English request.
    tab = open_tab(page, "Visualise")
    tab.get_by_role("textbox", name="Describe a chart", exact=True).fill(
        "body mass vs flipper length"
    )
    tab.get_by_role("button", name="Create chart").click()
    tab.locator(".js-plotly-plot").first.wait_for()
    wait_idle(page)
    shot(
        page,
        "07-chart",
        tab.get_by_role("heading", name="Visualise"),
        tab.get_by_text("Scatter plot showing"),
    )
    tab.get_by_role("heading", name="Quick look").scroll_into_view_if_needed()
    shot(
        page,
        "08-quick-look",
        tab.get_by_role("heading", name="Quick look"),
        tab.locator(".js-plotly-plot").last,
    )

    # 7. Profiling report.
    tab = open_tab(page, "Profile")
    tab.get_by_role("button", name="Generate report").click()
    report = tab.locator("iframe")
    report.wait_for(timeout=180_000)
    page.frame_locator('[role="tabpanel"]:visible iframe').get_by_text(
        "Dataset statistics"
    ).wait_for(timeout=60_000)
    page.wait_for_timeout(2_000)
    shot(page, "09-profile", tab.get_by_role("heading", name="Profile"), report)


def capture_llm(page: Page) -> None:
    """A question the keyword rules cannot answer, plus the connection check."""
    tab = open_tab(page, "Ask & query")
    tab.get_by_role("textbox", name="Question", exact=True).fill(
        "What is the average body mass of male Adelie penguins?"
    )
    tab.get_by_role("button", name="Ask").click()
    tab.get_by_text("AI-generated SQL").wait_for(timeout=600_000)
    wait_idle(page)
    shot(
        page,
        "10-ask-local-llm",
        tab.get_by_role("heading", name="Ask a question"),
        tab.get_by_role("button", name="Download result as CSV").first,
        sidebar=True,
    )

    tab = open_tab(page, "Settings")
    tab.get_by_role("button", name="Test LLM connection").click()
    tab.get_by_text("Connected to").wait_for(timeout=300_000)
    wait_idle(page)
    shot(
        page,
        "11-settings-local-llm",
        tab.get_by_role("heading", name="Settings"),
        tab.get_by_text("Connected to"),
    )


if __name__ == "__main__":
    main()
