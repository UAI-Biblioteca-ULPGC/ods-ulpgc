"""OpenAlex API client for harvesting institutional publication records."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)

OPENALEX_BASE_URL = "https://api.openalex.org"
WORKS_ENDPOINT = f"{OPENALEX_BASE_URL}/works"
DEFAULT_PER_PAGE = 100
DEFAULT_TIMEOUT_SECONDS = 45
MAX_RETRIES = 5
BACKOFF_BASE_SECONDS = 2.0
MAX_PER_PAGE = 100


def _normalize_institution_id(institution_id: str) -> str:
    """Normalize institution identifier to OpenAlex URI format."""
    clean_institution_id = institution_id.strip()
    if clean_institution_id.startswith("https://openalex.org/"):
        return clean_institution_id
    return f"https://openalex.org/{clean_institution_id}"


def _normalize_ror(ror: str) -> str:
    """Normalize ROR identifier to the canonical URI format."""
    clean_ror = ror.strip()
    if clean_ror.startswith("https://ror.org/"):
        return clean_ror
    return f"https://ror.org/{clean_ror.lstrip('/')}"


def _build_document_type_filter(document_types: tuple[str, ...] | list[str] | None) -> str:
    """Build the OpenAlex type filter clause when types are configured."""
    if not document_types:
        return ""

    normalized_types = [document_type.strip() for document_type in document_types if document_type.strip()]
    if not normalized_types:
        return ""
    return f",type:{'|'.join(normalized_types)}"


def _build_institution_filter(
    *,
    institution_id: str | None = None,
    institution_ror: str | None = None,
) -> str:
    """Build the institution filter clause using OpenAlex ID or ROR."""
    if institution_id and institution_id.strip():
        return f"institutions.id:{_normalize_institution_id(institution_id)}"
    if institution_ror and institution_ror.strip():
        return f"institutions.ror:{_normalize_ror(institution_ror)}"
    raise ValueError("Either institution_id or institution_ror must be provided.")


def _build_user_agent() -> str:
    """Build a polite user agent for OpenAlex requests."""
    return "institutional-openalex-etl/0.1"


def _build_session() -> requests.Session:
    """Create a configured requests session for OpenAlex."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": _build_user_agent(),
            "Accept": "application/json",
        }
    )

    return session


def _build_request_params(
    institution_id: str | None,
    institution_ror: str | None,
    start_year: int,
    end_year: int,
    per_page: int,
    cursor: str,
    document_types: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """Build OpenAlex request parameters according to API contract."""
    params: dict[str, Any] = {
        "filter": (
            f"{_build_institution_filter(institution_id=institution_id, institution_ror=institution_ror)},"
            f"publication_year:{start_year}-{end_year}"
            f"{_build_document_type_filter(document_types)}"
        ),
        "select": (
            "id,doi,display_name,publication_year,"
            "primary_location,type,cited_by_count,open_access,"
            "primary_topic,sustainable_development_goals,"
            "countries_distinct_count,institutions_distinct_count,"
            "fwci,citation_normalized_percentile"
        ),
        "per_page": per_page,
        "cursor": cursor,
    }
    api_key = os.getenv("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def _request_with_retry(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Execute an HTTP GET request with retries and backoff.

    Handles transient errors including network failures,
    HTTP 429, and 5xx responses.
    """
    attempt = 0
    while True:
        try:
            response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            if attempt >= MAX_RETRIES:
                raise RuntimeError(
                    "OpenAlex request failed after retries due to network error."
                ) from exc
            sleep_seconds = BACKOFF_BASE_SECONDS**attempt
            LOGGER.warning(
                "OpenAlex network error on attempt %s/%s. Retrying in %.1f seconds.",
                attempt + 1,
                MAX_RETRIES + 1,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            attempt += 1
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt >= MAX_RETRIES:
                raise RuntimeError(
                    "OpenAlex request failed after retries with status "
                    f"{response.status_code}: {response.text}"
                )
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                sleep_seconds = float(retry_after)
            else:
                sleep_seconds = BACKOFF_BASE_SECONDS**attempt
            LOGGER.warning(
                (
                    "OpenAlex temporary HTTP %s on attempt %s/%s. "
                    "Retrying in %.1f seconds."
                ),
                response.status_code,
                attempt + 1,
                MAX_RETRIES + 1,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            attempt += 1
            continue

        if not response.ok:
            raise RuntimeError(
                "OpenAlex request failed with non-retryable status "
                f"{response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError("OpenAlex response was not valid JSON.") from exc


def fetch_works(
    institution_id: str | None,
    start_year: int,
    end_year: int,
    per_page: int = DEFAULT_PER_PAGE,
    *,
    institution_ror: str | None = None,
    document_types: tuple[str, ...] | list[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch OpenAlex works for an institution and year window.

    Args:
        institution_id: OpenAlex institution ID or URI.
        start_year: Start year (inclusive).
        end_year: End year (inclusive).
        per_page: Number of records per page.
        institution_ror: Optional ROR identifier used when OpenAlex ID is absent.
        document_types: Optional OpenAlex work types to include.

    Returns:
        List of OpenAlex work dictionaries.
    """
    current_year = datetime.now().year

    if not isinstance(start_year, int) or not isinstance(end_year, int):
        raise TypeError("start_year and end_year must be integers.")
    if start_year < 1900 or end_year > current_year:
        raise ValueError(
            (
                "Year range must be between 1900 and "
                f"{current_year}: {start_year}-{end_year}."
            )
        )
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")
    if not (institution_id and institution_id.strip()) and not (
        institution_ror and institution_ror.strip()
    ):
        raise ValueError("institution_id or institution_ror must be a non-empty string.")
    if per_page < 1 or per_page > MAX_PER_PAGE:
        raise ValueError(f"per_page must be between 1 and {MAX_PER_PAGE}.")

    session = _build_session()
    works: list[dict[str, Any]] = []
    cursor = "*"
    page_number = 0
    using_api_key = bool(os.getenv("OPENALEX_API_KEY"))

    LOGGER.info(
        "Starting OpenAlex fetch for institution %s (%s-%s), per_page=%s, api_key=%s.",
        institution_id,
        start_year,
        end_year,
        per_page,
        "enabled" if using_api_key else "disabled",
    )

    while cursor:
        page_number += 1
        params = _build_request_params(
            institution_id=institution_id,
            institution_ror=institution_ror,
            start_year=start_year,
            end_year=end_year,
            per_page=per_page,
            cursor=cursor,
            document_types=document_types,
        )

        payload = _request_with_retry(session, WORKS_ENDPOINT, params)
        page_results = payload.get("results", [])
        if not isinstance(page_results, list):
            raise RuntimeError("OpenAlex response 'results' field is not a list.")

        valid_page_results = [item for item in page_results if isinstance(item, dict)]
        works.extend(valid_page_results)

        meta = payload.get("meta", {})
        if not isinstance(meta, dict):
            LOGGER.info(
                "OpenAlex page %s returned %s valid works; missing meta prevented further pagination.",
                page_number,
                len(valid_page_results),
            )
            break
        next_cursor = meta.get("next_cursor")
        LOGGER.info(
            "OpenAlex page %s fetched %s valid works (total=%s); next_cursor=%s.",
            page_number,
            len(valid_page_results),
            len(works),
            next_cursor if isinstance(next_cursor, str) and next_cursor else "<end>",
        )
        cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else ""

    LOGGER.info(
        "Fetched %s OpenAlex works for institution %s (%s-%s) across %s page(s).",
        len(works),
        institution_id,
        start_year,
        end_year,
        page_number,
    )
    return works
