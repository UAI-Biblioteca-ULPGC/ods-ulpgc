# ODS-ULPGC: Institutional Research Output Pipeline

[![Tests](https://github.com/UAI-Biblioteca-ULPGC/ods-ulpgc/actions/workflows/tests.yml/badge.svg)](https://github.com/UAI-Biblioteca-ULPGC/ods-ulpgc/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/UAI-Biblioteca-ULPGC/ods-ulpgc/releases/tag/v1.0.1)

## Descripción institucional / Institutional Abstract

Este repositorio contiene la infraestructura de datos desarrollada por la
Biblioteca Universitaria de la Universidad de Las Palmas de Gran Canaria
(ULPGC) para la recolección, transformación y publicación automatizada de la
producción científica institucional a partir de OpenAlex. Los resultados
alimentan un panel de visualización en Tableau Public orientado al seguimiento
de indicadores de investigación y de la contribución institucional a los
Objetivos de Desarrollo Sostenible (ODS) de la Agenda 2030. La arquitectura del
sistema es reutilizable: cualquier institución puede adaptarla mediante un
único archivo de configuración.

---

This repository contains the data infrastructure developed by the University
Library of the Universidad de Las Palmas de Gran Canaria (ULPGC) for the
automated harvesting, transformation, and publication of institutional research
output from OpenAlex. The results feed a Tableau Public dashboard that tracks
research performance indicators and the institution's contribution to the
Sustainable Development Goals (SDGs) of the 2030 Agenda. The pipeline is
reusable: another institution can adapt it by editing a single configuration
file.

---

Raw OpenAlex snapshots are not published through the Apps Script channel. That
channel is reserved for analytical outputs, the `refresh_log`, and snapshot
metadata. Raw JSON is retained locally and, in GitHub Actions, as a compressed
artifact.

## Public Visualization

The public dashboard generated from this pipeline is available on Tableau
Public:

[ULPGC research output and its contribution to the SDGs](https://public.tableau.com/views/LaULPCysucontribucincientficaalosODS/Historia1?:language=es-ES&:sid=&:redirect=auth&:display_count=n&:origin=viz_share_link)

It provides an external view of the institutional outputs derived from the
pipeline and supports exploratory analysis of ULPGC's contribution to the
Sustainable Development Goals.

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

This file defines the institution profile that governs pipeline behavior.
Configurable parameters include:

- `institution.name`
- `institution.openalex_institution_id`
- `institution.ror`
- `openalex.document_types`
- `project.slug`
- `project.spreadsheet_name`
- `project.worksheets`
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

Two execution modes are available.

**Scheduled execution.** GitHub Actions schedules the workflow twice per year:
on 1 January and 1 July at 02:15 UTC. The pipeline also checks the configured
calendar through `--enforce-schedule`, so scheduled runs outside the allowed
dates exit cleanly without producing artifacts for upload or publication.

**Manual execution.** A `workflow_dispatch` run executes immediately, regardless
of the configured schedule. The `publish_to_apps_script` input determines
whether the workflow stops after ETL artifact generation or continues with the
Apps Script publication step.

**Local execution.** `python -m institutional_pipeline.main` generates local
artifacts only. Remote publication is handled separately by
`python -m institutional_pipeline.publish_payload` or by the GitHub Actions
workflow.

By default, the pipeline analyzes the last five fully closed calendar years,
excluding the current year. This window advances automatically with each run:

| Execution date | Analysis window |
|----------------|-----------------|
| 2026-07-01     | 2021-2025       |
| 2027-01-01     | 2022-2026       |
| 2027-07-01     | 2022-2026       |

The `analysis.end_year_offset` parameter adjusts this behavior when needed.

## Operational Flow

The production sequence follows five stages:

1. Fetch works from OpenAlex using the configured institution profile.
2. Transform the raw response into three analytical tables:
   `publications`, `sdg_exploded`, and `kpis_yearly`. In `sdg_exploded`, every
   publication is retained even when no SDG is assigned; those rows keep
   `sdg_code`, `sdg_label`, and `score` empty so downstream statistics and
   visualizations preserve the full corpus.
3. Persist raw data, processed outputs, snapshot metadata, and the
   `refresh_log`.
4. Compress the raw JSON and retain it as a GitHub Actions artifact in
   orchestrated runs.
5. Publish the files that fall within the Apps Script channel's scope.

## OpenAlex Integration

The OpenAlex client authenticates via `OPENALEX_API_KEY` when available, which
provides higher rate limits and clearer institutional traceability. It falls
back to anonymous access with a descriptive `User-Agent` header when no key is
configured. Additional client capabilities include:

- Filtering by either OpenAlex institution ID or ROR identifier.
- Configurable document types. The bundled ULPGC profile includes `article`,
  `review`, `book`, `book-chapter`, `dataset`, and `preprint`.
- Logging of pagination cursors, API-key usage, and record counts for
  operational traceability.
- Explicit retry, backoff, timeout, and JSON-validation behavior for request
  failures.

## Apps Script Publishing

The web application code is in
[`apps_script/Code.js`](/C:/ods-ulpgc/apps_script/Code.js).

The publication layer uses a webhook-driven architecture. Python prepares the
payload and Apps Script handles Drive and Google Sheets updates. The Apps
Script side implements four operational safeguards:

- `LockService` prevents concurrent executions.
- Drive files are updated in place rather than deleted and recreated.
- Google Sheets updates use a staging-and-promotion pattern.
- Temporary sheets are rolled back and cleaned up if promotion fails.

The following project properties must be set directly in the Apps Script
environment, not in the Python `.env` file:

- `ROOT_FOLDER_ID`
- `SPREADSHEET_ID`
- `WEBHOOK_SHARED_SECRET`

## Outputs and Traceability

Four artifacts anchor the operational workflow:

- Analytical CSV files (`publications`, `sdg_exploded`, `kpis_yearly`)
- `latest_snapshot_metadata.json`, the canonical snapshot manifest
- `refresh_log.csv`, a compact execution history with a stable schema
- The compressed raw OpenAlex artifact retained by GitHub Actions

The JSON manifest carries the full snapshot record; `refresh_log.csv` provides
the lightweight operational trace. Current `refresh_log.csv` schema:

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

`load_dotenv()` is called only in CLI entry points, not during library import.

## Testing

The regression suite runs under `pytest` and is automated through
[`.github/workflows/tests.yml`](/C:/ods-ulpgc/.github/workflows/tests.yml).
Current test coverage spans:

| Test file | Scope |
|-----------|-------|
| `tests/test_transform.py` | Transformation logic |
| `tests/test_openalex_client.py` | OpenAlex client behavior |
| `tests/test_publish_payload.py` | Publishing payload construction |
| `tests/test_snapshot_manager.py` | Snapshot persistence and rotation |
| `tests/test_main.py` | CLI parsing and execution rules |
| `tests/test_institution_settings.py` | Configuration loading and validation |

## Implementation Notes

The current implementation follows these repository-level conventions:

- Environment variables are loaded only in the executable entry points
  (`main.py` and `publish_payload.py`).
- Request timeouts are defined per call rather than as hidden global session
  defaults.
- Raw snapshot archival and compressed artifact generation are distinct steps:
  the Python pipeline writes JSON locally, and GitHub Actions compresses and
  uploads the artifact during orchestrated runs.
- Python does not write directly to Google Sheets. It publishes a validated
  webhook payload that Apps Script receives and applies.

## Project Structure

```text
ods-ulpgc/
|-- .github/
|   `-- workflows/
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
|       `-- transform.py
`-- tests/
```

## License

[MIT](LICENSE)
