"""Tests for the institutional pipeline CLI."""

from datetime import date

from institutional_pipeline.config import get_closed_window
from institutional_pipeline.main import _should_run_today, parse_args


def test_parse_args_defaults_skip_sheets_to_false() -> None:
    """CLI should publish by default unless ETL-only mode is requested."""
    args = parse_args([])

    assert args.skip_sheets is False
    assert args.settings is None


def test_parse_args_accepts_skip_sheets_flag() -> None:
    """CLI should expose an explicit ETL-only mode."""
    args = parse_args(["--skip-sheets"])

    assert args.skip_sheets is True


def test_parse_args_accepts_settings_path() -> None:
    """CLI should allow a custom institution settings file."""
    args = parse_args(["--settings", "config/custom.toml"])

    assert args.settings == "config/custom.toml"


def test_parse_args_accepts_enforce_schedule_flag() -> None:
    """CLI should allow schedule enforcement for automated runs."""
    args = parse_args(["--enforce-schedule"])

    assert args.enforce_schedule is True


def test_should_run_today_matches_configured_month_and_day() -> None:
    """Schedule matching should require both month and day to match."""
    assert _should_run_today(
        today=date(2026, 7, 1),
        schedule_months=(1, 7),
        schedule_day=1,
    )
    assert not _should_run_today(
        today=date(2026, 7, 2),
        schedule_months=(1, 7),
        schedule_day=1,
    )


def test_get_closed_window_supports_custom_period() -> None:
    """Analysis window should support configurable length and offset."""
    assert get_closed_window(
        today=date(2026, 4, 6),
        window_years=3,
        end_year_offset=0,
    ) == (2024, 2026)
