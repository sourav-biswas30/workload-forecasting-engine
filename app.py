"""Web interface. Start with:  streamlit run app.py"""
import glob
import sqlite3
import altair as alt
import pandas as pd
import streamlit as st
import yaml
from engine import data, forecast, risk, workload
from engine.run import alerts, safety_margin

st.set_page_config(page_title="Workload forecast", layout="wide")
st.title("Staffing forecast: how many inspectors do we need?")

configs = sorted(glob.glob("configs/*.yaml"))
with st.sidebar:
    st.header("Settings")
    cfg_path = st.selectbox("Department config", configs)
    cfg = yaml.safe_load(open(cfg_path))
    conn0 = sqlite3.connect(cfg["db"])
    last_day = pd.to_datetime(conn0.execute(
        "SELECT MAX(created_day) FROM requests_clean WHERE agency = ?", (cfg["agency"],)).fetchone()[0])
    conn0.close()
    first_ok = pd.Timestamp(cfg["train_start"]) + pd.Timedelta(days=240)
    target = st.date_input("Day to forecast", value=last_day - pd.Timedelta(days=13),
                           min_value=first_ok, max_value=last_day)
    capacity = st.number_input("Capacity per inspector (effort units/day)", 1.0, 1000.0,
                               float(cfg["capacity_per_inspector"]))
    level = st.slider("Service level: share of days with enough inspectors", 0.50, 0.95,
                      float(cfg.get("service_level", 0.90)), 0.05,
                      help="0.90 means: in the past year, this safety margin would have been enough on 90% of days.")
    st.caption("Demo mode: the data ends on " + str(last_day.date()) +
               ", so we forecast a past day using only data up to two days before it.")


@st.cache_data(show_spinner="Training the model and checking the last year of errors...")
def compute(cfg_path, target):
    c = yaml.safe_load(open(cfg_path))
    conn = sqlite3.connect(c["db"])
    weather = forecast.load_weather(c["weather_csv"])
    res = workload.forecast_workload(conn, c, str(target), weather)
    found, holes = alerts(conn, c, str(target), weather)
    errs, _ = safety_margin(conn, c, str(target), weather)
    split = workload.split_other(conn, c, str(target), res["requests"].get("other", 0))
    t = pd.Timestamp(target)
    series = data.daily_counts(conn, c["agency"], str((t - pd.Timedelta(days=60)).date()), str(t.date()))["all"]
    conn.close()
    return res, found, holes, series, errs, split


res, found, holes, series, errs, split = compute(cfg_path, str(target))
buf = risk.buffer_for(errs, level)
inspectors = workload.inspectors_for(res["effort"], capacity, buf)
t = pd.Timestamp(target)
today = t - pd.Timedelta(days=forecast.HORIZON)
total_req = sum(res["requests"].values())

st.subheader(f"{cfg['agency']} · {t.strftime('%A %d %B %Y')}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Inspectors needed", inspectors)
c2.metric("Expected requests", f"{total_req:,}")
c3.metric("Total effort", f"{res['effort']:,.0f}")
c4.metric("Safety margin", f"+{buf:.0%}")
st.caption(f"Inspectors = effort × (1 + margin) ÷ capacity. The margin is learned from the last {len(errs)} days of "
           f"forecast errors: at {level:.0%} service level it would have been enough on {level:.0%} of those days.")

left, right = st.columns([3, 2])
with left:
    known = pd.DataFrame({"day": series[series.index <= today].index, "actual": series[series.index <= today].values})
    known = known[known["day"] > today - pd.Timedelta(days=35)]
    xax = alt.X("day:T", title=None, axis=alt.Axis(format="%a %d %b", tickCount="week", labelAngle=-45))
    base = alt.Chart(known).mark_line(point=True).encode(
        x=xax, y=alt.Y("actual:Q", title="Requests per day"),
        tooltip=[alt.Tooltip("day:T", title="Day", format="%a %d %b %Y"), alt.Tooltip("actual:Q", title="Requests")])
    pts = [{"day": t, "value": total_req, "what": "Forecast"}]
    if series.index.max() >= t:
        pts.append({"day": t, "value": float(series[t]), "what": "What really happened (demo only)"})
    marks = alt.Chart(pd.DataFrame(pts)).mark_point(size=160, filled=True).encode(
        x=xax, y="value:Q", color=alt.Color("what:N", title=None),
        tooltip=[alt.Tooltip("what:N", title=""), alt.Tooltip("value:Q", title="Requests", format=",.0f")])
    st.altair_chart((base + marks).properties(height=320), width="stretch")
    st.caption("Line: requests we already know (up to two days before). Dot: the forecast.")
with right:
    st.markdown("**Breakdown**")
    table = pd.DataFrame({"expected requests": res["requests"], "effort per request": res["weights"]})
    table["effort"] = (table["expected requests"] * table["effort per request"]).round(0)
    st.dataframe(table, width="stretch")
    st.caption("Heat requests are many but quick; other types are fewer but heavier.")
    st.markdown("**What is inside 'other' (estimate)**")
    st.dataframe(pd.DataFrame({"expected requests": split}), width="stretch")
    st.caption("Estimate: the 'other' forecast split by each type's share of the last 90 days. Not a separate model.")

st.subheader("Alerts in the last 14 known days")
if found.empty and holes.empty:
    st.success("No alerts.")
for d, row in found.iterrows():
    st.warning(f"**Unusual volume {d.date()}** — actual {row.actual:.0f} vs forecast {row.forecast:.0f} (z = {row.robust_z:.1f})")
for d, row in holes.iterrows():
    st.error(f"**Possible data problem {d.date()}** — {row['count']:.0f} requests, only {row.share_of_typical:.0%} of a typical day")

with st.expander("How this works"):
    st.write("Poisson regression forecasts requests two days ahead (weekday, holidays, recent levels, "
             "weather for heat). Counts are converted to effort with the median resolution time of each "
             "type, then to inspectors with the capacity and the safety margin. The margin is learned from "
             "the forecast errors of the past year. Alerts compare actual days with forecast errors of the "
             "previous 60 days. Effort is a proxy; capacity is an assumption.")