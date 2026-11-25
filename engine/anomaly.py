"""Alerts: compare what happened with what was forecast."""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar

def _robust_scale(x):
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def find_anomalies(actual, forecast, window=60, min_periods=30, threshold=3.0):
    """Business alarm: days where the forecast error is unusually large.

    Each day is judged only against the errors of the previous `window` days.
    """
    df = pd.DataFrame({"actual": actual.reindex(forecast.index), "forecast": forecast})
    df["rel_error"] = df["actual"] / df["forecast"] - 1
    past = df["rel_error"].shift(1)
    center = past.rolling(window, min_periods=min_periods).median()
    scale = past.rolling(window, min_periods=min_periods).apply(_robust_scale, raw=True)
    df["robust_z"] = (df["rel_error"] - center) / scale
    df["anomaly"] = df["robust_z"].abs() > threshold
    return df


def find_data_gaps(series, ratio=0.5, weeks=4, skip_holidays=True):
    """Data alarm: days far below the same weekday of the previous weeks (or zero).

    Only the low side is flagged on purpose: a high day can be a real event
    (a cold snap), while a near-empty day for a busy agency is a data problem.
    Federal holidays are skipped unless the count is exactly zero.
    """
    s = series.astype(float)
    ref = pd.concat([s.shift(7 * k) for k in range(1, weeks + 1)], axis=1).median(axis=1)
    out = pd.DataFrame({"count": s, "typical_same_weekday": ref})
    out["share_of_typical"] = out["count"] / out["typical_same_weekday"]
    flagged = out[(out["count"] == 0) | (out["share_of_typical"] < ratio)]
    if skip_holidays:
        holidays = USFederalHolidayCalendar().holidays(start=s.index.min(), end=s.index.max())
        flagged = flagged[(flagged["count"] == 0) | ~flagged.index.isin(holidays)]
    return flagged