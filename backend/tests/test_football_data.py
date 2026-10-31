from pathlib import Path

from edgebet.data.teams import TeamResolver, normalize_name
from edgebet.sports.football.football_data_uk import parse, season_code, season_label, season_start_years

SAMPLE = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HTHG,HTAG,HTR,HS,AS,HST,AST,HC,AC,PSH,PSD,PSA,AvgH,AvgD,AvgA,MaxH,MaxD,MaxA,P>2.5,P<2.5,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA,,
F1,16/08/2024,20:45,Le Havre,Paris SG,1,4,A,0,2,A,7,15,2,8,3,6,9.5,5.9,1.3,8.9,5.6,1.31,9.9,6.2,1.34,1.5,2.7,10.2,6.1,1.29,9.5,5.9,1.3,,
F1,17/08/2024,17:00,Brest,Marseille,1,5,A,0,2,A,10,14,4,9,5,4,3.1,3.5,2.3,3.05,3.4,2.35,3.2,3.6,2.4,1.9,2.0,3.2,3.5,2.25,3.1,3.4,2.3,,
F1,18/08/2024,,Lyon,Rennes,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,,
"""


def test_parse_sample(tmp_path: Path):
    p = tmp_path / "2425_F1.csv"
    p.write_text(SAMPLE, encoding="utf-8")
    df = parse(p, "F1", 2024)
    assert len(df) == 2  # la ligne sans score est ignorée
    row = df.iloc[0]
    assert row["home"] == "Le Havre" and row["away"] == "Paris SG"
    assert row["hg"] == 1 and row["ag"] == 4 and row["result"] == "A"
    assert row["date"].hour == 20 and row["date"].minute == 45
    assert row["odds_ps_a"] == 1.3 and row["odds_psc_h"] == 10.2 and row["odds_avgc_a"] == 1.3
    assert row["odds_ps_over25"] == 1.5
    assert row["season"] == "2024-25" and row["league"] == "F1"
    assert row["match_id"] == "F1:2024-08-16:le-havre:paris-sg"


def test_season_helpers():
    assert season_code(2024) == "2425" and season_label(1999) == "1999-00"
    from datetime import date

    assert season_start_years(3, date(2026, 10, 31)) == [2024, 2025, 2026]
    assert season_start_years(1, date(2026, 3, 1)) == [2025]


def test_team_resolver_aliases_and_fuzzy():
    r = TeamResolver.from_yaml()
    assert r.resolve("Paris Saint Germain") == "Paris SG"
    assert r.resolve("Olympique de Marseille") == "Marseille"
    assert r.resolve("Manchester United") == "Man United"
    assert r.resolve("Atlético Madrid") == "Ath Madrid"
    assert r.resolve("Borussia Mönchengladbach") == "M'gladbach"
    assert r.resolve("Stade Brestois 29", candidates=["Brest", "Lyon"]) == "Brest"
    assert r.resolve("AS Saint-Étienne", candidates=["St Etienne", "Reims"]) == "St Etienne"
    assert normalize_name("Saint-Étienne") == "saint etienne"
    assert r.resolve("Club Totalement Inconnu", candidates=["Brest", "Lyon"]) is None
