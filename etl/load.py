import os
import pandas as pd
from supabase import create_client, Client


class SupabaseLoader:
    """將清理後資料寫入 Supabase"""

    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    def upsert_summary(self, df: pd.DataFrame) -> None:
        if df.empty:
            print("Summary DataFrame is empty, skipping.")
            return

        records = df.to_dict(orient="records")
        # 把 NaN 換成 None（JSON 相容）
        records = [
            {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
             for k, v in row.items()}
            for row in records
        ]
        self.client.table("rent_summary").upsert(
            records, on_conflict="district"
        ).execute()
        print(f"Upserted {len(records)} rows to rent_summary.")

    def upsert_trend(self, df: pd.DataFrame) -> None:
        if df.empty:
            print("Trend DataFrame is empty, skipping.")
            return

        records = df.to_dict(orient="records")
        records = [
            {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
             for k, v in row.items()}
            for row in records
        ]
        self.client.table("rent_monthly_trend").upsert(
            records, on_conflict="district,year_month"
        ).execute()
        print(f"Upserted {len(records)} rows to rent_monthly_trend.")

    def insert_raw(self, df: pd.DataFrame, batch_size: int = 500) -> None:
        if df.empty:
            return

        keep_cols = [c for c in ["district", "area", "total_price",
                                  "unit_price", "transaction_date",
                                  "build_type", "floor", "build_year"]
                     if c in df.columns]
        df = df[keep_cols]

        records = df.to_dict(orient="records")
        records = [
            {k: (None if (isinstance(v, float) and pd.isna(v)) else v)
             for k, v in row.items()}
            for row in records
        ]
        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            self.client.table("rent_raw").insert(batch).execute()
        print(f"Inserted {len(records)} rows to rent_raw.")