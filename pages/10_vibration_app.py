import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime

# إعدادات الصفحة
st.set_page_config(page_title="ATS DocIntel GenAI - Industrial Suite", layout="wide")

st.title("⚡ ATS DocIntel GenAI - Industrial Suite")
st.markdown("منظومة الذكاء الاصطناعي التوليدي لمراقبة وتشخيص المعدات الدوارة - **ADDOMA TRADING SERVICES**")

# دالة تحليل الاهتزازات
def analyze_vibration(readings, warning_limit=4.5, critical_limit=7.0):
    max_vib = np.max(readings)
    if max_vib >= critical_limit:
        status = "Critical (حرج - يتطلب توقف فوري)"
        color = "red"
        recommendation = "خطر حرج: تجاوز حدود الاهتزاز الآمنة. احتكاك محتمل أو تلف في المحامل. يلزم إيقاف المعدة فوراً."
    elif max_vib >= warning_limit:
        status = "Warning (تنبيه - مراقبة مكثفة)"
        color = "orange"
        recommendation = "ارتفاع ملحوظ في الاهتزاز: يوصى بفحص محاذاة العمود (Misalignment) أو ارتخاء قواعد التثبيت."
    else:
        status = "Normal (طبيعي - كفاءة عالية)"
        color = "green"
        recommendation = "المعدة تعمل ضمن الحدود التشغيلية الآمنة واستقرار دائم."
        
    return max_vib, status, color, recommendation

# دالة حساب العمر المتبقي RUL
def calculate_rul(max_hist_vib):
    estimated_hours_left = max(0, int(1000 - (max_hist_vib * 85)))
    return estimated_hours_left

# لوحة إعدادات التحكم الجانبية
st.sidebar.header("إعدادات المنظومة الذكية")
gen_id = st.sidebar.text_input("معرف المعدة / المولد", "ATS-GEN-350KVA-01")
warning_limit = st.sidebar.slider("حد التنبيه (Warning RMS mm/s)", 2.0, 6.0, 4.5)
critical_limit = st.sidebar.slider("الحد الحرج (Critical RMS mm/s)", 5.0, 10.0, 7.0)

# اختيار وضع التشغيل
app_mode = st.sidebar.selectbox("اختر وحدة التشغيل:", [
    "📊 التشخيص اليدوي الفوري", 
    "📁 تحليل السجلات التاريخية والتنبؤ بالعمر (RUL)", 
    "🤖 المساعد الذكي لتقارير الصيانة (GenAI Chat)"
])

if app_mode == "📊 التشخيص اليدوي الفوري":
    st.subheader("📊 لوحة إدخال قراءات السرعة الاهتزازية (Velocity RMS)")
    col1, col2, col3 = st.columns(3)

    with col1:
        h_val = st.number_input("الاتجاه الأفقي (Horizontal - H)", value=3.2, step=0.1)
    with col2:
        v_val = st.number_input("الاتجاه العمودي (Vertical - V)", value=2.8, step=0.1)
    with col3:
        a_val = st.number_input("الاتجاه المحوري (Axial - A)", value=5.1, step=0.1)

    readings = [h_val, v_val, a_val]
    directions = ['Horizontal (H)', 'Vertical (V)', 'Axial (A)']

    if st.button("🚀 تشخيص وتحليل الحالة الهندسية"):
        max_vib, status, color, recommendation = analyze_vibration(readings, warning_limit, critical_limit)

        st.markdown(f"### حالة التشخيص: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
        st.info(f"**التوصية الهندسية الصادرة عن ATS DocIntel:** {recommendation}")

        # رسم المخطط
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(directions, readings, color=['#38bdf8', '#00A651', '#f59e0b'])
        ax.axhline(y=warning_limit, color='orange', linestyle='--', label='حد التنبيه')
        ax.axhline(y=critical_limit, color='red', linestyle='--', label='الحد الحرج')
        ax.set_ylabel('Velocity RMS (mm/s)')
        ax.set_title(f'تحليل الاهتزازات الفوري - {gen_id}')
        ax.legend()
        st.pyplot(fig)

        report_data = {
            "generator_id": gen_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "readings": {"H": h_val, "V": v_val, "A": a_val},
            "max_velocity_rms": float(max_vib),
            "status": status,
            "recommendation": recommendation
        }
        
        st.subheader("🔗 مخرج النظام المتوافق مع الذكاء الاصطناعي (JSON)")
        st.code(json.dumps(report_data, ensure_ascii=False, indent=4), language='json')

elif app_mode == "📁 تحليل السجلات التاريخية والتنبؤ بالعمر (RUL)":
    st.subheader("📁 رفع سجلات الاهتزاز التاريخية ونمذجة التنبؤ")
    st.markdown("قم برفع ملف `CSV` يحتوي على أعمدة: `Timestamp`, `Velocity_RMS` لمتابعة تدهور الحالة.")
    
    uploaded_file = st.file_uploader("اختر ملف CSV السجلي", type=["csv"])
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write("عينة من البيانات السجلية:")
        st.dataframe(df.head())
        
        if 'Velocity_RMS' in df.columns:
            max_hist_vib = df['Velocity_RMS'].max()
            avg_hist_vib = df['Velocity_RMS'].mean()
            
            col_a, col_b = st.columns(2)
            col_a.metric(label="أقصى قيمة اهتزاز تاريخية", value=f"{max_hist_vib:.2f} mm/s")
            col_b.metric(label="متوسط الاهتزاز التشغيلي", value=f"{avg_hist_vib:.2f} mm/s")
            
            estimated_hours_left = calculate_rul(max_hist_vib)
            st.warning(f"⚠️ تقدير الذكاء الاصطناعي للعمر التشغيلي المتبقي للمحامل تقريباً: **{estimated_hours_left} ساعة تشغيلية** قبل الصيانة الوقائية الإجبارية.")

            st.subheader("📈 منحنى تتبع تدهور الأداء عبر الزمن")
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df.index, df['Velocity_RMS'], marker='o', color='#00A651', linewidth=2, label='Actual Velocity RMS')
            ax.axhline(y=warning_limit, color='orange', linestyle='--', label='حد التنبيه')
            ax.axhline(y=critical_limit, color='red', linestyle='--', label='الحد الحرج')
            ax.set_ylabel('Velocity RMS (mm/s)')
            ax.set_title(f'تحليل السجل التاريخي والتنبؤ - {gen_id}')
            ax.legend()
            st.pyplot(fig)
        else:
            st.error("تأكد من أن ملف الـ CSV يحتوي على عمود باسم `Velocity_RMS`.")

else:
    st.subheader("🤖 محادثة المساعد الذكي (ATS DocIntel GenAI Copilot)")
    st.markdown("اسأل الذكاء الاصطناعي عن أي استفسار فني يخص أعطال المولدات، الاهتزازات، أو استراتيجيات الصيانة التنبؤية:")
    
    user_prompt = st.text_input("اكتب استفسارك الهندسي هنا:", "ما هي أسباب ارتفاع الاهتزاز المحوري في مولدات بيركنز؟")
    
    if st.button("إرسال الاستفسار للمساعد الذكي"):
        st.success("**رد ATS DocIntel GenAI:**")
        st.markdown("""
        بناءً على قاعدة المعارف الهندسية المدمجة لـ **Addoma Trading Services**:
        إن ارتفاع الاهتزاز في الاتجاه المحوري (Axial Vibration) للمعدات الدوارة والمولدات يرجع غالباً إلى الأسباب التالية:
        1. **عدم الاستقامة الحادة (Angular / Parallel Misalignment)** بين محرك الديزل والمولد الكهربائي (Alternator).
        2. **مشاكل أو تآكل في محامل الدفع (Thrust Bearings Failure)**.
        3. **تفاوت أو التواء في أعمدة الإدارة (Shaft Deflection)** نتيجة الأَحمال غير المتزنة.
        *التوصية:* يُنصح بمراجعة محاذاة الوصلة (Coupling Alignment) فوراً باستخدام أدوات القياس الليزرية.
        """)
