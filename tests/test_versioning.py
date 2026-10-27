import pandas as pd
import pytest

from data_analyst_agent.exceptions import VersioningError
from data_analyst_agent.versioning import VersionStore


@pytest.fixture
def store(tmp_path):
    return VersionStore(tmp_path / "versions")


def test_round_trip_preserves_types(store, sales):
    version = store.save(sales, "  first  ")

    loaded = store.load(version.version_id)

    pd.testing.assert_frame_equal(loaded, sales)
    assert version.message == "first"
    assert (version.n_rows, version.n_columns) == (5, 4)


def test_history_is_newest_first_and_ids_are_unique(store, sales):
    ids = [store.save(sales, str(i)).version_id for i in range(3)]

    history = store.history()

    assert len(set(ids)) == 3  # several saves within one second must not collide
    assert [v.message for v in history] == ["2", "1", "0"]


def test_history_of_missing_directory(tmp_path):
    assert VersionStore(tmp_path / "absent").history() == []


def test_history_skips_corrupt_metadata(store, sales):
    store.save(sales)
    broken = store.root / "20240101T000000Z-abcdef"
    broken.mkdir()
    (broken / "metadata.json").write_text("{not json", encoding="utf-8")

    assert len(store.history()) == 1


def test_detects_tampering(store, sales):
    version = store.save(sales)
    (store.root / version.version_id / "data.parquet").write_bytes(b"tampered")

    with pytest.raises(VersioningError, match="integrity"):
        store.load(version.version_id)


@pytest.mark.parametrize("version_id", ["../../etc", "", "20240101T000000Z-zzzzzz"])
def test_rejects_invalid_ids(store, version_id):
    with pytest.raises(VersioningError, match="Invalid version id"):
        store.load(version_id)


def test_unknown_version(store):
    with pytest.raises(VersioningError, match="does not exist"):
        store.load("20240101T000000Z-abcdef")


def test_mixed_type_columns_are_saved_as_text(store):
    df = pd.DataFrame({"mixed": ["a", 1, None]})

    loaded = store.load(store.save(df).version_id)

    assert loaded["mixed"].tolist() == ["a", "1", None]
