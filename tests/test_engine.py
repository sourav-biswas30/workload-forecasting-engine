"""Small safety tests. Run with:  pytest -q"""
import sqlite3
import numpy as np
import pandas as pd
from engine import allocate, anomaly, data


def _tasks(n=60, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"task_id": range(n), "effort": rng.choice([0.4, 1.0, 2.4], n),
                         "urgency": rng.random(n)})


def test_every_task_assigned_exactly_once():
    t = _tasks()
    for solve in (allocate.solve_round_robin, allocate.solve_greedy):
        a = solve(t, 5)
        assert sorted(a.index) == list(t["task_id"])
        assert a.between(0, 4).all()
    a = allocate.solve_optimal(t, 5, time_limit=2)
    assert sorted(a.index) == list(t["task_id"]) and a.between(0, 4).all()


def test_optimal_is_not_worse_than_greedy():
    t = _tasks()
    g = allocate.kpis(t, allocate.solve_greedy(t, 5), 5)["max_load"]
    o = allocate.kpis(t, allocate.solve_optimal(t, 5, time_limit=2), 5)["max_load"]
    assert o <= g + 1e-9


def test_inspectors_needed_uses_buffer():
    assert allocate.inspectors_needed(100, 10, buffer=0.10) == 11


def test_spike_is_flagged_as_anomaly():
    idx = pd.date_range("2024-01-01", periods=120)
    forecast = pd.Series(1000.0, index=idx)
    rng = np.random.default_rng(1)
    actual = pd.Series(1000 * (1 + rng.normal(0, 0.03, 120)), index=idx)
    actual.iloc[100] = 2500
    res = anomaly.find_anomalies(actual, forecast)
    assert res["anomaly"].iloc[100]
    assert res["anomaly"].sum() <= 3


def test_empty_day_is_flagged_as_data_gap():
    idx = pd.date_range("2024-01-01", periods=60)
    s = pd.Series(500.0, index=idx)
    s.iloc[50] = 0
    assert idx[50] in anomaly.find_data_gaps(s).index


def test_complaint_types_are_merged_regardless_of_case():
    conn = sqlite3.connect(":memory:")
    conn.execute("""CREATE TABLE requests_raw (unique_key, agency, complaint_type, descriptor,
                    borough, status, incident_zip, created_date, closed_date)""")
    rows = [(1, "HPD", "Heat/Hot Water", "", "", "", "", "2024-01-01T10:00:00", "2024-01-01T15:00:00"),
            (2, "HPD", "HEAT/HOT WATER", "", "", "", "", "2024-01-01T11:00:00", "2024-01-01T12:00:00")]
    conn.executemany("INSERT INTO requests_raw VALUES (?,?,?,?,?,?,?,?,?)", rows)
    data.build_clean_table(conn)
    out = data.daily_counts(conn, "HPD", "2024-01-01", "2024-01-02", groups={"heat": ["HEAT/HOT WATER"]})
    assert out.loc["2024-01-01", "heat"] == 2 and out.loc["2024-01-01", "other"] == 0




def test_buffer_for_matches_service_level():
    from engine import risk
    errs = pd.Series(np.linspace(-0.2, 0.4, 101))      # 101 errors from -20% to +40%
    assert abs(risk.buffer_for(errs, 0.90) - 0.34) < 1e-9
    assert risk.buffer_for(pd.Series([-0.3, -0.1]), 0.90) == 0.0   # never negative




def test_split_of_other_adds_up():
    from engine import workload
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE requests_clean (agency, complaint_type, created_day)")
    rows = [("HPD", "HEAT/HOT WATER", "2024-01-05")] * 50 + [("HPD", "PLUMBING", "2024-01-05")] * 30 + \
           [("HPD", "ELECTRIC", "2024-01-06")] * 20
    conn.executemany("INSERT INTO requests_clean VALUES (?,?,?)", rows)
    cfg = {"agency": "HPD", "groups": {"heat": ["HEAT/HOT WATER"]}}
    out = workload.split_other(conn, cfg, "2024-01-08", 1000, top=1)
    assert out == {"PLUMBING": 600, "REST": 400}