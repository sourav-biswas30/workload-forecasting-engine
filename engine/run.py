"""One command: forecast a day, say how many inspectors are needed, and show alerts.

Example:  python -m engine.run --config configs/hpd.yaml --date 2024-12-18
"""
import argparse
import sqlite3
import pandas as pd
import yaml
from engine import anomaly, data, forecast, risk, workload


def alerts(conn, cfg, target, weather):
    """Look at the last days we know (up to two days before target) and report problems."""
    today = pd.Timestamp(target) - pd.Timedelta(days=forecast.HORIZON)
    series = data.daily_counts(conn, cfg["agency"], cfg["train_start"], str(today.date()))["all"]
    use_w = bool(cfg.get("weather_groups"))
    gaps = [pd.Timestamp(d) for d in cfg.get("gap_days", []) if pd.Timestamp(d) <= today]
    start = (today - pd.Timedelta(days=cfg.get("alert_history_days", 120))).strftime("%Y-%m-%d")
    pred = forecast.backtest(series, start, str(today.date()), weather, use_w, gap_days=gaps)
    last = today - pd.Timedelta(days=cfg.get("alert_days", 14) - 1)
    found = anomaly.find_anomalies(series, pred)
    found = found[(found.index >= last) & found["anomaly"] & ~found.index.isin(gaps)]
    holes = anomaly.find_data_gaps(series)
    holes = holes[(holes.index >= last) & ~holes.index.isin(gaps)]
    return found, holes

def safety_margin(conn, cfg, target, weather):
    """Buffer learned from the past year of forecast errors, for the configured service level."""
    today = pd.Timestamp(target) - pd.Timedelta(days=forecast.HORIZON)
    series = data.daily_counts(conn, cfg["agency"], cfg["train_start"], str(today.date()))["all"]
    errs = risk.past_errors(series, today, weather, bool(cfg.get("weather_groups")),
                            cfg.get("gap_days", []), cfg["train_start"])
    return errs, risk.buffer_for(errs, cfg.get("service_level", 0.90))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--date", required=True, help="the day to forecast, e.g. 2024-12-18")
    a = p.parse_args()
    cfg = yaml.safe_load(open(a.config))
    conn = sqlite3.connect(cfg["db"])
    weather = forecast.load_weather(cfg["weather_csv"])
    r = workload.forecast_workload(conn, cfg, a.date, weather)
    print(f"Forecast for {r['date']} ({cfg['agency']})")
    print("  expected requests :", r["requests"])
    print("  effort per request:", r["weights"])
    print("  total effort      :", r["effort"])
    errs, buf = safety_margin(conn, cfg, a.date, weather)
    level = cfg.get("service_level", 0.90)
    need = workload.inspectors_for(r["effort"], cfg["capacity_per_inspector"], buf)
    print(f"  safety margin     : +{buf:.0%} (enough on {level:.0%} of the last {len(errs)} days)")
    print("  inspectors needed :", need)
    found, holes = alerts(conn, cfg, a.date, weather)
    print("\nAlerts, last", cfg.get("alert_days", 14), "known days:")
    if found.empty and holes.empty:
        print("  none")
    for d, row in found.iterrows():
        print(f"  UNUSUAL VOLUME {d.date()}: actual {row.actual:.0f} vs forecast {row.forecast:.0f} (z={row.robust_z:.1f})")
    for d, row in holes.iterrows():
        print(f"  POSSIBLE DATA PROBLEM {d.date()}: {row['count']:.0f} requests, only {row.share_of_typical:.0%} of a typical day")


if __name__ == "__main__":
    main()