"""Regression tests for snapshot persistence helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import shutil
import tempfile

import pandas as pd
import pytest

from institutional_pipeline import snapshot_manager
from institutional_pipeline.institution_settings import InstitutionSettings


def _build_test_settings() -> InstitutionSettings:
    """Return a deterministic settings object for snapshot tests."""
    return InstitutionSettings(
        project_slug="demo-project",
        institution_name="Demo University",
        openalex_institution_id="I123",
        institution_ror="https://ror.org/12345",
        document_types=("article", "review"),
        spreadsheet_name="demo_sheet",
        worksheets=("publications", "sdg_exploded", "kpis_yearly", "refresh_log"),
        window_years=5,
        end_year_offset=1,
        schedule_months=(1, 7),
        schedule_day=1,
    )


def _configure_snapshot_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> dict[str, Path]:
    """Point snapshot manager outputs to temporary files."""
    raw_latest = tmp_path / "raw" / "latest" / "openalex_works_latest.json"
    raw_archive_dir = tmp_path / "raw" / "archive"
    processed_latest_dir = tmp_path / "processed" / "latest"
    processed_archive_dir = tmp_path / "processed" / "archive"
    logs_dir = tmp_path / "logs"
    manifests_dir = tmp_path / "manifests"

    raw_latest.parent.mkdir(parents=True)
    raw_archive_dir.mkdir(parents=True)
    processed_latest_dir.mkdir(parents=True)
    processed_archive_dir.mkdir(parents=True)
    logs_dir.mkdir(parents=True)
    manifests_dir.mkdir(parents=True)

    monkeypatch.setattr(snapshot_manager, "RAW_LATEST_PATH", raw_latest)
    monkeypatch.setattr(
        snapshot_manager,
        "PROCESSED_LATEST_PUBLICATIONS",
        processed_latest_dir / "publications_latest.csv",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "PROCESSED_LATEST_SDG",
        processed_latest_dir / "sdg_exploded_latest.csv",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "PROCESSED_LATEST_KPIS",
        processed_latest_dir / "kpis_yearly_latest.csv",
    )
    monkeypatch.setattr(snapshot_manager, "REFRESH_LOG_PATH", logs_dir / "refresh_log.csv")
    monkeypatch.setattr(
        snapshot_manager,
        "METADATA_PATH",
        manifests_dir / "latest_snapshot_metadata.json",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "build_raw_archive_path",
        lambda snapshot_label: raw_archive_dir / f"openalex_works_{snapshot_label}.json",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "build_processed_archive_publications_path",
        lambda snapshot_label: processed_archive_dir / f"publications_{snapshot_label}.csv",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "build_processed_archive_sdg_path",
        lambda snapshot_label: processed_archive_dir / f"sdg_exploded_{snapshot_label}.csv",
    )
    monkeypatch.setattr(
        snapshot_manager,
        "build_processed_archive_kpis_path",
        lambda snapshot_label: processed_archive_dir / f"kpis_yearly_{snapshot_label}.csv",
    )
    return {
        "raw_latest": raw_latest,
        "refresh_log": snapshot_manager.REFRESH_LOG_PATH,
        "metadata": snapshot_manager.METADATA_PATH,
    }


def test_snapshot_outputs_and_refresh_log_are_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Snapshot helpers should persist raw data, CSVs, metadata, and the refresh log."""
    temp_dir = Path(tempfile.mkdtemp(dir=".", prefix="test-snapshot-"))
    try:
        paths = _configure_snapshot_paths(monkeypatch, temp_dir)
        raw_works = [{"id": "W1", "display_name": "Example"}]
        snapshot_label = "20260101T000000Z"

        latest_raw_path, archive_raw_path = snapshot_manager.write_raw_outputs(
            raw_works=raw_works,
            snapshot_label=snapshot_label,
        )
        publications_df = pd.DataFrame([{"work_id": "W1", "title": "Example"}])
        sdg_df = pd.DataFrame([{"work_id": "W1", "sdg_code": "3"}])
        kpis_df = pd.DataFrame([{"publication_year": 2025, "total_publications": 1}])

        written_paths = snapshot_manager.write_processed_outputs(
            publications_df=publications_df,
            sdg_exploded_df=sdg_df,
            kpis_yearly_df=kpis_df,
            snapshot_label=snapshot_label,
        )
        metadata = snapshot_manager.build_snapshot_metadata(
            settings=_build_test_settings(),
            snapshot_date=date(2026, 1, 1),
            snapshot_label=snapshot_label,
            analysis_start_year=2021,
            analysis_end_year=2025,
            raw_record_count=1,
            publications_row_count=1,
            sdg_exploded_row_count=1,
            kpis_yearly_row_count=1,
            status="success",
        )
        metadata_path = snapshot_manager.write_metadata(metadata)
        refresh_log_path = snapshot_manager.append_refresh_log(metadata)

        assert latest_raw_path.exists()
        assert archive_raw_path.exists()
        assert written_paths["latest_publications"].exists()
        assert written_paths["archive_publications"].exists()
        assert metadata_path == paths["metadata"]
        assert refresh_log_path == paths["refresh_log"]

        persisted_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert persisted_metadata["latest_snapshot"]["snapshot_label"] == snapshot_label
        assert persisted_metadata["raw_artifact"]["file_name"] == "openalex_demo-project_20260101T000000Z.json.gz"
        assert persisted_metadata["raw_artifact"]["source_file_bytes"] is not None
        assert persisted_metadata["institution_openalex_id"] == "I123"
        assert persisted_metadata["institution_ror"] == "12345"
        assert persisted_metadata["document_types"] == ["article", "review"]
        assert persisted_metadata["analysis"] == {"window_years": 5, "end_year_offset": 1}
        assert persisted_metadata["update_schedule"] == {
            "frequency": "semiannual",
            "months": ["01", "07"],
            "day": 1,
        }

        refresh_log_df = pd.read_csv(refresh_log_path)
        assert refresh_log_df.columns.tolist() == snapshot_manager.REFRESH_LOG_COLUMNS
        assert refresh_log_df["snapshot_label"].tolist() == [snapshot_label]
        assert refresh_log_df["status"].tolist() == ["success"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_append_refresh_log_normalizes_legacy_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing refresh logs should be normalized to the stable schema on append."""
    temp_dir = Path(tempfile.mkdtemp(dir=".", prefix="test-snapshot-"))
    try:
        paths = _configure_snapshot_paths(monkeypatch, temp_dir)
        pd.DataFrame(
            [
                {
                    "snapshot_date": "2026-01-01",
                    "snapshot_label": "20260101",
                    "analysis_start_year": 2021,
                    "analysis_end_year": 2025,
                    "raw_record_count": 10,
                    "publications_row_count": 10,
                    "sdg_exploded_row_count": 4,
                    "kpis_yearly_row_count": 5,
                    "status": "success",
                    "generated_at_utc": "2026-01-01T00:00:00+00:00",
                }
            ]
        ).to_csv(paths["refresh_log"], index=False)

        metadata = {
            "latest_snapshot": {
                "snapshot_date": "2026-07-01",
                "snapshot_label": "20260701T000000Z",
                "analysis_start_year": 2022,
                "analysis_end_year": 2026,
                "raw_record_count": 12,
                "publications_row_count": 12,
                "sdg_exploded_row_count": 5,
                "kpis_yearly_row_count": 5,
                "status": "success",
                "run_timestamp_utc": "2026-07-01T00:00:01+00:00",
            }
        }

        snapshot_manager.append_refresh_log(metadata)

        refresh_log_df = pd.read_csv(paths["refresh_log"])
        assert refresh_log_df.columns.tolist() == snapshot_manager.REFRESH_LOG_COLUMNS
        assert refresh_log_df["snapshot_label"].tolist() == ["20260101", "20260701T000000Z"]
        assert pd.isna(refresh_log_df.iloc[0]["run_timestamp_utc"])
        assert refresh_log_df.iloc[1]["run_timestamp_utc"] == "2026-07-01T00:00:01+00:00"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
