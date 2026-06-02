import pandas as pd
import numpy as np


class RentTransformer:
    """清理並轉換租賃資料"""

    DISTRICT_COL_CANDIDATES = ["county", "city", "district", "行政區"]
    PRICE_COL_CANDIDATES = ["total_price", "租金", "price", "rent_price"]
    AREA_COL_CANDIDATES = ["building_area", "area", "租賃面積"]

    def transform(self, df: pd.DataFrame) -> dict:
        """
        回傳 dict:
            raw     -> 清理後的原始 DataFrame
            summary -> 各區彙總 DataFrame
            trend   -> 月趨勢 DataFrame
        """
        if df.empty:
            return {"raw": df, "summary": pd.DataFrame(), "trend": pd.DataFrame()}

        df = self._standardize_columns(df)
        df = self._clean_values(df)

        summary = self._build_summary(df)
        trend = self._build_trend(df)

        return {"raw": df, "summary": summary, "trend": trend}

    def _standardize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = [c.lower().strip() for c in df.columns]
        rename_map = {}

        # 找行政區欄位
        for c in df.columns:
            if any(k in c for k in ["district", "鄉鎮", "行政區", "town"]):
                rename_map[c] = "district"
                break

        # 找總租金欄位
        for c in df.columns:
            if any(k in c for k in ["total_price", "租金", "rent"]):
                rename_map[c] = "total_price"
                break

        # 找面積欄位
        for c in df.columns:
            if any(k in c for k in ["area", "面積"]):
                rename_map[c] = "area"
                break

        # 找日期欄位
        for c in df.columns:
            if any(k in c for k in ["date", "日期", "transaction"]):
                rename_map[c] = "transaction_date"
                break

        return df.rename(columns=rename_map)

    def _clean_values(self, df: pd.DataFrame) -> pd.DataFrame:
        if "total_price" in df.columns:
            df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
            # 過濾不合理租金：月租 1000~300000
            df = df[df["total_price"].between(1000, 300000)]

        if "area" in df.columns:
            df["area"] = pd.to_numeric(df["area"], errors="coerce")
            df = df[df["area"] > 0]
            df["unit_price"] = (df["total_price"] / df["area"]).round(0)

        df = df.dropna(subset=["district", "total_price"])
        return df.reset_index(drop=True)

    def _build_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        grp = df.groupby("district")
        summary = grp["total_price"].agg(
            avg_price="mean",
            median_price="median",
            case_count="count",
        ).round(0).reset_index()

        if "unit_price" in df.columns:
            unit = grp["unit_price"].mean().round(0).reset_index()
            unit.columns = ["district", "avg_unit_price"]
            summary = summary.merge(unit, on="district", how="left")
        else:
            summary["avg_unit_price"] = np.nan

        return summary

    def _build_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        if "transaction_date" not in df.columns:
            return pd.DataFrame()

        df = df.copy()
        df["year_month"] = pd.to_datetime(
            df["transaction_date"], errors="coerce"
        ).dt.to_period("M").astype(str)

        trend = (
            df.groupby(["district", "year_month"])["total_price"]
            .agg(avg_price="mean", case_count="count")
            .round(0)
            .reset_index()
        )
        return trend