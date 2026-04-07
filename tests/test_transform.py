"""Regression tests for transformation outputs."""

from __future__ import annotations

import math

import pandas as pd

from institutional_pipeline.transform import (
    KPIS_COLUMNS,
    PUBLICATIONS_COLUMNS,
    SDG_COLUMNS,
    build_kpis_yearly_df,
    build_outputs,
    build_publications_df,
    build_sdg_exploded_df,
)


def sample_raw_works() -> list[dict[str, object]]:
    """Build representative raw works for transformation tests."""
    return [
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.1234/example-1",
            "display_name": " First publication ",
            "publication_year": 2021,
            "primary_location": {"source": {"display_name": "Journal One"}},
            "type": "article",
            "cited_by_count": "5",
            "open_access": {"is_oa": True, "oa_status": "gold"},
            "primary_topic": {
                "display_name": "Sustainability",
                "field": {"display_name": "Medicine"},
            },
            "countries_distinct_count": 2,
            "institutions_distinct_count": "3",
            "fwci": "1.25",
            "citation_normalized_percentile": {"value": "0.91"},
            "sustainable_development_goals": [
                {
                    "id": "https://metadata.un.org/sdg/3",
                    "display_name": "Good Health and Well-being",
                    "score": "0.85",
                },
                {
                    "id": "https://metadata.un.org/sdg/4",
                    "display_name": "Quality Education",
                    "score": 0.55,
                },
            ],
        },
        {
            "id": "https://openalex.org/W2",
            "doi": None,
            "display_name": "Second publication",
            "publication_year": 2022,
            "primary_location": {"source": {"display_name": "Journal Two"}},
            "type": "review",
            "cited_by_count": 1,
            "open_access": {"is_oa": False, "oa_status": "closed"},
            "primary_topic": {
                "display_name": "Marine Science",
                "field": {"display_name": "Earth Sciences"},
            },
            "countries_distinct_count": 1,
            "institutions_distinct_count": 2,
            "fwci": 0.8,
            "citation_normalized_percentile": {"value": 0.35},
            "sustainable_development_goals": [],
        },
        {
            "id": "https://openalex.org/W3",
            "doi": "https://doi.org/10.1234/example-3",
            "display_name": "Third publication",
            "publication_year": 2022,
            "primary_location": {},
            "type": "article",
            "cited_by_count": None,
            "open_access": {},
            "primary_topic": {},
            "countries_distinct_count": None,
            "institutions_distinct_count": None,
            "fwci": "not-a-number",
            "citation_normalized_percentile": {"value": "not-a-number"},
            "sustainable_development_goals": [
                {
                    "id": "https://metadata.un.org/sdg/14",
                    "display_name": "Life Below Water",
                    "score": "not-a-number",
                }
            ],
        },
        "ignore-me",
    ]


def test_build_publications_df_normalizes_core_fields() -> None:
    """Publications output should normalize raw OpenAlex work fields."""
    publications_df = build_publications_df(sample_raw_works())

    assert list(publications_df.columns) == PUBLICATIONS_COLUMNS
    assert len(publications_df.index) == 3

    first_row = publications_df.iloc[0].to_dict()
    assert first_row["work_id"] == "https://openalex.org/W1"
    assert first_row["title"] == "First publication"
    assert first_row["journal_title"] == "Journal One"
    assert first_row["is_oa"] is True
    assert first_row["oa_status"] == "gold"
    assert first_row["countries_distinct_count"] == 2
    assert first_row["institutions_distinct_count"] == 3
    assert first_row["fwci"] == 1.25
    assert first_row["citation_normalized_percentile_value"] == 0.91
    assert first_row["fields"] == "Medicine"
    assert first_row["sdg_count"] == 2

    third_row = publications_df.iloc[2].to_dict()
    assert pd.isna(third_row["journal_title"])
    assert pd.isna(third_row["oa_status"])
    assert pd.isna(third_row["fwci"])
    assert pd.isna(third_row["citation_normalized_percentile_value"])
    assert pd.isna(third_row["fields"])
    assert third_row["sdg_count"] == 1


def test_build_sdg_exploded_df_extracts_rows_and_scores() -> None:
    """Exploded SDG output should flatten goals and coerce invalid scores."""
    sdg_exploded_df = build_sdg_exploded_df(sample_raw_works())

    assert list(sdg_exploded_df.columns) == SDG_COLUMNS
    assert len(sdg_exploded_df.index) == 4

    first_row = sdg_exploded_df.iloc[0].to_dict()
    assert first_row["work_id"] == "https://openalex.org/W1"
    assert first_row["sdg_code"] == "3"
    assert first_row["sdg_label"] == "Good Health and Well-being"
    assert math.isclose(first_row["score"], 0.85)

    third_row = sdg_exploded_df.iloc[2].to_dict()
    assert third_row["work_id"] == "https://openalex.org/W2"
    assert pd.isna(third_row["sdg_code"])
    assert pd.isna(third_row["sdg_label"])
    assert pd.isna(third_row["score"])

    fourth_row = sdg_exploded_df.iloc[3].to_dict()
    assert fourth_row["sdg_code"] == "14"
    assert pd.isna(fourth_row["score"])


def test_build_kpis_yearly_df_keeps_closed_window_and_calculates_metrics() -> None:
    """Yearly KPIs should cover every year and aggregate OA and SDG metrics."""
    publications_df = build_publications_df(sample_raw_works())
    sdg_exploded_df = build_sdg_exploded_df(sample_raw_works())

    kpis_df = build_kpis_yearly_df(
        publications_df=publications_df,
        sdg_exploded_df=sdg_exploded_df,
        start_year=2020,
        end_year=2022,
    )

    assert list(kpis_df.columns) == KPIS_COLUMNS
    assert kpis_df["publication_year"].tolist() == [2020, 2021, 2022]

    year_2020 = kpis_df[kpis_df["publication_year"] == 2020].iloc[0].to_dict()
    assert year_2020["total_publications"] == 0
    assert year_2020["oa_share"] == 0.0

    year_2021 = kpis_df[kpis_df["publication_year"] == 2021].iloc[0].to_dict()
    assert year_2021["total_publications"] == 1
    assert year_2021["total_oa_publications"] == 1
    assert year_2021["total_sdg_mentions"] == 2
    assert year_2021["publications_with_sdg"] == 1
    assert year_2021["avg_citations"] == 5.0
    assert year_2021["oa_share"] == 1.0

    year_2022 = kpis_df[kpis_df["publication_year"] == 2022].iloc[0].to_dict()
    assert year_2022["total_publications"] == 2
    assert year_2022["total_oa_publications"] == 0
    assert year_2022["total_sdg_mentions"] == 1
    assert year_2022["publications_with_sdg"] == 1
    assert year_2022["avg_citations"] == 0.5
    assert year_2022["oa_share"] == 0.0


def test_build_outputs_returns_the_three_publishable_dataframes() -> None:
    """Combined output builder should keep the three ETL tables in sync."""
    publications_df, sdg_exploded_df, kpis_df = build_outputs(
        raw_works=sample_raw_works(),
        start_year=2021,
        end_year=2022,
    )

    assert len(publications_df.index) == 3
    assert len(sdg_exploded_df.index) == 4
    assert kpis_df["publication_year"].tolist() == [2021, 2022]
