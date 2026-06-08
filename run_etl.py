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

def parse_row(row):
    try:
        total_price = float(row.get("rps22_amountsunitdollars") or 0)
        area = float(row.get("rps15_area") or 0)
        unit_price = float(row.get("rps23_amountsunitdollars") or 0)
        return {
            "serial_number": str(row.get("rps28", "")),
            "district": str(row.get("district", "")),
            "town": str(row.get("district", "")),
            "build_type": str(row.get("rps11", "")),
            "area": area if area > 0 else None,
            "total_price": total_price if total_price > 0 else None,
            "unit_price": unit_price if unit_price > 0 else None,
            "floor": str(row.get("rps09", "")),
            "build_year": str(row.get("rps14_yyymmddroc", "")),
            "transaction_date": str(row.get("rps07_yyymmddroc", "")),
        }
    except:
        return None

# 檢查 rent_raw 是否有資料（母體是否已存在）
existing = client.table("rent_raw").select("id", count="exact").execute()
existing_count = existing.count or 0
print(f"Existing rows in rent_raw: {existing_count}")

if existing_count == 0:
    # 第一次：下載 CSV 母體
    print("No existing data. Downloading full CSV...")
    try:
        resp = requests.get(CSV_URL, verify=False, timeout=60)
        resp.raise_for_status()
        df_csv = pd.read_csv(
            io.StringIO(resp.content.decode("utf-8-sig", errors="replace")),
            low_memory=False
        )
        print(f"CSV downloaded: {len(df_csv)} rows")
        print(f"CSV downloaded: {len(df_csv)} rows")
        # CSV 欄位對應
        df_csv = df_csv.rename(columns={
            "鄉鎮市區": "district",
            "租賃總額元": "total_price",
            "建物移轉總面積平方公尺": "area",
            "租賃年月日": "transaction_date",
            "單價元平方公尺": "unit_price",
            "建物型態": "build_type",
            "移轉層次": "floor",
            "建築完成年月": "build_year",
            "序號": "serial_number",
        })
        df_csv["total_price"] = pd.to_numeric(df_csv["total_price"], errors="coerce")
        df_csv["area"] = pd.to_numeric(df_csv.get("area", pd.Series()), errors="coerce")
        df_csv["unit_price"] = pd.to_numeric(df_csv.get("unit_price", pd.Series()), errors="coerce")
        df_csv = df_csv[df_csv["total_price"].between(1000, 300000)]
        df_csv = df_csv.dropna(subset=["district", "total_price"]).reset_index(drop=True)
        
        keep = ["serial_number", "district", "total_price", "area", "unit_price", "transaction_date", "build_type", "floor", "build_year"]
        keep = [c for c in keep if c in df_csv.columns]
        df_csv = df_csv[keep]
        
        csv_records = []
        for _, row in df_csv.iterrows():
            r = {}
            for k in keep:
                v = row.get(k)
                if pd.isna(v) if isinstance(v, float) else False:
                    r[k] = None
                else:
                    r[k] = v
            csv_records.append(r)
        
        # 分批寫入
        batch_size = 500
        for i in range(0, len(csv_records), batch_size):
            client.table("rent_raw").insert(csv_records[i:i+batch_size]).execute()
        print(f"Inserted {len(csv_records)} rows from CSV to rent_raw.")
    except Exception as e:
    except Exception as e:
        print(f"CSV download failed: {e}")

# 增量更新：抓最新 30 筆
print("Fetching latest 30 records from API...")
try:
    resp = requests.get(API_URL, params={"offset": 0, "limit": 30}, verify=False, timeout=30)
    resp.raise_for_status()
    new_records = resp.json()
    print(f"API returned {len(new_records)} records")
except Exception as e:
    print(f"API fetch failed: {e}")
    sys.exit(1)

# 取得現有 serial_number
existing_serials = set()
try:
    serials_resp = client.table("rent_raw").select("serial_number").execute()
    existing_serials = {r["serial_number"] for r in serials_resp.data if r.get("serial_number")}
    print(f"Existing serial numbers: {len(existing_serials)}")
except Exception as e:
    print(f"Failed to fetch existing serials: {e}")

# 篩選新資料
to_insert = []
for row in new_records:
    serial = str(row.get("rps28", ""))
    if serial and serial not in existing_serials:
        parsed = parse_row(row)
        if parsed and parsed.get("total_price") and 1000 <= parsed["total_price"] <= 300000:
            to_insert.append(parsed)

print(f"New records to insert: {len(to_insert)}")

if to_insert:
    client.table("rent_raw").insert(to_insert).execute()
    print(f"Inserted {len(to_insert)} new rows.")
else:
    print("No new records.")

# 重新計算彙總（從 rent_raw 全量計算）
print("Recalculating summary from rent_raw...")
all_data = client.table("rent_raw").select("district,total_price,unit_price").execute()
df = pd.DataFrame(all_data.data)

if df.empty:
    print("rent_raw is empty, skipping summary.")
    sys.exit(0)

df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
df = df[df["total_price"].between(1000, 300000)].dropna(subset=["district", "total_price"])

grp = df.groupby("district")
summary = grp["total_price"].agg(
    avg_price="mean",
    median_price="median",
    case_count="count",
).round(0).reset_index()

unit = grp["unit_price"].mean().round(0).reset_index()
unit.columns = ["district", "avg_unit_price"]
summary = summary.merge(unit, on="district", how="left")

records = [
    {k: (None if isinstance(v, float) and pd.isna(v) else int(v) if isinstance(v, (np.integer, np.floating)) else v)
     for k, v in row.items()}
    for row in summary.to_dict(orient="records")
]
client.table("rent_summary").upsert(records, on_conflict="district").execute()
print(f"Upserted {len(records)} districts to rent_summary.")
print("=== ETL Complete ===")
