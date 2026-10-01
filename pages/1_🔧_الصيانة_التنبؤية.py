import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LinearRegression

# 🔒 التحقق من تسجيل الدخول - ضعه في أول الصفحة الرئيسية فقط إذا عندك نظام Login
if "authenticated" in st.session_state:
    if not st.session_state.get("authenticated", False):
        st.warning("⚠️ يرجى تسجيل الدخول أولاً من الصفحة الرئيسية.")
        st.stop()

st.set_page_config(page_title="الصيانة التنبؤية AI V3.1", page_icon="🧠", layout="wide")

st.title("🧠 نظام الصيانة التنبؤية الذكي V3.1 - Predictive + Generative AI")
st.caption("Anomaly Detection + Future Forecast 24h + RUL + Gemini | Addoma Trading Services - Fixed 2026")

# --- إعداد Gemini بشكل آمن ---
client = None
gemini_error = None
try:
    from google import genai
    import os
    gemini_key = st.secrets.get("GEMINI_API_KEY", None) if hasattr(st, 'secrets') else None
    if not gemini_key:
        gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        client = genai.Client(api_key=gemini_key)
except Exception as e:
    gemini_error = str(e)
    client = None

# --- الشريط الجانبي ---
with st.sidebar:
    st.header("⚙️ معلمات المولد اللحظية")
    temp = st.slider("حرارة المحرك (°C):", 40.0, 120.0, 85.0, 0.5)
    vibration = st.slider("اهتزاز (mm/s):", 0.0, 15.0, 2.5, 0.1)
    voltage = st.number_input("جهد (Volt):", 300.0, 500.0, 400.0, 5.0)
    oil_press = st.slider("ضغط الزيت (Bar):", 0.5, 8.0, 4.5, 0.1)
    coolant = st.slider("حرارة سائل التبريد (°C):", 40.0, 110.0, 80.0, 0.5)
    hours = st.number_input("ساعات التشغيل:", 0, 50000, 12000, 500)
    st.divider()
    enable_gemini = st.checkbox("🤖 تفعيل تقرير Gemini التوليدي", True)
    st.caption(f"Gemini Status: {'✅ متصل' if client else f'❌ غير متصل {gemini_error or \"ضع المفتاح في Secrets\"}'}")

# --- 1. بيانات تاريخية محاكاة (في الإنتاج تأتي من Supabase / InfluxDB) ---
np.random.seed(int(hours % 97))
hist = pd.DataFrame({
    't': np.arange(120),
    'temp': 82 + np.random.normal(0, 1.5, 120) + np.linspace(0, 6, 120),
    'vib': 2.5 + np.random.normal(0, 0.3, 120) + np.linspace(0, 0.8, 120)
})
# إضافة القراءة الحالية
new_row = pd.DataFrame({'t': [120], 'temp': [temp], 'vib': [vibration]})
hist = pd.concat([hist, new_row], ignore_index=True)

# --- 2. كشف الشذوذ ---
iso = IsolationForest(contamination=0.08, random_state=42)
X = hist[['temp','vib']]
hist['anomaly'] = iso.fit_predict(X)
anomaly_score = iso.decision_function(X)[-1]
is_anomaly = hist['anomaly'].iloc[-1] == -1

# --- 3. تنبؤ 24 ساعة ---
reg = LinearRegression().fit(hist[['t']], hist['temp'])
future_t = np.array([[130],[140],[144]])
future_temp = reg.predict(future_t)
slope = float(reg.coef_[0])

# --- 4. حساب الخطر و RUL ---
def advanced_risk(temp, vib, volt, oil, cool, hrs, anomaly_score, slope):
    score = 0
    reasons = []
    if temp > 95:
        score+=35; reasons.append("ارتفاع حرارة حرج >95°C - خطر Overheating")
    elif temp > 88:
        score+=15; reasons.append("حرارة مرتفعة - افحص الراديتر والمروحة")
    if vib > 7.0:
        score+=35; reasons.append("اهتزاز عالي >7mm/s - خلل بيرنغ أو عدم اتزان")
    elif vib > 4.5:
        score+=12; reasons.append("اهتزاز غير منتظم")
    if volt < 360 or volt > 440:
        score+=25; reasons.append(f"انحراف جهد {volt}V - مشكلة AVR")
    if oil < 2.0:
        score+=35; reasons.append("ضغط زيت منخفض جداً - أوقف المحرك فوراً")
    elif oil < 3.5:
        score+=10; reasons.append("ضغط زيت أقل من المثالي")
    if cool > 95:
        score+=20; reasons.append("حرارة تبريد عالية - ثرموستات أو مضخة ماء")
    if hrs > 20000:
        score+=10; reasons.append("تجاوز 20 ألف ساعة بدون عمرة")
    if anomaly_score < -0.05:
        score+=25; reasons.append(f"نمط شاذ Anomaly Score {anomaly_score:.2f}")
    if slope > 0.04:
        score+=15; reasons.append(f"اتجاه حراري صاعد {slope:.3f}°/ساعة - تدهور تدريجي")

    if score < 30: rul = 600
    elif score < 60: rul = 120
    elif score < 85: rul = 24
    else: rul = 4
    return min(score,100), reasons, rul

risk_score, reasons, rul_hours = advanced_risk(temp, vibration, voltage, oil_press, coolant, hours, anomaly_score, slope)

# --- العرض الرئيسي ---
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("حرارة", f"{temp}°C", f"{slope:+.3f}/h")
c2.metric("اهتزاز", f"{vibration} mm/s", "شاذ 🔴" if is_anomaly else "طبيعي 🟢")
c3.metric("جهد", f"{voltage} V")
c4.metric("ضغط زيت", f"{oil_press} Bar")
c5.metric("تنبؤ 24س", f"{future_temp[2]:.1f}°C", delta_color="inverse")

st.divider()

left, right = st.columns([1, 1.8])

with left:
    st.subheader("📊 مؤشر الخطر + RUL")
    st.progress(risk_score/100)
    if risk_score < 35:
        st.success(f"🟢 ممتاز {risk_score}% | RUL: {rul_hours} ساعة")
    elif risk_score < 70:
        st.warning(f"🟡 صيانة خلال 72س | RUL: {rul_hours} ساعة ({risk_score}%)")
    else:
        st.error(f"🔴 تدخل فوري! | RUL: {rul_hours} ساعة فقط ({risk_score}%)")

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist['t'][:-1], y=hist['temp'][:-1], name="تاريخ", line=dict(color="#182b49")))
    fig.add_trace(go.Scatter(x=[120,130,140,144], y=[temp, future_temp[0], future_temp[1], future_temp[2]], name="تنبؤ AI 24h", line=dict(dash='dash', color='red')))
    fig.update_layout(title="اتجاه الحرارة - تنبؤ 24 ساعة", height=300, margin=dict(l=0,r=0,t=30,b=0))
    st.plotly_chart(fig, use_container_width=True)

    fig2 = go.Figure(go.Indicator(mode="gauge+number", value=risk_score, gauge={'axis':{'range':[0,100]}, 'bar':{'color':"red" if risk_score>70 else "orange" if risk_score>35 else "green"}, 'steps':[{'range':[0,35],'color':"#e6f4ea"},{'range':[35,70],'color':"#fef7e0"},{'range':[70,100],'color':"#fce8e6"}]}, title={'text':"Risk Score"}))
    fig2.update_layout(height=250, margin=dict(l=20,r=20,t=40,b=20))
    st.plotly_chart(fig2, use_container_width=True)

with right:
    st.subheader("🤖 تقرير التشخيص التوليدي")
    if reasons:
        for r in reasons:
            st.write(f"- ⚠️ {r}")
    else:
        st.success("✅ جميع المؤشرات ضمن النطاق الطبيعي")

    st.divider()

    if enable_gemini:
        if st.button("🧠 توليد تقرير استشاري بـ Gemini", type="primary"):
            if not client:
                st.warning("⚠️ Gemini غير متصل. أضف GEMINI_API_KEY في Streamlit Secrets")
                st.info(f"""
                **🛠️ تشخيص محلي ذكي (بدون Gemini):**
                - **السبب الجذري:** اتجاه حراري صاعد {slope:.3f}°/ساعة يدل على بداية انسداد راديتر أو ضعف مروحة
                - **الإجراء الفوري:** نظف الراديتر بضغط هواء، افحص سير المروحة، مستوى سائل التبريد
                - **قطع غيار متوقعة:** فلتر هواء، ثرموستات، سير مروحة
                - **RUL:** {rul_hours} ساعة عمل آمن
                """)
            else:
                with st.spinner("Gemini يحلل السبب الجذري..."):
                    prompt = f"""
                    أنت كبير مهندسي مولدات ديزل Perkins/Cummins وخبير DSE.
                    بيانات: حرارة {temp}C, اهتزاز {vibration}mm/s, جهد {voltage}V, زيت {oil_press}Bar, تبريد {coolant}C, ساعات {hours}
                    Anomaly: {is_anomaly}, Score {anomaly_score:.3f}, Slope {slope:.4f}, Risk {risk_score}%, RUL {rul_hours}h
                    الأسباب: {', '.join(reasons) if reasons else 'لا يوجد'}
                    المطلوب: تقرير فني من 3 نقاط: 1- Root Cause 2- إجراء فوري 3- قطع غيار. عربي فني مختصر.
                    """
                    success = False
                    # قائمة الموديلات المدعومة في 2026 بالترتيب
                    models_to_try = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
                    for model_name in models_to_try:
                        try:
                            response = client.models.generate_content(model=model_name, contents=prompt)
                            st.markdown(response.text)
                            st.caption(f"تم عبر {model_name}")
                            success = True
                            break
                        except Exception as e:
                            err_msg = str(e)
                            if "404" in err_msg or "NOT_FOUND" in err_msg:
                                continue
                            else:
                                st.error(f"خطأ في {model_name}: {err_msg}")
                                break
                    if not success:
                        st.warning("⚠️ فشلت جميع موديلات Gemini، هذا تشخيص محلي:")
                        st.markdown(f"""
                        - **Root Cause:** اتجاه صاعد {slope:.3f} - انسداد راديتر محتمل
                        - **إجراء:** تنظيف راديتر + فحص ثرموستات + شد سير
                        - **قطع غيار:** فلتر هواء، ثرموستات
                        """)
    else:
        st.info("فعّل خيار Gemini من الشريط الجانبي للحصول على تقرير توليدي")

    st.divider()
    st.caption(f"Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Anomaly Score: {anomaly_score:.3f}")
