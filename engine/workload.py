"""Turn request counts into workload (effort) and number of inspectors."""
import math
import pandas as pd
from engine import data, forecast


def effort_weights(conn, agency, groups, start, end):
    """Effort of one request, per group, relative to the overall typical request.

    Effort = median resolution hours of the group / median of all requests.
    It is a proxy (waiting time), not real working hours. Only rows with quality_flag = 'ok'.
    """
    df = pd.read_sql(
        """SELECT complaint_type AS ctype, resolution_hours AS h FROM requests_clean
           WHERE agency = ? AND quality_flag = 'ok' AND created_day BETWEEN ? AND ?""",
        conn, params=(agency, start, end))
    lookup = {t.upper(): g for g, types in groups.items() for t in types}
    df["group"] = df["ctype"].str.upper().map(lookup).fillna("other")
    overall = df["h"].median()
    return (df.groupby("group")["h"].median() / overall).to_dict()

def inspectors_for(effort, capacity, buffer):
    """Inspectors needed for an effort, with a safety margin (buffer = 0.10 means +10%)."""
    return max(1, math.ceil(round(effort * (1 + buffer) / capacity, 6)))

def forecast_workload(conn, cfg, target_date, weather):
    """Forecast requests per group for target_date, then convert to effort and inspectors."""
    t = pd.Timestamp(target_date)
    train_end = t - pd.Timedelta(days=forecast.HORIZON)
    counts = data.daily_counts(conn, cfg["agency"], cfg["train_start"], str(train_end.date()),
                               groups=cfg["groups"])
    weights = effort_weights(conn, cfg["agency"], cfg["groups"], cfg["train_start"], str(train_end.date()))
    rows = {}
    for g in counts.columns:
        use_w = g in cfg.get("weather_groups", [])
        rows[g] = forecast.forecast_day(counts[g], t, weather, use_w, cfg.get("gap_days", []))
    effort = sum(rows[g] * weights[g] for g in rows)
    need = inspectors_for(effort, cfg["capacity_per_inspector"], cfg["buffer"])
    return {"date": str(t.date()), "requests": {g: round(v) for g, v in rows.items()},
            "weights": {g: round(w, 2) for g, w in weights.items()},
            "effort": round(effort, 1), "inspectors": need}




def split_other(conn, cfg, target_date, other_forecast, top=6, days=90):
    """Estimated split of the 'other' forecast by complaint type.

    Each type gets its share of the last `days` known days (not a separate model).
    Returns {type: expected requests}, the `top` biggest types plus 'REST'.
    """
    today = pd.Timestamp(target_date) - pd.Timedelta(days=forecast.HORIZON)
    start = today - pd.Timedelta(days=days - 1)
    df = pd.read_sql(
        """SELECT complaint_type AS ctype, COUNT(*) AS n FROM requests_clean
           WHERE agency = ? AND created_day BETWEEN ? AND ? GROUP BY complaint_type""",
        conn, params=(cfg["agency"], str(start.date()), str(today.date())))
    named = {t.upper() for types in cfg["groups"].values() for t in types}
    df = df[~df["ctype"].str.upper().isin(named)].sort_values("n", ascending=False)
    share = df.set_index("ctype")["n"] / df["n"].sum()
    out = (share.head(top) * other_forecast).to_dict()
    out["REST"] = float(share.iloc[top:].sum() * other_forecast)
    return {k: round(v) for k, v in out.items()}