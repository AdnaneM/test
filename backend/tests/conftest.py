import pytest

from tests.synthetic import simulate_league


@pytest.fixture(scope="session")
def league_df():
    df, truth = simulate_league(n_teams=18, n_seasons=6, seed=1)
    return df, truth
