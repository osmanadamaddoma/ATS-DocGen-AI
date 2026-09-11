from datetime import datetime, timedelta
import io
import pandas as pd
import streamlit as st
from fpdf import FPDF

st.set_page_config(
    page_title="Industrial Generator & Lifespan Maintenance Tracker",
    layout="wide"
)

st.title("⚙️ نظام الصيانة التنبؤية وإدارة قطع الغيار والتشغيل الصناعي")

# قاعدة بيانات العملاء وأكواد التفعيل الفردية
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم (Addoma Trading Services)",
        "plan": "سنوي (Yearly)",
        "start_date": "2026-01-01",
        "duration_days": 365,
    },
    "CLIENT-M-881": {
        "name": "شركة النيل للصناعات الهندسية",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-01",
        "duration_days": 30,
    },
}

# الشريط الجانبي: بوابة تفعيل العميل والصلاحيات
st.sidebar.header("🔐 بوابة تفعيل العميل والصلاحيات")
input_code = st.sidebar.text_input("أدخل كود التفعيل الخاص بالعميل:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    
    if datetime.now().date() <= expiry_dt:
        is_pro = True
        st.sidebar.success(f"✅ مفعل: {client_name} ({plan_type})")
    else:
        st.sidebar.error("❌ انتهت صلاحية اشتراك هذا العميل.")
elif input_code != "":
    st.sidebar.error("❌ كود التفعيل غير صحيح.")
else:
    st.sidebar.info("💡 أدخل كود العميل لفتح التحليلات المتقدمة.")

st.sidebar.divider()

# إدخال البيانات التشغيلية والمناخية وساعات المولد العامة
st.sidebar.header("📥 لوحة إدخال البيانات والتشغيل العامة")

with st.sidebar.form("generator_comprehensive_form"):
    st.subheader("ساعات التشغيل وسعات المولد")
    run_hours = st.number_input("ساعات التشغيل العامة للمولد (Total Run Hours)", min_value=0.0, max_value=50000.0, value=1250.0, step=10.0)
    gen_kw = st.number_input("سعة المولد الكلية (Generator kW)", min_value=5.0, max_value=3000.0, value=250.0, step=10.0)
    load_kw = st.number_input("حجم الحمولة الحالية (Load kW)", min_value=0.0, max_value=3000.0, value=150.0, step=10.0)
    ambient_temp = st.number_input("درجة الحرارة المحيطة / المناخ (°C)", min_value=10.0, max_value=60.0, value=43.0, step=1.0)

    st.subheader("قراءات الشاشة والمؤشرات الميكانيكية")
    coolant_temp = st.number_input("حرارة سائل التبريد (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    vibration = st.number_input("مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2, disabled=not is_pro)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    amperes = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=4000.0, value=350.0)
    pf = st.number_input("معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85, disabled=not is_pro)

    submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

# حساب نسبة الحمل المئوية
load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

# الواجهة الرئيسية
st.info(f"🔹 **العميل الحالي:** {client_name} | **الباقة:** {plan_type}")
st.subheader("📊 لوحة المراقبة التشغيلية والبيانات الكهربائية")

col1, col2, col3, col4 = st.columns(4)
col1.metric("إجمالي التشغيل", f"{run_hours} hrs")
col2.metric("سعة المولد", f"{gen_kw} kW")
col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
col4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

col5, col6, col7, col8 = st.columns(4)
col5.metric("حرارة المحرك", f"{coolant_temp} °C")
col6.metric("ضغط الزيت", f"{oil_press} Bar")
col7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
col8.metric("التيار / معامل القدرة", f"{amperes}A | {pf}" if is_pro else f"{amperes}A | 🔒")

st.divider()

# التقييم المناخي وتوصيات الزيوت والأحمال
st.subheader("🌡️ التقييم المناخي وتوصيات الزيوت والأحمال القصوى")

recommended_oil = "15W40 (الوضع القياسي)"
max_allowed_load = 80.0
climate_alerts = []

if ambient_temp >= 45.0:
    recommended_oil = "20W50 (موصى به لدرجات الحرارة القصوى 45°C فأكثر)"
    max_allowed_load = 60.0
    if load_percentage > 60.0:
        climate_alerts.append(f"🚨 **تحذير مناخي فائق (≥ 45°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **60%**.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى (60%) في الأجواء الحارة جداً.")
        
elif ambient_temp >= 43.0:
    recommended_oil = "15W40 (مع مراعاة اللزوجة في المناخ الحار)"
    max_allowed_load = 70.0
    if load_percentage > 70.0:
        climate_alerts.append(f"⚠️ **تحذير مناخي (≥ 43°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **70%**.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى المسموح (70%) عند درجة حرارة 43°C.")
else:
    climate_alerts.append(f"✅ **الظروف المناخية معتدلة (< 43°C):** تشغيل ضمن الحدود القياسية.")

st.markdown(f"🛢️ **نوع لزوجة زيت المحرك الواجب استخدامه:** **{recommended_oil}**")
st.markdown(f"📉 **الحد الأقصى الموصى به للحمولة في هذا المناخ:** **{max_allowed_load}%**")

for alert in climate_alerts:
    if "🚨" in alert or "⚠️" in alert:
        st.warning(alert)
    else:
        st.success(alert)

st.divider()

# تهيئة بيانات الجدول في الذاكرة المؤقتة (Session State)
if "maintenance_df" not in st.session_state:
    initial_data = [
        {"تصنيف القطعة": "الصيانة الدورية (Service)", "اسم قطعة الغيار (Spare Part)": "فلتر زيت (Oil Filter)", "العمر الافتراضي (Hours)": 250.0, "الساعات المنقضية (Hours Used)": 210.0},
        {"تصنيف القطعة": "الصيانة الدورية (Service)", "اسم قطعة الغيار (Spare Part)": "فلتر وقود - أولي (Primary Fuel Filter)", "العمر الافتراضي (Hours)": 500.0, "الساعات المنقضية (Hours Used)": 430.0},
        {"تصنيف القطعة": "الصيانة الدورية (Service)", "اسم قطعة الغيار (Spare Part)": "فلتر وقود - ثانوي (Secondary Fuel Filter)", "العمر الافتراضي (Hours)": 500.0, "الساعات المنقضية (Hours Used)": 455.0},
        {"تصنيف القطعة": "نظام الهواء (Air System)", "اسم قطعة الغيار (Spare Part)": "فلتر هواء (Air Filter)", "العمر الافتراضي (Hours)": 1000.0, "الساعات المنقضية (Hours Used)": 860.0},
        {"تصنيف القطعة": "نظام التبريد (Cooling System)", "اسم قطعة الغيار (Spare Part)": "قشاط المروحة (Fan Belt)", "العمر الافتراضي (Hours)": 2000.0, "الساعات المنقضية (Hours Used)": 1550.0},
        {"تصنيف القطعة": "نظام التبريد (Cooling System)", "اسم قطعة الغيار (Spare Part)": "سائل تبريد (Coolant ELC)", "العمر الافتراضي (Hours)": 3000.0, "الساعات المنقضية (Hours Used)": 2200.0},
        {"تصنيف القطعة": "نظام الوقود (Fuel System)", "اسم قطعة الغيار (Spare Part)": "بخاخات الوقود (Injectors Check)", "العمر الافتراضي (Hours)": 5000.0, "الساعات المنقضية (Hours Used)": 4400.0},
        {"تصنيف القطعة": "النظام الكهربائي (Electrical)", "اسم قطعة الغيار (Spare Part)": "بطاريات (Batteries)", "العمر الافتراضي (Hours)": 8000.0, "الساعات المنقضية (Hours Used)": 6100.0},
        {"تصنيف القطعة": "النظام الكهربائي (Electrical)", "اسم قطعة الغيار (Spare Part)": "دينامو الشحن (Charging Alternator)", "العمر الافتراضي (Hours)": 10000.0, "الساعات المنقضية (Hours Used)": 8900.0},
        {"تصنيف القطعة": "المحرك - ميكانيك (Motor)", "اسم قطعة الغيار (Spare Part)": "طقم عمرة رأس (Top Overhaul)", "العمر الافتراضي (Hours)": 10000.0, "الساعات المنقضية (Hours Used)": 9100.0},
        {"تصنيف القطعة": "المحرك - ميكانيك (Motor)", "اسم قطعة الغيار (Spare Part)": "عمرة كاملة (Major Overhaul)", "العمر الافتراضي (Hours)": 20000.0, "الساعات المنقضية (Hours Used)": 15000.0},
        {"تصنيف القطعة": "نظام التبريد (Cooling System)", "اسم قطعة الغيار (Spare Part)": "مبرد الزيت (Oil Cooler Clean)", "العمر الافتراضي (Hours)": 5000.0, "الساعات المنقضية (Hours Used)": 3800.0},
        {"تصنيف القطعة": "نظام التبريد (Cooling System)", "اسم قطعة الغيار (Spare Part)": "مضخة الماء (Water Pump)", "العمر الافتراضي (Hours)": 6000.0, "الساعات المنقضية (Hours Used)": 5200.0},
        {"تصنيف القطعة": "نظام الهواء (Air System)", "اسم قطعة الغيار (Spare Part)": "تيربو (Turbocharger Check)", "العمر الافتراضي (Hours)": 8000.0, "الساعات المنقضية (Hours Used)": 7100.0}
    ]
    st.session_state.maintenance_df = pd.DataFrame(initial_data)

st.subheader("🔧 جدول تتبع العمر الافتراضي لقطع الغيار والصيانة (الإدخال والتعديل اليدوي المباشر)")
st.info("💡 **ملاحظة هامة:** عند تعديل أو كتابة أي رقم في خانة (الساعات المنقضية) أو (العمر الافتراضي) داخل الجدول أدناه، يرجى **الضغط على زر Enter** أو **النقر في أي مكان خارج الخلية** ليتم تحديث الحسابات فوراً.")

edited_table = st.data_editor(
    st.session_state.maintenance_df,
    num_rows="dynamic",
    use_container_width=True,
    key="maintenance_manual_editor"
)

st.session_state.maintenance_df = edited_table

processed_rows = []
for index, row in edited_table.iterrows():
    category = str(row.get("تصنيف القطعة", "أخرى"))
    part_name = str(row.get("اسم قطعة الغيار (Spare Part)", "قطعة جديدة"))
    
    lifespan = pd.to_numeric(row.get("العمر الافتراضي (Hours)", 250), errors='coerce')
    used_hours = pd.to_numeric(row.get("الساعات المنقضية (Hours Used)", 0), errors='coerce')
    
    if pd.isna(lifespan) or lifespan <= 0:
        lifespan = 250.0
    if pd.isna(used_hours):
        used_hours = 0.0

    usage_pct = (used_hours / lifespan) * 100
    remaining_hours = lifespan - used_hours
    
    if usage_pct >= 90:
        status = "تغيير فوري (خطر) 🔴"
    elif usage_pct >= 80:
        status = "قرب الخدمة 🟡"
    elif usage_pct >= 70:
        status = "تنبيه (استعداد) 🟠"
    else:
        status = "حالة جيدة 🟢"
        
    processed_rows.append({
        "تصنيف القطعة": category,
        "اسم قطعة الغيار (Spare Part)": part_name,
        "العمر الافتراضي (Hours)": lifespan,
        "الساعات المنقضية (Hours Used)": round(used_hours, 1),
        "نسبة الاستهلاك (%)": f"{usage_pct:.1f}%",
        "العمر المتبقي (Remaining)": round(remaining_hours, 1),
        "حالة التنبيه (Alert Status)": status
    })

st.subheader("📋 تقرير الحالة الفنية والنسب المحسوبة فوراً")
df_result = pd.DataFrame(processed_rows)
st.dataframe(df_result, use_container_width=True)

# التحليلات التنبؤية المتقدمة
advanced_alerts = []
if is_pro:
    st.divider()
    st.subheader("🔍 تحليلات التنبؤ بالأعطال المتقدمة (AI Diagnostics)")
    
    if vibration > 4.0:
        advanced_alerts.append("⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن المحور أو تآكل كراسي المحرك.")
    if pf < 0.8:
        advanced_alerts.append("💡 **معامل قدرة منخفض (< 0.8):** يوصى بمراجعة لوحة مكثفات تحسين القدرة (PFC).")
    if coolant_temp >= 95:
        advanced_alerts.append("🚨 **خطر ارتفاع الحرارة:** حرارة سائل التبريد تتجاوز الحد الطبيعي.")
        
    if advanced_alerts:
        for alert in advanced_alerts:
            st.error(alert)
    else:
        st.success("🌟 كافة مؤشرات الاهتزاز ومعامل القدرة ضمن النطاق المثالي الآمن.")
else:
    st.info("ℹ️ للوصول إلى تحليلات الاهتزاز ومعامل القدرة المتقدمة، يرجى تفعيل كود العميل في الشريط الجانبي.")

# ---------------------------------------------------------
# 📥 قسم تصدير التقارير (Excel & PDF)
# ---------------------------------------------------------
st.divider()
st.subheader("📥 تصدير التقارير والبيانات (Excel & PDF Export)")

col_exp1, col_exp2 = st.columns(2)

# 1. إعداد وتنزيل ملف إكسل Excel
with col_exp1:
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        df_result.to_excel(writer, index=False, sheet_name='Lifespan_Report')
    excel_data = excel_buffer.getvalue()
    
    st.download_button(
        label="📊 تنزيل التقرير بصيغة إكسل (Excel .xlsx)",
        data=excel_data,
        file_name=f"Generator_Maintenance_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

# 2. إعداد وتنزيل ملف PDF آمن برمجياً
def generate_pdf_report(df, client_name, run_hours, gen_kw, load_kw, ambient_temp):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    
    # العنوان الرئيسي
    pdf.cell(0, 10, "Industrial Generator Maintenance Report", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 8, f"Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align='C')
    pdf.ln(5)
    
    # معالجة اسم العميل لتفادي ترميز الأحرف غير اللاتينية
    safe_client_name = client_name.encode('latin-1', 'ignore').decode('latin-1')
    if not safe_client_name.strip():
        safe_client_name = "Authorized Client / User"
        
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 8, "1. System & Operational Summary", ln=True)
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 6, f"Client Profile: {safe_client_name}", ln=True)
    pdf.cell(0, 6, f"Total Run Hours: {run_hours} hrs | Generator Capacity: {gen_kw} kW", ln=True)
    pdf.cell(0, 6, f"Current Active Load: {load_kw} kW ({((load_kw/gen_kw)*100 if gen_kw>0 else 0):.1f}%)", ln=True)
    pdf.cell(0, 6, f"Ambient Temperature: {ambient_temp} C", ln=True)
    pdf.ln(5)
    
    # جدول الصيانة
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 8, "2. Spare Parts & Maintenance Status", ln=True)
    pdf.set_font("Helvetica", 'B', 9)
    
    # عناوين أعمدة الجدول
    pdf.cell(55, 7, "Spare Part", border=1)
    pdf.cell(32, 7, "Lifespan (hrs)", border=1)
    pdf.cell(32, 7, "Used Hours", border=1)
    pdf.cell(32, 7, "Usage (%)", border=1)
    pdf.cell(35, 7, "Remaining (hrs)", border=1)
    pdf.ln()
    
    pdf.set_font("Helvetica", '', 8)
    for idx, row in df.iterrows():
        raw_part = str(row["اسم قطعة الغيار (Spare Part)"])
        # استخراج المسمى الإنجليزي من بين الأقواس لتأمين طباعة الـ PDF
        if "(" in raw_part and ")" in raw_part:
            part_eng = raw_part.split("(")[1].split(")")[0]
        else:
            part_eng = raw_part.encode('latin-1', 'ignore').decode('latin-1')
            if not part_eng.strip():
                part_eng = f"Component #{idx+1}"
                
        lifespan = str(row["العمر الافتراضي (Hours)"])
        used = str(row["الساعات المنقضية (Hours Used)"])
        usage = str(row["نسبة الاستهلاك (%)"])
        remaining = str(row["العمر المتبقي (Remaining)"])
        
        pdf.cell(55, 6, part_eng[:28], border=1)
        pdf.cell(32, 6, lifespan, border=1)
        pdf.cell(32, 6, used, border=1)
        pdf.cell(32, 6, usage, border=1)
        pdf.cell(35, 6, remaining, border=1)
        pdf.ln()
        
    return pdf.output()

with col_exp2:
    try:
        pdf_bytes = generate_pdf_report(
            df_result, client_name, run_hours, gen_kw, load_kw, ambient_temp
        )
        st.download_button(
            label="📄 تنزيل التقرير بصيغة PDF (Technical Report)",
            data=bytes(pdf_bytes),
            file_name=f"Generator_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    except Exception as e:
        st.error(f"تعذر إنشاء ملف PDF: {e}")
