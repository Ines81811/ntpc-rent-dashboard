import os
import io
import sys
import requests
import pandas as pd
import numpy as np
import urllib3
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

print("=== ETL Start ===")

SEASONS = ["113S1", "113S2", "113S3", "113S4"]
BASE_URL = "https://plvr.land.moi.gov.tw/DownloadSeason?season={season}&type=lvr&fileName=F_lvr_land_C.CSV"

all_dfs = []
for season in SEASONS:
    url = BASE_URL.format(season=season)
    print(f"Fetching {season}...")
    try:
        resp = requests.get(url, verify=False, timeout=60)
        if resp.status_code != 200 or len(resp.content) < 1000:
            print(f"  Skipped {season}")
            continue
        lines = resp.content.decode("utf-8-sig", errors="replace").split("\n")
        if len(lines) < 3:
            continue
        header = lines[1]
        data_lines = "\n".join([header] + lines[2:])
        df = pd.read_csv(io.StringIO(data_lines), low_memory=False)
        df["season"] = season
        all_dfs.append(df)
        print(f"  {season}: {len(df)} rows")
    except Exception as e:
        print(f"  Error {season}: {e}")

if not all_dfs:
    print("No data fetched.")
    sys.exit(0)

df = pd.concat(all_dfs, ignore_index=True)
print(f"Total rows before cleaning: {len(df)}")

df = df.rename(columns={
    "The villages and towns urban district": "district",
    "total price NTD": "total_price",
    "the unit price (NTD / square meter)": "unit_price",
    "building shifting total area": "area",
    "transaction year month and day": "transaction_date",
})

df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
df = df[df["total_price"].between(1000, 300000)]

if "area" in df.columns:
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    df = df[df["area"] > 0]

df = df.dropna(subset=["district", "total_price"]).reset_index(drop=True)
print(f"Total rows after cleaning: {len(df)}")

grp = df.groupby("district")
summary = grp["total_price"].agg(
    avg_price="mean",
    median_price="median",
    case_count="count",
).round(0).reset_index()

if "unit_price" in df.columns:
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    unit = grp["unit_price"].mean().round(0).reset_index()
    unit.columns = ["district", "avg_unit_price"]
    summary = summary.merge(unit, on="district", how="left")

client = create_client(SUPABASE_URL, SUPABASE_KEY)
records = [
    {k: (None if isinstance(v, float) and pd.isna(v) else int(v) if isinstance(v, (np.integer, np.floating)) else v)
     for k, v in row.items()}
    for row in summary.to_dict(orient="records")
]
client.table("rent_summary").upsert(records, on_conflict="district").execute()
print(f"Upserted {len(records)} rows to rent_summary.")
print("=== ETL Complete ===")
