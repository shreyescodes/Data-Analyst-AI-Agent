# ADR-0003: Framework-free core package with a thin Streamlit UI

## Status
Accepted

## Date
2026-10-27

## Context
The original code was a 637-line `app.py` that mixed Streamlit widgets with
data logic, plus loosely organised `modules/` and `utils/` directories that
were not an installable package. None of it could be tested without running
the UI, and the only test was `assert True`.

## Decision
- Ship one installable package, `data_analyst_agent`, in a `src/` layout.
- Core modules (`ingestion`, `cleaning`, `storage`, `assistant`, `charts`,
  `profiling`, `versioning`, `config`) never import Streamlit. They take and
  return plain values (DataFrames, frozen dataclasses) and raise subclasses
  of `DataAgentError` for expected failures.
- `data_analyst_agent.ui` holds the Streamlit layer: one module per tab, a
  typed `SessionState` wrapper, and process-wide resources cached with
  `st.cache_resource`.
- The root `app.py` is a three-line entry point so `streamlit run app.py`
  keeps working.

## Alternatives considered

### FastAPI backend + separate frontend
- Pros: a reusable HTTP API.
- Cons: two deployables and an API contract to maintain, with no current
  consumer other than the UI.
- Rejected for now. The core package boundary means an API layer can be
  added later without touching business logic.

## Consequences
- The core is unit-tested directly; the UI is covered by end-to-end tests
  using `streamlit.testing.v1.AppTest`.
- UI code only translates between widgets and core calls, so it stays small.
