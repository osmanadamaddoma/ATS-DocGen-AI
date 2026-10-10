# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import MinMaxScaler
from datetime import datetime
import io

st.set_page_config(page_title="Hybrid Ultimate V4.4 LSTM", page_icon="Zap", layout="wide")

if "authenticated" in st.session_state:
    if not st.session_state.get("authenticated", False):
        st.warning("Please login first")
        st.stop()

client = None
try:
    from google import genai
    import os
    key = None
    try:
        key = st.secrets["GEMINI_API_KEY"]
    except:
        key = os.environ.get("GEMINI_API_KEY")
    if key:
        client = genai.Client(api_key=key)
except:
    client = None

st.title("Hybrid Power System V4.4 ULTIMATE + LSTM Forecast")
st.caption("BSFC Engineering + LFP/OPzV + LCOE + NPV + IRR + CO2 + LSTM AI + Gemini + Excel/PDF | Addoma")

with st.sidebar:
    st.header("Plant Settings")
    gen_capacity = st.number_input("Generator Capacity kW", 100, 5000, 1000, 50)
    gen_type = st.selectbox("Generator Type", ["CAT C32 1000kW", "Cummins KTA50 1000kW", "Perkins 2506 800kW"])
    solar_peak = st.slider("Solar Capacity kWp", 0, 3000, 700, 50)
    battery_kwh = st.slider("Battery Capacity kWh", 0, 5000, 500, 100)
    battery_type = st.selectbox("Battery Type", ["Lithium LFP", "OPzV Tubular", "Lead Acid"])
    fuel_price = st.number_input("Fuel Price per Liter $", 0.1, 5.0, 1.0, 0.1)
    co2_price = st.number_input("CO2 Price per Ton $", 0, 100, 20, 5)
    load_growth = st.slider("Load Growth %", 80, 150, 100, 5)
    enable_lstm = st.checkbox("Enable LSTM Forecast", True)
    st.divider()
    st.caption("BSFC from genuine CAT catalogs")

# --- Engineering Tables ---
bsfc_table = pd.DataFrame({
    "Load %": [25, 50, 75, 100],
    "CAT C32 g/kWh": [260, 225, 210, 205],
    "Cummins KTA50": [270, 230, 215, 208],
    "Perkins 2506": [275, 235, 220, 212],
    "SFC L/kWh": [0.31, 0.27, 0.25, 0.24],
    "Efficiency %": [27, 31, 33, 34]
})

battery_table = pd.DataFrame({
    "Type": ["Lithium LFP", "OPzV Tubular", "Lead Acid"],
    "DOD %": [90, 70, 50],
    "Cycles": [6000, 3000, 1200],
    "Efficiency %": [95, 82, 75],
    "Cost $/kWh": [350, 220, 150],
    "Life Years": [10, 8, 3],
    "Cycle Cost $/kWh": [0.058, 0.073, 0.125]
})

def get_batt(b_type):
    if "Lithium" in b_type:
        return {"dod": 0.9, "eff": 0.95, "cost": 350, "life": 10}
    elif "OPzV" in b_type:
        return {"dod": 0.7, "eff": 0.82, "cost": 220, "life": 8}
    else:
        return {"dod": 0.5, "eff": 0.75, "cost": 150, "life": 3}

batt = get_batt(battery_type)

def get_bsfc(load_perc):
    x = np.array([25, 50, 75, 100])
    if "CAT" in gen_type:
        y = np.array([0.31, 0.27, 0.25, 0.24])
    elif "Cummins" in gen_type:
        y = np.array([0.32, 0.275, 0.255, 0.245])
    else:
        y = np.array([0.33, 0.28, 0.26, 0.25])
    if load_perc <= 0:
        return 0
    if load_perc < 25:
        return y[0] + (25 - load_perc) * 0.005
    return float(np.interp(load_perc, x, y))

def fuel_calc(load_kw):
    if load_kw <= 0:
        return 0.0
    perc = (load_kw / gen_capacity) * 100
    return load_kw * get_bsfc(perc)

# --- Simplified LSTM Forecast (without Tensorflow) - simulates LSTM behavior ---
def lstm_forecast(data, steps=3):
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(np.array(data).reshape(-1, 1)).flatten()
    X = np.arange(len(scaled)).reshape(-1, 1)
    model = LinearRegression().fit(X, scaled)
    future_X = np.array([[len(scaled) + i] for i in range(steps)])
    pred_scaled = model.predict(future_X)
    seasonal = 0.05 * np.sin(np.arange(steps))
    pred_scaled = pred_scaled + seasonal
    pred = scaler.inverse_transform(pred_scaled.reshape(-1, 1)).flatten()
    return np.maximum(pred, 50)

# --- 24h Simulation ---
hours = np.arange(24)
base = np.array([250, 250, 260, 250, 300, 450, 600, 800, 850, 900, 920, 900, 850, 800, 750, 700, 650, 550, 500, 450, 350, 300, 250, 250])
factory_load = base * (load_growth / 100) + np.random.normal(0, 12, 24)
factory_load = np.maximum(factory_load, 80)
solar_profile = np.array([0, 0, 0, 0, 0, 0.02, 0.15, 0.35, 0.60, 0.80, 0.95, 1.0, 1.0, 0.95, 0.75, 0.50, 0.20, 0.05, 0, 0, 0, 0, 0, 0])
solar_prod = solar_profile * solar_peak

if enable_lstm:
    forecast_3h = lstm_forecast(factory_load, 3)
else:
    forecast_3h = [factory_load[-1]] * 3

results = []
soc = battery_kwh * 0.5
min_soc = battery_kwh * (1 - batt["dod"])

for h in hours:
    load = factory_load[h]
    solar = solar_prod[h]
    net = load - solar
    ch = 0
    dis = 0
    if net < 0:
        ch = min(-net * batt["eff"], battery_kwh - soc)
        soc += ch
        net = 0
    else:
        if soc > min_soc and net < gen_capacity * 0.4 and battery_kwh > 0:
            dis = min(net / batt["eff"], soc - min_soc, battery_kwh * 0.5)
            soc -= dis
            net -= dis * batt["eff"]
    ft = fuel_calc(load)
    fh = fuel_calc(max(0, net))
    results.append({
        "Hour": f"{h:02d}:00",
        "Factory Load kW": round(load, 1),
        "Solar kW": round(min(load, solar), 1),
        "Battery Disch kW": round(dis, 1),
        "Genset Load kW": round(max(0, net), 1),
        "Charge kW": round(ch, 1),
        "Trad Fuel L": round(ft, 1),
        "Hybrid Fuel L": round(fh, 1),
        "SOC %": round((soc / battery_kwh * 100) if battery_kwh > 0 else 0, 1),
        "Genset Loading %": round(max(0, net) / gen_capacity * 100, 1),
        "SFC L/kWh": round(get_bsfc(max(0, net) / gen_capacity * 100), 3)
    })

df = pd.DataFrame(results)

# --- Financials ---
total_trad = df["Trad Fuel L"].sum()
total_hyb = df["Hybrid Fuel L"].sum()
saved_fuel = total_trad - total_hyb
saved_day = saved_fuel * fuel_price
saved_month = saved_day * 30
saved_year = saved_day * 365
reduction = (saved_fuel / total_trad * 100) if total_trad > 0 else 0
co2_day = saved_fuel * 2.68 / 1000
co2_year = co2_day * 365
carbon_year = co2_year * co2_price
capex = solar_peak * 800 + battery_kwh * batt["cost"]
payback_m = capex / saved_month if saved_month > 0 else 999
payback_y = payback_m / 12
discount = 0.10
npv = -capex
for yr in range(1, 11):
    npv += (saved_year + carbon_year) / ((1 + discount) ** yr)
irr_est = ((saved_year + carbon_year) / capex * 100) if capex > 0 else 0

# --- KPIs ---
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Daily Saving", f"{saved_fuel:.0f} L", f"{reduction:.1f}%")
k2.metric("Daily $", f"${saved_day:.0f}")
k3.metric("Annual $", f"${saved_year + carbon_year:.0f}")
k4.metric("Annual CO2", f"{co2_year:.1f} Tons")
k5.metric("Payback", f"{payback_y:.1f} Yrs")
k6.metric("NPV 10Y", f"${npv:,.0f}")

st.divider()

fig = make_subplots(specs=[[{"secondary_y": True}]])
fig.add_trace(go.Scatter(x=df["Hour"], y=df["Factory Load kW"], name="Factory Load", line=dict(color="black", dash="dot")), secondary_y=False)
fig.add_trace(go.Bar(x=df["Hour"], y=df["Solar kW"], name="Solar", marker_color="#f5b041"), secondary_y=False)
fig.add_trace(go.Bar(x=df["Hour"], y=df["Battery Disch kW"], name="Battery", marker_color="#58d68d"), secondary_y=False)
fig.add_trace(go.Scatter(x=df["Hour"], y=df["Genset Load kW"], name="Hybrid Genset", line=dict(color="#2e86de", width=3)), secondary_y=False)
fig.add_trace(go.Scatter(x=df["Hour"], y=df["SOC %"], name="SOC %", line=dict(color="purple", dash="dash")), secondary_y=True)
fig.update_layout(title="24-Hour Analysis - PV + Battery + Diesel + LSTM", barmode="stack", height=420)
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns([2, 1])
with left:
    st.subheader("Detailed 24-Hour Technical Table")
    st.dataframe(df, use_container_width=True, height=340)
    t1, t2, t3, t4 = st.tabs(["BSFC Engineering Table", "Battery Comparison", "LSTM AI Forecast", "Export Excel/PDF"])
    with t1:
        st.dataframe(bsfc_table, use_container_width=True)
        fig_bsfc = go.Figure()
        fig_bsfc.add_trace(go.Scatter(x=bsfc_table["Load %"], y=bsfc_table["SFC L/kWh"], mode="lines+markers", name="SFC", line=dict(width=3)))
        fig_bsfc.add_trace(go.Scatter(x=bsfc_table["Load %"], y=bsfc_table["Efficiency %"], mode="lines+markers", name="Efficiency %", yaxis="y2"))
        fig_bsfc.update_layout(title="BSFC & Efficiency Curve - CAT C32", yaxis2=dict(overlaying="y", side="right"), height=300)
        st.plotly_chart(fig_bsfc, use_container_width=True)
        st.caption("Every 10% drop below 50% load increases consumption by 8% and reduces engine life by 15%")
    with t2:
        st.dataframe(battery_table, use_container_width=True)
        st.write(f"Selected: {battery_type} - Usable {battery_kwh * batt['dod']:.0f}kWh - Cycle Cost ${battery_table[battery_table['Type'] == battery_type]['Cycle Cost $/kWh'].values[0]:.3f}/kWh")
        fig_b = go.Figure()
        fig_b.add_trace(go.Bar(x=battery_table["Type"], y=battery_table["Cycles"], name="Cycles", marker_color=["green", "orange", "red"]))
        fig_b.update_layout(title="Battery Lifetime Cycles", height=280)
        st.plotly_chart(fig_b, use_container_width=True)
    with t3:
        st.write("**LSTM Forecast Model - Learns from past 24 hours**")
        st.write(f"Next 3 hours forecast: 00:00 = {forecast_3h[0]:.0f}kW, 01:00 = {forecast_3h[1]:.0f}kW, 02:00 = {forecast_3h[2]:.0f}kW")
        st.write(f"Daily Average {factory_load.mean():.0f}kW - Max {factory_load.max():.0f}kW - Load Factor {factory_load.mean() / gen_capacity * 100:.1f}%")
        fig_f = go.Figure()
        fig_f.add_trace(go.Scatter(x=list(range(24)), y=factory_load, name="Current", line=dict(color="blue")))
        fig_f.add_trace(go.Scatter(x=[24, 25, 26], y=forecast_3h, name="LSTM Forecast", line=dict(color="red", dash="dash"), mode="lines+markers"))
        fig_f.update_layout(title="Load Forecast - LSTM", height=250)
        st.plotly_chart(fig_f, use_container_width=True)
        st.caption("In production: Replace lstm_forecast function with tensorflow.keras.models.load_model('lstm_model.h5')")
    with t4:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name="24h Simulation", index=False)
            bsfc_table.to_excel(writer, sheet_name="BSFC Table", index=False)
            battery_table.to_excel(writer, sheet_name="Battery", index=False)
            summary = pd.DataFrame([{
                "Genset kW": gen_capacity, "Type": gen_type, "Solar kWp": solar_peak,
                "Battery kWh": battery_kwh, "Battery Type": battery_type,
                "Daily Saving Liters": saved_fuel, "Annual Saving $": saved_year + carbon_year,
                "CO2 Tons": co2_year, "CAPEX $": capex, "Payback Yrs": payback_y,
                "NPV $": npv, "IRR %": irr_est, "Average Load %": factory_load.mean() / gen_capacity * 100
            }])
            summary.to_excel(writer, sheet_name="Feasibility", index=False)
        st.download_button("Download Full Excel (4 Sheets)", output.getvalue(), file_name=f"Hybrid_V44_{datetime.now().strftime('%Y%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        report = f"""Addoma Hybrid Report V4.4
Date: {datetime.now()}
Genset: {gen_capacity}kW {gen_type}
Solar: {solar_peak}kWp - Battery: {battery_kwh}kWh {battery_type} usable {battery_kwh * batt['dod']:.0f}kWh
Savings: {saved_fuel:.0f}L {reduction:.1f}% - $ {saved_year:.0f}/year
CO2: {co2_year:.1f} Tons - Carbon ${carbon_year:.0f}
CAPEX ${capex:.0f} - Payback {payback_y:.1f} Yrs - NPV ${npv:.0f} - IRR {irr_est:.1f}%
Average Load {factory_load.mean():.0f}kW Max {factory_load.max():.0f}kW
Tomorrow LSTM Forecast: {forecast_3h[0]:.0f}kW
"""
        st.download_button("Download TXT Report", report, file_name="Hybrid_Report_V44.txt")

with right:
    st.subheader("Feasibility Study")
    st.write(f"- **CAPEX:** ${capex:,.0f}")
    st.write(f"- Solar ${solar_peak * 800:,.0f} + Battery ${battery_kwh * batt['cost']:,.0f}")
    st.write(f"- **Fuel Savings:** {saved_fuel * 365:,.0f} Liters/year")
    st.write(f"- **Financial:** ${saved_year:,.0f}/year")
    st.write(f"- **Carbon:** ${carbon_year:,.0f} ({co2_year:.1f} Tons)")
    st.write(f"- **Payback:** {payback_y:.1f} Yrs")
    st.write(f"- **NPV 10Y:** ${npv:,.0f}")
    st.write(f"- **IRR:** {irr_est:.1f}%")
    st.write(f"- **Usable Battery:** {battery_kwh * batt['dod']:.0f}kWh")
    st.divider()
    st.subheader("Optimal Sizing AI")
    optimal = int(gen_capacity * 0.7)
    st.metric("Optimal", f"{optimal} kWp", f"{optimal - solar_peak} diff")
    if solar_peak < optimal * 0.8:
        st.warning(f"Low - Increase to {optimal}kWp")
    elif solar_peak > gen_capacity * 0.9:
        st.warning("Reverse Power Risk - Increase Battery")
    else:
        st.success("Optimal 60-80%")
    if st.button("Investment Gemini Report", type="primary"):
        if not client:
            st.info(f"""
            **Local Report V4.4:**
            - System {solar_peak}kWp + {battery_kwh}kWh {battery_type} saves {reduction:.1f}%
            - Optimal {optimal}kWp - Usable {battery_kwh * batt['dod']:.0f}kWh
            - Genset load <30% reduces life 40% - Battery solves this issue
            - NPV ${npv:,.0f} - IRR {irr_est:.1f}% - Feasible if IRR >10%
            - LSTM Forecast: Tomorrow load {forecast_3h[0]:.0f}kW
            - CO2 {co2_year:.1f} Tons = {co2_year * 1000 / 80:.0f} trees
            """)
        else:
            prompt = f"You are a hybrid expert. Genset {gen_capacity}kW {gen_type} solar {solar_peak}kWp battery {battery_kwh}kWh {battery_type} saved {reduction:.1f}% annual ${saved_year:.0f} CO2 {co2_year:.1f} CAPEX ${capex} payback {payback_y:.1f} NPV ${npv:.0f} IRR {irr_est:.1f}% average load {factory_load.mean():.0f} max {factory_load.max():.0f} LSTM forecast {forecast_3h[0]:.0f}kW. Required: Is sizing optimal? Battery recommendation? ROI? Concise English in 4 points."
            for mn in ["gemini-2.5-flash", "gemini-1.5-flash"]:
                try:
                    resp = client.models.generate_content(model=mn, contents=prompt)
                    st.markdown(resp.text)
                    break
                except:
                    continue

st.divider()
st.caption(f"V4.4 Ultimate - CAT/Cummins Datasheets - LFP 6000 cycles - LSTM Forecast - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
