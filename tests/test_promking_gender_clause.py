"""Regression tests for the pornstars.gender filter.

`pornstars.gender` is a Postgres ENUM (`gender`). Comparing it directly to
`ANY($N::text[])` raises `DataError: operator does not exist: gender = text[]`,
which FastAPI turns into a 500 and made every public list endpoint that
defaults to `actor_gender=female` look like "Catalog API unreachable".

Always cast the column to text on the comparison side so PG can match the
enum against text[].
"""
from pathlib import Path

import pytest

from app.routers.promking.videos import build_gender_clause


def test_concrete_gender_casts_enum_to_text():
    clause, params = build_gender_clause("female", "a.gender", next_param_index=5)
    assert clause == "(a.gender::text = ANY($5::text[]))"
    assert params == [["female"]]


def test_multiple_concrete_values():
    clause, params = build_gender_clause("female,trans", "pornstars.gender", 3)
    assert clause == "(pornstars.gender::text = ANY($3::text[]))"
    assert params == [["female", "trans"]]


def test_null_token_uses_is_null_without_params():
    clause, params = build_gender_clause("null", "a.gender", 9)
    assert clause == "a.gender IS NULL"
    assert params == []


def test_has_token_uses_is_not_null():
    clause, params = build_gender_clause("has", "pornstars.gender", 2)
    assert clause == "pornstars.gender IS NOT NULL"
    assert params == []


def test_mixed_concrete_and_null_uses_or():
    clause, params = build_gender_clause("female,null", "a.gender", 4)
    assert clause == "(a.gender::text = ANY($4::text[]) OR a.gender IS NULL)"
    assert params == [["female"]]


@pytest.mark.parametrize("value", [None, "", "all", "ALL", "All"])
def test_no_filter_returns_empty(value):
    clause, params = build_gender_clause(value, "a.gender", 1)
    assert clause == ""
    assert params == []


def test_uppercase_input_is_normalized():
    clause, params = build_gender_clause("FEMALE", "a.gender", 1)
    assert clause == "(a.gender::text = ANY($1::text[]))"
    assert params == [["female"]]


# Cross-module regression guard: taxonomies.py keeps an inline copy of the
# gender filter (different placeholder strategy), so a future refactor that
# drops the ::text cast there would silently re-break /taxonomies/pornstars.
# This check is intentionally a source-level grep so it survives even if the
# helper signature evolves.
def test_taxonomies_module_still_casts_gender_to_text():
    src = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "routers"
        / "promking"
        / "taxonomies.py"
    ).read_text()
    # Both list_terms and count_terms must keep the ::text cast.
    assert src.count(".gender::text = ANY(") >= 2, (
        "taxonomies.py must cast .gender to text in every ANY(...) comparison; "
        "without the cast Postgres raises DataError and the endpoint 500s."
    )
    assert ".gender = ANY(" not in src, (
        "taxonomies.py contains an unsafe `.gender = ANY(...)` comparison — "
        "Postgres can't match the gender enum against text[] without a cast."
    )
