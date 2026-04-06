"""CLI entry point for the institutional ETL pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from dotenv import load_dotenv

from institutional_pipeline.config import (
    build_unique_snapshot_label,
    ensure_data_dirs,
    get_closed_window,
)
from institutional_pipeline.institution_settings import load_institution_settings
from institutional_pipeline.openalex_client import fetch_works
from institutional_pipeline.snapshot_manager import (
    append_refresh_log,
    build_snapshot_metadata,
    write_metadata,
    write_processed_outputs,
    write_raw_outputs,
)
from institutional_pipeline.transform import build_outputs

LOGGER = logging.getLogger(__name__)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure process-wide logging."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for pipeline execution."""
    parser = argparse.ArgumentParser(
        prog="ods-ulpgc",
        description="Run the institutional OpenAlex ETL pipeline and generate artifacts for optional publication.",
    )
    parser.add_argument(
        "--skip-sheets",
        action="store_true",
        help="Run ETL only and skip downstream Apps Script publication in orchestrated runs.",
    )
    parser.add_argument(
        "--settings",
        default=None,
        help="Optional path to an institution TOML settings file.",
    )
    parser.add_argument(
        "--enforce-schedule",
        action="store_true",
        help="Skip execution unless today matches the configured schedule in the settings file.",
    )
    return parser.parse_args(argv)


def _should_run_today(*, today: date, schedule_months: tuple[int, ...], schedule_day: int) -> bool:
    """Return whether the current date matches the configured run schedule."""
    return today.month in schedule_months and today.day == schedule_day


def run_pipeline(
    skip_sheets: bool = False,
    settings_path: str | None = None,
    *,
    enforce_schedule: bool = False,
) -> None:
    """Execute the ETL pipeline end-to-end."""
    ensure_data_dirs()
    settings = load_institution_settings(settings_path)
    snapshot_date = date.today()

    if enforce_schedule and not _should_run_today(
        today=snapshot_date,
        schedule_months=settings.schedule_months,
        schedule_day=settings.schedule_day,
    ):
        LOGGER.info(
            "Skipping run because %s does not match configured schedule (months=%s, day=%s).",
            snapshot_date.isoformat(),
            settings.schedule_months,
            settings.schedule_day,
        )
        return

    start_year, end_year = get_closed_window(
        window_years=settings.window_years,
        end_year_offset=settings.end_year_offset,
    )

    LOGGER.info("%s pipeline starting.", settings.project_slug)
    LOGGER.info("Institution: %s", settings.institution_name)
    LOGGER.info("Closed analysis window: %s-%s", start_year, end_year)

    raw_works = fetch_works(
        institution_id=settings.openalex_institution_id,
        institution_ror=settings.institution_ror,
        start_year=start_year,
        end_year=end_year,
        document_types=settings.document_types,
    )
    LOGGER.info("Fetched raw records: %s", len(raw_works))

    publications_df, sdg_exploded_df, kpis_yearly_df = build_outputs(
        raw_works=raw_works,
        start_year=start_year,
        end_year=end_year,
    )

    snapshot_label = build_unique_snapshot_label()

    write_raw_outputs(raw_works=raw_works, snapshot_label=snapshot_label)
    write_processed_outputs(
        publications_df=publications_df,
        sdg_exploded_df=sdg_exploded_df,
        kpis_yearly_df=kpis_yearly_df,
        snapshot_label=snapshot_label,
    )

    metadata = build_snapshot_metadata(
        settings=settings,
        snapshot_date=snapshot_date,
        snapshot_label=snapshot_label,
        analysis_start_year=start_year,
        analysis_end_year=end_year,
        raw_record_count=len(raw_works),
        publications_row_count=len(publications_df.index),
        sdg_exploded_row_count=len(sdg_exploded_df.index),
        kpis_yearly_row_count=len(kpis_yearly_df.index),
        status="success",
    )
    write_metadata(metadata)
    append_refresh_log(metadata)

    if skip_sheets:
        LOGGER.info(
            "--skip-sheets specified; ETL artifacts generated without downstream Sheets publication."
        )

    LOGGER.info("Institutional pipeline completed successfully.")


def main(argv: list[str] | None = None) -> int:
    """Run CLI and return process exit code."""
    args = parse_args(argv)
    configure_logging()
    load_dotenv()

    try:
        run_pipeline(
            skip_sheets=args.skip_sheets,
            settings_path=args.settings,
            enforce_schedule=args.enforce_schedule,
        )
    except Exception:
        LOGGER.exception("Institutional pipeline failed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
