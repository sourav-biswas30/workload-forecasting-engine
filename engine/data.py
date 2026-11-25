"""Load and clean 311-style request data."""
import pandas as pd

CLEAN_SQL = """
CREATE TABLE requests_clean AS
SELECT
    unique_key, agency, upper(complaint_type) AS complaint_type, descriptor,
    borough, status, incident_zip,
    substr(created_date, 1, 19) AS created_ts,
    substr(created_date, 1, 10) AS created_day,
    CASE WHEN closed_date IS NULL OR closed_date = '' THEN NULL
         ELSE substr(closed_date, 1, 19) END AS closed_ts,
    quality_flag,
    CASE WHEN quality_flag = 'ok'
         THEN (julianday(closed_date) - julianday(created_date)) * 24 END AS resolution_hours
FROM (
    SELECT *,
        CASE WHEN closed_date IS NULL OR closed_date = '' THEN 'no_close_date'
             WHEN closed_date < created_date THEN 'closed_before_created'
             WHEN closed_date = created_date THEN 'closed_instantly'
             ELSE 'ok' END AS quality_flag
    FROM requests_raw
)
"""


def build_clean_table(conn):
    """Rebuild requests_clean from requests_raw (complaint types upper-cased)."""
    conn.execute("DROP TABLE IF EXISTS requests_clean")
    conn.execute(CLEAN_SQL)
    conn.commit()


def daily_counts(conn, agency, start, end, groups=None):
    """Requests per day for one agency.

    groups: optional dict like {"heat": ["HEAT/HOT WATER"]}. The result then has one
    column per group plus 'other'. Without groups there is a single column 'all'.
    """
    df = pd.read_sql(
        """SELECT created_day AS day, complaint_type AS ctype, COUNT(*) AS n
           FROM requests_clean
           WHERE agency = ? AND created_day BETWEEN ? AND ?
           GROUP BY created_day, complaint_type""",
        conn, params=(agency, start, end))
    df["day"] = pd.to_datetime(df["day"])
    df["ctype"] = df["ctype"].str.upper()
    groups = groups or {}
    lookup = {t.upper(): g for g, types in groups.items() for t in types}
    df["group"] = df["ctype"].map(lookup).fillna("other" if groups else "all")
    out = df.pivot_table(index="day", columns="group", values="n", aggfunc="sum")
    for col in list(groups) + (["other"] if groups else ["all"]):
        if col not in out.columns:
            out[col] = 0.0
    out = out[list(groups) + (["other"] if groups else ["all"])]
    return out.reindex(pd.date_range(start, end)).fillna(0.0)