
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="IB Futures Event Study Dashboard", layout="wide")

st.title("IB Futures Event Study Dashboard")
st.caption("Compare SVB Collapse, Yen Carry Unwind, and Liberation Day using prices, implied rates, volume, spreads, and rolling z-scores.")

EVENTS = {
    "SVB Collapse": {
        "file_hint": "Use 2023 file: YIBc_Trades_Only...",
        "pre_start": "2023-02-15",
        "event_start": "2023-03-08",
        "event_end": "2023-03-13",
        "post_end": "2023-03-31",
        "marker": "2023-03-10",
        "description": "US banking stress event; test whether Australian IB futures repriced through outright prices or curve compression."
    },
    "Yen Carry Unwind": {
        "file_hint": "Use 2024-2026 master file",
        "pre_start": "2024-07-15",
        "event_start": "2024-08-01",
        "event_end": "2024-08-09",
        "post_end": "2024-08-30",
        "marker": "2024-08-05",
        "description": "Funding/yield-differential shock; test whether front-end or curve positioning changed."
    },
    "Liberation Day": {
        "file_hint": "Use 2024-2026 master file",
        "pre_start": "2025-03-15",
        "event_start": "2025-04-02",
        "event_end": "2025-04-11",
        "post_end": "2025-04-30",
        "marker": "2025-04-02",
        "description": "Tariff/growth shock; test whether lower future policy-rate expectations were priced."
    }
}

def detect_datetime_col(df):
    for col in ["DateTime (AET)", "AUS_Local_DateTime", "DateTime", "Datetime", "Date"]:
        if col in df.columns:
            return col
    return None

def detect_sheet_names(xls):
    names = xls.sheet_names
    mapping = {}
    for c in ["YIBc1", "YIBc2", "YIBc3", "YIBc4"]:
        if c in names:
            mapping[c] = c
        elif c + "." in names:
            mapping[c] = c + "."
    return mapping

@st.cache_data(show_spinner=False)
def load_contracts(uploaded_file):
    xls = pd.ExcelFile(uploaded_file)
    sheet_map = detect_sheet_names(xls)

    data = {}
    for contract, sheet in sheet_map.items():
        df = pd.read_excel(xls, sheet_name=sheet)
        dt_col = detect_datetime_col(df)

        if dt_col is None:
            raise ValueError(f"No datetime column found in sheet {sheet}")

        df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
        df = df.dropna(subset=[dt_col]).sort_values(dt_col)

        df = df.rename(columns={dt_col: "DateTime"})

        if "Last" not in df.columns:
            raise ValueError(f"No Last column found in sheet {sheet}")

        if "Volume" not in df.columns:
            df["Volume"] = np.nan

        df["Implied_Rate"] = 100 - df["Last"]
        df["Return"] = df["Last"].pct_change()

        data[contract] = df[["DateTime", "Last", "Implied_Rate", "Volume", "Return"]].copy()

    return data

def build_curve(data, ffill_limit=1):
    curve = None

    for contract, df in data.items():
        temp = df[["DateTime", "Last"]].rename(columns={"Last": contract})
        curve = temp if curve is None else curve.merge(temp, on="DateTime", how="outer")

    curve = curve.sort_values("DateTime")
    cols = [c for c in ["YIBc1", "YIBc2", "YIBc3", "YIBc4"] if c in curve.columns]

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
    fig.add_vrect(x0=event_start, x1=event_end, fillcolor="gray", opacity=0.18, line_width=0)
    fig.add_vline(x=marker, line_dash="dash", line_width=2)

uploaded = st.sidebar.file_uploader("Upload IB futures Excel file", type=["xlsx"])

event_name = st.sidebar.selectbox("Select event", list(EVENTS.keys()))
cfg = EVENTS[event_name]

st.sidebar.info(cfg["file_hint"])

pre_start = pd.Timestamp(st.sidebar.date_input("Pre start", pd.Timestamp(cfg["pre_start"])))
event_start = pd.Timestamp(st.sidebar.date_input("Event start", pd.Timestamp(cfg["event_start"])))
event_end = pd.Timestamp(st.sidebar.date_input("Event end", pd.Timestamp(cfg["event_end"])))
post_end = pd.Timestamp(st.sidebar.date_input("Post end", pd.Timestamp(cfg["post_end"])))
marker = pd.Timestamp(st.sidebar.date_input("Main marker date", pd.Timestamp(cfg["marker"])))
z_window = st.sidebar.slider("Rolling z-score window", 5, 80, 20)
ffill_limit = st.sidebar.slider("Spread forward-fill limit", 0, 10, 1)

st.write(cfg["description"])

if uploaded is None:
    st.warning("Upload your Excel file to start.")
    st.stop()

data = load_contracts(uploaded)
available_contracts = list(data.keys())

if not available_contracts:
    st.error("No YIBc sheets detected. Expected sheets like YIBc1, YIBc2, YIBc3, YIBc4.")
    st.stop()

plot_start = pre_start
plot_end = post_end

tabs = st.tabs(["Prices", "Implied Rates", "Volume", "Spreads", "Z-Scores", "Event Summary"])

with tabs[0]:
    st.subheader("Outright Futures Prices")
    selected = st.multiselect("Contracts", available_contracts, default=available_contracts)

    long_rows = []
    for c in selected:
        df = data[c]
        temp = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()
        temp["Contract"] = c
        long_rows.append(temp)

    if long_rows:
        prices = pd.concat(long_rows)
        fig = px.line(prices, x="DateTime", y="Last", color="Contract", title=f"{event_name}: IB Futures Prices")
        add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

with tabs[1]:
    st.subheader("Market-Implied Future Rates")
    selected = st.multiselect("Contracts for implied rate", available_contracts, default=available_contracts, key="ir")

    rows = []
    for c in selected:
        df = data[c]
        temp = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)].copy()
        temp["Contract"] = c
        rows.append(temp)

    if rows:
        implied = pd.concat(rows)
        fig = px.line(implied, x="DateTime", y="Implied_Rate", color="Contract", title=f"{event_name}: Implied Future Rates")
        add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

with tabs[2]:
    st.subheader("Volume Analysis")
    contract = st.selectbox("Contract", available_contracts, key="volcontract")
    df = data[contract]
    vol = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)]

    fig = px.bar(vol, x="DateTime", y="Volume", title=f"{event_name}: {contract} Volume")
    add_event_shapes(fig, event_start, event_end, marker)
    st.plotly_chart(fig, use_container_width=True)

    st.write("Top event-window volume rows")
    top = df[(df["DateTime"] >= event_start) & (df["DateTime"] <= event_end)].nlargest(20, "Volume")
    st.dataframe(top, use_container_width=True)

with tabs[3]:
    st.subheader("Curve Spreads")
    curve = build_curve(data, ffill_limit=ffill_limit)
    spread_cols = [c for c in ["Y1_Y2", "Y2_Y3", "Y3_Y4", "Y1_Y4"] if c in curve.columns]
    selected_spreads = st.multiselect("Spreads", spread_cols, default=spread_cols)

    curve_plot = curve[(curve["DateTime"] >= plot_start) & (curve["DateTime"] <= plot_end)]
    if selected_spreads:
        curve_long = curve_plot.melt(id_vars="DateTime", value_vars=selected_spreads, var_name="Spread", value_name="Value")
        fig = px.line(curve_long, x="DateTime", y="Value", color="Spread", title=f"{event_name}: Curve Spreads")
        add_event_shapes(fig, event_start, event_end, marker)
        st.plotly_chart(fig, use_container_width=True)

with tabs[4]:
    st.subheader("Rolling Z-Scores")
    contract = st.selectbox("Contract", available_contracts, key="zcontract")
    df = data[contract].copy()
    df["ZScore"] = (df["Last"] - df["Last"].rolling(z_window).mean()) / df["Last"].rolling(z_window).std()
    z = df[(df["DateTime"] >= plot_start) & (df["DateTime"] <= plot_end)]

    fig = px.line(z, x="DateTime", y="ZScore", title=f"{event_name}: {contract} Rolling {z_window}-Period Z-Score")
    fig.add_hline(y=2, line_dash="dash")
    fig.add_hline(y=-2, line_dash="dash")
    add_event_shapes(fig, event_start, event_end, marker)
    st.plotly_chart(fig, use_container_width=True)

    event_z = df[(df["DateTime"] >= event_start) & (df["DateTime"] <= event_end)]
    c1, c2, c3 = st.columns(3)
    c1.metric("Max Z", f"{event_z['ZScore'].max():.2f}")
    c2.metric("Min Z", f"{event_z['ZScore'].min():.2f}")
    c3.metric("Max |Z|", f"{event_z['ZScore'].abs().max():.2f}")

with tabs[5]:
    st.subheader("Event Summary")

    summary_rows = []

    for c in available_contracts:
        df = data[c].copy()
        df["Window"] = df["DateTime"].apply(lambda x: window_label(x, pre_start, event_start, event_end, post_end))

        pre = df[df["Window"] == "Pre"]
        event = df[df["Window"] == "Event"]

        if len(pre) and len(event):
            price_change = event["Last"].mean() - pre["Last"].mean()
            implied_change = -price_change
            implied_bp = implied_change * 100
            hikes_25bp = implied_bp / 25

            if pre["Volume"].sum() and event["Volume"].sum():
                pre_vwap = (pre["Last"] * pre["Volume"]).sum() / pre["Volume"].sum()
                event_vwap = (event["Last"] * event["Volume"]).sum() / event["Volume"].sum()
                vwap_delta_r_bp = -(event_vwap - pre_vwap) * 100
            else:
                pre_vwap = np.nan
                event_vwap = np.nan
                vwap_delta_r_bp = np.nan

            summary_rows.append({
                "Contract": c,
                "Pre Avg Price": pre["Last"].mean(),
                "Event Avg Price": event["Last"].mean(),
                "Price Change": price_change,
                "Delta r bp": implied_bp,
                "25bp Moves Priced": hikes_25bp,
                "Pre Avg Volume": pre["Volume"].mean(),
                "Event Avg Volume": event["Volume"].mean(),
                "Volume % Change": (event["Volume"].mean() / pre["Volume"].mean() - 1) if pre["Volume"].mean() else np.nan,
                "Pre VWAP": pre_vwap,
                "Event VWAP": event_vwap,
                "VWAP Delta r bp": vwap_delta_r_bp
            })

    summary = pd.DataFrame(summary_rows)
    st.dataframe(summary, use_container_width=True)

    if not summary.empty:
        fig = px.bar(summary, x="Contract", y="25bp Moves Priced", title=f"{event_name}: Equivalent 25bp Moves Priced")
        st.plotly_chart(fig, use_container_width=True)

    curve = build_curve(data, ffill_limit=ffill_limit)
    curve["Window"] = curve["DateTime"].apply(lambda x: window_label(x, pre_start, event_start, event_end, post_end))
    spread_cols = [c for c in ["Y1_Y2", "Y2_Y3", "Y3_Y4", "Y1_Y4"] if c in curve.columns]

    spread_summary = []
    for s in spread_cols:
        pre_mean = curve[curve["Window"] == "Pre"][s].mean()
        event_mean = curve[curve["Window"] == "Event"][s].mean()

        spread_summary.append({
            "Spread": s,
            "Pre Mean": pre_mean,
            "Event Mean": event_mean,
            "Event - Pre": event_mean - pre_mean
        })

    spread_summary = pd.DataFrame(spread_summary)
    st.write("Spread compression")
    st.dataframe(spread_summary, use_container_width=True)
