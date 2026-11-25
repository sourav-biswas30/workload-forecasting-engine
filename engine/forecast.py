"""Forecast daily request counts two days ahead with Poisson regression."""
import numpy as np
import pandas as pd
from pandas.tseries.holiday import USFederalHolidayCalendar
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

HORIZON = 2   # we forecast the day after tomorrow: only data up to "today" is known

BASE_FEATS = ["weekday", "is_holiday", "lag2", "lag3", "lag7",
              "avg_last_7d", "avg_last_28d", "avg_same_weekday_4w"]
WEATHER_FEATS = ["tmin", "tmean", "tmin_today", "cold10", "tmin_change3"]


def feature_names(use_weather):
    return BASE_FEATS + (WEATHER_FEATS if use_weather else [])


def load_weather(path):
    """Daily weather saved earlier (columns temperature_2m_min / _mean / _max)."""
    return pd.read_csv(path, index_col=0, parse_dates=True)


def fill_gaps(series, gap_days):
    """Replace days with bad data by the average of the same weekday 2 and 3 weeks earlier."""
    s = series.astype(float).copy()
    for d in sorted(pd.to_datetime(list(gap_days))):
        s[d] = (s[d - pd.Timedelta(days=14)] + s[d - pd.Timedelta(days=21)]) / 2
    return s


def build_features(series, weather=None, use_weather=False):
    """One row per day: the value to predict ('y') and variables known 2 days earlier."""
    s = series.astype(float)
    idx = s.index
    holidays = USFederalHolidayCalendar().holidays(start=idx.min(), end=idx.max())
    f = pd.DataFrame(index=idx)
    f["y"] = s
    f["weekday"] = idx.day_of_week
    f["is_holiday"] = idx.isin(holidays).astype(int)
    f["lag2"] = s.shift(2)
    f["lag3"] = s.shift(3)
    f["lag7"] = s.shift(7)
    f["avg_last_7d"] = s.shift(2).rolling(7).mean()
    f["avg_last_28d"] = s.shift(2).rolling(28).mean()
    f["avg_same_weekday_4w"] = (s.shift(7) + s.shift(14) + s.shift(21) + s.shift(28)) / 4
    if use_weather:
        t_min = weather["temperature_2m_min"]
        f["tmin"] = t_min.reindex(idx)
        f["tmean"] = weather["temperature_2m_mean"].reindex(idx)
        f["tmin_today"] = t_min.shift(2).reindex(idx)
        f["cold10"] = (10 - t_min).clip(lower=0).reindex(idx)
        f["tmin_change3"] = (t_min - t_min.shift(3)).reindex(idx)
    return f


def _pipeline(feats):
    numeric = [c for c in feats if c != "weekday"]
    prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["weekday"]),
                              ("num", StandardScaler(), numeric)])
    return make_pipeline(prep, PoissonRegressor(alpha=1.0, max_iter=1000))


def fit_model(train, feats):
    model = _pipeline(feats)
    model.fit(train[feats], train["y"])
    return model


def backtest(series, start, end, weather=None, use_weather=False, gap_days=()):
    """Honest test: for each month, train only on data from before that month."""
    gaps = pd.to_datetime(list(gap_days))
    s = fill_gaps(series, gaps) if len(gaps) else series.astype(float)
    f = build_features(s, weather, use_weather).dropna().drop(index=gaps, errors="ignore")
    feats = feature_names(use_weather)
    parts = []
    for m in pd.period_range(start, end, freq="M"):
        m_start, m_end = m.start_time, m.end_time.normalize()
        train = f[f.index < m_start - pd.Timedelta(days=HORIZON)]
        test = f[(f.index >= m_start) & (f.index <= m_end)]
        if train.empty or test.empty:
            continue
        model = fit_model(train, feats)
        parts.append(pd.Series(model.predict(test[feats]), index=test.index))
    return pd.concat(parts)


def forecast_day(series, target_date, weather=None, use_weather=False, gap_days=()):
    """Predict the count for target_date, using only data up to two days before."""
    target = pd.Timestamp(target_date)
    today = target - pd.Timedelta(days=HORIZON)
    known = series[series.index <= today]
    gaps = pd.to_datetime([d for d in gap_days if pd.Timestamp(d) <= today])
    s = fill_gaps(known, gaps) if len(gaps) else known.astype(float)
    s = s.reindex(pd.date_range(s.index.min(), target))        # unknown days stay empty
    f = build_features(s, weather, use_weather)
    feats = feature_names(use_weather)
    train = f[f.index <= today].dropna().drop(index=gaps, errors="ignore")
    model = fit_model(train, feats)
    row = f.loc[[target], feats]
    if row.isna().values.any():
        raise ValueError("Missing inputs for the target day (is the weather available?)")
    return float(model.predict(row)[0])


def baseline_same_weekday(series, target_date, weeks=4):
    """Simple rule to beat: average of the same weekday over the last few weeks."""
    target = pd.Timestamp(target_date)
    days = [target - pd.Timedelta(days=7 * k) for k in range(1, weeks + 1)]
    return float(series.reindex(days).mean())