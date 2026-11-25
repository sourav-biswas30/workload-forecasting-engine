import io
import time
from pathlib import Path

import pandas as pd
import requests

URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.csv"
AGENCIES = ["HPD", "DOT", "DSNY"]
START = "2023-01-01T00:00:00"
END = "2024-12-31T23:59:59"
COLUMNS = ("unique_key,created_date,closed_date,agency,complaint_type,"
           "descriptor,borough,status,incident_zip")
PAGE = 50000  # rows per request


def fetch_page(params):
    r = requests.get(URL, params=params, timeout=120)
    r.raise_for_status()
    return r.text


def download_agency(agency, out_file, fetch=fetch_page, sleep=1):
    offset = 0
    total = 0
    first = True
    while True:
        params = {
            "$select": COLUMNS,
            "$where": (f"agency='{agency}' AND created_date >= '{START}' "
                       f"AND created_date <= '{END}'"),
            "$order": "unique_key",
            "$limit": PAGE,
            "$offset": offset,
        }
        text = fetch(params)
        if not text.strip():
            break
        df = pd.read_csv(io.StringIO(text), dtype=str)
        if df.empty:
            break
        df.to_csv(out_file, mode="w" if first else "a",
                  header=first, index=False)
        first = False
        total += len(df)
        offset += PAGE
        print(agency, "rows so far:", total)
        if len(df) < PAGE:
            break
        time.sleep(sleep)
    return total


if __name__ == "__main__":
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    for agency in AGENCIES:
        out_file = out_dir / f"311_{agency}.csv"
        n = download_agency(agency, out_file)
        print("saved", out_file, "-", n, "rows")