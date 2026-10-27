"""Load tabular data from files, HTTP APIs and SQL databases."""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
from collections.abc import Mapping
from pathlib import PurePath
from typing import IO, Any
from urllib.parse import urlparse

import pandas as pd
import requests
import sqlalchemy as sa

from data_analyst_agent.exceptions import IngestionError

logger = logging.getLogger(__name__)

SUPPORTED_FILE_TYPES = ("csv", "xlsx")
_CSV_ENCODINGS = ("utf-8-sig", "latin-1")
# Keys commonly used by REST APIs to wrap the list of records.
_JSON_RECORD_KEYS = ("data", "results", "items", "records", "rows")
# DB drivers are optional extras; map the import name to the extra that installs it.
_DRIVER_EXTRAS = {"psycopg": "postgres", "psycopg2": "postgres", "pymysql": "mysql"}


def load_file(file: IO[bytes], filename: str) -> pd.DataFrame:
    """Read a CSV or Excel upload into a DataFrame.

    CSV files are decoded as UTF-8 (with or without BOM), falling back to
    Latin-1, which accepts any byte sequence.
    """
    extension = PurePath(filename).suffix.lower().lstrip(".")
    if extension not in SUPPORTED_FILE_TYPES:
        raise IngestionError(
            f"Unsupported file type '.{extension}'. "
            f"Expected one of: {', '.join(SUPPORTED_FILE_TYPES)}."
        )

    try:
        df = _read_csv(file) if extension == "csv" else pd.read_excel(file)
    except (ValueError, pd.errors.ParserError) as exc:
        raise IngestionError(f"Could not parse '{filename}': {exc}") from exc

    _ensure_not_empty(df, f"'{filename}' contains no rows")
    logger.info("Loaded %s: %d rows x %d columns", filename, *df.shape)
    return df


def load_from_api(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
    allow_private: bool = False,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Fetch records from an HTTP endpoint returning JSON or CSV.

    Unless ``allow_private`` is set, hosts resolving to private, loopback,
    link-local or otherwise non-public addresses are refused, so a deployed
    instance cannot be used to reach internal services or cloud metadata
    endpoints (SSRF). Redirects are not followed, since they could bypass
    that check.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise IngestionError("API URL must be an absolute http(s) URL.")
    if not allow_private:
        _ensure_public_host(parsed.hostname)

    http = session or requests.Session()
    try:
        response = http.get(
            url, headers=dict(headers or {}), timeout=timeout, allow_redirects=False
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise IngestionError(f"Request to {parsed.netloc} failed: {exc}") from exc
    if response.is_redirect:
        location = response.headers.get("Location", "an unknown location")
        raise IngestionError(f"The API redirected to {location}; use that URL directly.")

    content_type = response.headers.get("Content-Type", "")
    if "csv" in content_type:
        df = _read_csv(io.BytesIO(response.content))
    else:
        try:
            payload = response.json()
        except ValueError as exc:
            raise IngestionError(
                f"Response from {parsed.netloc} is neither JSON nor CSV "
                f"(Content-Type: {content_type or 'unknown'})."
            ) from exc
        df = _frame_from_json(payload)

    _ensure_not_empty(df, "The API returned no records")
    logger.info("Loaded %d rows x %d columns from %s", *df.shape, parsed.netloc)
    return df


def load_from_database(connection_url: str, table: str) -> pd.DataFrame:
    """Read a whole table through SQLAlchemy.

    The table name is resolved via reflection, never interpolated into SQL.
    """
    if not table.strip():
        raise IngestionError("A table name is required.")

    try:
        engine = sa.create_engine(connection_url)
    except ModuleNotFoundError as exc:
        extra = _DRIVER_EXTRAS.get(exc.name or "")
        hint = f' Install it with: pip install ".[{extra}]"' if extra else ""
        raise IngestionError(f"Database driver '{exc.name}' is missing.{hint}") from exc
    except sa.exc.ArgumentError as exc:
        raise IngestionError(f"Invalid connection URL: {exc}") from exc

    try:
        df = pd.read_sql_table(table, engine)
    except ValueError as exc:  # raised by pandas when the table does not exist
        raise IngestionError(f"Table '{table}' was not found.") from exc
    except sa.exc.SQLAlchemyError as exc:
        raise IngestionError(f"Database error: {exc}") from exc
    finally:
        engine.dispose()

    _ensure_not_empty(df, f"Table '{table}' is empty")
    logger.info("Loaded table %s: %d rows x %d columns", table, *df.shape)
    return df


def _ensure_public_host(host: str) -> None:
    # ponytail: the address is checked here and resolved again by requests, so a
    # DNS-rebinding attacker could still race it; pin the IP in a custom adapter
    # if this app is ever exposed to untrusted users on a sensitive network.
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror as exc:
        raise IngestionError(f"Could not resolve host '{host}'.") from exc
    for address in addresses:
        ip = ipaddress.ip_address(str(address).split("%", 1)[0])
        if not ip.is_global:
            raise IngestionError(
                f"'{host}' resolves to a private or reserved address ({ip}). "
                "Set ALLOW_PRIVATE_URLS=true to load from internal hosts."
            )


def _read_csv(file: IO[bytes]) -> pd.DataFrame:
    for encoding in _CSV_ENCODINGS:
        file.seek(0)
        try:
            return pd.read_csv(file, encoding=encoding)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    # Latin-1 decodes every byte sequence, so this is unreachable in practice.
    raise IngestionError("Could not decode the CSV file.")


def _frame_from_json(payload: Any) -> pd.DataFrame:
    if isinstance(payload, list):
        return pd.json_normalize(payload)
    if isinstance(payload, dict):
        for key in _JSON_RECORD_KEYS:
            if isinstance(payload.get(key), list):
                return pd.json_normalize(payload[key])
        return pd.json_normalize(payload)
    raise IngestionError("JSON response must be an object or an array of records.")


def _ensure_not_empty(df: pd.DataFrame, message: str) -> None:
    if df.empty:
        raise IngestionError(message)
