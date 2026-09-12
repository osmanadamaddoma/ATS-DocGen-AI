from datetime import datetime, timedelta
import io
import os
import pandas as pd
import streamlit as st
from fpdf import FPDF
from PIL import Image

st.set_page_config(
    page_title="Industrial Generator Maintenance & Comprehensive Reporting System",
    layout="wide"
)

st.title("⚙️ نظام الصيانة التنبؤية والتقارير الشاملة للمولدات الصناعية")

# ---------------------------------------------------------
# 1. قاعدة بيانات العملاء وأكواد التفعيل
# ---------------------------------------------------------
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

st.sidebar.header("🔐 بوابة تفعيل العميل والصلاحيات")
input_code = st.sidebar.text_input("أدخل كود التفعيل الخاص بالعميل:", type="password")

is_authenticated = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    
    if datetime.now().date() <= expiry_dt:
        is_authenticated = True
        st.sidebar.success(f"✅ تم التفعيل بنجاح: {client_name} ({plan_type})")
    else:
        st.sidebar.error("❌ انتهت صلاحية اشتراك هذا العميل.")
elif input_code != "":
    st.sidebar.error("❌ كود التفعيل غير صحيح.")
else:
    st.sidebar.warning("⚠️ أدخل كود التفعيل في الشريط الجانبي للوصول إلى النظام.")

if not is_authenticated:
    st.error("🔒 **النظام مقفل:** يرجى إدخال كود تفعيل صحيح في الشريط الجانبي لفتح لوحة التحكم والتعديل وطباعة التقارير.")
    st.info("💡 للوصول والتجربة، يمكنك استخدام الكود الخاص بك: `ADDOMA-2026-PRO`")
    st.stop()

st.sidebar.divider()

# ---------------------------------------------------------
# 2. إعدادات المعايير والحدود للإنذارات
# ---------------------------------------------------------
st.sidebar.header("🎯 ضبط معايير الحدود والإنذارات (Thresholds Setting)")
st.sidebar.caption("حدد النطاقات الآمنة يدوياً للتنبيه باللون الأحمر عند تجاوزها:")

col_v1, col_v2 = st.sidebar.columns(2)
v_min = col_v1.number_input("أدنى جهد مسموح (V Min)", value=380.0, step=5.0)
v_max = col_v2.number_input("أقصى جهد مسموح (V Max)", value=420.0, step=5.0)

col_f1, col_f2 = st.sidebar.columns(2)
f_min = col_f1.number_input("أدنى تردد مسموح (Hz Min)", value=48.0, step=0.5)
f_max = col_f2.number_input("أقصى تردد مسموح (Hz Max)", value=52.0, step=0.5)

col_t1, col_amp = st.sidebar.columns(2)
temp_max_limit = col_t1.number_input("أقصى حرارة مسموحة (°C)", value=90.0, step=1.0)
amp_max_limit = col_amp.number_input("أقصى تيار مسموح (A Max)", value=400.0, step=10.0)

st.sidebar.divider()

# ---------------------------------------------------------
# 3. إدخال القراءات الفنية ورفع صورة المولد
# ---------------------------------------------------------
st.sidebar.header("📥 لوحة إدخال البيانات والتشغيل")

with st.sidebar.form("generator_comprehensive_form"):
    st.subheader("معلومات المولد العامة")
    gen_model = st.text_input("طراز / اسم المولد (Generator Model/ID)", value="Perkins 250 kVA - DSE 8610")
    run_hours = st.number_input("ساعات التشغيل العامة (Total Run Hours)", min_value=0.0, max_value=50000.0, value=1250.0, step=10.0)
    gen_kw = st.number_input("سعة المولد الكلية (Generator kW)", min_value=5.0, max_value=3000.0, value=250.0, step=10.0)
    load_kw = st.number_input("حجم الحمولة الحالية (Load kW)", min_value=0.0, max_value=3000.0, value=150.0, step=10.0)
    ambient_temp = st.number_input("درجة الحرارة المحيطة / المناخ (°C)", min_value=10.0, max_value=60.0, value=43.0, step=1.0)

    st.subheader("المؤشرات الميكانيكية والبيئية")
    coolant_temp = st.number_input("حرارة سائل التبريد (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    vibration = st.number_input("مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    amperes = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=4000.0, value=350.0)
    pf = st.number_input("معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85)

    st.subheader("بيانات خدمة زيت المحرك")
    last_oil_change_hours = st.number_input("قراءة الساعات عند آخر تغيير زيت", min_value=0.0, value=1000.0, step=10.0)
    oil_change_interval = st.number_input("الفترة القياسية لتغيير الزيت (ساعة)", min_value=100.0, value=250.0, step=50.0)

    submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

st.sidebar.divider()
st.sidebar.subheader("📸 رفع صورة المولد للتقرير")
uploaded_image = st.sidebar.file_uploader("اختر صورة المولد (PNG, JPG, JPEG):", type=["png", "jpg", "jpeg"])

# ---------------------------------------------------------
# 4. عرض القراءات والإنذارات في الواجهة الرئيسية
# ---------------------------------------------------------
load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

st.success(f"🔓 **العميل المفعل:** {client_name} | **نوع الاشتراك:** {plan_type} | **طراز المولد:** {gen_model}")

if uploaded_image:
    st.image(uploaded_image, caption=f"صورة المولد: {gen_model}", width=300)

col1, col2, col3, col4 = st.columns(4)
col1.metric("إجمالي التشغيل", f"{run_hours} hrs")
col2.metric("سعة المولد", f"{gen_kw} kW")
col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
col4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

col5, col6, col7, col8 = st.columns(4)
col5.metric("حرارة المحرك", f"{coolant_temp} °C")
col6.metric("ضغط الزيت", f"{oil_press} Bar")
col7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
col8.metric("التيار / معامل القدرة", f"{amperes}A | {pf}")

st.divider()
st.subheader("🚨 إنذارات وتنبيهات تجاوز المعايير التشغيلية (Threshold Alarms)")

range_alarms = []
if voltage < v_min: range_alarms.append(f"🔴 **انخفاض الجهد:** ({voltage}V) أقل من الحد الأدنى ({v_min}V).")
elif voltage > v_max: range_alarms.append(f"🔴 **ارتفاع الجهد:** ({voltage}V) أعلى من الحد الأقصى ({v_max}V).")

if freq < f_min: range_alarms.append(f"🔴 **انخفاض التردد:** ({freq} Hz) أقل من الحد الأدنى ({f_min} Hz).")
elif freq > f_max: range_alarms.append(f"🔴 **ارتفاع التردد:** ({freq} Hz) أعلى من الحد الأقصى ({f_max} Hz).")

if coolant_temp > temp_max_limit: range_alarms.append(f"🔴 **ارتفاع حرارة المحرك:** ({coolant_temp}°C) تتجاوز الحد الأقصى ({temp_max_limit}°C).")
if amperes > amp_max_limit: range_alarms.append(f"🔴 **زيادة التيار (Overcurrent):** ({amperes} A) يتجاوز الحد المسموح ({amp_max_limit} A).")

if range_alarms:
    for alarm in range_alarms: st.error(alarm)
else:
    st.success("🟢 جميع قراءات الجهد، التردد، الحرارة، والتيار ضمن المعايير الآمنة المحددة.")

# ---------------------------------------------------------
# 5. جدولة خدمة تغيير الزيت واللزوجة
# ---------------------------------------------------------
st.divider()
st.subheader("🛢️ جدول الخدمة وتغيير زيت المحرك (Oil Service Schedule)")

hours_since_oil_change = run_hours - last_oil_change_hours
hours_until_next_oil_change = oil_change_interval - hours_since_oil_change

recommended_oil = "15W40 (Standard)"
if ambient_temp >= 45.0: recommended_oil = "20W50 (Extreme Hot Climate >= 45C)"
elif ambient_temp >= 43.0: recommended_oil = "15W40 (Hot Climate)"

col_oil1, col_oil2, col_oil3 = st.columns(3)
col_oil1.metric("ساعات الزيت الحالية", f"{hours_since_oil_change} hrs")
col_oil2.metric("المتبقي للخدمة القادمة", f"{hours_until_next_oil_change} hrs")
col_oil3.metric("اللزوجة الموصى بها", recommended_oil)

if hours_until_next_oil_change <= 0:
    st.error("🚨 **تنبيه هام:** تجاوز المولد فترة تغيير الزيت المسموحة! يرجى الاستبدال فوراً.")
elif hours_until_next_oil_change <= 30:
    st.warning("⚠️ **تنبيه:** اقتربت مواعيد تغيير زيت المحرك (متبقي أقل من 30 ساعة).")

# ---------------------------------------------------------
# 6. جدول الصيانة التنبؤية للقطع
# ---------------------------------------------------------
st.divider()
st.subheader("🔧 جدول تتبع العمر الافتراضي لقطع الغيار")

if "maintenance_df" not in st.session_state:
    initial_data = [
        {"تصنيف القطعة": "الصيانة الدورية", "اسم قطعة الغيار (Spare Part)": "فلتر زيت (Oil Filter)", "العمر الافتراضي (Hours)": 250.0, "الساعات المنقضية (Hours Used)": 210.0},
        {"تصنيف القطعة": "الصيانة الدورية", "اسم قطعة الغيار (Spare Part)": "فلتر وقود (Fuel Filter)", "العمر الافتراضي (Hours)": 500.0, "الساعات المنقضية (Hours Used)": 430.0},
        {"تصنيف القطعة": "نظام الهواء", "اسم قطعة الغيار (Spare Part)": "فلتر هواء (Air Filter)", "العمر الافتراضي (Hours)": 1000.0, "الساعات المنقضية (Hours Used)": 860.0},
        {"تصنيف القطعة": "نظام التبريد", "اسم قطعة الغيار (Spare Part)": "قشاط المروحة (Fan Belt)", "العمر الافتراضي (Hours)": 2000.0, "الساعات المنقضية (Hours Used)": 1550.0},
        {"تصنيف القطعة": "النظام الكهربائي", "اسم قطعة الغيار (Spare Part)": "بطاريات (Batteries)", "العمر الافتراضي (Hours)": 8000.0, "الساعات المنقضية (Hours Used)": 6100.0},
        {"تصنيف القطعة": "المحرك - ميكانيك", "اسم قطعة الغيار (Spare Part)": "طقم عمرة رأس (Top Overhaul)", "العمر الافتراضي (Hours)": 10000.0, "الساعات المنقضية (Hours Used)": 9100.0}
    ]
    st.session_state.maintenance_df = pd.DataFrame(initial_data)

edited_table = st.data_editor(st.session_state.maintenance_df, num_rows="dynamic", use_container_width=True)
st.session_state.maintenance_df = edited_table

processed_rows = []
for index, row in edited_table.iterrows():
    category = str(row.get("تصنيف القطعة", "أخرى"))
    part_name = str(row.get("اسم قطعة الغيار (Spare Part)", "قطعة جديدة"))
    lifespan = pd.to_numeric(row.get("العمر الافتراضي (Hours)", 250), errors='coerce') or 250.0
    used_hours = pd.to_numeric(row.get("الساعات المنقضية (Hours Used)", 0), errors='coerce') or 0.0
    
    usage_pct = (used_hours / lifespan) * 100
    rem_hrs = lifespan - used_hours
    status = "Replace Immediately [CRITICAL]" if usage_pct >= 90 else ("Service Soon [WARNING]" if usage_pct >= 80 else "Good Condition [OK]")
    
    processed_rows.append({
        "تصنيف القطعة": category,
        "اسم قطعة الغيار (Spare Part)": part_name,
        "العمر الافتراضي (Hours)": lifespan,
        "الساعات المنقضية (Hours Used)": used_hours,
        "نسبة الاستهلاك (%)": f"{usage_pct:.1f}%",
        "العمر المتبقي (Remaining)": rem_hrs,
        "حالة التنبيه": status
    })

df_result = pd.DataFrame(processed_rows)

# ---------------------------------------------------------
# 7. محرك طباعة تقرير PDF الشامل المعدل (خالي من مشاكل ASCII)
# ---------------------------------------------------------
st.divider()
st.subheader("📄 استخراج وطباعة التقرير الفني الشامل (Full PDF Report)")

class ComprehensivePDF(FPDF):
    def header(self):
        self.set_font("Helvetica", 'B', 14)
        self.cell(0, 8, "INDUSTRIAL GENERATOR COMPREHENSIVE TECHNICAL REPORT", ln=True, align='C')
        self.set_font("Helvetica", 'I', 9)
        self.cell(0, 5, "Addoma Trading Services - Predictive Maintenance Platform", ln=True, align='C')
        self.line(10, 22, 200, 22)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", 'I', 8)
        self.cell(0, 10, f"Page {self.page_no()} | Generated Automatically by Addoma Maintenance System", align='C')

def clean_ascii(text):
    """دالة لتنظيف النص وإزالة أي أحرف غير تدعمها خطوط Helvetica القياسية"""
    if not isinstance(text, str):
        text = str(text)
    return "".join([c for c in text if ord(c) < 128])

def generate_full_pdf():
    pdf = ComprehensivePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # تحويل النصوص إلى ASCII آمنة
    safe_client = clean_ascii(client_name) or "Authorized Client"
    safe_model = clean_ascii(gen_model) or "Generator Unit"
    safe_plan = clean_ascii(plan_type) or "Standard Plan"
    
    # 1. المخطط العام والصورة
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(0, 5, f"Client: {safe_client} | Model: {safe_model}", ln=True)
    pdf.set_font("Helvetica", '', 9)
    pdf.cell(0, 5, f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Subscription: {safe_plan}", ln=True)
    pdf.ln(2)

    # إدراج الصورة المرفوعة معالجة
    if uploaded_image is not None:
        try:
            img = Image.open(uploaded_image)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            temp_img_path = "temp_generator_img.jpg"
            img.save(temp_img_path, "JPEG", quality=85)
            
            pdf.image(temp_img_path, x=140, y=28, w=55)
            if os.path.exists(temp_img_path):
                os.remove(temp_img_path)
            pdf.ln(2)
        except Exception:
            pass

    # 2. البيانات التشغيلية والميكانيكية والكهربائية
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, "1. Operational, Electrical & Mechanical Readings", ln=True)
    pdf.set_font("Helvetica", '', 9)
    
    readings = [
        f"Total Run Hours: {run_hours} hrs",
        f"Generator Capacity: {gen_kw} kW",
        f"Current Active Load: {load_kw} kW ({load_percentage:.1f}%)",
        f"Ambient Temp: {ambient_temp} C",
        f"Voltage: {voltage} V (Limits: {v_min}V - {v_max}V)",
        f"Frequency: {freq} Hz (Limits: {f_min}Hz - {f_max}Hz)",
        f"Current: {amperes} A (Max Limit: {amp_max_limit}A)",
        f"Power Factor: {pf}",
        f"Coolant Temp: {coolant_temp} C (Max Limit: {temp_max_limit}C)",
        f"Oil Pressure: {oil_press} Bar",
        f"Vibration Level: {vibration} mm/s"
    ]
    
    for r in readings:
        pdf.cell(120, 5, f"- {r}", ln=True)
    
    pdf.ln(3)

    # 3. الإنذارات وتنبيهات الحدود
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, "2. System Alarms & Threshold Status", ln=True)
    pdf.set_font("Helvetica", '', 9)
    if range_alarms:
        for alarm in range_alarms:
            clean_alarm = clean_ascii(alarm.replace("🔴", "[ALARM]").replace("**", ""))
            pdf.cell(0, 5, f"WARNING: {clean_alarm}", ln=True)
    else:
        pdf.cell(0, 5, "Status: All electrical & mechanical parameters are within safe limits.", ln=True)
        
    pdf.ln(3)

    # 4. جدول تغيير وساعات الزيت
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, "3. Engine Oil Service Status", ln=True)
    pdf.set_font("Helvetica", '', 9)
    pdf.cell(0, 5, f"- Last Oil Change Run Hours: {last_oil_change_hours} hrs", ln=True)
    pdf.cell(0, 5, f"- Hours Used on Current Oil: {hours_since_oil_change} hrs", ln=True)
    pdf.cell(0, 5, f"- Remaining Hours to Next Oil Change: {hours_until_next_oil_change} hrs", ln=True)
    pdf.cell(0, 5, f"- Recommended Oil Grade: {clean_ascii(recommended_oil)}", ln=True)
    
    pdf.ln(4)

    # 5. جدول قطعة الغيار والصيانة التنبؤية
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(0, 6, "4. Predictive Maintenance & Spare Parts Schedule", ln=True)
    
    pdf.set_font("Helvetica", 'B', 8)
    pdf.cell(50, 6, "Part Name", border=1)
    pdf.cell(30, 6, "Lifespan (hrs)", border=1)
    pdf.cell(30, 6, "Used (hrs)", border=1)
    pdf.cell(30, 6, "Usage (%)", border=1)
    pdf.cell(40, 6, "Remaining (hrs)", border=1)
    pdf.ln()

    pdf.set_font("Helvetica", '', 8)
    for idx, row in df_result.iterrows():
        raw_part = str(row["اسم قطعة الغيار (Spare Part)"])
        if "(" in raw_part and ")" in raw_part:
            part_eng = raw_part.split("(")[1].split(")")[0]
        else:
            part_eng = clean_ascii(raw_part) or f"Part #{idx+1}"
        
        pdf.cell(50, 5, part_eng[:25], border=1)
        pdf.cell(30, 5, str(row["العمر الافتراضي (Hours)"]), border=1)
        pdf.cell(30, 5, str(row["الساعات المنقضية (Hours Used)"]), border=1)
        pdf.cell(30, 5, str(row["نسبة الاستهلاك (%)"]), border=1)
        pdf.cell(40, 5, str(row["العمر المتبقي (Remaining)"]), border=1)
        pdf.ln()

    return pdf.output()

try:
    pdf_output = generate_full_pdf()
    st.download_button(
        label="🖨️ طباعة وتنزيل التقرير الفني الشامل بصيغة PDF (Full Comprehensive Report)",
        data=bytes(pdf_output),
        file_name=f"Full_Generator_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
except Exception as e:
    st.error(f"حدث خطأ أثناء معالجة ملف PDF: {e}")
