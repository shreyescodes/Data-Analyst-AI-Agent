"""Lightweight column classification shared by query generation and charting."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
from pandas.api import types as ptypes


class ColumnKind(StrEnum):
    NUMERIC = "numeric"
    DATETIME = "datetime"
    BOOLEAN = "boolean"
    TEXT = "text"


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    kind: ColumnKind
    dtype: str


@dataclass(frozen=True, slots=True)
class Schema:
    columns: tuple[Column, ...]

    @classmethod
    def from_frame(cls, df: pd.DataFrame) -> Schema:
        return cls(
            tuple(Column(str(name), classify(df[name]), str(df[name].dtype)) for name in df.columns)
        )

    def names(self, kind: ColumnKind | None = None) -> list[str]:
        return [c.name for c in self.columns if kind is None or c.kind is kind]

    @property
    def numeric(self) -> list[str]:
        return self.names(ColumnKind.NUMERIC)

    @property
    def text(self) -> list[str]:
        return self.names(ColumnKind.TEXT)

    @property
    def datetime(self) -> list[str]:
        return self.names(ColumnKind.DATETIME)

    def mentioned_in(self, question: str, candidates: list[str]) -> list[str]:
        """Return ``candidates`` mentioned in ``question``, in the order mentioned.

        Matching ignores case and treats underscores as spaces. A column also
        matches when every word longer than two letters in its name appears
        in the question (allowing a plural "s" or "es"), so ``body_mass_g`` matches
        "average body mass" and ``region`` matches "sales across regions".
        Exact matches win ties.
        """
        words = normalise_text(question).split()
        hits: list[tuple[int, int, str]] = []
        for name in candidates:
            tokens = normalise_text(name).split()
            exact = _find_phrase(words, tokens)
            if exact is not None:
                hits.append((exact, 0, name))
                continue
            significant = [t for t in tokens if len(t) > 2]
            positions = [_find_word(words, t) for t in significant]
            if significant and all(p is not None for p in positions):
                hits.append((min(p for p in positions if p is not None), 1, name))
        return [name for *_, name in sorted(hits)]


def classify(series: pd.Series) -> ColumnKind:
    dtype = series.dtype
    if ptypes.is_bool_dtype(dtype):
        return ColumnKind.BOOLEAN
    if ptypes.is_numeric_dtype(dtype):
        return ColumnKind.NUMERIC
    if ptypes.is_datetime64_any_dtype(dtype):
        return ColumnKind.DATETIME
    return ColumnKind.TEXT


def is_text_dtype(series: pd.Series) -> bool:
    """True for free-form string columns (object or pandas string dtype)."""
    return ptypes.is_object_dtype(series.dtype) or isinstance(series.dtype, pd.StringDtype)


def normalise_text(value: str) -> str:
    """Lower-case, turn underscores and punctuation into spaces, collapse runs."""
    return re.sub(r"[\W_]+", " ", value.lower()).strip()


def _find_phrase(words: list[str], phrase: list[str]) -> int | None:
    size = len(phrase)
    for i in range(len(words) - size + 1):
        if words[i : i + size] == phrase:
            return i
    return None


def _find_word(words: list[str], token: str) -> int | None:
    for i, word in enumerate(words):
        if word in (token, f"{token}s", f"{token}es"):
            return i
    return None
