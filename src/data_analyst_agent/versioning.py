"""Immutable, checksummed snapshots of datasets on the local filesystem.

Layout::

    <root>/<version_id>/data.parquet
    <root>/<version_id>/metadata.json

Parquet keeps column types (dates, integers, nullable values) intact across a
save/load round trip, unlike CSV. A SHA-256 of the data file is stored in the
metadata and verified on load.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from pandas.api import types as ptypes

from data_analyst_agent.exceptions import VersioningError

logger = logging.getLogger(__name__)

_DATA_FILE = "data.parquet"
_METADATA_FILE = "metadata.json"
_VERSION_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{6}$")


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    version_id: str
    created_at: datetime
    message: str
    n_rows: int
    n_columns: int
    sha256: str

    def to_json(self) -> str:
        data = asdict(self)
        data["created_at"] = self.created_at.isoformat()
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> DatasetVersion:
        data = json.loads(raw)
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        return cls(**data)


class VersionStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, df: pd.DataFrame, message: str = "") -> DatasetVersion:
        now = datetime.now(UTC)
        version_id = f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"
        directory = self.root / version_id
        try:
            directory.mkdir(parents=True, exist_ok=False)
            data_path = directory / _DATA_FILE
            _parquet_safe(df).to_parquet(data_path, index=False)
            version = DatasetVersion(
                version_id=version_id,
                created_at=now,
                message=message.strip(),
                n_rows=len(df),
                n_columns=df.shape[1],
                sha256=_sha256(data_path),
            )
            # Metadata is written last, so a version only becomes visible to
            # history() once its data file is complete.
            tmp = directory / f"{_METADATA_FILE}.tmp"
            tmp.write_text(version.to_json(), encoding="utf-8")
            tmp.replace(directory / _METADATA_FILE)
        except (OSError, ValueError, TypeError) as exc:
            raise VersioningError(f"Could not save version: {exc}") from exc

        logger.info("Saved dataset version %s (%d rows)", version_id, len(df))
        return version

    def history(self) -> list[DatasetVersion]:
        """All complete versions, newest first."""
        if not self.root.exists():
            return []
        versions = []
        for metadata in self.root.glob(f"*/{_METADATA_FILE}"):
            try:
                versions.append(DatasetVersion.from_json(metadata.read_text("utf-8")))
            except (OSError, ValueError, TypeError, KeyError) as exc:
                logger.warning("Skipping unreadable version %s: %s", metadata.parent, exc)
        return sorted(versions, key=lambda v: v.created_at, reverse=True)

    def load(self, version_id: str) -> pd.DataFrame:
        if not _VERSION_ID.match(version_id):
            raise VersioningError(f"Invalid version id: {version_id!r}")
        directory = self.root / version_id
        try:
            version = DatasetVersion.from_json((directory / _METADATA_FILE).read_text("utf-8"))
        except FileNotFoundError as exc:
            raise VersioningError(f"Version {version_id} does not exist.") from exc

        data_path = directory / _DATA_FILE
        if _sha256(data_path) != version.sha256:
            raise VersioningError(
                f"Version {version_id} failed its integrity check; the data file "
                "was modified after it was saved."
            )
        return pd.read_parquet(data_path)


def _parquet_safe(df: pd.DataFrame) -> pd.DataFrame:
    """Store mixed-type object columns as strings, which Parquet requires."""
    mixed = [
        col
        for col in df.columns
        if ptypes.is_object_dtype(df[col].dtype)
        and ptypes.infer_dtype(df[col], skipna=True).startswith("mixed")
    ]
    if not mixed:
        return df
    logger.info("Storing mixed-type columns as text: %s", ", ".join(map(str, mixed)))
    safe = df.copy()
    for col in mixed:
        safe[col] = safe[col].map(lambda v: v if pd.isna(v) else str(v))
    return safe


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()
