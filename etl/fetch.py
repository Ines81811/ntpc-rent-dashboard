import requests
import pandas as pd
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RentFetcher:
    """從新北市資料開放平臺抓租賃實價登錄資料"""

    API_URL = "https://data.ntpc.gov.tw/api/datasets/18d62577-1d5f-4967-ab9c-d71faba8cde1/json"

    def __init__(self, token: str = None):
        self.token = token

    def fetch(self) -> pd.DataFrame:
        all_records = []
        offset = 0
        limit = 1000

        while True:
            params = {"offset": offset, "limit": limit}
            print(f"Fetching offset={offset}...")
            resp = requests.get(self.API_URL, params=params, timeout=60, verify=False)
            resp.raise_for_status()
            records = resp.json()

            if not records:
                break

            all_records.extend(records)

            if len(records) < limit:
                break

            offset += limit

        if not all_records:
            print("No data returned.")
            return pd.DataFrame()

        df = pd.DataFrame(all_records)
        print(f"Fetched {len(df)} records total.")
        return df
