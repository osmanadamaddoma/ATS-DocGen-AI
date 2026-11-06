import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime

# إعدادات الصفحة
st.set_page_config(page_title="ATS DocIntel GenAI - Gas & Steam Turbines Suite", layout="wide")

st.title("⚡ ATS DocIntel GenAI - Turbomachinery & Equipment Suite")
st.markdown("منظومة الذكاء الاصطناعي التوليدي المتكاملة لمراقبة وتشخيص التوربينات الغازية، البخارية والمعدات الدوارة - **ADDOMA TRADING SERVICES**")

# ==========================================
# وحدة الدوال الهندسية والتحليلية الشاملة
# ==========================================

def analyze_vibration(readings, warning_limit=4.5, critical_limit=7.0):
    """
    تحليل قراءات الاهتزاز (Velocity RMS) للاتجاهات (H, V, A)
    """
    max_vib = np.max(readings)
    if max_vib >= critical_limit:
        status = "Critical (حرج - يتطلب توقف فوري)"
        color = "red"
        recommendation = "خطر حرج: تجاوز حدود الاهتزاز الآمنة للمحامل. احتكاك محتمل أو عدم اتزان حاد. يلزم الإيقاف الفوري."
    elif max_vib >= warning_limit:
        status = "Warning (تنبيه - مراقبة مكثفة)"
        color = "orange"
        recommendation = "ارتفاع ملحوظ في الاهتزاز: يوصى بفحص محاذاة العمود (Misalignment) أو ارتخاء قواعد التثبيت."
    else:
        status = "Normal (طبيعي - كفاءة عالية)"
        color = "green"
        recommendation = "المعدة تعمل ضمن الحدود التشغيلية الآمنة واستقرار دائم."
        
    return max_vib, status, color, recommendation

def evaluate_turbine_health(turbine_id, exhaust_temp, vibration_rms, load_mw, max_temp_limit=550.0, max_vib_limit=4.0):
    """
    تقييم حالة التوربينات الغازية والبخارية بناءً على الحرارة، الاهتزاز، والحمل
    """
    status = "Optimal (تشغيل مثالي للتوربينة)"
    color = "green"
    recommendation = "التوربينة تعمل بكفاءة عالية وفي النطاق التشغيلي الآمن."

    if exhaust_temp > max_temp_limit or vibration_rms > max_vib_limit:
        if vibration_rms > (max_vib_limit * 1.5) or exhaust_temp > (max_temp_limit + 30):
            status = "Critical (حرج - خطر تلف الريش أو المحامل)"
            color = "red"
            recommendation = "تجاوز خطير في الحرارة أو الاهتزازات. قد يشير ذلك إلى تلف في ريش التوربينة (Blade Damage). يلزم الفحص بـ NDT."
        else:
            status = "Warning (تنبيه - مراقبة حرارية وميكانيكية)"
            color = "orange"
            recommendation = "ارتفاع ملحوظ في مؤشرات التشغيل. يوصى بفحص خلوصات المحامل ومراجعة بيانات الفحص اللاهدمي."

    report = {
        "equipment_id": turbine_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "load_mw": float(load_mw),
        "exhaust_temp_c": float(exhaust_temp),
        "vibration_rms_mm_s": float(vibration_rms),
        "status": status,
        "recommendation": recommendation
    }
    return report

def calculate_thermal_efficiency(power_output_mw, fuel_flow_kg_s, lhv_kj_kg=50000):
    """
    حساب الكفاءة الحرارية للتوربينة (Thermal Efficiency %)
    """
    power_kw = power_output_mw * 1000.0  # kJ/s
    total_heat_input = fuel_flow_kg_s * lhv_kj_kg  # kJ/s
    
    if total_heat_input <= 0:
        return 0.0
        
    efficiency = (power_kw / total_heat_input) * 100.0
    return round(efficiency, 2)

def calculate_rul(max_hist_vib):
    """
    حساب العمر التشغيلي المتبقي للمحامل (Remaining Useful Life - RUL)
    """
    estimated_hours_left = max(0, int(1000 - (max_hist_vib * 85)))
    return estimated_hours_left

# ==========================================
# لوحة التحكم والوحدات الجانبية (Sidebar)
# ==========================================
st.sidebar.header("إعدادات المنظومة الذكية")
asset_id = st.sidebar.text_input("معرف المعدة / التوربينة", "ATS-GAS-STEAM-TURBINE-01")
warning_limit = st.sidebar.slider("حد التنبيه للاهتزاز (Warning RMS mm/s)", 2.0, 6.0, 4.5)
critical_limit = st.sidebar.slider("الحد الحرج للاهتزاز (Critical RMS mm/s)", 5.0, 10.0, 7.0)

# اختيار وضع التشغيل
app_mode = st.sidebar.selectbox("اختر وحدة التشغيل والتحليل:", [
    "📊 التشخيص اليدوي للاهتزازات (Velocity RMS)", 
    "⚙️ تشخيص وتقييم التوربينات (Gas & Steam Turbines)",
    "🔥 تحليل الكفاءة الحرارية (Thermal Efficiency)",
    "📁 تحليل السجلات التاريخية والتنبؤ بالعمر (RUL & CSV)", 
    "🤖 المساعد الذكي لتشخيص الأعطال والصيانة (GenAI)"
])

# ==========================================
# 1. التشخيص اليدوي للاهتزازات
# ==========================================
if app_mode == "📊 التشخيص اليدوي للاهتزازات (Velocity RMS)":
    st.subheader("📊 لوحة إدخال قراءات الاهتزاز عند قواعد المحامل (H, V, A)")
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

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(directions, readings, color=['#38bdf8', '#00A651', '#f59e0b'])
        ax.axhline(y=warning_limit, color='orange', linestyle='--', label='حد التنبيه')
        ax.axhline(y=critical_limit, color='red', linestyle='--', label='الحد الحرج')
        ax.set_ylabel('Velocity RMS (mm/s)')
        ax.set_title(f'تحليل الاهتزازات - {asset_id}')
        ax.legend()
        st.pyplot(fig)

        report_data = {
            "equipment_id": asset_id,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "readings": {"H": h_val, "V": v_val, "A": a_val},
            "max_velocity_rms": float(max_vib),
            "status": status,
            "recommendation": recommendation
        }
        st.subheader("🔗 مخرج النظام المتوافق مع الذكاء الاصطناعي (JSON)")
        st.code(json.dumps(report_data, ensure_ascii=False, indent=4), language='json')

# ==========================================
# 2. تشخيص وتقييم التوربينات (Gas & Steam Turbines)
# ==========================================
elif app_mode == "⚙️ تشخيص وتقييم التوربينات (Gas & Steam Turbines)":
    st.subheader("⚙️ وحدة مراقبة وتقييم التوربينات الغازية والبخارية")
    st.markdown("متابعة درجات حرارة العادم (EGT)، الاهتزاز الميكانيكي، وحالة الأجزاء الدوارة والريش:")

    col_g1, col_g2, col_g3 = st.columns(3)
    with col_g1:
        load_val = st.number_input("الحمل الحالي (MW)", value=115.0, step=0.5)
    with col_g2:
        temp_val = st.number_input("درجة حرارة العادم EGT (°C)", value=530.0, step=1.0)
    with col_g3:
        vib_val = st.number_input("قراءة الاهتزاز الكلية RMS (mm/s)", value=3.5, step=0.1)

    if st.button("🔍 تقييم حالة التوربينة الشاملة"):
        turbine_report = evaluate_turbine_health(asset_id, temp_val, vib_val, load_val)
        
        t_color = "green"
        if "Critical" in turbine_report["status"]:
            t_color = "red"
        elif "Warning" in turbine_report["status"]:
            t_color = "orange"

        st.markdown(f"### الحالة التشغيلية: <span style='color:{t_color};'>{turbine_report['status']}</span>", unsafe_allow_html=True)
        st.info(f"**التوصية الهندسية للتوربينة:** {turbine_report['recommendation']}")

        st.subheader("🔗 تقرير التوربينة الموجه لـ ATS DocIntel")
        st.code(json.dumps(turbine_report, ensure_ascii=False, indent=4), language='json')

# ==========================================
# 3. تحليل الكفاءة الحرارية (Thermal Efficiency)
# ==========================================
elif app_mode == "🔥 تحليل الكفاءة الحرارية (Thermal Efficiency)":
    st.subheader("🔥 وحدة حساب ومراقبة الكفاءة الحرارية للتوربينات")
    st.markdown("حساب نسبة الكفاءة الحرارية الفعلية استناداً إلى الطاقة المنتجة ومعدل استهلاك الوقود:")

    col_t1, col_t2, col_t3 = st.columns(3)
    with col_t1:
        power_mw = st.number_input("الطاقة الكهربائية المنتجة (MW)", value=125.0, step=0.5)
    with col_t2:
        fuel_flow = st.number_input("معدل تدفق الوقود (kg/s)", value=7.5, step=0.1)
    with col_t3:
        lhv_val = st.number_input("القيمة الحرارية للوقود LHV (kJ/kg)", value=50000.0, step=100.0)

    if st.button("⚙️ احسب الكفاءة الحرارية"):
        efficiency = calculate_thermal_efficiency(power_mw, fuel_flow, lhv_val)
        
        perf_status = "ممتازة (Optimal Performance)"
        perf_color = "green"
        if efficiency < 30.0:
            perf_status = "منخفضة (تتطلب فحص غرف الاحتراق أو تلوث الريش)"
            perf_color = "red"
        elif efficiency < 35.0:
            perf_status = "دون المعدل (مقبولة مع وجود هدر طاقي)"
            perf_color = "orange"

        st.metric(label="الكفاءة الحرارية المحسوبة (Thermal Efficiency)", value=f"{efficiency}%")
        st.markdown(f"### تقييم الكفاءة: <span style='color:{perf_color};'>{perf_status}</span>", unsafe_allow_html=True)
        
        if efficiency < 35.0:
            st.warning("⚠️ ملاحظة هندسية: انخفاض الكفاءة الحرارية قد ينتج عن انسداد مرشحات الهواء أو تراكم الرواسب على ريش الضاغط (Compressor Fouling).")
        else:
            st.success("✅ الأداء الحراري للتوربينة مستقر وضمن الحدود التصميمية الممتازة.")

# ==========================================
# 4. السجلات التاريخية والعمر المتبقي (RUL & CSV)
# ==========================================
elif app_mode == "📁 تحليل السجلات التاريخية والتنبؤ بالعمر (RUL & CSV)":
    st.subheader("📁 رفع سجلات الاهتزاز التاريخية ونمذجة العمر المتبقي (RUL)")
    st.markdown("قم برفع ملف `CSV` يحتوي على أعمدة: `Timestamp`, `Velocity_RMS` لمتابعة تدهور الأداء.")
    
    uploaded_file = st.file_uploader("اختر ملف CSV السجلي", type=["csv"])
    
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.write("عينة من البيانات المرفوعة:")
        st.dataframe(df.head())
        
        if 'Velocity_RMS' in df.columns:
            max_hist_vib = df['Velocity_RMS'].max()
            avg_hist_vib = df['Velocity_RMS'].mean()
            
            col_a, col_b = st.columns(2)
            col_a.metric(label="أقصى قيمة اهتزاز تاريخية", value=f"{max_hist_vib:.2f} mm/s")
            col_b.metric(label="متوسط الاهتزاز التشغيلي", value=f"{avg_hist_vib:.2f} mm/s")
            
            estimated_hours_left = calculate_rul(max_hist_vib)
            st.warning(f"⚠️ تقدير الذكاء الاصطناعي للعمر التشغيلي المتبقي للمحامل (RUL): **{estimated_hours_left} ساعة تشغيلية** قبل الصيانة الوقائية الإجبارية.")

            st.subheader("📈 منحنى تتبع تدهور الأداء عبر الزمن")
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(df.index, df['Velocity_RMS'], marker='o', color='#00A651', linewidth=2, label='Actual Velocity RMS')
            ax.axhline(y=warning_limit, color='orange', linestyle='--', label='حد التنبيه')
            ax.axhline(y=critical_limit, color='red', linestyle='--', label='الحد الحرج')
            ax.set_ylabel('Velocity RMS (mm/s)')
            ax.set_title(f'تحليل السجل التاريخي وتوقع العمر المتبقي - {asset_id}')
            ax.legend()
            st.pyplot(fig)
        else:
            st.error("تأكد من أن ملف الـ CSV يحتوي على عمود باسم `Velocity_RMS`.")

# ==========================================
# 5. المساعد الذكي GenAI Copilot
# ==========================================
else:
    st.subheader("🤖 محادثة المساعد الذكي (ATS DocIntel GenAI Copilot)")
    st.markdown("اسأل الذكاء الاصطناعي عن أي استفسار فني يخص صيانة التوربينات، أعطال المحامل، الفحص اللاهدمي (NDT)، أو كفاءة الطاقة:")
    
    user_prompt = st.text_input("اكتب استفسارك الهندسي هنا:", "ما هي أسباب ارتفاع اهتزازات المحامل في التوربينات الغازية؟")
    
    if st.button("إرسال الاستفسار للمساعد الذكي"):
        st.success("**رد ATS DocIntel GenAI:**")
        st.markdown("""
        بناءً على قاعدة المعارف الهندسية المدمجة لـ **Addoma Trading Services (ATS Engineering)**:
        إن ارتفاع الاهتزازات في التوربينات الغازية والبخارية يرجع غالباً إلى الأسباب الرئيسية التالية:
        1. **عدم الاتزان الكتلي أو الحراري (Mass or Thermal Unbalance)** في الدوار نتيجة تراكم الرواسب أو التشوه الحراري للريش.
        2. **عدم الاستقامة الحادة (Misalignment)** بين أجزاء التوربينة وصندوق التروس أو المولد.
        3. **تآكل أو تلف في محامل الدفع أو الارتكاز (Journal & Thrust Bearings Failure)**.
        4. **ظواهر الرنين الميكانيكي (Mechanical Resonance)** أو خلوصات غير مطابقة للمواصفات.
        *التوصية الهندسية:* يُنصح بمراجعة منحنيات الاهتزاز (FFT)، التحقق من درجات حرارة المحامل، وجدولة فحص لاهدمي (NDT) عند الحاجة.
        """)
