"""Free-text search on the public vehicle list.

The Showroom search box sends `?q=`. Before the parameter existed FastAPI
dropped it silently and the screen returned the whole catalogue for every
query — a failure that looks like working software. These tests exist to make
that failure mode loud: several of them would pass against a `q` that does
nothing, so each one asserts on what is EXCLUDED, not just what is found.
"""

import pytest

VEHICLES = "/api/v1/vehicles"


@pytest.fixture
def catalogue(vehicle_factory):
    """Three vehicles that differ on make, model and trim."""
    return {
        "corolla": vehicle_factory(make="Toyota", model="Corolla", trim="XLE", year=2024),
        "hilux": vehicle_factory(make="Toyota", model="Hilux", trim="SR5", year=2022),
        "dashing": vehicle_factory(make="Jetour", model="Dashing", trim="Flagship", year=2024),
    }


def _models(res) -> set[str]:
    return {item["model"] for item in res.json()["items"]}


def test_search_matches_the_model_and_excludes_the_rest(client, catalogue):
    res = client.get(VEHICLES, params={"q": "corolla"})
    assert res.status_code == 200
    assert _models(res) == {"Corolla"}, "q returned vehicles it should have filtered out"


def test_search_matches_the_make(client, catalogue):
    res = client.get(VEHICLES, params={"q": "jetour"})
    assert _models(res) == {"Dashing"}


def test_search_matches_the_trim(client, catalogue):
    res = client.get(VEHICLES, params={"q": "SR5"})
    assert _models(res) == {"Hilux"}


def test_search_is_case_insensitive(client, catalogue):
    assert _models(client.get(VEHICLES, params={"q": "HILUX"})) == {"Hilux"}


def test_multiple_terms_narrow_rather_than_widen(client, catalogue):
    """"toyota corolla" must not return every Toyota.

    If the terms were OR-ed together, matching "toyota" alone would pull in the
    Hilux — the single most likely way to get this wrong.
    """
    res = client.get(VEHICLES, params={"q": "toyota corolla"})
    assert _models(res) == {"Corolla"}


def test_no_match_returns_an_empty_list_not_everything(client, catalogue):
    res = client.get(VEHICLES, params={"q": "lamborghini"})
    assert res.status_code == 200
    assert res.json()["items"] == []
    assert res.json()["total"] == 0


def test_omitting_q_returns_the_whole_catalogue(client, catalogue):
    res = client.get(VEHICLES)
    assert _models(res) == {"Corolla", "Hilux", "Dashing"}


def test_blank_q_is_treated_as_no_filter(client, catalogue):
    """The input debounces to '' when cleared; that must not mean 'match nothing'."""
    res = client.get(VEHICLES, params={"q": "   "})
    assert res.status_code in (200, 422)
    if res.status_code == 200:
        assert _models(res) == {"Corolla", "Hilux", "Dashing"}


def test_search_is_public(client, catalogue):
    """The Showroom is browsable before sign-in."""
    assert client.get(VEHICLES, params={"q": "corolla"}).status_code == 200
