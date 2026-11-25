"""How much safety margin do we need? Learn it from the forecast errors of the past year."""
import numpy as np
import pandas as pd
from engine import forecast


def past_errors(series, today, weather, use_weather, gap_days, train_start, days=365, min_history=150):
    """Relative errors (actual / forecast - 1) on days up to `today`, never using the future.

    +0.20 means the real count was 20% higher than forecast.
    """
    today = pd.Timestamp(today)
    gaps = [pd.Timestamp(d) for d in gap_days if pd.Timestamp(d) <= today]
    start = max(today - pd.Timedelta(days=days), pd.Timestamp(train_start) + pd.Timedelta(days=min_history))
    pred = forecast.backtest(series[series.index <= today], start.strftime("%Y-%m-%d"),
                             today.strftime("%Y-%m-%d"), weather, use_weather, gap_days=gaps)
    df = pd.DataFrame({"actual": series.reindex(pred.index), "forecast": pred}).drop(index=gaps, errors="ignore")
    return (df["actual"] / df["forecast"] - 1).dropna()


def buffer_for(errors, service_level):
    """Margin that would have been enough on `service_level` share of past days (never below 0)."""
    return max(0.0, float(errors.quantile(service_level)))