"""Regression tests for the OpenAlex client."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
import requests

from institutional_pipeline import openalex_client


class FakeResponse:
    """Minimal HTTP response stub for retry tests."""

    def __init__(
        self,
        *,
        status_code: int,
        json_data: dict[str, Any] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.text = text
        self.headers = headers or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict[str, Any]:
        if self._json_data is None:
            raise ValueError("invalid json")
        return self._json_data


def test_build_request_params_normalizes_institution_and_includes_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Request params should follow the OpenAlex API contract."""
    monkeypatch.setenv("OPENALEX_API_KEY", "secret-key")

    params = openalex_client._build_request_params(
        institution_id="I123",
        institution_ror=None,
        start_year=2020,
        end_year=2024,
        per_page=50,
        cursor="*",
    )

    assert params["filter"] == (
        "institutions.id:https://openalex.org/I123,publication_year:2020-2024"
    )
    assert "publication_date" not in params["select"]
    assert "open_access" in params["select"]
    assert "countries_distinct_count" in params["select"]
    assert "institutions_distinct_count" in params["select"]
    assert "fwci" in params["select"]
    assert "citation_normalized_percentile" in params["select"]
    assert params["per_page"] == 50
    assert params["cursor"] == "*"
    assert params["api_key"] == "secret-key"


def test_build_request_params_supports_ror_and_document_type_filters() -> None:
    """Request params should support institution ROR and OR-filtered work types."""
    params = openalex_client._build_request_params(
        institution_id=None,
        institution_ror="01abcde12",
        start_year=2020,
        end_year=2024,
        per_page=50,
        cursor="*",
        document_types=["article", "review"],
    )

    assert params["filter"] == (
        "institutions.ror:https://ror.org/01abcde12,"
        "publication_year:2020-2024,type:article|review"
    )


def test_request_with_retry_retries_after_temporary_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Temporary 429 responses should retry and eventually return JSON."""

    class FakeSession:
        def __init__(self) -> None:
            self.calls = 0

        def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
            self.calls += 1
            if self.calls == 1:
                return FakeResponse(
                    status_code=429,
                    text="rate limited",
                    headers={"Retry-After": "0"},
                )
            return FakeResponse(
                status_code=200,
                json_data={"results": [], "meta": {"next_cursor": None}},
            )

    sleeps: list[float] = []
    monkeypatch.setattr(openalex_client.time, "sleep", sleeps.append)

    session = FakeSession()
    payload = openalex_client._request_with_retry(session, "https://example.org", {})

    assert payload == {"results": [], "meta": {"next_cursor": None}}
    assert session.calls == 2
    assert sleeps == [0.0]


def test_request_with_retry_raises_after_network_retries_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated network failures should raise a deterministic runtime error."""

    class FakeSession:
        def get(self, url: str, params: dict[str, Any], timeout: int) -> FakeResponse:
            raise requests.RequestException("boom")

    monkeypatch.setattr(openalex_client.time, "sleep", lambda seconds: None)

    with pytest.raises(RuntimeError, match="network error"):
        openalex_client._request_with_retry(FakeSession(), "https://example.org", {})


def test_fetch_works_validates_input_arguments() -> None:
    """Invalid year ranges and page sizes should fail fast."""
    current_year = datetime.now().year

    with pytest.raises(ValueError, match="must be between 1900"):
        openalex_client.fetch_works("I123", 1899, 1900)

    with pytest.raises(ValueError, match="must be between 1900"):
        openalex_client.fetch_works("I123", 2020, current_year + 1)

    with pytest.raises(ValueError, match="less than or equal to"):
        openalex_client.fetch_works("I123", 2024, 2023)

    with pytest.raises(ValueError, match="non-empty string"):
        openalex_client.fetch_works("   ", 2020, 2021)

    with pytest.raises(ValueError, match="between 1 and"):
        openalex_client.fetch_works("I123", 2020, 2021, per_page=0)


def test_fetch_works_paginates_until_next_cursor_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paginator should keep requesting pages until OpenAlex closes the cursor."""
    session = object()
    seen_cursors: list[str] = []
    payloads = [
        {
            "results": [{"id": "W1"}, "ignore-me"],
            "meta": {"next_cursor": "page-2"},
        },
        {
            "results": [{"id": "W2"}],
            "meta": {"next_cursor": None},
        },
    ]

    monkeypatch.setattr(openalex_client, "_build_session", lambda: session)

    def fake_request_with_retry(
        current_session: object,
        url: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        assert current_session is session
        seen_cursors.append(params["cursor"])
        return payloads[len(seen_cursors) - 1]

    monkeypatch.setattr(
        openalex_client,
        "_request_with_retry",
        fake_request_with_retry,
    )

    works = openalex_client.fetch_works("I123", 2020, 2021, per_page=25)

    assert works == [{"id": "W1"}, {"id": "W2"}]
    assert seen_cursors == ["*", "page-2"]
