import os
import sys
import requests
import pandas as pd
import numpy as np
import urllib3
from supabase import create_client

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
API_URL = "https://data.ntpc.gov.tw/api/datasets/18d62577-1d5f-4967-ab9c-d71faba8cde1/json"

print("=== ETL Start ===")

# 1. Fetch
all_records = []
offset = 0
limit = 1000

while True:
    params = {"offset": offset, "limit": limit}
    print(f"Fetching offset={offset}...")
    resp = requests.get(API_URL, params=params, timeout=60, verify=False)
    resp.raise_for_status()
    records = resp.json()
    if not records:
        break
    all_records.extend(records)
    if len(records) < limit:
        break
    offset += limit

if not all_records:
    print("No data fetched.")
    sys.exit(0)

df = pd.DataFrame(all_records)
print(f"Fetched {len(df)} records.")

# 2. Transform
df = df.rename(columns={
    "district": "district",
    "rps22_amountsunitdollars": "total_price",
    "rps15_area": "area",
    "rps07_yyymmddroc": "transaction_date",
})

df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
df = df[df["total_price"].between(1000, 300000)]

if "area" in df.columns:
    df["area"] = pd.to_numeric(df["area"], errors="coerce")
    df = df[df["area"] > 0]
    df["unit_price"] = (df["total_price"] / df["area"]).round(0)

df = df.dropna(subset=["district", "total_price"]).reset_index(drop=True)

# Summary
grp = df.groupby("district")
summary = grp["total_price"].agg(avg_price="mean", median_price="median", case_count="count").round(0).reset_index()
if "unit_price" in df.columns:
    unit = grp["unit_price"].mean().round(0).reset_index()
    unit.columns = ["district", "avg_unit_price"]
    summary = summary.merge(unit, on="district", how="left")

# 3. Load
client = create_client(SUPABASE_URL, SUPABASE_KEY)

records = [{k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in row.items()} for row in summary.to_dict(orient="records")]
client.table("rent_summary").upsert(records, on_conflict="district").execute()
print(f"Upserted {len(records)} rows to rent_summary.")

print("=== ETL Complete ===")
