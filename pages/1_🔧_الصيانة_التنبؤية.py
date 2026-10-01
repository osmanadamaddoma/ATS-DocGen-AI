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
        st.warning("يرجى تسجيل الدخول اولا")
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

st.title("نظام الصيانة التنبؤية الذكي V3.2")
st.caption("Anomaly + Forecast 24h + RUL + Gemini - Fixed for Python 3.14")

# --- Sidebar ---
with st.sidebar:
    st.header("معلمات المولد")
    temp = st.slider("حرارة المحرك C", 40.0, 120.0, 85.0, 0.5)
    vibration = st.slider("اهتزاز mm/s", 0.0, 15.0, 2.5, 0.1)
    voltage = st.number_input("جهد Volt", 300.0, 500.0, 400.0, 5.0)
    oil_press = st.slider("ضغط الزيت Bar", 0.5, 8.0, 4.5, 0.1)
    coolant = st.slider("حرارة التبريد C", 40.0, 110.0, 80.0, 0.5)
    hours = st.number_input("ساعات التشغيل", 0, 50000, 12000, 500)
    enable_gemini = st.checkbox("تفعيل Gemini", True)

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
        reasons.append("حرارة حرجة اكبر من 95")
    elif temp > 88:
        score += 15
        reasons.append("حرارة مرتفعة")
    if vib > 7.0:
        score += 35
        reasons.append("اهتزاز عالي اكبر من 7")
    elif vib > 4.5:
        score += 12
        reasons.append("اهتزاز غير منتظم")
    if volt < 360 or volt > 440:
        score += 25
        reasons.append(f"انحراف جهد {volt}V")
    if oil < 2.0:
        score += 35
        reasons.append("ضغط زيت منخفض جدا")
    if cool > 95:
        score += 20
        reasons.append("حرارة تبريد عالية")
    if hrs > 20000:
        score += 10
        reasons.append("تجاوز 20000 ساعة")
    if anomaly_score < -0.05:
        score += 25
        reasons.append(f"نمط شاذ Score {anomaly_score:.2f}")
    if slope > 0.04:
        score += 15
        reasons.append(f"اتجاه صاعد {slope:.3f} درجة/ساعة")

    if score < 30:
        rul = 600
    elif score < 60:
        rul = 120
    elif score < 85:
        rul = 24
    else:
        rul = 4
    return min(score,100), reasons, rul

risk_score, reasons, rul_hours = calc_risk(temp, vibration, voltage, oil_press, coolant, hours, anomaly_score, slope)

# --- Display ---
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("حرارة", f"{temp} C", f"{slope:+.3f}/h")
c2.metric("اهتزاز", f"{vibration} mm/s", "شاذ" if is_anomaly else "طبيعي")
c3.metric("جهد", f"{voltage} V")
c4.metric("زيت", f"{oil_press} Bar")
c5.metric("تنبؤ 24س", f"{future_temp[2]:.1f} C")

st.divider()
left, right = st.columns([1, 1.8])

with left:
    st.subheader("مؤشر الخطر + RUL")
    st.progress(risk_score/100)
    if risk_score < 35:
        st.success(f"ممتاز {risk_score}% | RUL {rul_hours} ساعة")
    elif risk_score < 70:
        st.warning(f"صيانة خلال 72س | RUL {rul_hours} ساعة {risk_score}%")
    else:
        st.error(f"تدخل فوري | RUL {rul_hours} ساعة {risk_score}%")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist['t'][:-1], y=hist['temp'][:-1], name="تاريخ"))
    fig.add_trace(go.Scatter(x=[120,130,140,144], y=[temp, future_temp[0], future_temp[1], future_temp[2]], name="تنبؤ 24h", line=dict(dash='dash', color='red')))
    fig.update_layout(title="اتجاه الحرارة", height=300, margin=dict(l=0,r=0,t=30,b=0))
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("تقرير التشخيص")
    if reasons:
        for r in reasons:
            st.write(f"- {r}")
    else:
        st.success("جميع المؤشرات طبيعية")

    st.divider()
    if enable_gemini and st.button("توليد تقرير Gemini", type="primary"):
        if not client:
            st.warning("Gemini غير متصل - تشخيص محلي:")
            st.info(f"السبب: اتجاه صاعد {slope:.3f} يدل على انسداد راديتر. RUL {rul_hours}h. نظف الراديتر وافحص سير المروحة.")
        else:
            with st.spinner("يحلل..."):
                prompt = f"انت مهندس مولدات ديزل خبير. حلل: حرارة {temp}C اهتزاز {vibration} جهد {voltage} زيت {oil_press} تبريد {coolant} ساعات {hours} anomaly {anomaly_score:.2f} slope {slope:.3f} risk {risk_score}% RUL {rul_hours}h اسباب {reasons}. اعطني Root Cause واجراء فوري وقطع غيار. عربي مختصر."
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
                    st.info(f"تشخيص محلي: اتجاه {slope:.3f} - افحص الراديتر. RUL {rul_hours}h")

    st.caption(f"Update {datetime.now().strftime('%Y-%m-%d %H:%M')} | Score {anomaly_score:.3f}")
