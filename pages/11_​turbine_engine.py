import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime

# إعدادات الصفحة
st.set_page_config(page_title="ATS DocIntel GenAI - Industrial Asset Platform", layout="wide")

st.title("⚡ ATS DocIntel GenAI - Enterprise Turbomachinery & PdM Suite")
st.markdown("المنظومة الرقمية المتقدمة لمراقبة التوربينات والمعدات الدوارة، أنظمة التحكم، والصيانة التنبؤية - **ADDOMA TRADING SERVICES**")

# ==========================================
# 1. مكتبة الدوال الهندسية والتحليلية المتقدمة
# ==========================================

def analyze_vibration(readings, warning_limit=4.5, critical_limit=7.0):
    max_vib = np.max(readings)
    if max_vib >= critical_limit:
        status = "Critical (حرج - خطر تلف المحامل أو عدم اتزان)"
        color = "red"
        recommendation = "خطر حرج: تجاوز حدود الاهتزاز الآمنة. يلزم الإيقاف الفوري والفحص الطيفي (FFT) وتحليل الزيت."
    elif max_vib >= warning_limit:
        status = "Warning (تنبيه - مراقبة مكثفة)"
        color = "orange"
        recommendation = "ارتفاع ملحوظ في الاهتزاز: يوصى بفحص محاذاة العمود (Misalignment) ومراجعة خلوصات المحامل."
    else:
        status = "Normal (طبيعي - استقرار تشغيلي)"
        color = "green"
        recommendation = "المعدة تعمل ضمن النطاق الآمن وفق معايير ISO 10816."
    return max_vib, status, color, recommendation

def evaluate_turbine_advanced(load_mw, egt_temp, vibration_rms, lube_temp, oil_debris_ppm):
    """
    تقييم شامل للتوربينة يشمل الحرارة، الاهتزاز، حرارة الزيت، والشوائب المعدنية
    """
    health_score = 100
    alerts = []
    
    if egt_temp > 550.0:
        health_score -= 25
        alerts.append("تجاوز في درجات حرارة العادم (EGT High)")
    if vibration_rms > 4.5:
        health_score -= 30
        alerts.append("مستويات اهتزاز غير مطابقة للمواصفات")
    if lube_temp > 70.0:
        health_score -= 15
        alerts.append("ارتفاع حرارة زيت التزييت (Lube Oil Temperature)")
    if oil_debris_ppm > 50:
        health_score -= 30
        alerts.append("تركز عالٍ للراسب المعدني في الزيت (Wear Debris Alert)")
        
    health_score = max(0, health_score)
    
    if health_score >= 85:
        status = "ممتازة (Optimal Asset Health)"
        color = "green"
    elif health_score >= 60:
        status = "متوسطة (Requires Predictive Action)"
        color = "orange"
    else:
        status = "حرجة (Immediate Intervention Required)"
        color = "red"
        
    return health_score, status, color, alerts

def calculate_thermal_efficiency(power_output_mw, fuel_flow_kg_s, lhv_kj_kg=50000):
    power_kw = power_output_mw * 1000.0
    total_heat_input = fuel_flow_kg_s * lhv_kj_kg
    if total_heat_input <= 0:
        return 0.0
    return round((power_kw / total_heat_input) * 100.0, 2)

def calculate_rul(max_hist_vib):
    return max(0, int(1000 - (max_hist_vib * 85)))

# ==========================================
# لوحة التحكم والوحدات الجانبية (Sidebar)
# ==========================================
st.sidebar.header("لوحة تحكم المنظومة الصناعية")
asset_id = st.sidebar.text_input("معرف المعدة / التوربينة", "ATS-GAS-TURBINE-01")

app_mode = st.sidebar.selectbox("اختر وحدة التشغيل:", [
    "📊 التشخيص الميداني للاهتزازات (Velocity RMS)", 
    "⚙️ تقييم صحة التوربينات الشامل (Advanced Diagnostics)",
    "🔥 كفاءة التوربينات الحرارية (Thermal Efficiency)",
    "🛠️ أجهزة الاستشعار وأنظمة التحكم (Sensors & Control)",
    "🔮 الصيانة التنبؤية والسجلات التاريخية (PdM & RUL)",
    "📋 خارطة طريق التنفيذ الميداني (Implementation Guide)",
    "🤖 المساعد الذكي للصيانة (GenAI Copilot)"
])

# ==========================================
# 1. التشخيص الميداني للاهتزازات
# ==========================================
if app_mode == "📊 التشخيص الميداني للاهتزازات (Velocity RMS)":
    st.subheader("📊 مراقبة اهتزازات المحامل (Horizontal, Vertical, Axial)")
    col1, col2, col3 = st.columns(3)
    with col1: h_val = st.number_input("أفقي H (mm/s)", value=3.2, step=0.1)
    with col2: v_val = st.number_input("عمودي V (mm/s)", value=2.8, step=0.1)
    with col3: a_val = st.number_input("محوري A (mm/s)", value=5.1, step=0.1)

    if st.button("🚀 تحليل الاهتزاز الفوري"):
        max_v, status, color, rec = analyze_vibration([h_val, v_val, a_val])
        st.markdown(f"### الحالة: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
        st.info(f"**التوصية الهندسية:** {rec}")
        
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.bar(['Horizontal', 'Vertical', 'Axial'], [h_val, v_val, a_val], color=['#38bdf8', '#00A651', '#f59e0b'])
        ax.axhline(y=4.5, color='orange', linestyle='--', label='حد التنبيه')
        ax.axhline(y=7.0, color='red', linestyle='--', label='الحد الحرج')
        ax.set_ylabel('Velocity RMS (mm/s)')
        ax.legend()
        st.pyplot(fig)

# ==========================================
# 2. تقييم صحة التوربينات الشامل
# ==========================================
elif app_mode == "⚙️ تقييم صحة التوربينات الشامل (Advanced Diagnostics)":
    st.subheader("⚙️ وحدة التشخيص المتكامل للتوربينات الغازية والبخارية")
    
    col_a, col_b = st.columns(2)
    with col_a:
        load_mw = st.number_input("الحمل (MW)", value=120.0)
        egt = st.number_input("حرارة العادم EGT (°C)", value=535.0)
        vib = st.number_input("اهتزاز المحامل RMS (mm/s)", value=3.8)
    with col_b:
        lube_t = st.number_input("حرارة زيت التزييت (°C)", value=62.0)
        debris = st.number_input("الشوائب المعدنية في الزيت (PPM)", value=15.0)

    if st.button("🔍 تنفيذ التشخيص الشامل للصحة (Asset Health Index)"):
        score, status, color, alerts = evaluate_turbine_advanced(load_mw, egt, vib, lube_t, debris)
        st.metric(label="مؤشر صحة الأصول (Asset Health Index)", value=f"{score} / 100")
        st.markdown(f"### حالة النظام: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
        
        if alerts:
            st.error("⚠️ التنبيهات النشطة المحررة من الحساسات:\n" + "\n".join([f"- {a}" for a in alerts]))
        else:
            st.success("✅ جميع المؤشرات الفيزيائية والحرارية ضمن النطاق الطبيعي المستقر.")

# ==========================================
# 3. الكفاءة الحرارية
# ==========================================
elif app_mode == "🔥 كفاءة التوربينات الحرارية (Thermal Efficiency)":
    st.subheader("🔥 حساب الكفاءة الحرارية واستهلاك الوقود")
    c1, c2, c3 = st.columns(3)
    with c1: p_mw = st.number_input("القدرة (MW)", value=130.0)
    with c2: f_flow = st.number_input("تدفق الوقود (kg/s)", value=7.8)
    with c3: lhv = st.number_input("LHV (kJ/kg)", value=50000.0)

    if st.button("⚙️ احسب الكفاءة الحرارية"):
        eff = calculate_thermal_efficiency(p_mw, f_flow, lhv)
        st.metric("الكفاءة الحرارية الفعلية", f"{eff}%")
        st.info("💡 ملاحظة: الكفاءة النموذجية للتوربينات الغازية الصناعية تتراوح بين 35% إلى 42%.")

# ==========================================
# 4. أجهزة الاستشعار وأنظمة التحكم
# ==========================================
elif app_mode == "🛠️ أجهزة الاستشعار وأنظمة التحكم (Sensors & Control)":
    st.subheader("🛠️ منظومة الحساسات وأجهزة الفحص والتحكم الصناعي")
    
    st.markdown("""
    تعتمد دقة المنظومة على دقة وسائط الإدخال والتحكم الميداني المعتمدة في **ATS Engineering**:
    
    ### 1. أنواع المستشعرات وأجهزة الفحص (Sensors & Diagnostic Hardware):
    * **مستشعرات الاهتزاز (Accelerometers & Velocity Probes):** لقياس الاهتزازات عند قواعد المحامل (مثل مكسرات الانبعاث ومجسات بيركنز وكوماتسو).
    * **مجسات الإزاحة (Eddy Current Proximity Probes):** لقياس الخلوصات المحورية والانحراف (Radial & Axial Shaft Displacement).
    * **مزدوجات الحرارة وبيرومترات العادم (Thermocouples Type K/S & Pyrometers):** لمراقبة حرارة العادم (EGT) واحتراق الغرف.
    * **أجهزة الفحص اللاهدمي (NDT Tools):** الموجات فوق الصوتية (UT) لفحص الشقوق، والفحص المغناطيسي (MPI) لريش التوربينات.

    ### 2. أنواع أنظمة التحكم (Control Systems Architecture):
    * **أنظمة التحكم المنطقي القابل للبرمجة (PLCs):** إدارة عمليات بدء التشغيل، الإيقاف الآمن، ومراقبة الـ Interlocks (مثل Allen-Bradley أو Siemens S7).
    * **وحدات التحكم الإلكترونية في السرعة (Electronic Governors / PID Loops):** تنظيم سرعة التوربينة والتردد (مثل Woodward UG / DSE 8610 MKII).
    * **أنظمة الـ SCADA وغرف التحكم المركزية:** لجمع البيانات اللحظية (Telemetry) والعرض المرئي عبر واجهات التشغيل HMI.
    """)

# ==========================================
# 5. الصيانة التنبؤية والسجلات
# ==========================================
elif app_mode == "🔮 الصيانة التنبؤية والسجلات التاريخية (PdM & RUL)":
    st.subheader("🔮 الصيانة التنبؤية (Predictive Maintenance) وتحليل السجلات")
    st.markdown("قم برفع ملف `CSV` يحتوي على سجلات `Velocity_RMS` لتقدير العمر المتبقي للمحامل (RUL):")
    
    up_file = st.file_uploader("اختر ملف سجلات الاهتزاز CSV", type=["csv"])
    if up_file is not None:
        df = pd.read_csv(up_file)
        st.dataframe(df.head())
        if 'Velocity_RMS' in df.columns:
            max_v = df['Velocity_RMS'].max()
            rul_hours = calculate_rul(max_v)
            st.warning(f"⚠️ العمر التشغيلي المتبقي المقدر للمحامل (RUL): **{rul_hours} ساعة تشغيلية**.")
            
            st.line_chart(df['Velocity_RMS'])
        else:
            st.error("يجب أن يحتوي الملف على عمود `Velocity_RMS`.")

# ==========================================
# 6. خارطة طريق التنفيذ الميداني
# ==========================================
elif app_mode == "📋 خارطة طريق التنفيذ الميداني (Implementation Guide)":
    st.subheader("📋 الدليل الهندسي لتنفيذ وتشغيل منظومة المراقبة والصيانة التنبؤية")
    
    st.markdown("""
    تنفذ استراتيجية **Addoma Trading Services (ATS)** لنشر أنظمة المراقبة والصيانة التنبؤية عبر المراحل الأربع التالية:
    
    1. **مرحلة التدقيق الهندسي وتحديد النقاط الحرجة (Audit & Assessment):**
       * دراسة الخرائط الميكانيكية للتوربينات والمولدات.
       * تحديد نقاط قياس الاهتزاز والحرارة الحرجة (Critical Bearings & EGT Zones).
    
    2. **مرحلة التركيب الميداني وربط الحساسات (Hardware Deployment):**
       * تثبيت مسامير التثبيت ومجسات التسارع والحرارة بدقة ميكانيكية عالية.
       * ربط المستشعرات بوحدات الـ Edge Gateways لجمع الإشارات الرقمية.
    
    3. **مرحلة المعالجة السحابية وربط منصة ATS DocIntel GenAI (Cloud & AI Integration):**
       * تدفق البيانات عبر بروتوكولات الصناعة (MQTT / Modbus) إلى منصة الاستضافة على Streamlit.
       * معالجة الإشارات عبر أكواد Python وتحليل اتجاهات التدهور (Trends).
    
    4. **مرحلة تفعيل الصيانة التنبؤية واتخاذ القرار (Actionable Insights):**
       * إطلاق التنبيهات التلقائية عند تجاوز الحدود الحرجة.
       * توليد تقارير الصيانة المعتمدة الجاهزة للتسليم للعملاء والجهات الهندسية.
    """)

# ==========================================
# 7. المساعد الذكي GenAI
# ==========================================
else:
    st.subheader("🤖 محادثة المساعد الذكي (ATS DocIntel GenAI Copilot)")
    prompt = st.text_input("اطرح سؤالك الهندسي:", "ما هي أفضل ممارسات الصيانة التنبؤية للتوربينات الغازية؟")
    if st.button("إرسال الاستفسار"):
        st.success("**رد منظومة ATS DocIntel الذكية:**")
        st.markdown("""
        بناءً على المعايير الهندسية لـ **ATS Engineering**:
        تعتمد أفضل ممارسات الصيانة التنبؤية (PdM) على الدمج بين:
        1. **مراقبة الاهتزازات المستمرة (Online Vibration Monitoring)** لكشف مشاكل المحامل ومحاذاة الأعمدة مبكراً.
        2. **تحليل الزيوت والتشحيم (Tribology & Oil Analysis)** لرصد الشواهد المعدنية وتآكل التروس.
        3. **الفحص الحراري (Thermography & EGT Monitoring)** لكفاءة غرف الاحتراق وريش التوربينة.
        *الهدف:* الانتقال الكامل من استراتيجية "الإصلاح بعد العطل" إلى "الصيانة الاستباقية المונة بالتكلفة والموثوقية العالية".
        """)
