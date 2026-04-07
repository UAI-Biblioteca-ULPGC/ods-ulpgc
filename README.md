# ODS-ULPGC: Institutional Research Output Pipeline
[![Tests](https://github.com/igarate/ods-ulpgc/actions/workflows/tests.yml/badge.svg)](https://github.com/igarate/ods-ulpgc/actions/workflows/tests.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Descripción institucional / Institutional Abstract

Este repositorio contiene la infraestructura de datos desarrollada por la
Biblioteca Universitaria de la Universidad de Las Palmas de Gran Canaria
(ULPGC) para la recolección, transformación y publicación automatizada de
la producción científica institucional a partir de OpenAlex. Los resultados
alimentan un panel de visualización en Tableau Public orientado al
seguimiento de los indicadores de investigación y la contribución
institucional a los Objetivos de Desarrollo Sostenible (ODS) de la Agenda
2030. La arquitectura del sistema es reutilizable: cualquier institución
puede adaptar el pipeline modificando un único archivo de configuración.

---

This repository contains the data infrastructure developed by the
University Library of the Universidad de Las Palmas de Gran Canaria (ULPGC)
for the automated harvesting, transformation, and publication of
institutional research output from OpenAlex. The results feed a Tableau
Public dashboard tracking research performance indicators and the
institution's contribution to the Sustainable Development Goals (SDGs) of
the 2030 Agenda. The pipeline architecture is reusable: any institution can
adapt it by editing a single configuration file.

---

Raw OpenAlex snapshots are not published through the Apps Script channel.
That channel is reserved for analytical outputs, the `refresh_log`, and
snapshot metadata. Raw JSON is retained as a compressed GitHub Actions
artifact.

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

## Institution Configuration

The primary configuration file is
[`config/institution.toml`](/C:/ods-ulpgc/config/institution.toml).

This file defines the institution profile that governs pipeline behaviour.
Configurable parameters include:

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

The ULPGC profile ships as the default reference. Multiple institution
profiles are supported via the `--settings` flag or the
`ODS_SETTINGS_PATH` environment variable:

```bash
python -m institutional_pipeline.main --settings config/institution.toml
python -m institutional_pipeline.main --settings config/my_other_institution.toml
```

## Execution Model

The main workflow is defined in
[`.github/workflows/institutional_pipeline.yml`](/C:/ods-ulpgc/.github/workflows/institutional_pipeline.yml).

Two execution modes are available:

**Scheduled execution.** The workflow runs daily in GitHub Actions. The
pipeline proceeds only when the current date matches the schedule defined
in `config/institution.toml`. The default ULPGC profile triggers on
January 1st and July 1st.

**Manual execution.** A `workflow_dispatch` run executes immediately,
regardless of the configured schedule.

By default, the pipeline analyses the last five fully closed calendar
years, excluding the current year. This window advances automatically
with each run:

| Execution date | Analysis window |
|----------------|-----------------|
| 2026-07-01     | 2021–2025       |
| 2027-01-01     | 2022–2026       |
| 2027-07-01     | 2022–2026       |

The `analysis.end_year_offset` parameter adjusts this behaviour when
needed.

## Operational Flow

The production sequence follows five stages:

1. Fetch works from OpenAlex using the configured institution profile.
2. Transform the raw response into three analytical tables:
   `publications`, `sdg_exploded`, and `kpis_yearly`.
3. Persist raw data, processed outputs, snapshot metadata, and the
   `refresh_log`.
4. Compress the raw JSON and retain it as a GitHub Actions artifact.
5. Publish the files that fall within the Apps Script channel's scope.

The `publish_to_apps_script` input in manual runs controls whether the
ETL runs with remote publishing (`true`) or without it (`false`).
Scheduled runs that fall outside the configured calendar exit cleanly;
the workflow skips artifact upload and publishing steps.

## OpenAlex Integration

The OpenAlex client is designed for reliability and reproducibility:

- Authenticates via `OPENALEX_API_KEY` when available, which grants
  higher rate limits and ensures institutional traceability.
- Falls back to anonymous access with a descriptive `User-Agent` header
  when no key is configured.
- Accepts filtering by either OpenAlex institution ID or ROR identifier.
- Accepts configurable document types: `article`, `review`,
  `book-chapter`, and others.
- Logs pagination cursors, API-key usage, and record counts for
  traceability.

## Apps Script Publishing

The web application code is in
[`apps_script/Code.js`](/C:/ods-ulpgc/apps_script/Code.js).

The publishing layer implements four operational safeguards:

- `LockService` prevents concurrent executions.
- Drive files are updated in place rather than deleted and recreated.
- Google Sheets updates use a staging-and-promotion pattern.
- Temporary sheets are rolled back and cleaned up if promotion fails.

The following Apps Script project properties must be set in the Apps
Script environment (not in the Python `.env` file):

- `ROOT_FOLDER_ID`
- `SPREADSHEET_ID`
- `WEBHOOK_SHARED_SECRET`

## Outputs and Traceability

Four artefacts anchor the operational workflow:

- Analytical CSV files (`publications`, `sdg_exploded`, `kpis_yearly`).
- `latest_snapshot_metadata.json` — the canonical snapshot manifest.
- `refresh_log.csv` — a compact execution history with a stable schema.
- The compressed raw OpenAlex artefact retained by GitHub Actions.

The JSON manifest carries the full snapshot record; `refresh_log.csv`
provides the lightweight operational trace. Current `refresh_log.csv`
schema:

| Column | Description |
|--------|-------------|
| `run_timestamp_utc` | UTC timestamp of pipeline execution |
| `snapshot_date` | Date of the OpenAlex snapshot |
| `snapshot_label` | Human-readable snapshot identifier |
| `analysis_start_year` | First year of the analysis window |
| `analysis_end_year` | Last year of the analysis window |
| `raw_record_count` | Records retrieved from OpenAlex |
| `publications_row_count` | Rows in the publications table |
| `sdg_exploded_row_count` | Rows in the SDG-exploded table |
| `kpis_yearly_row_count` | Rows in the yearly KPI table |
| `status` | Pipeline exit status |

## Environment Variables

The variable template is in
[`.env.example`](/C:/ods-ulpgc/.env.example). Python reads:

| Variable | Purpose |
|----------|---------|
| `OPENALEX_API_KEY` | Optional API key for OpenAlex |
| `ODS_SETTINGS_PATH` | Path to the active institution profile |
| `APPS_SCRIPT_WEBAPP_URL` | Endpoint for the Apps Script web app |
| `APPS_SCRIPT_SHARED_SECRET` | Shared secret for webhook authentication |
| `APPS_SCRIPT_MAX_FILE_BYTES` | Maximum payload size for publishing |

`load_dotenv()` is called only in CLI entry points, not during library
import, preserving side-effect-free module loading.

## Testing

The regression suite runs under `pytest` and is automated through
[`.github/workflows/tests.yml`](/C:/ods-ulpgc/.github/workflows/tests.yml).
Current test coverage spans:

| Test file | Scope |
|-----------|-------|
| `tests/test_transform.py` | Transformation logic |
| `tests/test_openalex_client.py` | OpenAlex client behaviour |
| `tests/test_publish_payload.py` | Publishing payload construction |
| `tests/test_snapshot_manager.py` | Snapshot persistence and rotation |
| `tests/test_main.py` | End-to-end pipeline orchestration |
| `tests/test_institution_settings.py` | Configuration loading and validation |

## Implementation Notes

The current codebase was reviewed against the local implementation and
verified against the external behaviour of `python-dotenv` and `requests`
via Context7. Three areas were confirmed to align with documented
behaviour:

- `load_dotenv()` is invoked at CLI entry points only, consistent with
  the intent to keep library imports side-effect free.
- `requests` calls carry explicit per-request timeouts; timeouts are
  not set globally on the session, which matches the library's design.
- JSON decoding is wrapped so that malformed responses surface as
  controlled runtime errors rather than silent failures.

No documentation-level discrepancies requiring code changes were
identified in this review pass.

## Project Structure

```text
ods-ulpgc/
├── .github/
│   └── workflows/
│       ├── institutional_pipeline.yml
│       └── tests.yml
├── apps_script/
│   ├── appsscript.json
│   └── Code.js
├── config/
│   └── institution.toml
├── data/
│   ├── manifests/
│   │   └── latest_snapshot_metadata.json
│   ├── raw/
│   │   ├── latest/
│   │   └── archive/
│   ├── processed/
│   │   ├── latest/
│   │   └── archive/
│   └── logs/
├── src/
│   └── institutional_pipeline/
│       ├── __init__.py
│       ├── config.py
│       ├── institution_settings.py
│       ├── main.py
│       ├── openalex_client.py
│       ├── publish_payload.py
│       ├── snapshot_manager.py
│       ├── sheets_writer.py
│       └── transform.py
└── tests/
```

## License

[MIT](LICENSE)
