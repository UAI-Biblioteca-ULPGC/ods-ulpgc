"""Configuration utilities for the institutional ETL pipeline.

This module centralizes filesystem paths, filename conventions, and
window-related helpers used across the pipeline.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(".")
DATA_DIR = BASE_DIR / "data"

RAW_DIR = DATA_DIR / "raw"
RAW_LATEST_DIR = RAW_DIR / "latest"
RAW_ARCHIVE_DIR = RAW_DIR / "archive"

PROCESSED_DIR = DATA_DIR / "processed"
PROCESSED_LATEST_DIR = PROCESSED_DIR / "latest"
PROCESSED_ARCHIVE_DIR = PROCESSED_DIR / "archive"

LOGS_DIR = DATA_DIR / "logs"
MANIFESTS_DIR = DATA_DIR / "manifests"

RAW_LATEST_PATH = RAW_LATEST_DIR / "openalex_works_latest.json"
PROCESSED_LATEST_PUBLICATIONS = PROCESSED_LATEST_DIR / "publications_latest.csv"
PROCESSED_LATEST_SDG = PROCESSED_LATEST_DIR / "sdg_exploded_latest.csv"
PROCESSED_LATEST_KPIS = PROCESSED_LATEST_DIR / "kpis_yearly_latest.csv"
REFRESH_LOG_PATH = LOGS_DIR / "refresh_log.csv"
METADATA_PATH = MANIFESTS_DIR / "latest_snapshot_metadata.json"

DEFAULT_WINDOW_YEARS = 5


def ensure_data_dirs() -> None:
    """Create all required local directories for pipeline outputs."""
    required_dirs = [
        RAW_LATEST_DIR,
        RAW_ARCHIVE_DIR,
        PROCESSED_LATEST_DIR,
        PROCESSED_ARCHIVE_DIR,
        LOGS_DIR,
        MANIFESTS_DIR,
    ]
    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)


def get_closed_window(
    today: date | None = None,
    *,
    window_years: int = DEFAULT_WINDOW_YEARS,
    end_year_offset: int = 1,
) -> tuple[int, int]:
    """Return the analysis window ending a configurable number of years back.

    Args:
        today: Optional date used for deterministic testing. If omitted,
            the current system date is used.

    Returns:
        A tuple ``(start_year, end_year)``.
    """
    reference_date = today or date.today()
    if window_years < 1:
        raise ValueError("window_years must be at least 1.")
    if end_year_offset < 0:
        raise ValueError("end_year_offset must be 0 or greater.")
    end_year = reference_date.year - end_year_offset
    start_year = end_year - window_years + 1
    return start_year, end_year


def build_snapshot_label(snapshot_date: date | None = None) -> str:
    """Build a deterministic label for snapshot artifacts.

    Args:
        snapshot_date: Date used for naming; defaults to current date.

    Returns:
        Snapshot label in ``YYYYMMDD`` format.
    """
    effective_date = snapshot_date or date.today()
    return effective_date.strftime("%Y%m%d")


def build_unique_snapshot_label(now: datetime | None = None) -> str:
    """Build a collision-safe snapshot label with UTC timestamp precision."""
    timestamp = now or datetime.utcnow()
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def build_raw_archive_path(snapshot_label: str) -> Path:
    """Return the archived raw JSON path for a snapshot label."""
    return RAW_ARCHIVE_DIR / f"openalex_works_{snapshot_label}.json"


def build_processed_archive_publications_path(snapshot_label: str) -> Path:
    """Return the archived publications CSV path for a snapshot label."""
    return PROCESSED_ARCHIVE_DIR / f"publications_{snapshot_label}.csv"


def build_processed_archive_sdg_path(snapshot_label: str) -> Path:
    """Return the archived SDG exploded CSV path for a snapshot label."""
    return PROCESSED_ARCHIVE_DIR / f"sdg_exploded_{snapshot_label}.csv"


def build_processed_archive_kpis_path(snapshot_label: str) -> Path:
    """Return the archived yearly KPIs CSV path for a snapshot label."""
    return PROCESSED_ARCHIVE_DIR / f"kpis_yearly_{snapshot_label}.csv"
