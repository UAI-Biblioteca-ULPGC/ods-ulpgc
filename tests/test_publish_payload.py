"""Regression tests for Apps Script publish payload handling."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from institutional_pipeline import publish_payload as publish_module


class FakeResponse:
    """Minimal HTTP response stub for webhook tests."""

    def __init__(
        self,
        *,
        ok: bool,
        status_code: int,
        json_data: dict[str, Any] | None = None,
        text: str = "",
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self) -> dict[str, Any]:
        if self._json_data is None:
            raise ValueError("invalid json")
        return self._json_data


def _configure_publish_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> dict[str, Path]:
    """Point publish module paths to temporary test files."""
    processed_latest = tmp_path / "processed" / "latest"
    logs_dir = tmp_path / "logs"
    manifests_dir = tmp_path / "manifests"
    processed_latest.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    manifests_dir.mkdir(parents=True)

    publications = processed_latest / "publications_latest.csv"
    sdg = processed_latest / "sdg_exploded_latest.csv"
    kpis = processed_latest / "kpis_yearly_latest.csv"
    log_path = logs_dir / "refresh_log.csv"
    metadata_path = manifests_dir / "latest_snapshot_metadata.json"

    monkeypatch.setattr(publish_module, "PROCESSED_LATEST_PUBLICATIONS", publications)
    monkeypatch.setattr(publish_module, "PROCESSED_LATEST_SDG", sdg)
    monkeypatch.setattr(publish_module, "PROCESSED_LATEST_KPIS", kpis)
    monkeypatch.setattr(publish_module, "LOG_PATH", log_path)
    monkeypatch.setattr(publish_module, "METADATA_PATH", metadata_path)
    monkeypatch.setattr(
        publish_module,
        "PUBLISHABLE_PATHS",
        {
            "publications_csv_base64": publications,
            "sdg_exploded_csv_base64": sdg,
            "kpis_yearly_csv_base64": kpis,
            "refresh_log_csv_base64": log_path,
            "metadata_json_base64": metadata_path,
        },
    )
    return {
        "publications": publications,
        "sdg": sdg,
        "kpis": kpis,
        "log": log_path,
        "metadata": metadata_path,
    }


def test_extract_snapshot_metadata_supports_nested_and_flat_formats() -> None:
    """Metadata extraction should work for current and legacy shapes."""
    nested = publish_module.extract_snapshot_metadata(
        {
            "latest_snapshot": {
                "snapshot_date": "2026-01-01",
                "snapshot_label": "20260101T000000Z",
                "analysis_start_year": 2021,
                "analysis_end_year": 2025,
            }
        }
    )
    flat = publish_module.extract_snapshot_metadata(
        {
            "snapshot_date": "2026-01-01",
            "snapshot_label": "20260101T000000Z",
            "analysis_start_year": 2021,
            "analysis_end_year": 2025,
        }
    )

    assert nested["snapshot_label"] == "20260101T000000Z"
    assert flat["analysis_end_year"] == 2025


def test_build_payload_requires_environment_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Publishing should fail fast when webhook secrets are missing."""
    monkeypatch.delenv("APPS_SCRIPT_WEBAPP_URL", raising=False)
    monkeypatch.delenv("APPS_SCRIPT_SHARED_SECRET", raising=False)

    with pytest.raises(EnvironmentError, match="Missing required environment variables"):
        publish_module.validate_environment()


def test_build_payload_reads_files_and_encodes_expected_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Payload builder should encode all publishable files and metadata."""
    paths = _configure_publish_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("APPS_SCRIPT_WEBAPP_URL", "https://example.org/webhook")
    monkeypatch.setenv("APPS_SCRIPT_SHARED_SECRET", "shared-secret")
    monkeypatch.setenv("APPS_SCRIPT_MAX_FILE_BYTES", "1024")

    paths["publications"].write_text("id,title\n1,Example\n", encoding="utf-8")
    paths["sdg"].write_text("work_id,sdg_code\n1,3\n", encoding="utf-8")
    paths["kpis"].write_text("publication_year,total_publications\n2025,1\n", encoding="utf-8")
    paths["log"].write_text("snapshot_label,status\n20250101T000000Z,success\n", encoding="utf-8")
    metadata = {
        "latest_snapshot": {
            "snapshot_date": "2025-01-01",
            "snapshot_label": "20250101T000000Z",
            "analysis_start_year": 2021,
            "analysis_end_year": 2025,
        }
    }
    paths["metadata"].write_text(json.dumps(metadata), encoding="utf-8")

    payload = publish_module.build_payload()

    assert payload["secret"] == "shared-secret"
    assert payload["snapshot_label"] == "20250101T000000Z"
    assert payload["analysis_end_year"] == 2025
    assert (
        base64.b64decode(payload["publications_csv_base64"])
        .decode("utf-8")
        .replace("\r\n", "\n")
        == "id,title\n1,Example\n"
    )
    decoded_metadata = json.loads(
        base64.b64decode(payload["metadata_json_base64"]).decode("utf-8")
    )
    assert decoded_metadata == metadata


def test_validate_publishable_sizes_raises_for_oversized_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Oversized files should fail before making the webhook request."""
    paths = _configure_publish_paths(monkeypatch, tmp_path)
    for path in paths.values():
        path.write_text("0123456789", encoding="utf-8")

    monkeypatch.setenv("APPS_SCRIPT_MAX_FILE_BYTES", "5")

    with pytest.raises(ValueError, match="exceed the Apps Script publish threshold"):
        publish_module.validate_publishable_sizes()


def test_publish_payload_posts_json_and_requires_ok_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Webhook client should POST the payload and validate the response body."""
    monkeypatch.setenv("APPS_SCRIPT_WEBAPP_URL", "https://example.org/webhook")
    captured: dict[str, Any] = {}

    def fake_post(url: str, json: dict[str, Any], timeout: int) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse(ok=True, status_code=200, json_data={"status": "ok"})

    monkeypatch.setattr(publish_module.requests, "post", fake_post)

    payload = {"snapshot_label": "20250101T000000Z"}
    publish_module.publish_payload(payload)

    assert captured == {
        "url": "https://example.org/webhook",
        "json": payload,
        "timeout": 180,
    }
