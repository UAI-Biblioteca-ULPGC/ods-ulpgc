"""Data transformation utilities from raw OpenAlex works to analytical outputs."""

from __future__ import annotations

from typing import Any

import pandas as pd

PUBLICATIONS_COLUMNS = [
    "work_id",
    "doi",
    "title",
    "publication_year",
    "journal_title",
    "type",
    "cited_by_count",
    "is_oa",
    "oa_status",
    "countries_distinct_count",
    "institutions_distinct_count",
    "fwci",
    "citation_normalized_percentile_value",
    "fields",
    "sdg_count",
]

SDG_COLUMNS = [
    "work_id",
    "publication_year",
    "sdg_code",
    "sdg_label",
    "score",
]

KPIS_COLUMNS = [
    "publication_year",
    "total_publications",
    "total_oa_publications",
    "oa_share",
    "total_sdg_mentions",
    "publications_with_sdg",
    "avg_citations",
]


def _safe_str(value: Any) -> str | None:
    """Convert a value to stripped string, returning ``None`` for empties."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_journal_title(work: dict[str, Any]) -> str | None:
    """Extract source title from OpenAlex primary_location when available."""
    primary_location = work.get("primary_location")
    if not isinstance(primary_location, dict):
        return None
    source = primary_location.get("source")
    if not isinstance(source, dict):
        return None
    return _safe_str(source.get("display_name"))


def _extract_field(work: dict[str, Any]) -> str | None:
    """Extract field label from the work primary topic hierarchy."""
    primary_topic = work.get("primary_topic")
    if not isinstance(primary_topic, dict):
        return None
    field = primary_topic.get("field")
    if not isinstance(field, dict):
        return None
    return _safe_str(field.get("display_name"))


def _extract_is_oa(work: dict[str, Any]) -> bool:
    """Extract Open Access boolean flag from OpenAlex payload."""
    open_access = work.get("open_access")
    if not isinstance(open_access, dict):
        return False
    return bool(open_access.get("is_oa", False))


def _extract_oa_status(work: dict[str, Any]) -> str | None:
    """Extract Open Access status from OpenAlex payload."""
    open_access = work.get("open_access")
    if not isinstance(open_access, dict):
        return None
    return _safe_str(open_access.get("oa_status"))


def _extract_citation_normalized_percentile_value(work: dict[str, Any]) -> float | None:
    """Extract citation normalized percentile value from nested OpenAlex payload."""
    percentile = work.get("citation_normalized_percentile")
    if not isinstance(percentile, dict):
        return None
    value = pd.to_numeric(percentile.get("value"), errors="coerce")
    return float(value) if pd.notna(value) else None


def _extract_sdg_rows(work: dict[str, Any]) -> list[dict[str, Any]]:
    """Explode SDG entries for a single work into row dictionaries."""
    work_id = _safe_str(work.get("id"))
    publication_year = work.get("publication_year")

    raw_sdgs = work.get("sustainable_development_goals")
    if not isinstance(raw_sdgs, list):
        return []

    rows: list[dict[str, Any]] = []
    for sdg in raw_sdgs:
        if not isinstance(sdg, dict):
            continue
        sdg_id = sdg.get("id")
        sdg_code = _safe_str(sdg_id.split("/")[-1] if isinstance(sdg_id, str) else None)

        score = pd.to_numeric(sdg.get("score"), errors="coerce")
        rows.append(
            {
                "work_id": work_id,
                "publication_year": publication_year,
                "sdg_code": sdg_code,
                "sdg_label": _safe_str(sdg.get("display_name")),
                "score": float(score) if pd.notna(score) else None,
            }
        )
    return rows


def build_publications_df(raw_works: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the publications output DataFrame from raw OpenAlex works."""
    rows: list[dict[str, Any]] = []
    for work in raw_works:
        if not isinstance(work, dict):
            continue

        sdg_entries = work.get("sustainable_development_goals")
        sdg_count = len(sdg_entries) if isinstance(sdg_entries, list) else 0

        rows.append(
            {
                "work_id": _safe_str(work.get("id")),
                "doi": _safe_str(work.get("doi")),
                "title": _safe_str(work.get("display_name")),
                "publication_year": work.get("publication_year"),
                "journal_title": _extract_journal_title(work),
                "type": _safe_str(work.get("type")),
                "cited_by_count": pd.to_numeric(
                    work.get("cited_by_count", 0), errors="coerce"
                ),
                "is_oa": _extract_is_oa(work),
                "oa_status": _extract_oa_status(work),
                "countries_distinct_count": pd.to_numeric(
                    work.get("countries_distinct_count"), errors="coerce"
                ),
                "institutions_distinct_count": pd.to_numeric(
                    work.get("institutions_distinct_count"), errors="coerce"
                ),
                "fwci": pd.to_numeric(work.get("fwci"), errors="coerce"),
                "citation_normalized_percentile_value": _extract_citation_normalized_percentile_value(work),
                "fields": _extract_field(work),
                "sdg_count": sdg_count,
            }
        )

    return pd.DataFrame(rows, columns=PUBLICATIONS_COLUMNS)


def build_sdg_exploded_df(raw_works: list[dict[str, Any]]) -> pd.DataFrame:
    """Build the exploded publication-SDG DataFrame."""
    rows: list[dict[str, Any]] = []
    for work in raw_works:
        if isinstance(work, dict):
            rows.extend(_extract_sdg_rows(work))
    return pd.DataFrame(rows, columns=SDG_COLUMNS)


def build_kpis_yearly_df(
    publications_df: pd.DataFrame,
    sdg_exploded_df: pd.DataFrame,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Build yearly KPIs for every year in the analysis window."""
    years = pd.DataFrame({"publication_year": list(range(start_year, end_year + 1))})

    if publications_df.empty:
        return years.assign(
            total_publications=0,
            total_oa_publications=0,
            oa_share=0.0,
            total_sdg_mentions=0,
            publications_with_sdg=0,
            avg_citations=0.0,
        )[KPIS_COLUMNS]

    pubs = publications_df.copy()
    pubs["publication_year"] = pd.to_numeric(
        pubs["publication_year"], errors="coerce"
    ).astype("Int64")
    pubs["is_oa"] = pubs["is_oa"].fillna(False).astype(bool)
    pubs["cited_by_count"] = pd.to_numeric(
        pubs["cited_by_count"], errors="coerce"
    ).fillna(0)

    yearly = pubs.groupby("publication_year", dropna=True).agg(
        total_publications=("work_id", "count"),
        total_oa_publications=("is_oa", "sum"),
        avg_citations=("cited_by_count", "mean"),
    )

    sdg_mentions = pd.DataFrame(columns=["publication_year", "total_sdg_mentions"])
    publications_with_sdg = pd.DataFrame(
        columns=["publication_year", "publications_with_sdg"]
    )
    if not sdg_exploded_df.empty:
        sdg = sdg_exploded_df.copy()
        sdg["publication_year"] = pd.to_numeric(
            sdg["publication_year"], errors="coerce"
        ).astype("Int64")

        sdg_mentions = (
            sdg.groupby("publication_year", dropna=True)
            .size()
            .rename("total_sdg_mentions")
            .reset_index()
        )

        publications_with_sdg = (
            sdg.dropna(subset=["work_id"])
            .groupby("publication_year", dropna=True)["work_id"]
            .nunique()
            .rename("publications_with_sdg")
            .reset_index()
        )

    kpis = (
        years.merge(yearly.reset_index(), on="publication_year", how="left")
        .merge(sdg_mentions, on="publication_year", how="left")
        .merge(publications_with_sdg, on="publication_year", how="left")
        .fillna(0)
    )

    kpis["oa_share"] = kpis.apply(
        lambda row: (
            float(row["total_oa_publications"]) / float(row["total_publications"])
            if row["total_publications"]
            else 0.0
        ),
        axis=1,
    )

    for column in [
        "total_publications",
        "total_oa_publications",
        "total_sdg_mentions",
        "publications_with_sdg",
    ]:
        kpis[column] = kpis[column].astype(int)

    kpis["avg_citations"] = kpis["avg_citations"].astype(float)
    kpis["oa_share"] = kpis["oa_share"].astype(float)

    return kpis[KPIS_COLUMNS].sort_values("publication_year").reset_index(drop=True)


def build_outputs(
    raw_works: list[dict[str, Any]],
    start_year: int,
    end_year: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build all output DataFrames from raw works in a single call."""
    publications_df = build_publications_df(raw_works)
    sdg_exploded_df = build_sdg_exploded_df(raw_works)
    kpis_yearly_df = build_kpis_yearly_df(
        publications_df=publications_df,
        sdg_exploded_df=sdg_exploded_df,
        start_year=start_year,
        end_year=end_year,
    )
    return publications_df, sdg_exploded_df, kpis_yearly_df
