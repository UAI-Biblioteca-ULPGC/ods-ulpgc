# Institutional OpenAlex to Google Sheets Pipeline

This project harvests institutional publications from OpenAlex, transforms them into analytical tables, and publishes the results to Google Sheets.

In the current ULPGC setup, the final goal is to maintain a Google Sheets dataset that feeds a Tableau Public story focused on research output and SDG-related analysis. The repository is no longer tied to a single institution, though: ULPGC remains the default profile, and other institutions can adapt the pipeline by editing one configuration file.

The raw OpenAlex snapshot is not published through Apps Script. That channel is now reserved for the analytical outputs, the `refresh_log`, and the snapshot metadata. The raw JSON is kept as a compressed GitHub Actions artifact instead.

## Quick Start

Install dependencies and run the pipeline locally:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m institutional_pipeline.main --skip-sheets
```

Run the test suite:

```bash
pip install pytest
python -m pytest -q
```

## The Main File to Edit

If another institution wants to reuse this repository, the first file to edit is [`config/institution.toml`](/C:/ods-ulpgc/config/institution.toml).

That file acts as the institution profile for the pipeline. It controls:

- `institution.name`
- `institution.openalex_institution_id`
- `institution.ror`
- `openalex.document_types`
- `project.slug`
- `project.spreadsheet_name`
- `analysis.window_years`
- `analysis.end_year_offset`
- `schedule.months`
- `schedule.day`

ULPGC remains in that file as the default example so the configuration is easy to edit instead of rebuilding it from scratch.

If you want multiple profiles, create additional TOML files and call the CLI with `--settings`:

```bash
python -m institutional_pipeline.main --settings config/institution.toml
python -m institutional_pipeline.main --settings config/my_other_institution.toml
```

You can also point to a profile with `ODS_SETTINGS_PATH`.

## Execution Model

The main workflow lives in [`.github/workflows/institutional_pipeline.yml`](/C:/ods-ulpgc/.github/workflows/institutional_pipeline.yml).

There are two execution modes:

1. Scheduled execution
   The workflow runs daily in GitHub Actions, but the pipeline only proceeds when the current date matches the schedule defined in `config/institution.toml`.

2. Manual execution
   A manual `workflow_dispatch` run always executes immediately, even if the date does not match the configured schedule.

The current ULPGC profile is set to run on:

- January 1st
- July 1st

It analyzes the last five fully closed years by default, which means the current year is excluded unless `analysis.end_year_offset` is changed.

Examples for the default ULPGC profile:

- `2026-07-01` -> `2021-2025`
- `2027-01-01` -> `2022-2026`
- `2027-07-01` -> `2022-2026`

## Operational Flow

The production flow is straightforward:

1. Fetch works from OpenAlex.
2. Transform the raw response into `publications`, `sdg_exploded`, and `kpis_yearly`.
3. Persist raw data, processed outputs, metadata, and `refresh_log`.
4. Compress the raw JSON and keep it as a GitHub Actions artifact.
5. Publish only the files that fit the Apps Script channel.

The manual workflow includes the `publish_to_apps_script` input:

- `true`: run ETL and publishing
- `false`: run ETL only and skip remote publishing

When a scheduled run falls outside the configured calendar, the pipeline exits cleanly and the workflow skips artifact and publishing steps.

## OpenAlex Integration

The OpenAlex client:

- uses a clear `User-Agent`
- supports `OPENALEX_API_KEY` when available
- can filter by either an OpenAlex institution ID or a ROR identifier
- supports configurable document types such as `article`, `review`, or `book-chapter`
- logs pagination, cursors, API-key usage, and record counts

## Apps Script Publishing

The web app code lives in [`apps_script/Code.js`](/C:/ods-ulpgc/apps_script/Code.js).

The publishing layer includes a few safeguards that matter in practice:

- `LockService` avoids concurrent executions
- Drive files are updated in place instead of `trash + create`
- Google Sheets updates use staging and promotion
- temporary sheets are rolled back and cleaned up if promotion fails

Apps Script project properties hold:

- `ROOT_FOLDER_ID`
- `SPREADSHEET_ID`
- `WEBHOOK_SHARED_SECRET`

Those values are not stored in the Python `.env` file.

## Outputs and Traceability

The project keeps four operational outputs at the center of the workflow:

- analytical CSV files
- `latest_snapshot_metadata.json`
- `refresh_log.csv`
- the compressed raw OpenAlex artifact

[`refresh_log.csv`](/C:/ods-ulpgc/data/logs/refresh_log.csv) uses a stable schema oriented to operational traceability. The JSON manifest remains the richer artifact, while the CSV keeps the compact execution history.

Current `refresh_log.csv` columns:

- `run_timestamp_utc`
- `snapshot_date`
- `snapshot_label`
- `analysis_start_year`
- `analysis_end_year`
- `raw_record_count`
- `publications_row_count`
- `sdg_exploded_row_count`
- `kpis_yearly_row_count`
- `status`

## Configuration

The environment variable template lives in [`.env.example`](/C:/ods-ulpgc/.env.example).

Python uses:

- `OPENALEX_API_KEY`
- `ODS_SETTINGS_PATH`
- `APPS_SCRIPT_WEBAPP_URL`
- `APPS_SCRIPT_SHARED_SECRET`
- `APPS_SCRIPT_MAX_FILE_BYTES`

`load_dotenv()` is called only in CLI entry points and not during library import.

## Testing

The regression suite runs with `pytest` and is automated through [`.github/workflows/tests.yml`](/C:/ods-ulpgc/.github/workflows/tests.yml).

Current test coverage includes:

- [`tests/test_transform.py`](/C:/ods-ulpgc/tests/test_transform.py)
- [`tests/test_openalex_client.py`](/C:/ods-ulpgc/tests/test_openalex_client.py)
- [`tests/test_publish_payload.py`](/C:/ods-ulpgc/tests/test_publish_payload.py)
- [`tests/test_snapshot_manager.py`](/C:/ods-ulpgc/tests/test_snapshot_manager.py)
- [`tests/test_main.py`](/C:/ods-ulpgc/tests/test_main.py)
- [`tests/test_institution_settings.py`](/C:/ods-ulpgc/tests/test_institution_settings.py)

## Notes from the Current Review

I reviewed the current implementation against the local codebase and checked the external behavior of `python-dotenv` and `requests` through Context7.

The code is aligned with the documented behavior in the areas that matter most here:

- `load_dotenv()` is used in CLI entry points rather than during module import, which matches the current intent of keeping library imports side-effect free.
- `requests` calls use explicit per-request timeouts, which is important because timeouts are applied per request, not globally on a session.
- JSON decoding is already wrapped so invalid JSON surfaces as a controlled runtime error.

I did not find a docs-level issue that needed a code change in this review pass.

## Project Structure

```text
ods-ulpgc/
|-- .github/
|   |-- workflows/
|       |-- institutional_pipeline.yml
|       `-- tests.yml
|-- apps_script/
|   |-- appsscript.json
|   `-- Code.js
|-- config/
|   `-- institution.toml
|-- data/
|   |-- manifests/
|   |   `-- latest_snapshot_metadata.json
|   |-- raw/
|   |   |-- latest/
|   |   `-- archive/
|   |-- processed/
|   |   |-- latest/
|   |   `-- archive/
|   `-- logs/
|-- src/
|   `-- institutional_pipeline/
|       |-- __init__.py
|       |-- config.py
|       |-- institution_settings.py
|       |-- main.py
|       |-- openalex_client.py
|       |-- publish_payload.py
|       |-- snapshot_manager.py
|       |-- sheets_writer.py
|       `-- transform.py
`-- tests/
```
