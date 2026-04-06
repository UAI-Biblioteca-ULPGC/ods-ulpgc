"""Tests for reusable institution settings."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pytest

from institutional_pipeline.institution_settings import load_institution_settings


def test_load_institution_settings_reads_custom_toml() -> None:
    """Custom TOML settings should override the bundled defaults."""
    temp_dir = Path(tempfile.mkdtemp(dir=".", prefix="test-settings-"))
    try:
        settings_path = temp_dir / "institution.toml"
        settings_path.write_text(
            "\n".join(
                [
                    "[project]",
                    'slug = "demo-project"',
                    'spreadsheet_name = "demo_sheet"',
                    "",
                    "[institution]",
                    'name = "Demo University"',
                    'ror = "https://ror.org/12345"',
                    "",
                    "[openalex]",
                    'document_types = ["article", "book-chapter"]',
                    "",
                    "[analysis]",
                    "window_years = 3",
                    "end_year_offset = 0",
                    "",
                    "[schedule]",
                    "months = [3, 9]",
                    "day = 15",
                ]
            ),
            encoding="utf-8",
        )

        settings = load_institution_settings(settings_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    assert settings.project_slug == "demo-project"
    assert settings.institution_name == "Demo University"
    assert settings.openalex_institution_id is None
    assert settings.institution_ror == "https://ror.org/12345"
    assert settings.document_types == ("article", "book-chapter")
    assert settings.window_years == 3
    assert settings.end_year_offset == 0
    assert settings.schedule_months == (3, 9)
    assert settings.schedule_day == 15
    assert settings.institution_filter_field == "institutions.ror"


def test_load_institution_settings_requires_an_identifier() -> None:
    """At least one institution selector should be configured."""
    temp_dir = Path(tempfile.mkdtemp(dir=".", prefix="test-settings-"))
    try:
        settings_path = temp_dir / "institution.toml"
        settings_path.write_text(
            "\n".join(
                [
                    "[project]",
                    'slug = "demo-project"',
                    "",
                    "[institution]",
                    'name = "Demo University"',
                    'openalex_institution_id = ""',
                    'ror = ""',
                ]
            ),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="openalex_institution_id or institution.ror"):
            load_institution_settings(settings_path)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
