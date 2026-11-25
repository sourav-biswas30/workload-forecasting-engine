"""Do more complaint groups give a better workload forecast? Run from the project folder:
    python -m scripts.compare_groups
Tests 2024 month by month (each month predicted from earlier data only).
"""
import sqlite3
import numpy as np
import pandas as pd
import yaml
from engine import data, forecast, workload

cfg = yaml.safe_load(open("configs/hpd.yaml"))
conn = sqlite3.connect(cfg["db"])
weather = forecast.load_weather(cfg["weather_csv"])
gaps = pd.to_datetime(cfg["gap_days"])
A = cfg["agency"]

OPTIONS = {
    "2 groups (heat, other)": {"heat": ["HEAT/HOT WATER"]},
    "7 groups": {"heat": ["HEAT/HOT WATER"], "unsanitary": ["UNSANITARY CONDITION"],
                 "plumbing": ["PLUMBING"], "paint": ["PAINT/PLASTER"],
                 "door_window": ["DOOR/WINDOW"], "water_leak": ["WATER LEAK"]},
}

rows = []
for name, groups in OPTIONS.items():
    counts = data.daily_counts(conn, A, cfg["train_start"], "2024-12-31", groups=groups)
    w = workload.effort_weights(conn, A, groups, cfg["train_start"], "2024-12-31")
    counts = counts.loc[:, [g for g in counts.columns if counts[g].sum() > 0]]   # skip empty groups
    pred = {}
    for g in counts.columns:
        pred[g] = forecast.backtest(counts[g], "2024-01-01", "2024-12-31", weather, g == "heat", gap_days=gaps)
    idx = pred["heat"].index.difference(gaps)
    eff_pred = sum(pred[g].reindex(idx) * w[g] for g in counts.columns)
    eff_act = sum(counts[g].reindex(idx) * w[g] for g in counts.columns)
    err = eff_act / eff_pred - 1
    rows.append({"grouping": name,
                 "WAPE": (eff_act - eff_pred).abs().sum() / eff_act.sum(),
                 "average error": err.mean(),
                 "margin for 90% of days": err.quantile(0.90)})
res = pd.DataFrame(rows).set_index("grouping")
print((res * 100).round(1).astype(str).add("%").to_string())
print("\nLower is better for WAPE and for the margin needed.")