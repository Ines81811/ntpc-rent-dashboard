import os
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────
st.set_page_config(
    page_title="新北市租屋成本 Dashboard",
    page_icon="🏠",
    layout="wide",
)

# ── Supabase Client ───────────────────────────────────────
@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY"),
    )


# ── Data Loaders ──────────────────────────────────────────
@st.cache_data(ttl=60)
def load_summary() -> pd.DataFrame:
    client = get_supabase()
    resp = client.table("rent_summary").select("*").execute()
    df = pd.DataFrame(resp.data)
    return df.sort_values("avg_price", ascending=False).reset_index(drop=True)


@st.cache_data(ttl=60)
def load_trend() -> pd.DataFrame:
    client = get_supabase()
    resp = client.table("rent_monthly_trend").select("*").execute()
    return pd.DataFrame(resp.data)


# ── UI ────────────────────────────────────────────────────
st.title("🏠 新北市租屋成本 Dashboard")
st.caption("資料來源：實價登錄租賃資料 via FinMind API")

summary_df = load_summary()
trend_df = load_trend()

if summary_df.empty:
    st.warning("資料庫目前無資料，請先執行 ETL 程式。")
    st.stop()

# ── KPI Cards ─────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "全市平均月租金",
    f"NT$ {int(summary_df['avg_price'].mean()):,}",
)
col2.metric(
    "最高均租行政區",
    summary_df.iloc[0]["district"],
    f"NT$ {int(summary_df.iloc[0]['avg_price']):,}",
)
col3.metric(
    "最低均租行政區",
    summary_df.iloc[-1]["district"],
    f"NT$ {int(summary_df.iloc[-1]['avg_price']):,}",
    delta_color="inverse",
)
col4.metric(
    "總統計行政區數",
    len(summary_df),
)

st.divider()

# ── 各區平均租金長條圖 ────────────────────────────────────
st.subheader("各行政區平均月租金")

fig_bar = px.bar(
    summary_df,
    x="district",
    y="avg_price",
    color="avg_price",
    color_continuous_scale="Blues",
    labels={"district": "行政區", "avg_price": "平均月租金 (NT$)"},
    text_auto=True,
)
fig_bar.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45)
st.plotly_chart(fig_bar, use_container_width=True)

# ── 中位數 vs 平均值比較 ──────────────────────────────────
st.subheader("平均值 vs 中位數比較")

fig_compare = go.Figure()
fig_compare.add_trace(go.Bar(
    name="平均租金",
    x=summary_df["district"],
    y=summary_df["avg_price"],
    marker_color="#4C9BE8",
))
fig_compare.add_trace(go.Bar(
    name="中位數租金",
    x=summary_df["district"],
    y=summary_df["median_price"],
    marker_color="#F4A261",
))
fig_compare.update_layout(
    barmode="group",
    xaxis_tickangle=-45,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_compare, use_container_width=True)

# ── 每坪租金排行 ──────────────────────────────────────────
if "avg_unit_price" in summary_df.columns and summary_df["avg_unit_price"].notna().any():
    st.subheader("每坪平均租金排行")
    unit_df = summary_df.dropna(subset=["avg_unit_price"]).sort_values(
        "avg_unit_price", ascending=True
    )
    fig_unit = px.bar(
        unit_df,
        x="avg_unit_price",
        y="district",
        orientation="h",
        color="avg_unit_price",
        color_continuous_scale="Oranges",
        labels={"district": "行政區", "avg_unit_price": "每坪租金 (NT$)"},
        text_auto=True,
    )
    fig_unit.update_layout(coloraxis_showscale=False)
    st.plotly_chart(fig_unit, use_container_width=True)

