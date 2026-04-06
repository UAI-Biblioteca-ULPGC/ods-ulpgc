"""Publish institutional pipeline outputs to the Apps Script web app."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

PROCESSED_LATEST_PUBLICATIONS = Path("data/processed/latest/publications_latest.csv")
PROCESSED_LATEST_SDG = Path("data/processed/latest/sdg_exploded_latest.csv")
PROCESSED_LATEST_KPIS = Path("data/processed/latest/kpis_yearly_latest.csv")
LOG_PATH = Path("data/logs/refresh_log.csv")
METADATA_PATH = Path("data/manifests/latest_snapshot_metadata.json")

PUBLISHABLE_PATHS = {
    "publications_csv_base64": PROCESSED_LATEST_PUBLICATIONS,
    "sdg_exploded_csv_base64": PROCESSED_LATEST_SDG,
    "kpis_yearly_csv_base64": PROCESSED_LATEST_KPIS,
    "refresh_log_csv_base64": LOG_PATH,
    "metadata_json_base64": METADATA_PATH,
}
DEFAULT_MAX_WEBHOOK_FILE_BYTES = 8000000


def get_max_webhook_file_bytes() -> int:
    """Return the maximum allowed file size for webhook publishing."""
    return int(os.getenv("APPS_SCRIPT_MAX_FILE_BYTES", str(DEFAULT_MAX_WEBHOOK_FILE_BYTES)))


def read_file_base64(path: Path) -> str:
    """Read a file and return its Base64-encoded content."""
    with path.open("rb") as file_handle:
        return base64.b64encode(file_handle.read()).decode("utf-8")


def load_metadata() -> dict[str, Any]:
    """Load the latest snapshot metadata JSON."""
    with METADATA_PATH.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def validate_environment() -> None:
    """Validate required environment variables."""
    required_env = [
        "APPS_SCRIPT_WEBAPP_URL",
        "APPS_SCRIPT_SHARED_SECRET",
    ]
    missing = [name for name in required_env if not os.environ.get(name)]
    if missing:
        missing_text = ", ".join(missing)
        raise EnvironmentError(
            f"Missing required environment variables: {missing_text}"
        )


def validate_required_files() -> None:
    """Validate that all required local files exist before publishing."""
    required_paths = list(PUBLISHABLE_PATHS.values())

    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        missing_text = "\n - ".join(missing)
        raise FileNotFoundError(
            "Missing required files before publishing:\n"
            f" - {missing_text}"
        )


def validate_publishable_sizes() -> None:
    """Fail fast when a file is too large for the Apps Script webhook flow."""
    oversized: list[tuple[str, Path, int]] = []
    max_webhook_file_bytes = get_max_webhook_file_bytes()

    for field_name, path in PUBLISHABLE_PATHS.items():
        file_size = path.stat().st_size
        if file_size > max_webhook_file_bytes:
            oversized.append((field_name, path, file_size))

    if oversized:
        details = "\n".join(
            f" - {field_name}: {path} ({file_size} bytes)"
            for field_name, path, file_size in oversized
        )
        raise ValueError(
            "One or more files exceed the Apps Script publish threshold "
            f"({max_webhook_file_bytes} bytes):\n{details}"
        )


def extract_snapshot_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized snapshot metadata from nested or flat JSON."""
    if not isinstance(metadata, dict):
        raise ValueError("Metadata payload must be a dictionary.")

    latest_snapshot = metadata.get("latest_snapshot")
    if isinstance(latest_snapshot, dict):
        snapshot_data = latest_snapshot.copy()
    else:
        snapshot_data = metadata.copy()

    # Fallbacks in case some keys are top-level in older metadata formats.
    for key in (
        "snapshot_date",
        "snapshot_label",
        "analysis_start_year",
        "analysis_end_year",
    ):
        if key not in snapshot_data and key in metadata:
            snapshot_data[key] = metadata[key]

    required_keys = [
        "snapshot_date",
        "snapshot_label",
        "analysis_start_year",
        "analysis_end_year",
    ]
    missing = [
        key
        for key in required_keys
        if key not in snapshot_data or snapshot_data.get(key) in (None, "")
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise KeyError(
            "Metadata file is missing required snapshot keys: "
            f"{missing_text}. Check {METADATA_PATH}."
        )

    return snapshot_data


def build_payload() -> dict[str, Any]:
    """Build the JSON payload for the Apps Script webhook."""
    validate_environment()
    validate_required_files()
    validate_publishable_sizes()

    metadata = load_metadata()
    snapshot_data = extract_snapshot_metadata(metadata)

    payload = {
        "secret": os.environ["APPS_SCRIPT_SHARED_SECRET"],
        "snapshot_date": snapshot_data["snapshot_date"],
        "snapshot_label": snapshot_data["snapshot_label"],
        "analysis_start_year": snapshot_data["analysis_start_year"],
        "analysis_end_year": snapshot_data["analysis_end_year"],
    }
    for field_name, path in PUBLISHABLE_PATHS.items():
        payload[field_name] = read_file_base64(path)
    return payload


def publish_payload(payload: dict[str, Any]) -> None:
    """POST payload to the Apps Script web app."""
    webhook_url = os.environ["APPS_SCRIPT_WEBAPP_URL"]

    response = requests.post(
        webhook_url,
        json=payload,
        timeout=180,
    )

    if not response.ok:
        raise RuntimeError(
            "Apps Script webhook request failed with "
            f"HTTP {response.status_code}: {response.text}"
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Apps Script response is not valid JSON: {response.text}"
        ) from exc

    if body.get("status") != "ok":
        raise RuntimeError(f"Apps Script error: {body}")


def main() -> None:
    """Build and publish the payload."""
    load_dotenv()
    payload = build_payload()
    publish_payload(payload)
    print("[INFO] Apps Script webhook completed successfully.")


if __name__ == "__main__":
    main()
