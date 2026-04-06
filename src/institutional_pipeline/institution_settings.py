"""Load reusable institution-level settings for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tomllib

DEFAULT_WORKSHEETS = ("publications", "sdg_exploded", "kpis_yearly", "refresh_log")
DEFAULT_SETTINGS_PATH = Path("config") / "institution.toml"
DEFAULT_WINDOW_YEARS = 5
DEFAULT_END_YEAR_OFFSET = 1
DEFAULT_SCHEDULE_MONTHS = (1, 7)
DEFAULT_SCHEDULE_DAY = 1


@dataclass(frozen=True)
class InstitutionSettings:
    """Institution-specific settings that make the pipeline reusable."""

    project_slug: str
    institution_name: str
    openalex_institution_id: str | None
    institution_ror: str | None
    document_types: tuple[str, ...]
    spreadsheet_name: str
    worksheets: tuple[str, ...]
    window_years: int
    end_year_offset: int
    schedule_months: tuple[int, ...]
    schedule_day: int

    @property
    def institution_filter_field(self) -> str:
        """Return the OpenAlex works filter field to use for the institution."""
        if self.openalex_institution_id:
            return "institutions.id"
        return "institutions.ror"

    @property
    def institution_filter_value(self) -> str:
        """Return the configured institution selector value."""
        if self.openalex_institution_id:
            return self.openalex_institution_id
        if self.institution_ror:
            return self.institution_ror
        raise ValueError(
            "At least one institution identifier is required: "
            "openalex_institution_id or institution_ror."
        )


def _read_settings_payload(path: Path) -> dict[str, object]:
    """Read TOML settings from disk when the file exists."""
    if not path.exists():
        return {}
    raw_text = path.read_text(encoding="utf-8-sig")
    return tomllib.loads(raw_text)


def _as_tuple_of_strings(value: object, *, field_name: str) -> tuple[str, ...]:
    """Validate a list-like TOML value and normalize it into a tuple."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a TOML array of strings.")
    return tuple(item.strip() for item in value if item.strip())


def _as_tuple_of_ints(value: object, *, field_name: str) -> tuple[int, ...]:
    """Validate a list-like TOML value of integers."""
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, int) for item in value):
        raise ValueError(f"{field_name} must be a TOML array of integers.")
    return tuple(item for item in value)


def load_institution_settings(
    settings_path: str | os.PathLike[str] | None = None,
) -> InstitutionSettings:
    """Load institution settings from TOML, falling back to bundled defaults."""
    resolved_path = Path(
        settings_path or os.getenv("ODS_SETTINGS_PATH") or DEFAULT_SETTINGS_PATH
    )
    settings_file_exists = resolved_path.exists()
    payload = _read_settings_payload(resolved_path)

    project = payload.get("project", {})
    institution = payload.get("institution", {})
    openalex = payload.get("openalex", {})
    pipeline = payload.get("pipeline", {})
    analysis = payload.get("analysis", {})
    schedule = payload.get("schedule", {})

    if not isinstance(project, dict):
        raise ValueError("[project] must be a TOML table.")
    if not isinstance(institution, dict):
        raise ValueError("[institution] must be a TOML table.")
    if not isinstance(openalex, dict):
        raise ValueError("[openalex] must be a TOML table.")
    if not isinstance(pipeline, dict):
        raise ValueError("[pipeline] must be a TOML table.")
    if not isinstance(analysis, dict):
        raise ValueError("[analysis] must be a TOML table.")
    if not isinstance(schedule, dict):
        raise ValueError("[schedule] must be a TOML table.")

    settings = InstitutionSettings(
        project_slug=str(project.get("slug", "ods-ulpgc")).strip(),
        institution_name=str(
            institution.get("name", "Universidad de Las Palmas de Gran Canaria")
        ).strip(),
        openalex_institution_id=str(
            institution.get(
                "openalex_institution_id",
                "" if settings_file_exists else "I119635470",
            )
        ).strip()
        or None,
        institution_ror=str(institution.get("ror", "")).strip() or None,
        document_types=_as_tuple_of_strings(
            openalex.get("document_types", ["article", "review"]),
            field_name="openalex.document_types",
        ),
        spreadsheet_name=str(
            project.get("spreadsheet_name", "ods_ulpgc_datahub")
        ).strip(),
        worksheets=_as_tuple_of_strings(
            project.get("worksheets", list(DEFAULT_WORKSHEETS)),
            field_name="project.worksheets",
        )
        or DEFAULT_WORKSHEETS,
        window_years=int(
            analysis.get("window_years", pipeline.get("window_years", DEFAULT_WINDOW_YEARS))
        ),
        end_year_offset=int(
            analysis.get(
                "end_year_offset",
                pipeline.get("end_year_offset", DEFAULT_END_YEAR_OFFSET),
            )
        ),
        schedule_months=_as_tuple_of_ints(
            schedule.get("months", list(DEFAULT_SCHEDULE_MONTHS)),
            field_name="schedule.months",
        )
        or DEFAULT_SCHEDULE_MONTHS,
        schedule_day=int(schedule.get("day", DEFAULT_SCHEDULE_DAY)),
    )

    if not settings.project_slug:
        raise ValueError("project.slug must be a non-empty string.")
    if not settings.institution_name:
        raise ValueError("institution.name must be a non-empty string.")
    if settings.window_years < 1:
        raise ValueError("analysis.window_years must be at least 1.")
    if settings.end_year_offset < 0:
        raise ValueError("analysis.end_year_offset must be 0 or greater.")
    if not all(1 <= month <= 12 for month in settings.schedule_months):
        raise ValueError("schedule.months must contain values between 1 and 12.")
    if not 1 <= settings.schedule_day <= 31:
        raise ValueError("schedule.day must be between 1 and 31.")
    if not settings.openalex_institution_id and not settings.institution_ror:
        raise ValueError(
            "Provide institution.openalex_institution_id or institution.ror."
        )

    return settings
