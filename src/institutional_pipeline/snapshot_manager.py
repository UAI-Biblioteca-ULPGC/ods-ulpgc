"""Snapshot persistence and traceability helpers for the institutional pipeline."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from institutional_pipeline.config import (
    METADATA_PATH,
    PROCESSED_LATEST_KPIS,
    PROCESSED_LATEST_PUBLICATIONS,
    PROCESSED_LATEST_SDG,
    RAW_LATEST_PATH,
    REFRESH_LOG_PATH,
    build_processed_archive_kpis_path,
    build_processed_archive_publications_path,
    build_processed_archive_sdg_path,
    build_raw_archive_path,
)
from institutional_pipeline.institution_settings import InstitutionSettings

DATA_SOURCE = "OpenAlex"
REFRESH_LOG_COLUMNS = [
    "run_timestamp_utc",
    "snapshot_date",
    "snapshot_label",
    "analysis_start_year",
    "analysis_end_year",
    "raw_record_count",
    "publications_row_count",
    "sdg_exploded_row_count",
    "kpis_yearly_row_count",
    "status",
]


def _describe_schedule_frequency(months: tuple[int, ...]) -> str:
    """Return a compact label for the configured schedule frequency."""
    month_count = len(months)
    if month_count == 1:
        return "annual"
    if month_count == 2:
        return "semiannual"
    if month_count == 4:
        return "quarterly"
    if month_count == 12:
        return "monthly"
    return "custom"


def _build_short_identifier(identifier: str | None) -> str | None:
    """Build a short identifier token from a URI or short format."""
    if not identifier:
        return None
    return identifier.rsplit("/", maxsplit=1)[-1]


def _write_json(path: Path, payload: dict[str, Any] | list[dict[str, Any]]) -> None:
    """Write JSON with UTF-8 encoding and pretty formatting."""
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)


def write_raw_outputs(
    raw_works: list[dict[str, Any]],
    snapshot_label: str,
) -> tuple[Path, Path]:
    """Write latest and archived raw OpenAlex JSON outputs."""
    archive_path = build_raw_archive_path(snapshot_label)
    _write_json(RAW_LATEST_PATH, raw_works)
    _write_json(archive_path, raw_works)
    return RAW_LATEST_PATH, archive_path


def write_processed_outputs(
    publications_df: pd.DataFrame,
    sdg_exploded_df: pd.DataFrame,
    kpis_yearly_df: pd.DataFrame,
    snapshot_label: str,
) -> dict[str, Path]:
    """Write latest and archived processed CSV outputs."""
    archives = {
        "publications": build_processed_archive_publications_path(snapshot_label),
        "sdg_exploded": build_processed_archive_sdg_path(snapshot_label),
        "kpis_yearly": build_processed_archive_kpis_path(snapshot_label),
    }

    publications_df.to_csv(PROCESSED_LATEST_PUBLICATIONS, index=False)
    sdg_exploded_df.to_csv(PROCESSED_LATEST_SDG, index=False)
    kpis_yearly_df.to_csv(PROCESSED_LATEST_KPIS, index=False)

    publications_df.to_csv(archives["publications"], index=False)
    sdg_exploded_df.to_csv(archives["sdg_exploded"], index=False)
    kpis_yearly_df.to_csv(archives["kpis_yearly"], index=False)

    return {
        "latest_publications": PROCESSED_LATEST_PUBLICATIONS,
        "latest_sdg_exploded": PROCESSED_LATEST_SDG,
        "latest_kpis_yearly": PROCESSED_LATEST_KPIS,
        "archive_publications": archives["publications"],
        "archive_sdg_exploded": archives["sdg_exploded"],
        "archive_kpis_yearly": archives["kpis_yearly"],
    }


def build_snapshot_metadata(
    *,
    settings: InstitutionSettings,
    snapshot_date: date,
    snapshot_label: str,
    analysis_start_year: int,
    analysis_end_year: int,
    raw_record_count: int,
    publications_row_count: int,
    sdg_exploded_row_count: int,
    kpis_yearly_row_count: int,
    status: str,
) -> dict[str, Any]:
    """Build deterministic metadata payload for the latest snapshot."""
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    institution_openalex_id = _build_short_identifier(settings.openalex_institution_id)
    institution_ror = _build_short_identifier(settings.institution_ror)
    raw_latest_path = RAW_LATEST_PATH
    raw_archive_path = build_raw_archive_path(snapshot_label)
    latest_snapshot = {
        "snapshot_date": snapshot_date.isoformat(),
        "snapshot_label": snapshot_label,
        "analysis_start_year": analysis_start_year,
        "analysis_end_year": analysis_end_year,
        "raw_record_count": raw_record_count,
        "publications_row_count": publications_row_count,
        "sdg_exploded_row_count": sdg_exploded_row_count,
        "kpis_yearly_row_count": kpis_yearly_row_count,
        "raw_file_latest": str(raw_latest_path),
        "raw_file_archive": str(raw_archive_path),
        "processed_files_latest": [
            str(PROCESSED_LATEST_PUBLICATIONS),
            str(PROCESSED_LATEST_SDG),
            str(PROCESSED_LATEST_KPIS),
        ],
        "processed_files_archive": [
            str(build_processed_archive_publications_path(snapshot_label)),
            str(build_processed_archive_sdg_path(snapshot_label)),
            str(build_processed_archive_kpis_path(snapshot_label)),
        ],
        "records_retrieved": raw_record_count,
        "records_publications": publications_row_count,
        "records_sdg_exploded": sdg_exploded_row_count,
        "records_kpis_yearly": kpis_yearly_row_count,
        "status": status,
        "generated_at_utc": generated_at,
        "run_timestamp_utc": generated_at,
    }
    raw_artifact = {
        "storage": "github_actions_artifact",
        "file_name": f"openalex_{settings.project_slug}_{snapshot_label}.json.gz",
        "compression": "gzip",
        "source_file_bytes": raw_latest_path.stat().st_size if raw_latest_path.exists() else None,
    }

    return {
        "project": settings.project_slug,
        "institution_name": settings.institution_name,
        "institution_openalex_id": institution_openalex_id,
        "institution_ror": institution_ror,
        "data_source": DATA_SOURCE,
        "spreadsheet_name": settings.spreadsheet_name,
        "worksheets": list(settings.worksheets),
        "document_types": list(settings.document_types),
        "analysis": {
            "window_years": settings.window_years,
            "end_year_offset": settings.end_year_offset,
        },
        "update_schedule": {
            "frequency": _describe_schedule_frequency(settings.schedule_months),
            "months": [f"{month:02d}" for month in settings.schedule_months],
            "day": settings.schedule_day,
        },
        "latest_snapshot": latest_snapshot,
        "raw_artifact": raw_artifact,
    }


def write_metadata(metadata: dict[str, Any]) -> Path:
    """Write latest snapshot metadata manifest JSON."""
    _write_json(METADATA_PATH, metadata)
    return METADATA_PATH


def _build_refresh_log_row(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build a stable refresh log row from snapshot metadata."""
    latest_snapshot = metadata.get("latest_snapshot", {})
    if not isinstance(latest_snapshot, dict):
        raise ValueError("metadata['latest_snapshot'] must be a dictionary.")

    return {
        "run_timestamp_utc": latest_snapshot.get("run_timestamp_utc"),
        "snapshot_date": latest_snapshot.get("snapshot_date"),
        "snapshot_label": latest_snapshot.get("snapshot_label"),
        "analysis_start_year": latest_snapshot.get("analysis_start_year"),
        "analysis_end_year": latest_snapshot.get("analysis_end_year"),
        "raw_record_count": latest_snapshot.get("raw_record_count"),
        "publications_row_count": latest_snapshot.get("publications_row_count"),
        "sdg_exploded_row_count": latest_snapshot.get("sdg_exploded_row_count"),
        "kpis_yearly_row_count": latest_snapshot.get("kpis_yearly_row_count"),
        "status": latest_snapshot.get("status"),
    }


def append_refresh_log(metadata: dict[str, Any]) -> Path:
    """Append latest snapshot metadata to refresh log CSV."""
    refresh_row = pd.DataFrame([_build_refresh_log_row(metadata)], columns=REFRESH_LOG_COLUMNS)
    if REFRESH_LOG_PATH.exists():
        existing = pd.read_csv(REFRESH_LOG_PATH)
        existing = existing.reindex(columns=REFRESH_LOG_COLUMNS)
        merged = pd.concat([existing, refresh_row], ignore_index=True)
    else:
        merged = refresh_row

    merged = merged.reindex(columns=REFRESH_LOG_COLUMNS)
    merged.to_csv(REFRESH_LOG_PATH, index=False)
    return REFRESH_LOG_PATH
