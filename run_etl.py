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
API_URL = "https://data.ntpc.gov.tw/api/datasets/18d62577-1d5f-4967-ab9c-d71faba8cde1/json"
CSV_URL = "https://data.ntpc.gov.tw/api/datasets/18d62577-1d5f-4967-ab9c-d71faba8cde1/csv?size=100000"

print("=== ETL Start ===")

client = create_client(SUPABASE_URL, SUPABASE_KEY)


def clean_val(v):
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, (np.integer, np.floating)):
        return int(v)
    return v


def parse_api_row(row):
    try:
        total_price = float(row.get("rps22_amountsunitdollars") or 0)
        area = float(row.get("rps15_area") or 0)
        unit_price = float(row.get("rps23_amountsunitdollars") or 0)
        if not (1000 <= total_price <= 300000):
            return None
        return {
            "serial_number": str(row.get("rps28", "")),
            "district": str(row.get("district", "")),
            "town": str(row.get("district", "")),
            "build_type": str(row.get("rps11", "")),
            "area": area if area > 0 else None,
            "total_price": total_price,
            "unit_price": unit_price if unit_price > 0 else None,
            "floor": str(row.get("rps09", "")),
            "build_year": str(row.get("rps14_yyymmddroc", "")),
            "transaction_date": str(row.get("rps07_yyymmddroc", "")),
        }
    except Exception:
        return None


def fetch_all_from_supabase(table, columns):
    """分頁讀取 Supabase 全量資料"""
    all_rows = []
    page = 0
    page_size = 1000
    while True:
        resp = client.table(table).select(columns).range(
            page * page_size, (page + 1) * page_size - 1
        ).execute()
        if not resp.data:
            break
        all_rows.extend(resp.data)
        print(f"  Fetched page {page + 1}: {len(all_rows)} rows so far")
        if len(resp.data) < page_size:
            break
        page += 1
    return all_rows


# 檢查母體是否存在
existing = client.table("rent_raw").select("id", count="exact").execute()
existing_count = existing.count or 0
print(f"Existing rows in rent_raw: {existing_count}")

if existing_count == 0:
    print("No existing data. Downloading full CSV as base data...")
    try:
        resp = requests.get(CSV_URL, verify=False, timeout=60)
        resp.raise_for_status()
        df_csv = pd.read_csv(
            io.StringIO(resp.content.decode("utf-8-sig", errors="replace")),
            low_memory=False
        )
        print(f"CSV downloaded: {len(df_csv)} rows")

        df_csv.columns = [c.strip().strip('"') for c in df_csv.columns]

        col_map = {
            "district": "district",
            "rps07_yyymmddroc": "transaction_date",
            "rps22_amountsunitdollars": "total_price",
            "rps15_area": "area",
            "rps23_amountsunitdollars": "unit_price",
            "rps11": "build_type",
            "rps09": "floor",
            "rps14_yyymmddroc": "build_year",
            "rps28": "serial_number",
        }
        df_csv = df_csv.rename(columns=col_map)

        if "total_price" not in df_csv.columns:
            print("Cannot find total_price column, skipping CSV import.")
        else:
            df_csv["total_price"] = pd.to_numeric(df_csv["total_price"], errors="coerce")
            df_csv["area"] = pd.to_numeric(df_csv["area"], errors="coerce") if "area" in df_csv.columns else None
            df_csv["unit_price"] = pd.to_numeric(df_csv["unit_price"], errors="coerce") if "unit_price" in df_csv.columns else None
            df_csv = df_csv[df_csv["total_price"].between(1000, 300000)]
            df_csv = df_csv.dropna(subset=["district", "total_price"]).reset_index(drop=True)
            print(f"After cleaning: {len(df_csv)} rows, {df_csv['district'].nunique()} districts")

            keep = [c for c in ["serial_number", "district", "total_price", "area",
                                 "unit_price", "transaction_date", "build_type",
                                 "floor", "build_year"] if c in df_csv.columns]
            df_csv = df_csv[keep]

            csv_records = [{k: clean_val(row[k]) for k in keep} for _, row in df_csv.iterrows()]

            batch_size = 500
            for i in range(0, len(csv_records), batch_size):
                client.table("rent_raw").upsert(
                    csv_records[i:i+batch_size],
                    on_conflict="serial_number"
                ).execute()
                print(f"  Upserted batch {i//batch_size + 1} ({min(i+batch_size, len(csv_records))}/{len(csv_records)})")
            print(f"Upserted {len(csv_records)} rows from CSV.")

    except Exception as e:
        print(f"CSV download/import failed: {e}")

# 增量更新：抓最新 30 筆
print("Fetching latest 30 records from API...")
try:
    resp = requests.get(API_URL, params={"offset": 0, "limit": 30}, verify=False, timeout=30)
    resp.raise_for_status()
    new_records = resp.json()
    print(f"API returned {len(new_records)} records")
except Exception as e:
    print(f"API fetch failed: {e}")
    new_records = []

if new_records:
    try:
        existing_serials = set()
        page = 0
        while True:
            serials_resp = client.table("rent_raw").select("serial_number").range(
                page * 1000, (page + 1) * 1000 - 1
            ).execute()
            if not serials_resp.data:
                break
            existing_serials.update(
                r["serial_number"] for r in serials_resp.data if r.get("serial_number")
            )
            if len(serials_resp.data) < 1000:
                break
            page += 1
        print(f"Existing serial numbers: {len(existing_serials)}")
    except Exception as e:
        print(f"Failed to fetch serials: {e}")
        existing_serials = set()

    to_insert = []
    for row in new_records:
        serial = str(row.get("rps28", ""))
        if serial and serial not in existing_serials:
            parsed = parse_api_row(row)
            if parsed:
                to_insert.append(parsed)

    print(f"New records to insert: {len(to_insert)}")
    if to_insert:
        client.table("rent_raw").upsert(to_insert, on_conflict="serial_number").execute()
        print(f"Inserted {len(to_insert)} new rows.")
    else:
        print("No new records.")

# 重新計算彙總（全量分頁讀取）
print("Recalculating summary from rent_raw...")
all_rows = fetch_all_from_supabase("rent_raw", "district,total_price,unit_price")
print(f"Total rows fetched for summary: {len(all_rows)}")
df = pd.DataFrame(all_rows)

if df.empty:
    print("rent_raw is empty.")
    sys.exit(0)

df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
df = df[df["total_price"].between(1000, 300000)].dropna(subset=["district", "total_price"])
print(f"Districts in data: {sorted(df['district'].unique())}")

grp = df.groupby("district")
summary = grp["total_price"].agg(
    avg_price="mean",
    median_price="median",
    case_count="count",
).round(0).reset_index()

unit = grp["unit_price"].mean().round(0).reset_index()
unit.columns = ["district", "avg_unit_price"]
summary = summary.merge(unit, on="district", how="left")

records = [{k: clean_val(v) for k, v in row.items()} for row in summary.to_dict(orient="records")]
client.table("rent_summary").upsert(records, on_conflict="district").execute()
print(f"Upserted {len(records)} districts to rent_summary.")
print("=== ETL Complete ===")
