
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO

# -----------------------------
# Page Config
# -----------------------------
st.set_page_config(
    page_title="IB Futures Event Study Dashboard",
    page_icon="📈",
    layout="wide"
)

# -----------------------------
# Custom CSS
# -----------------------------
st.markdown("""
<style>
.main {
    background-color: #F7F9FC;
}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2rem;
}
h1, h2, h3 {
    color: #17324D;
}
.metric-card {
    background-color: white;
    padding: 18px;
    border-radius: 14px;
    border: 1px solid #E6EAF0;
    box-shadow: 0px 2px 8px rgba(20, 40, 80, 0.04);
}
.section-box {
    background-color: white;
    padding: 20px;
    border-radius: 14px;
    border: 1px solid #E6EAF0;
}
.small-muted {
    color: #65758B;
    font-size: 0.90rem;
}
</style>
""", unsafe_allow_html=True)

# -----------------------------
# Event Presets
# -----------------------------
EVENTS = {
    "SVB Collapse": {
        "file_hint": "Use 2023 workbook",
        "pre_start": "2023-02-15",
        "event_start": "2023-03-08",
        "event_end": "2023-03-13",
        "post_end": "2023-03-31",
        "marker": "2023-03-10",
        "theme": "Financial stability shock",
        "chain": "Banking stress → lower Fed/RBA hike expectations → bond rally → STIR repricing → curve compression",
        "description": "Tests whether US banking stress transmitted into Australian short-rate expectations."
    },
    "Yen Carry Unwind": {
        "file_hint": "Use 2024–2026 workbook",
        "pre_start": "2024-07-15",
        "event_start": "2024-08-01",
        "event_end": "2024-08-09",
        "post_end": "2024-08-30",
        "marker": "2024-08-05",
        "theme": "Funding and positioning shock",
        "chain": "BoJ repricing → yen funding stress → carry unwind → risk-off → global rates repositioning",
        "description": "Tests whether global funding stress altered Australian IB futures pricing."
    },
    "Liberation Day": {
        "file_hint": "Use 2024–2026 workbook",
        "pre_start": "2025-03-15",
        "event_start": "2025-04-02",
        "event_end": "2025-04-11",
        "post_end": "2025-04-30",
        "marker": "2025-04-02",
        "theme": "Trade and growth shock",
        "chain": "Tariffs → global growth concerns → risk-off → bond rally → lower policy-rate expectations → IB futures rise → curve compression",
        "description": "Tests whether tariff-driven growth fears lowered expected future RBA policy rates."
    }
}

CONTRACT_ORDER = ["YIBc1", "YIBc2", "YIBc3", "YIBc4"]

# -----------------------------
# Helpers
# -----------------------------
def detect_datetime_col(df):
    for col in ["DateTime (AET)", "AUS_Local_DateTime", "DateTime", "Datetime", "Date"]:
        if col in df.columns:
            return col
    return None

def detect_sheet_names(xls):
    names = xls.sheet_names
    mapping = {}
    for c in CONTRACT_ORDER:
        if c in names:
            mapping[c] = c
        elif c + "." in names:
            mapping[c] = c + "."
    return mapping

@st.cache_data(show_spinner=False)
def load_contracts(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    sheet_map = detect_sheet_names(xls)

    if not sheet_map:
        raise ValueError("No YIB contract sheets detected. Expected YIBc1/YIBc2/YIBc3/YIBc4.")

    data = {}
    for contract in CONTRACT_ORDER:
        if contract not in sheet_map:
            continue

        sheet = sheet_map[contract]
        df = pd.read_excel(xls, sheet_name=sheet)
        dt_col = detect_datetime_col(df)

        if dt_col is None:
            raise ValueError(f"No datetime column found in sheet {sheet}")

        if "Last" not in df.columns:
            raise ValueError(f"No 'Last' column found in sheet {sheet}")

        if "Volume" not in df.columns:
            df["Volume"] = np.nan

        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
        df = df.dropna(subset=[dt_col]).sort_values(dt_col)

        df = df.rename(columns={dt_col: "DateTime"})
        df["Last"] = pd.to_numeric(df["Last"], errors="coerce")
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
        df = df.dropna(subset=["Last"])

        df["Implied_Rate"] = 100 - df["Last"]
        df["Return"] = df["Last"].pct_change()
        df["Delta_r_bp"] = df["Implied_Rate"].diff() * 100

        data[contract] = df[["DateTime", "Last", "Implied_Rate", "Volume", "Return", "Delta_r_bp"]].copy()

    return data

def build_curve(data, ffill_limit=1):
    curve = None

    for contract in CONTRACT_ORDER:
        if contract not in data:
            continue
        df = data[contract][["DateTime", "Last"]].rename(columns={"Last": contract})
        curve = df if curve is None else curve.merge(df, on="DateTime", how="outer")

    curve = curve.sort_values("DateTime")
    cols = [c for c in CONTRACT_ORDER if c in curve.columns]
    curve[cols] = curve[cols].ffill(limit=ffill_limit)
    curve = curve.dropna(subset=cols)

    if all(c in curve.columns for c in ["YIBc1", "YIBc2"]):
        curve["Y1_Y2"] = curve["YIBc1"] - curve["YIBc2"]
    if all(c in curve.columns for c in ["YIBc2", "YIBc3"]):
        curve["Y2_Y3"] = curve["YIBc2"] - curve["YIBc3"]
    if all(c in curve.columns for c in ["YIBc3", "YIBc4"]):
        curve["Y3_Y4"] = curve["YIBc3"] - curve["YIBc4"]
    if all(c in curve.columns for c in ["YIBc1", "YIBc4"]):
        curve["Y1_Y4"] = curve["YIBc1"] - curve["YIBc4"]

    return curve

def window_label(dt, pre_start, event_start, event_end, post_end):
    if pre_start <= dt < event_start:
        return "Pre"
    if event_start <= dt <= event_end:
        return "Event"
    if event_end < dt <= post_end:
        return "Post"
    return None

def add_event_shapes(fig, event_start, event_end, marker):
    fig.add_vrect(x0=event_start, x1=event_end, fillcolor="#7F8EA3", opacity=0.18, line_width=0)
    fig.add_vline(x=marker, line_dash="dash", line_width=2, line_color="#C0392B")
    fig.update_layout(
        template="plotly_white",
        hovermode="x unified",
        legend_title_text="",
        margin=dict(l=30, r=30, t=60, b=30),
        height=520
    )
    return fig

def calc_summary(data, pre_start, event_start, event_end, post_end):
    rows = []
    for c in CONTRACT_ORDER:
        if c not in data:
            continue

        df = data[c].copy()
        df["Window"] = df["DateTime"].apply(lambda x: window_label(x, pre_start, event_start, event_end, post_end))

        pre = df[df["Window"] == "Pre"]
        event = df[df["Window"] == "Event"]
        post = df[df["Window"] == "Post"]

        if len(pre) == 0 or len(event) == 0:
            continue

        price_change = event["Last"].mean() - pre["Last"].mean()
        delta_r_bp = -price_change * 100
        moves_25bp = delta_r_bp / 25

        pre_vwap = (pre["Last"] * pre["Volume"]).sum() / pre["Volume"].sum() if pre["Volume"].sum() else np.nan
        event_vwap = (event["Last"] * event["Volume"]).sum() / event["Volume"].sum() if event["Volume"].sum() else np.nan
        vwap_delta_r_bp = -(event_vwap - pre_vwap) * 100 if pd.notna(pre_vwap) and pd.notna(event_vwap) else np.nan

        rows.append({
            "Contract": c,
            "Pre Avg Price": pre["Last"].mean(),
            "Event Avg Price": event["Last"].mean(),
            "Price Change": price_change,
            "Δr bp": delta_r_bp,
            "25bp Moves Priced": moves_25bp,
            "Pre Avg Volume": pre["Volume"].mean(),
            "Event Avg Volume": event["Volume"].mean(),
            "Volume % Change": (event["Volume"].mean() / pre["Volume"].mean() - 1) if pre["Volume"].mean() else np.nan,
            "Pre VWAP": pre_vwap,
            "Event VWAP": event_vwap,
            "VWAP Δr bp": vwap_delta_r_bp,
            "Event Return Vol": event["Return"].std(),
            "Event Max |Return|": event["Return"].abs().max()
        })

    return pd.DataFrame(rows)

def calc_spread_summary(curve, pre_start, event_start, event_end, post_end):
    spread_cols = [c for c in ["Y1_Y2", "Y2_Y3", "Y3_Y4", "Y1_Y4"] if c in curve.columns]
    curve = curve.copy()
    curve["Window"] = curve["DateTime"].apply(lambda x: window_label(x, pre_start, event_start, event_end, post_end))

    rows = []
    for s in spread_cols:
        pre_mean = curve[curve["Window"] == "Pre"][s].mean()
        event_mean = curve[curve["Window"] == "Event"][s].mean()
        post_mean = curve[curve["Window"] == "Post"][s].mean()

        rows.append({
            "Spread": s,
            "Pre Mean": pre_mean,
            "Event Mean": event_mean,
            "Post Mean": post_mean,
            "Event - Pre": event_mean - pre_mean,
            "Post - Event": post_mean - event_mean
        })

    return pd.DataFrame(rows)

def make_excel(summary, spread_summary):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary.to_excel(writer, index=False, sheet_name="Contract Summary")
        spread_summary.to_excel(writer, index=False, sheet_name="Spread Summary")
    return output.getvalue()

# -----------------------------
# Sidebar
# -----------------------------
st.sidebar.title("Controls")

uploaded = st.sidebar.file_uploader("Upload IB futures Excel workbook", type=["xlsx"])

event_name = st.sidebar.selectbox("Event preset", list(EVENTS.keys()))
cfg = EVENTS[event_name]

st.sidebar.markdown(f"**Suggested file:** {cfg['file_hint']}")

pre_start = pd.Timestamp(st.sidebar.date_input("Pre window start", pd.Timestamp(cfg["pre_start"])))
event_start = pd.Timestamp(st.sidebar.date_input("Event window start", pd.Timestamp(cfg["event_start"])))
event_end = pd.Timestamp(st.sidebar.date_input("Event window end", pd.Timestamp(cfg["event_end"])))
post_end = pd.Timestamp(st.sidebar.date_input("Post window end", pd.Timestamp(cfg["post_end"])))
marker = pd.Timestamp(st.sidebar.date_input("Main event marker", pd.Timestamp(cfg["marker"])))

z_window = st.sidebar.slider("Rolling z-score window", 5, 80, 20)
ffill_limit = st.sidebar.slider("Spread forward-fill limit", 0, 10, 1)

# -----------------------------
# Header
# -----------------------------
st.markdown("# IB Futures Event Study Dashboard")
st.markdown(
    f"""
    <div class='section-box'>
    <h3>{event_name}</h3>
    <p><b>Event type:</b> {cfg['theme']}</p>
    <p><b>Transmission chain:</b> {cfg['chain']}</p>
    <p class='small-muted'>{cfg['description']}</p>
    </div>
    """,
    unsafe_allow_html=True
)

if uploaded is None:
    st.info("Upload your Excel workbook from the sidebar to begin.")
    st.stop()

try:
    data = load_contracts(uploaded)
except Exception as e:
    st.error(str(e))
    st.stop()

available_contracts = [c for c in CONTRACT_ORDER if c in data]
curve = build_curve(data, ffill_limit=ffill_limit)
summary = calc_summary(data, pre_start, event_start, event_end, post_end)
spread_summary = calc_spread_summary(curve, pre_start, event_start, event_end, post_end)

# -----------------------------
# KPI Strip
# -----------------------------
st.markdown("## Executive KPIs")

k1, k2, k3, k4 = st.columns(4)

if not summary.empty:
    max_reprice = summary.loc[summary["Δr bp"].abs().idxmax()]
    y1 = summary[summary["Contract"] == "YIBc1"]
    y4 = summary[summary["Contract"] == "YIBc4"]

    y1_dr = y1["Δr bp"].iloc[0] if len(y1) else np.nan
    y4_dr = y4["Δr bp"].iloc[0] if len(y4) else np.nan

    y14 = spread_summary[spread_summary["Spread"] == "Y1_Y4"]
    y14_change = y14["Event - Pre"].iloc[0] if len(y14) else np.nan

    avg_vol_change = summary["Volume % Change"].mean()

    k1.metric("Largest repricing", f"{max_reprice['Contract']}", f"{max_reprice['Δr bp']:.2f} bp")
    k2.metric("YIBc1 Δr", f"{y1_dr:.2f} bp")
    k3.metric("YIBc4 Δr", f"{y4_dr:.2f} bp")
    k4.metric("Y1-Y4 spread change", f"{y14_change:.4f}")

st.download_button(
    "Download summary tables as Excel",
    data=make_excel(summary, spread_summary),
    file_name=f"{event_name.replace(' ', '_')}_event_summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# -----------------------------
# Tabs
# -----------------------------
tabs = st.tabs([
    "1. Prices",
    "2. Implied Rates",
    "3. Volume",
    "4. Curve Spreads",
    "5. Z-Scores",
    "6. Summary Tables",
    "7. Interpretation"
])

plot_start = pre_start
plot_end = post_end

with tabs[0]:
    st.subheader("Outright futures prices")
    selected = st.multiselect("Select contracts", available_contracts, default=available_contracts, key="price_select")

    rows = []
    for c in selected:
        df = data[c]
        temp = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()
        temp["Contract"] = c
        rows.append(temp)

    if rows:
        prices = pd.concat(rows)
        fig = px.line(prices, x="DateTime", y="Last", color="Contract", title=f"{event_name}: futures prices")
        fig = add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("Price rising means implied expected cash rate is falling because IB price = 100 - implied rate.")

with tabs[1]:
    st.subheader("Market-implied future rates")
    selected = st.multiselect("Select contracts", available_contracts, default=available_contracts, key="rate_select")

    rows = []
    for c in selected:
        df = data[c]
        temp = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()
        temp["Contract"] = c
        rows.append(temp)

    if rows:
        implied = pd.concat(rows)
        fig = px.line(implied, x="DateTime", y="Implied_Rate", color="Contract", title=f"{event_name}: implied future rates")
        fig = add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

    st.caption("This is market pricing, not the actual RBA cash-rate decision.")

with tabs[2]:
    st.subheader("Volume and participation")
    contract = st.selectbox("Select contract", available_contracts, key="volume_contract")
    df = data[contract]
    vol = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()

    fig = px.bar(vol, x="DateTime", y="Volume", title=f"{event_name}: {contract} traded volume")
    fig = add_event_shapes(fig, event_start, event_end, marker)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Top event-window volume rows")
    top = df[(df["DateTime"] >= event_start) & (df["DateTime"] <= event_end)].nlargest(20, "Volume")
    st.dataframe(top, use_container_width=True)

with tabs[3]:
    st.subheader("Curve spreads")
    spread_cols = [c for c in ["Y1_Y2", "Y2_Y3", "Y3_Y4", "Y1_Y4"] if c in curve.columns]
    selected_spreads = st.multiselect("Select spreads", spread_cols, default=spread_cols)

    curve_plot = curve[(curve["DateTime"] >= plot_start) & (curve["DateTime"] <= plot_end)]
    if selected_spreads:
        curve_long = curve_plot.melt(id_vars="DateTime", value_vars=selected_spreads, var_name="Spread", value_name="Spread Value")
        fig = px.line(curve_long, x="DateTime", y="Spread Value", color="Spread", title=f"{event_name}: curve spreads")
        fig = add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

    st.dataframe(spread_summary, use_container_width=True)

with tabs[4]:
    st.subheader("Rolling z-score analysis")
    contract = st.selectbox("Select contract", available_contracts, key="z_contract")

    df = data[contract].copy()
    df["ZScore"] = (df["Last"] - df["Last"].rolling(z_window).mean()) / df["Last"].rolling(z_window).std()
    z = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()

    fig = px.line(z, x="DateTime", y="ZScore", title=f"{event_name}: {contract} rolling {z_window}-period z-score")
    fig.add_hline(y=2, line_dash="dash", line_color="#C0392B")
    fig.add_hline(y=-2, line_dash="dash", line_color="#C0392B")
    fig = add_event_shapes(fig, event_start, event_end, marker)
    st.plotly_chart(fig, use_container_width=True)

    event_z = df[(df["DateTime"] >= event_start) & (df["DateTime"] <= event_end)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Max z-score", f"{event_z['ZScore'].max():.2f}")
    c2.metric("Min z-score", f"{event_z['ZScore'].min():.2f}")
    c3.metric("Max absolute z-score", f"{event_z['ZScore'].abs().max():.2f}")

with tabs[5]:
    st.subheader("Contract-level event summary")
    st.dataframe(summary, use_container_width=True)

    st.subheader("Equivalent 25 bp moves priced")
    if not summary.empty:
        fig = px.bar(
            summary,
            x="Contract",
            y="25bp Moves Priced",
            title=f"{event_name}: equivalent 25 bp moves priced"
        )
        fig.update_layout(template="plotly_white", height=480)
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Spread summary")
    st.dataframe(spread_summary, use_container_width=True)

with tabs[6]:
    st.subheader("Interpretation guide")

    st.markdown(f"""
    ### Event transmission
    **{cfg['chain']}**

    ### How to read the dashboard

    - **Futures price up** means **market-implied rates down**.
    - **Futures price down** means **market-implied rates up**.
    - **Δr bp** measures the change in market-implied future rates, not actual RBA policy.
    - **25bp Moves Priced** converts the repricing into standard RBA-sized policy steps.
    - **Y1-Y4 compression** means the front-to-back curve spread narrowed.
    - **High volume with price movement** suggests active repricing.
    - **High z-score** suggests the move was statistically unusual relative to recent trading.

    ### Professional wording

    Do not write: “The RBA cut because of this event.”

    Write: “The event changed market pricing of the expected future RBA policy path.”
    """)
