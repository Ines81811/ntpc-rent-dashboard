cat > etl/transform.py << 'EOF'
import pandas as pd
import numpy as np


class RentTransformer:
    """清理並轉換新北市租賃資料"""

    def transform(self, df: pd.DataFrame) -> dict:
        if df.empty:
            return {"raw": df, "summary": pd.DataFrame(), "trend": pd.DataFrame()}

        df = self._clean(df)
        if df.empty:
            return {"raw": df, "summary": pd.DataFrame(), "trend": pd.DataFrame()}

        summary = self._build_summary(df)
        trend = self._build_trend(df)
        return {"raw": df, "summary": summary, "trend": trend}

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        # 欄位對應
        rename_map = {
            "district": "district",
            "rps22_amountsunitdollars": "total_price",
            "rps15_area": "area",
            "rps07_yyymmddroc": "transaction_date",
            "rps23_amountsunitdollars": "unit_price",
            "rps11": "build_type",
            "rps09": "floor",
            "rps14_yyymmddroc": "build_year",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # 清理租金
        df["total_price"] = pd.to_numeric(df["total_price"], errors="coerce")
        df = df[df["total_price"].between(1000, 300000)]

        # 清理面積
        if "area" in df.columns:
            df["area"] = pd.to_numeric(df["area"], errors="coerce")
            df = df[df["area"] > 0]
            df["unit_price"] = (df["total_price"] / df["area"]).round(0)

        # 清理日期（民國年轉西元）
        if "transaction_date" in df.columns:
            df["transaction_date"] = df["transaction_date"].astype(str).str[:7]
            df["transaction_date"] = df["transaction_date"].apply(self._roc_to_ce)

        df = df.dropna(subset=["district", "total_price"])
        return df.reset_index(drop=True)

    def _roc_to_ce(self, roc_str: str) -> str:
        try:
            parts = roc_str.split("/") if "/" in roc_str else [roc_str[:3], roc_str[3:5]]
            year = int(parts[0]) + 1911
            month = int(parts[1]) if len(parts) > 1 else 1
            return f"{year}-{month:02d}"
        except:
            return None

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

        trend = (
            df.groupby(["district", "transaction_date"])["total_price"]
            .agg(avg_price="mean", case_count="count")
            .round(0)
            .reset_index()
            .rename(columns={"transaction_date": "year_month"})
        )
        return trend
EOF