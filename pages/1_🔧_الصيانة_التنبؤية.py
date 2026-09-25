import streamlit as st
import pandas as pd
import numpy as np

# 🔒 شرط الحقق من تسجيل الدخول من الصفحة الرئيسية
if not st.session_state.get("authenticated", False):
    st.warning("⚠️ يرجى تسجيل الدخول أولاً من الصفحة الرئيسية للوصول لهذا التطبيق.")
    st.stop()

st.set_page_config(page_title="الصيانة التنبؤية للمولدات", page_icon="🔧", layout="wide")

st.title("🔧 نظام الصيانة التنبؤية وتحليل أداء المولدات")
st.caption("أداة التنبؤ بالأعطال واختبار الإجهاد الحراري والميكانيكي - Addoma Trading Services")

# --- الشريط الجانبي للمدخلات الفنية ---
with st.sidebar:
    st.header("⚙️ معلمات المولد اللحظية")
    temp = st.slider("درجة حرارة المحرك (°C):", 40.0, 120.0, 85.0, 0.5)
    vibration = st.slider("مستوى الاهتزاز (mm/s):", 0.0, 15.0, 2.5, 0.1)
    voltage = st.number_input("جهد المولد (Volt):", 300.0, 500.0, 400.0, 5.0)
    hours = st.number_input("ساعات التشغيل الكلية:", 0, 50000, 12000, 500)

# --- خوارزمية التقييم والتنبؤ بالأعطال ---
def predict_fault(temp, vib, volt, hrs):
    score = 0
    reasons = []
    
    if temp > 95:
        score += 40
        reasons.append("ارتفاع حرارة المحرك عن الحد المسموح (Overheating)")
    elif temp > 88:
        score += 20
        reasons.append("تحذير: حرارة المحرك مرتفعة نسبياً")
        
    if vib > 7.0:
        score += 40
        reasons.append("اهتزاز ميكانيكي عالي (High Mechanical Vibration)")
    elif vib > 4.5:
        score += 15
        reasons.append("تحذير: اهتزازات غير منتظمة")
        
    if volt < 360 or volt > 440:
        score += 30
        reasons.append("انحراف الجهد عن النطاق المسموح (Voltage Fluctuation)")
        
    if hrs > 20000:
        score += 10
        reasons.append("المولد تجاوز ساعات الخدمة القياسية بدون صيانة عمرة")
        
    return min(score, 100), reasons

risk_score, fault_reasons = predict_fault(temp, vibration, voltage, hours)

# --- عرض نتائج التشخيص ---
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("حرارة المحرك", f"{temp} °C")
with col2:
    st.metric("مستوى الاهتزاز", f"{vibration} mm/s")
with col3:
    st.metric("الجهد الحالي", f"{voltage} V")

st.divider()

col_status, col_info = st.columns([1, 2])

with col_status:
    st.subheader("مؤشر الخطر (Fault Risk Score)")
    st.progress(risk_score / 100)
    
    if risk_score < 30:
        st.success(f"🟢 حالة المولد ممتازة ({risk_score}%)")
    elif risk_score < 65:
        st.warning(f"🟡 يحتاج صيانة وقائية قريباً ({risk_score}%)")
    else:
        st.error(f"🔴 خطر عطل وشيك! يتطلب تدخلاً فورياً ({risk_score}%)")

with col_info:
    st.subheader("📋 تقرير التشخيص الفني")
    if fault_reasons:
        for r in fault_reasons:
            st.write(f"- ⚠️ {r}")
    else:
        st.write("✅ جميع المؤشرات الفنية ضمن النطاق الطبيعي للتشغيل المستمر.")

    st.info("💡 نصيحة مهندس الصيانة: تأكد من مراجعة مستشعرات DSE وفحص الفلاتر ونظام التبريد بشكل دوري.")
