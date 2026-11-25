""" Run from the project folder:
    python -m scripts.check_bias
"""
import sqlite3
import numpy as np
import pandas as pd
import yaml
from engine import data, forecast

cfg = yaml.safe_load(open("configs/hpd.yaml"))
conn = sqlite3.connect(cfg["db"])
weather = forecast.load_weather(cfg["weather_csv"])
series = data.daily_counts(conn, cfg["agency"], cfg["train_start"], "2024-12-31")["all"]
gaps = pd.to_datetime(cfg["gap_days"])
pred = forecast.backtest(series, "2024-01-01", "2024-12-31", weather, bool(cfg["weather_groups"]), gap_days=gaps)
df = pd.DataFrame({"actual": series.reindex(pred.index), "forecast": pred}).drop(index=gaps, errors="ignore")
df["err"] = df["actual"] / df["forecast"] - 1          # +0.20 means 20% MORE requests than forecast

print("Days tested:", len(df))
print("Average error     :", f"{df['err'].mean():+.1%}", "(positive = forecast too low on average)")
print("Median error      :", f"{df['err'].median():+.1%}")
print("Days forecast too low :", f"{(df['err'] > 0).mean():.0%}")
print("Days too low by more than 20% :", f"{(df['err'] > 0.20).mean():.0%}")
print("\nIf we add a safety buffer, on how many days do we have enough?")
for b in (0, 0.10, 0.20, 0.30, 0.40):
    print(f"  buffer {b:.0%}: enough on {(df['err'] <= b).mean():.0%} of days")
for level in (0.90, 0.95):
    print(f"Buffer needed to be enough on {level:.0%} of days: {df['err'].quantile(level):+.0%}")
print("\nBy weekday (average error):")
print(df.groupby(df.index.day_name())["err"].mean().map("{:+.1%}".format).to_string())