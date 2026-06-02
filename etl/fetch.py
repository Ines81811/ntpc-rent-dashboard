import requests
import pandas as pd
import os
from datetime import datetime, timedelta


class RentFetcher:
    """從 FinMind API 抓租賃資料"""

    BASE_URL = "https://api.finmindtrade.com/api/v4/data"
    DATASET = "TaiwanRealEstateTenancy"

    def __init__(self, token: str):
        self.token = token

    def fetch(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        if start_date is None:
            start_date = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
        if end_date is None:
            end_date = datetime.today().strftime("%Y-%m-%d")

        params = {
            "dataset": self.DATASET,
            "start_date": start_date,
            "end_date": end_date,
            "token": self.token,
        }

        resp = requests.get(self.BASE_URL, params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != 200:
            raise ValueError(f"API error: {data.get('msg')}")

        records = data.get("data", [])
        if not records:
            print("No data returned from API.")
            return pd.DataFrame()

        df = pd.DataFrame(records)
        print(f"Fetched {len(df)} records from FinMind.")
        return df
