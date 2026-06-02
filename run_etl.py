import sys
import os

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from etl.fetch import RentFetcher
from etl.transform import RentTransformer
from etl.load import SupabaseLoader

supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")

print("=== ETL Start ===")

fetcher = RentFetcher()
raw_df = fetcher.fetch()

if raw_df.empty:
    print("No data fetched. ETL stopped.")
else:
    transformer = RentTransformer()
    result = transformer.transform(raw_df)

    loader = SupabaseLoader(url=supabase_url, key=supabase_key)
    loader.upsert_summary(result["summary"])
    loader.upsert_trend(result["trend"])
    print("=== ETL Complete ===")
