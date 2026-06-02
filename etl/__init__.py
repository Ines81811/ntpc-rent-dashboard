import os
from dotenv import load_dotenv
from etl.fetch import RentFetcher
from etl.transform import RentTransformer
from etl.load import SupabaseLoader

load_dotenv()


def run_etl():
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    print("=== ETL Start ===")

    fetcher = RentFetcher()
    raw_df = fetcher.fetch()

    if raw_df.empty:
        print("No data fetched. ETL stopped.")
        return

    transformer = RentTransformer()
    result = transformer.transform(raw_df)

    loader = SupabaseLoader(url=supabase_url, key=supabase_key)
    loader.upsert_summary(result["summary"])
    loader.upsert_trend(result["trend"])

    print("=== ETL Complete ===")


if __name__ == "__main__":
    run_etl()
