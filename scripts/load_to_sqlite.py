import sqlite3
from pathlib import Path

import pandas as pd

conn = sqlite3.connect("data/311.db")
conn.execute("DROP TABLE IF EXISTS requests_raw")

for csv in sorted(Path("data/raw").glob("311_*.csv")):
    for chunk in pd.read_csv(csv, dtype=str, chunksize=100000):
        chunk.to_sql("requests_raw", conn, if_exists="append", index=False)
    print("loaded", csv.name)

conn.close()