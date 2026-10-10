# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression
from datetime import datetime

st.set_page_config(page_title="Predictive AI V3.2", page_icon="Wrench", layout="wide")

# --- Auth check ---
if "authenticated" in st.session_state:
    if not st.session_state.get("authenticated", False):
        st.warning("Please login first")
        st.stop()

# --- Gemini setup safe ---
client = None
try:
    from google import genai
    import os
    api_key = None
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        client = genai.Client(api_key=api_key)
except Exception as e:
    client = None

st.title("Smart Predictive Maintenance System V3.2")
st.caption("Anomaly + Forecast 24h + RUL + Gemini - Fixed for Python 3.14")

# --- Sidebar ---
with st.sidebar:
    st.header("Generator Parameters")
    temp = st.slider("Engine Temp C", 40.0, 120.0, 85.0, 0.5)
    vibration = st.slider("Vibration mm/s", 0.0, 15.0, 2.5, 0.1)
    voltage = st.number_input("Voltage Volt", 300.0, 500.0, 400.0, 5.0)
    oil_press = st.slider("Oil Pressure Bar", 0.5, 8.0, 4.5, 0.1)
    coolant = st.slider("Coolant Temp C", 40.0, 110.0, 80.0, 0.5)
    hours = st.number_input("Operating Hours", 0, 50000, 12000, 500)
    enable_gemini = st.checkbox("Enable Gemini", True)

# --- Historical data simulation ---
np.random.seed(int(hours % 97))
hist = pd.DataFrame({
    't': np.arange(120),
    'temp': 82 + np.random.normal(0, 1.5, 120) + np.linspace(0, 6, 120),
    'vib': 2.5 + np.random.normal(0, 0.3, 120) + np.linspace(0, 0.8, 120)
})
new_row = pd.DataFrame({'t': [120], 'temp': [temp], 'vib': [vibration]})
hist = pd.concat([hist, new_row], ignore_index=True)

# --- Anomaly ---
iso = IsolationForest(contamination=0.08, random_state=42)
X = hist[['temp','vib']]
hist['anomaly'] = iso.fit_predict(X)
anomaly_score = float(iso.decision_function(X)[-1])
is_anomaly = hist['anomaly'].iloc[-1] == -1

# --- Forecast ---
reg = LinearRegression().fit(hist[['t']], hist['temp'])
future_t = np.array([[130],[140],[144]])
future_temp = reg.predict(future_t)
slope = float(reg.coef_[0])

# --- Risk ---
def calc_risk(temp, vib, volt, oil, cool, hrs, anomaly_score, slope):
    score = 0
    reasons = []
    if temp > 95:
        score += 35
        reasons.append("Critical temperature greater than 95")
    elif temp > 88:
        score += 15
        reasons.append("High temperature")
    if vib > 7.0:
        score += 35
        reasons.append("High vibration greater than 7")
    elif vib > 4.5:
        score += 12
        reasons.append("Irregular vibration")
    if volt < 360 or volt > 440:
        score += 25
        reasons.append(f"Voltage deviation {volt}V")
    if oil < 2.0:
        score += 35
        reasons.append("Very low oil pressure")
    if cool > 95:
        score += 20
        reasons.append("High coolant temperature")
    if hrs > 20000:
        score += 10
        reasons.append("Exceeded 20000 hours")
    if anomaly_score < -0.05:
        score += 25
        reasons.append(f"Anomalous pattern Score {anomaly_score:.2f}")
    if slope > 0.04:
        score += 15
        reasons.append(f"Upward trend {slope:.3f} deg/hr")
    
    if score < 30:
        rul = 600
    elif score < 60:
        rul = 120
    elif score < 85:
        rul = 24
    else:
        rul = 4
    return min(score, 100), reasons, rul

risk_score, reasons, rul_hours = calc_risk(temp, vibration, voltage, oil_press, coolant, hours, anomaly_score, slope)

# --- Display ---
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Temperature", f"{temp} C", f"{slope:+.3f}/h")
c2.metric("Vibration", f"{vibration} mm/s", "Anomaly" if is_anomaly else "Normal")
c3.metric("Voltage", f"{voltage} V")
c4.metric("Oil Press", f"{oil_press} Bar")
c5.metric("Forecast 24h", f"{future_temp[2]:.1f} C")

st.divider()

left, right = st.columns([1, 1.8])
with left:
    st.subheader("Risk Index + RUL")
    st.progress(risk_score / 100)
    if risk_score < 35:
        st.success(f"Excellent {risk_score}% | RUL {rul_hours} hours")
    elif risk_score < 70:
        st.warning(f"Maintenance within 72h | RUL {rul_hours} hours {risk_score}%")
    else:
        st.error(f"Immediate Intervention | RUL {rul_hours} hours {risk_score}%")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist['t'][:-1], y=hist['temp'][:-1], name="History"))
    fig.add_trace(go.Scatter(x=[120, 130, 140, 144], y=[temp, future_temp[0], future_temp[1], future_temp[2]], name="Forecast 24h", line=dict(dash='dash', color='red')))
    fig.update_layout(title="Temperature Trend", height=300, margin=dict(l=0, r=0, t=30, b=0))
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Diagnostics Report")
    if reasons:
        for r in reasons:
            st.write(f"- {r}")
    else:
        st.success("All parameters are normal")
    
    st.divider()
    if enable_gemini and st.button("Generate Gemini Report", type="primary"):
        if not client:
            st.warning("Gemini is not connected - Local diagnostics:")
            st.info(f"Reason: Upward trend {slope:.3f} indicates radiator blockage. RUL {rul_hours}h. Clean radiator and check fan belt.")
        else:
            with st.spinner("Analyzing..."):
                prompt = f"You are an expert diesel generator engineer. Analyze: Temp {temp}C, Vibration {vibration}, Voltage {voltage}, Oil {oil_press}, Coolant {coolant}, Hours {hours}, Anomaly {anomaly_score:.2f}, Slope {slope:.3f}, Risk {risk_score}%, RUL {rul_hours}h, Reasons {reasons}. Provide Root Cause, immediate action, and spare parts. Concise English."
                done = False
                for model_name in ["gemini-2.5-flash", "gemini-1.5-flash"]:
                    try:
                        resp = client.models.generate_content(model=model_name, contents=prompt)
                        st.markdown(resp.text)
                        st.caption(f"via {model_name}")
                        done = True
                        break
                    except Exception as e:
                        if "404" in str(e) or "NOT_FOUND" in str(e):
                            continue
                        else:
                            st.error(str(e))
                            break
                if not done:
                    st.info(f"Local diagnostics: Trend {slope:.3f} - Check radiator. RUL {rul_hours}h")
    
    st.caption(f"Update {datetime.now().strftime('%Y-%m-%d %H:%M')} | Score {anomaly_score:.3f}")
