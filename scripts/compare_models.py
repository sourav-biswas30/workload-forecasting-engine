"""Baseline and model comparison on the SAME days. Run from the project folder:
    python -m scripts.compare_models
Every month of 2024 is predicted by a model trained only on earlier data.
"""
import sqlite3
import pandas as pd
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from engine import data, forecast

cfg = yaml.safe_load(open("configs/hpd.yaml"))
conn = sqlite3.connect(cfg["db"])
weather = forecast.load_weather(cfg["weather_csv"])
gaps_hpd = pd.to_datetime(cfg["gap_days"])

MODELS = {
    "Poisson regression (chosen)": lambda: PoissonRegressor(alpha=1.0, max_iter=1000),
    "Ridge": lambda: Ridge(alpha=1.0),
    "Gradient boosting": lambda: HistGradientBoostingRegressor(random_state=0),
    "Random forest": lambda: RandomForestRegressor(n_estimators=200, min_samples_leaf=3, random_state=0, n_jobs=-1),
}


def backtest_with(estimator_fn, series, weather, use_weather, gaps):
    s = forecast.fill_gaps(series, gaps) if len(gaps) else series.astype(float)
    f = forecast.build_features(s, weather, use_weather).dropna().drop(index=gaps, errors="ignore")
    feats = forecast.feature_names(use_weather)
    numeric = [c for c in feats if c != "weekday"]
    parts = []
    for m in pd.period_range("2024-01", "2024-12", freq="M"):
        train = f[f.index < m.start_time - pd.Timedelta(days=forecast.HORIZON)]
        test = f[(f.index >= m.start_time) & (f.index <= m.end_time.normalize())]
        prep = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), ["weekday"]),
                                  ("num", StandardScaler(), numeric)])
        model = make_pipeline(prep, estimator_fn())
        model.fit(train[feats], train["y"])
        parts.append(pd.Series(model.predict(test[feats]), index=test.index))
    return pd.concat(parts)


def wape(actual, pred):
    return float((actual - pred).abs().sum() / actual.sum())


rows = {}
for agency in ("DOT", "DSNY", "HPD"):
    series = data.daily_counts(conn, agency, cfg["train_start"], "2024-12-31")["all"]
    if series.sum() == 0:
        continue
    gaps = gaps_hpd if agency == "HPD" else pd.to_datetime([])
    use_w = agency == "HPD"                     # weather helps only HPD (heating)
    preds = {name: backtest_with(fn, series, weather, use_w, gaps) for name, fn in MODELS.items()}
    idx = preds["Ridge"].index.difference(gaps)
    actual = series.reindex(idx)
    base4 = pd.Series({d: forecast.baseline_same_weekday(series, d, 4) for d in idx})
    base1 = pd.Series({d: forecast.baseline_same_weekday(series, d, 1) for d in idx})
    rows.setdefault("baseline: average of last 4 weeks", {})[agency] = wape(actual, base4)
    rows.setdefault("baseline: same weekday last week", {})[agency] = wape(actual, base1)
    for name, p in preds.items():
        rows.setdefault(name, {})[agency] = wape(actual, p.reindex(idx))

print(pd.DataFrame(rows).T.round(3).to_string())
print("\nWAPE on the days of 2024 (lower is better). HPD excludes the broken-data days.")