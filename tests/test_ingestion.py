import io
import socket

import pandas as pd
import pytest
import requests
import sqlalchemy as sa

from data_analyst_agent import ingestion
from data_analyst_agent.exceptions import IngestionError
from tests.helpers import json_response, mock_session, text_response


class TestLoadFile:
    def test_reads_utf8_csv_with_bom(self):
        content = "﻿city,population\nZürich,421878\n".encode()

        df = ingestion.load_file(io.BytesIO(content), "cities.csv")

        assert list(df.columns) == ["city", "population"]
        assert df.loc[0, "city"] == "Zürich"

    def test_falls_back_to_latin1(self):
        content = "city\nMünchen\n".encode("latin-1")

        df = ingestion.load_file(io.BytesIO(content), "cities.csv")

        assert df.loc[0, "city"] == "München"

    def test_reads_excel(self, sales):
        buffer = io.BytesIO()
        sales.to_excel(buffer, index=False)

        df = ingestion.load_file(buffer, "SALES.XLSX")

        assert df.shape == sales.shape

    @pytest.mark.parametrize("name", ["data.json", "data", "data.xls"])
    def test_rejects_unsupported_types(self, name):
        with pytest.raises(IngestionError, match="Unsupported file type"):
            ingestion.load_file(io.BytesIO(b"a,b\n1,2\n"), name)

    @pytest.mark.parametrize("content", [b"", b"a,b\n"])
    def test_rejects_empty_files(self, content):
        with pytest.raises(IngestionError, match="no rows"):
            ingestion.load_file(io.BytesIO(content), "empty.csv")


def fake_dns(address):
    def resolve(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 0))]

    return resolve


class TestLoadFromApi:
    @pytest.fixture(autouse=True)
    def public_dns(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", fake_dns("93.184.216.34"))

    def test_reads_json_list(self):
        session = mock_session(json_response([{"a": 1}, {"a": 2}]))

        df = ingestion.load_from_api("https://api.test/items", session=session)

        assert df["a"].tolist() == [1, 2]

    def test_unwraps_common_envelope_and_flattens_nested_fields(self):
        payload = {"meta": {"page": 1}, "results": [{"id": 1, "geo": {"lat": 1.5}}]}
        session = mock_session(json_response(payload))

        df = ingestion.load_from_api("https://api.test/items", session=session)

        assert list(df.columns) == ["id", "geo.lat"]

    def test_reads_csv_response(self):
        session = mock_session(text_response("a,b\n1,2\n", content_type="text/csv"))

        df = ingestion.load_from_api("https://api.test/export", session=session)

        assert df.to_dict("records") == [{"a": 1, "b": 2}]

    def test_passes_headers(self):
        session = mock_session(json_response([{"a": 1}]))

        ingestion.load_from_api(
            "https://api.test/items", headers={"Authorization": "Bearer t"}, session=session
        )

        assert session.get.call_args.kwargs["headers"] == {"Authorization": "Bearer t"}

    @pytest.mark.parametrize("url", ["file:///etc/passwd", "api.test/items", ""])
    def test_rejects_non_http_urls(self, url):
        with pytest.raises(IngestionError, match="http"):
            ingestion.load_from_api(url)

    @pytest.mark.parametrize(
        "address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"]
    )
    def test_blocks_private_addresses(self, monkeypatch, address):
        monkeypatch.setattr(socket, "getaddrinfo", fake_dns(address))
        session = mock_session(json_response([{"a": 1}]))

        with pytest.raises(IngestionError, match="private or reserved"):
            ingestion.load_from_api("http://internal.test/", session=session)
        session.get.assert_not_called()

    def test_private_addresses_can_be_allowed(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", fake_dns("127.0.0.1"))
        session = mock_session(json_response([{"a": 1}]))

        df = ingestion.load_from_api("http://localhost/", allow_private=True, session=session)

        assert len(df) == 1

    def test_unresolvable_host(self, monkeypatch):
        def fail(*_args, **_kwargs):
            raise socket.gaierror("nope")

        monkeypatch.setattr(socket, "getaddrinfo", fail)

        with pytest.raises(IngestionError, match="Could not resolve"):
            ingestion.load_from_api("https://missing.test/")

    def test_does_not_follow_redirects(self):
        redirect = text_response("", status=302)
        redirect.headers["Location"] = "http://169.254.169.254/latest/meta-data"
        session = mock_session(redirect)

        with pytest.raises(IngestionError, match="redirected"):
            ingestion.load_from_api("https://api.test/items", session=session)
        assert session.get.call_args.kwargs["allow_redirects"] is False

    def test_wraps_http_errors(self):
        session = mock_session(json_response({"error": "nope"}, status=500))

        with pytest.raises(IngestionError, match="failed"):
            ingestion.load_from_api("https://api.test/items", session=session)

    def test_wraps_connection_errors(self):
        session = mock_session(json_response([]))
        session.get.side_effect = requests.ConnectionError("refused")

        with pytest.raises(IngestionError, match="refused"):
            ingestion.load_from_api("https://api.test/items", session=session)

    def test_rejects_non_json_non_csv(self):
        session = mock_session(text_response("<html></html>", content_type="text/html"))

        with pytest.raises(IngestionError, match="neither JSON nor CSV"):
            ingestion.load_from_api("https://api.test/items", session=session)

    def test_rejects_empty_payload(self):
        session = mock_session(json_response({"data": []}))

        with pytest.raises(IngestionError, match="no records"):
            ingestion.load_from_api("https://api.test/items", session=session)


class TestLoadFromDatabase:
    @pytest.fixture
    def sqlite_url(self, tmp_path, sales):
        url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
        engine = sa.create_engine(url)
        sales.to_sql("orders", engine, index=False)
        engine.dispose()
        return url

    def test_reads_table(self, sqlite_url, sales):
        df = ingestion.load_from_database(sqlite_url, "orders")

        pd.testing.assert_frame_equal(df, sales)

    def test_missing_table(self, sqlite_url):
        with pytest.raises(IngestionError, match="not found"):
            ingestion.load_from_database(sqlite_url, "nope")

    def test_table_name_is_not_interpolated_into_sql(self, sqlite_url):
        with pytest.raises(IngestionError, match="not found"):
            ingestion.load_from_database(sqlite_url, "orders; DROP TABLE orders")
        assert len(ingestion.load_from_database(sqlite_url, "orders")) == 5

    def test_missing_driver_suggests_extra(self, monkeypatch):
        def missing_driver(*_args, **_kwargs):
            raise ModuleNotFoundError("No module named 'psycopg'", name="psycopg")

        monkeypatch.setattr(sa, "create_engine", missing_driver)

        with pytest.raises(IngestionError, match=r"\.\[postgres\]"):
            ingestion.load_from_database("postgresql+psycopg://u@h/db", "t")

    def test_invalid_url(self):
        with pytest.raises(IngestionError, match="Invalid connection URL"):
            ingestion.load_from_database("not a url", "t")

    def test_requires_table_name(self):
        with pytest.raises(IngestionError, match="table name"):
            ingestion.load_from_database("sqlite://", "  ")
