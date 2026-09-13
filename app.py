from datetime import datetime, timedelta
import io
import os
import re
from fpdf import FPDF
import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Maintenance & Comprehensive Reporting System",
    layout="wide",
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
input_code = st.sidebar.text_input(
    "أدخل كود التفعيل الخاص بالعميل:", type="password"
)

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
    st.sidebar.warning(
        "⚠️ أدخل كود التفعيل في الشريط الجانبي للوصول إلى النظام."
    )

if not is_authenticated:
    st.error(
        "🔒 **النظام مقفل:** يرجى إدخال كود تفعيل صحيح في الشريط الجانبي"
        " لفتح لوحة التحكم والتعديل وطباعة التقارير."
    )
    st.info(
        "💡 للوصول والتجربة، يمكنك استخدام الكود الخاص بك: `ADDOMA-2026-PRO`"
    )
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
temp_max_limit = col_t1.number_input(
    "أقصى حرارة مسموحة (°C)", value=90.0, step=1.0
)
amp_max_limit = col_amp.number_input(
    "أقصى تيار مسموح (A Max)", value=400.0, step=10.0
)

st.sidebar.divider()

# ---------------------------------------------------------
# 3. إدخال القراءات الفنية ورفع صورة المولد
# ---------------------------------------------------------
st.sidebar.header("📥 لوحة إدخال البيانات والتشغيل")

with st.sidebar.form("generator_comprehensive_form"):
    st.subheader("معلومات المولد العامة")
    gen_model = st.text_input(
        "طراز / اسم المولد (Generator Model/ID)",
        value="Perkins 410 kVA - DSE 7320",
    )
    run_hours = st.number_input(
        "ساعات التشغيل الحالية الكلية (Current Total Hours)",
        min_value=0.0,
        max_value=100000.0,
        value=700.0,
        step=10.0,
    )
    future_run_hours = st.number_input(
        "ساعات تشغيل العمل القادمة الافتراضية (Target Future Hours)",
        min_value=0.0,
        max_value=100000.0,
        value=940.0,
        step=10.0,
        help="الساعات المستهدفة للتشغيل القادم لتقييم استهلاك الزيت وقطع الغيار.",
    )

    gen_kw = st.number_input(
        "سعة المولد الكلية (Generator kW)",
        min_value=5.0,
        max_value=3000.0,
        value=410.0,
        step=10.0,
    )
    load_kw = st.number_input(
        "حجم الحمولة الحالية (Load kW)",
        min_value=0.0,
        max_value=3000.0,
        value=50.0,
        step=10.0,
    )
    ambient_temp = st.number_input(
        "درجة الحرارة المحيطة / المناخ (°C)",
        min_value=10.0,
        max_value=60.0,
        value=43.0,
        step=1.0,
    )

    st.subheader("المؤشرات الميكانيكية والبيئية")
    coolant_temp = st.number_input(
        "حرارة سائل التبريد (°C)", min_value=0.0, max_value=150.0, value=85.0
    )
    oil_press = st.number_input(
        "ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=2.5
    )
    vibration = st.number_input(
        "مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2
    )

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input(
        "الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0
    )
    freq = st.number_input(
        "التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0
    )
    amperes = st.number_input(
        "التيار Amperes (A)", min_value=0.0, max_value=4000.0, value=118.0
    )
    pf = st.number_input(
        "معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85
    )

    st.subheader("بيانات خدمة زيت المحرك والفلاتر")
    last_oil_change_hours = st.number_input(
        "قراءة عداد الساعات عند آخر تغيير زيت وفلاتر الدوري",
        min_value=0.0,
        value=460.0,
        step=10.0,
    )
    oil_change_interval = st.number_input(
        "الفترة القياسية الافتراضية للزيت والفلاتر (ساعة)",
        min_value=100.0,
        value=250.0,
        step=50.0,
    )

    submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

st.sidebar.divider()
st.sidebar.subheader("📸 رفع صورة المولد للتقرير")
uploaded_image = st.sidebar.file_uploader(
    "اختر صورة المولد (PNG, JPG, JPEG):", type=["png", "jpg", "jpeg"]
)

# ---------------------------------------------------------
# 4. عرض القراءات والإنذارات في الواجهة الرئيسية
# ---------------------------------------------------------
load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

st.success(
    f"🔓 **العميل المفعل:** {client_name} | **نوع الاشتراك:** {plan_type} |"
    f" **طراز المولد:** {gen_model}"
)

if uploaded_image:
    st.image(uploaded_image, caption=f"صورة المولد: {gen_model}", width=300)

col1, col2, col3, col4 = st.columns(4)
col1.metric("إجمالي التشغيل الحالي", f"{run_hours} hrs")
col2.metric("الساعات المستهدفة القادمة", f"{future_run_hours} hrs")
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
if voltage < v_min:
    range_alarms.append(
        f"Low Voltage Alert: ({voltage}V) below minimum ({v_min}V)"
    )
elif voltage > v_max:
    range_alarms.append(
        f"High Voltage Alert: ({voltage}V) exceeds maximum ({v_max}V)"
    )

if freq < f_min:
    range_alarms.append(
        f"Low Frequency Alert: ({freq} Hz) below minimum ({f_min} Hz)"
    )
elif freq > f_max:
    range_alarms.append(
        f"High Frequency Alert: ({freq} Hz) exceeds maximum ({f_max} Hz)"
    )

if coolant_temp > temp_max_limit:
    range_alarms.append(
        f"Engine Overheat Alert: ({coolant_temp}C) exceeds limit"
        f" ({temp_max_limit}C)"
    )
if amperes > amp_max_limit:
    range_alarms.append(
        f"Overcurrent Alert: ({amperes} A) exceeds limit ({amp_max_limit} A)"
    )

if range_alarms:
    for alarm in range_alarms:
        st.error(f"🔴 {alarm}")
else:
    st.success(
        "🟢 جميع قراءات الجهد، التردد، الحرارة، التيار ضمن المعايير الآمنة"
        " المحددة."
    )

# ---------------------------------------------------------
# 5. جدولة خدمة تغيير الزيت والتحذيرات الذكية (تلقائية الخصم)
# ---------------------------------------------------------
st.divider()
st.subheader("🛢️ جدول الخدمة وتغيير زيت المحرك (Oil Service Schedule)")

effective_hours = future_run_hours if future_run_hours > 0 else run_hours
hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)
hours_until_next_oil_change = oil_change_interval - hours_since_oil_change
oil_usage_pct = (
    (hours_since_oil_change / oil_change_interval) * 100
    if oil_change_interval > 0
    else 0
)

recommended_oil = "15W40 (Standard)"
if ambient_temp >= 45.0:
    recommended_oil = "20W50 (Extreme Hot Climate)"
elif ambient_temp >= 43.0:
    recommended_oil = "15W40 (Hot Climate)"

col_oil1, col_oil2, col_oil3, col_oil4 = st.columns(4)
col_oil1.metric(
    "المدة المنقضية للزيت الحالية", f"{hours_since_oil_change:.1f} hrs"
)
col_oil2.metric("الفترة الافتراضية للزيت", f"{oil_change_interval:.1f} hrs")
col_oil3.metric(
    "المدة المتبقية للخدمة",
    f"{max(0.0, hours_until_next_oil_change):.1f} hrs",
    f"استهلاك {oil_usage_pct:.0f}%",
)
col_oil4.metric("اللزوجة الموصى بها", recommended_oil)

if oil_usage_pct >= 100:
    st.error(
        "🚨 **تحذير حرج:** تم استهلاك مدة غيار الزيت بالكامل وتجاوز الفترة"
        f" الافتراضية بـ ({abs(hours_until_next_oil_change):.1f} ساعة)! يرجى"
        " استبدال الزيت والفلاتر فوراً."
    )
elif oil_usage_pct >= 90:
    st.warning(
        f"⚠️ **تنبيه:** تم استهلاك {oil_usage_pct:.1f}% من الفترة الافتراضية"
        f" (متبقي {hours_until_next_oil_change:.1f} ساعة فقط)."
    )
else:
    st.info("🟢 حالة زيت المحرك جيدة وتعمل ضمن الفترة المسموحة.")

# ---------------------------------------------------------
# 6. جدول الصيانة التنبؤية بالخصم التلقائي للمدة المنقضية والمتبقية
# ---------------------------------------------------------
st.divider()
st.subheader(
    "🔧 جدول تتبع العمر الافتراضي والمدد المتبقية لقطع الغيار والفلاتر"
)

service_used_hours = hours_since_oil_change

base_parts_data = [
    {
        "تصنيف القطعة (Category)": "Schedule Services",
        "اسم قطعة الغيار (Spare Part)": "Engine Oil & Filter (زيت وفلتر المحرك)",
        "العمر الافتراضي - ساعات (Lifespan)": float(oil_change_interval),
        "الساعات المنقضية (Hours Used)": float(service_used_hours),
    },
    {
        "تصنيف القطعة (Category)": "Schedule Services",
        "اسم قطعة الغيار (Spare Part)": "Primary Fuel Filter (فلتر وقود أولي)",
        "العمر الافتراضي - ساعات (Lifespan)": 500.0,
        "الساعات المنقضية (Hours Used)": float(service_used_hours),
    },
    {
        "تصنيف القطعة (Category)": "Schedule Services",
        "اسم قطعة الغيار (Spare Part)": (
            "Secondary Fuel Filter (فلتر وقود ثانوي)"
        ),
        "العمر الافتراضي - ساعات (Lifespan)": 500.0,
        "الساعات المنقضية (Hours Used)": float(service_used_hours),
    },
    {
        "تصنيف القطعة (Category)": "Air System",
        "اسم قطعة الغيار (Spare Part)": "Air Filter (فلتر هواء)",
        "العمر الافتراضي - ساعات (Lifespan)": 1000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Cooling System",
        "اسم قطعة الغيار (Spare Part)": "Fan Belt (قشاط المروحة)",
        "العمر الافتراضي - ساعات (Lifespan)": 2000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Cooling System",
        "اسم قطعة الغيار (Spare Part)": "ELC Coolant (سائل تبريد)",
        "العمر الافتراضي - ساعات (Lifespan)": 3000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Fuel System",
        "اسم قطعة الغيار (Spare Part)": "Fuel Injectors (بخاخات الوقود)",
        "العمر الافتراضي - ساعات (Lifespan)": 5000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Electrical System",
        "اسم قطعة الغيار (Spare Part)": "Batteries (البطاريات)",
        "العمر الافتراضي - ساعات (Lifespan)": 8000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Electrical System",
        "اسم قطعة الغيار (Spare Part)": (
            "Charging Alternator (دينامو الشحن)"
        ),
        "العمر الافتراضي - ساعات (Lifespan)": 10000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Engine Mechanical",
        "اسم قطعة الغيار (Spare Part)": "Top Overhaul (طقم عمرة رأس)",
        "العمر الافتراضي - ساعات (Lifespan)": 10000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
    {
        "تصنيف القطعة (Category)": "Engine Mechanical",
        "اسم قطعة الغيار (Spare Part)": "Major Overhaul (عمرة كاملة)",
        "العمر الافتراضي - ساعات (Lifespan)": 20000.0,
        "الساعات المنقضية (Hours Used)": float(effective_hours),
    },
]

df_parts_input = pd.DataFrame(base_parts_data)
edited_table = st.data_editor(
    df_parts_input,
    num_rows="dynamic",
    use_container_width=True,
    key="parts_editor",
)

processed_rows = []
warning_parts = []
expired_parts = []

for index, row in edited_table.iterrows():
    category = str(row.get("تصنيف القطعة (Category)", "Other"))
    part_name = str(row.get("اسم قطعة الغيار (Spare Part)", "Part"))
    lifespan = (
        pd.to_numeric(
            row.get("العمر الافتراضي - ساعات (Lifespan)", 250), errors="coerce"
        )
        or 250.0
    )
    used_hours = (
        pd.to_numeric(
            row.get("الساعات المنقضية (Hours Used)", effective_hours),
            errors="coerce",
        )
        or 0.0
    )

    rem_hrs = lifespan - used_hours
    usage_pct = (used_hours / lifespan) * 100 if lifespan > 0 else 0

    if rem_hrs <= 0:
        status = "EXPIRED (انقضاء الفترة)"
        expired_parts.append(
            f"{part_name} - انتهت مدته الخدمية وتجاوز بـ ({abs(rem_hrs):.0f}"
            " ساعة)"
        )
    elif usage_pct >= 90:
        status = "WARNING (متبقي أقل من 10%)"
        warning_parts.append(
            f"{part_name} - استهلك {usage_pct:.0f}% (متبقي {rem_hrs:.0f} ساعة"
            " فقط)"
        )
    elif usage_pct >= 75:
        status = "ATTENTION (قرب التغيير)"
    else:
        status = "GOOD (جيدة)"

    processed_rows.append({
        "تصنيف القطعة": category,
        "قطع الغيار / الفلاتر": part_name,
        "العمر الافتراضي (ساعة)": lifespan,
        "المدة المنقضية (ساعة)": used_hours,
        "نسبة الاستهلاك": f"{usage_pct:.0f}%",
        "المدة المتبقية (ساعة)": max(0.0, rem_hrs),
        "الحالة الفنية": status,
    })

df_result = pd.DataFrame(processed_rows)

st.caption("🔍 **لوحة التحليل الفني التلقائي لقطع الغيار والفلاتر:**")

if expired_parts:
    for item in expired_parts:
        st.error(
            f"🚨 **تحذير انقضاء الساعات:** {item} - يتطلب الاستبدال التلقائي!"
        )

if warning_parts:
    for item in warning_parts:
        st.warning(f"⚠️ **تنبيه اقتراب موعد الخدمة:** {item}")

if not expired_parts and not warning_parts:
    st.success(
        "🟢 جميع الفلاتر وقطع الغيار تعمل ضمن المدة المتبقية والحدود الآمنة."
    )

# ---------------------------------------------------------
# التحليل البياني لساعات التشغيل والمدد الافتراضية
# ---------------------------------------------------------
st.divider()
st.subheader("📊 التحليل البياني لساعات التشغيل والمدد الافتراضية")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    df_chart = df_result.copy()
    fig_bar = px.bar(
        df_chart,
        x="قطع الغيار / الفلاتر",
        y=["المدة المنقضية (ساعة)", "المدة المتبقية (ساعة)"],
        title="مقارنة الساعات المنقضية مقابل المتبقية لكل قطعة",
        labels={"value": "الساعات", "variable": "المؤشر"},
        color_discrete_sequence=["#d9534f", "#28a745"],
        barmode="stack",
    )
    fig_bar.update_layout(xaxis_tickangle=-45)
    st.plotly_chart(fig_bar, use_container_width=True)

with chart_col2:
    fig_pie = px.pie(
        df_chart,
        names="الحالة الفنية",
        title="توزيع قطع الغيار حسب الجاهزية والحالة الفنية",
        color="الحالة الفنية",
        color_discrete_map={
            "GOOD (جيدة)": "#28a745",
            "ATTENTION (قرب التغيير)": "#ffc107",
            "WARNING (متبقي أقل من 10%)": "#fd7e14",
            "EXPIRED (انقضاء الفترة)": "#dc3545",
        },
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# ---------------------------------------------------------
# 7. دالة تنظيف النصوص لـ PDF
# ---------------------------------------------------------


def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"


# ---------------------------------------------------------
# 8. محرك طباعة تقرير PDF الشامل (تم إصلاح التعامل مع الـ bytes)
# ---------------------------------------------------------
st.divider()
st.subheader("📄 استخراج وطباعة التقرير الفني الشامل (Full PDF Report)")


class SafePDF(FPDF):

    def header(self):
        self.set_font("Helvetica", "B", 14)
        self.cell(
            0,
            8,
            "INDUSTRIAL GENERATOR COMPREHENSIVE TECHNICAL REPORT",
            ln=True,
            align="C",
        )
        self.set_font("Helvetica", "I", 9)
        self.cell(
            0,
            5,
            "Addoma Trading Services - Maintenance Platform",
            ln=True,
            align="C",
        )
        self.line(10, 22, 200, 22)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(
            0,
            10,
            f"Page {self.page_no()} | Generated Automatically by Addoma System",
            align="C",
        )


def generate_safe_pdf():
    pdf = SafePDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    safe_client = sanitize_latin_only(client_name)
    if safe_client == "N/A":
        safe_client = "Addoma Trading Services Client"

    safe_model = sanitize_latin_only(gen_model)
    if safe_model == "N/A":
        safe_model = "Industrial Generator"

    # 1. المخطط العام
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, f"Client: {safe_client} | Model: {safe_model}", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0,
        5,
        f"Report Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ln=True,
    )
    pdf.ln(2)

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

    # 2. القراءات الأساسية
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "1. Operational & Technical Readings", ln=True)
    pdf.set_font("Helvetica", "", 9)

    readings = [
        f"Current Total Run Hours: {run_hours} hrs",
        f"Target Future Hours: {future_run_hours} hrs",
        f"Generator Capacity: {gen_kw} kW",
        f"Current Active Load: {load_kw} kW ({load_percentage:.1f}%)",
        f"Ambient Temp: {ambient_temp} C",
        f"Voltage: {voltage} V (Limits: {v_min}V - {v_max}V)",
        f"Frequency: {freq} Hz (Limits: {f_min}Hz - {f_max}Hz)",
        f"Current: {amperes} A (Max Limit: {amp_max_limit}A)",
        f"Power Factor: {pf}",
        f"Coolant Temp: {coolant_temp} C (Max Limit: {temp_max_limit}C)",
        f"Oil Pressure: {oil_press} Bar",
        f"Vibration Level: {vibration} mm/s",
    ]

    for r in readings:
        pdf.cell(120, 5, f"- {r}", ln=True)

    pdf.ln(3)

    # 3. حالة الإنذارات
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "2. System Alarms & Safety Status", ln=True)
    pdf.set_font("Helvetica", "", 9)
    if range_alarms:
        for alarm in range_alarms:
            pdf.cell(0, 5, f"[ALARM] {sanitize_latin_only(alarm)}", ln=True)
    else:
        pdf.cell(
            0, 5, "Status: All parameters are within safe limits.", ln=True
        )

    pdf.ln(3)

    # 4. جدول تغيير وساعات الزيت
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 6, "3. Engine Oil & Filter Service Status", ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(
        0, 5, f"- Default Oil Interval: {oil_change_interval} hrs", ln=True
    )
    pdf.cell(
        0,
        5,
        f"- Hours Used on Current Oil: {hours_since_oil_change} hrs"
        f" ({oil_usage_pct:.0f}%)",
        ln=True,
    )
    pdf.cell(
        0,
        5,
        "- Remaining Hours to Next Oil Change:"
        f" {max(0.0, hours_until_next_oil_change)} hrs",
        ln=True,
    )
    pdf.cell(
        0,
        5,
        f"- Recommended Oil Grade: {sanitize_latin_only(recommended_oil)}",
        ln=True,
    )

    pdf.ln(4)

    # 5. جدول قطع الغيار
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(
        0, 6, "4. Predictive Maintenance & Parts Remaining Schedule", ln=True
    )

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(45, 6, "Part Name", border=1)
    pdf.cell(25, 6, "Lifespan(h)", border=1)
    pdf.cell(25, 6, "Used(h)", border=1)
    pdf.cell(25, 6, "Usage (%)", border=1)
    pdf.cell(25, 6, "Remaining(h)", border=1)
    pdf.cell(35, 6, "Status", border=1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for idx, row in df_result.iterrows():
        part_clean = sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))
        status_clean = sanitize_latin_only(str(row["الحالة الفنية"]))

        pdf.cell(45, 5, part_clean[:22], border=1)
        pdf.cell(25, 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
        pdf.cell(25, 5, str(row["المدة المنقضية (ساعة)"]), border=1)
        pdf.cell(25, 5, str(row["نسبة الاستهلاك"]), border=1)
        pdf.cell(25, 5, str(row["المدة المتبقية (ساعة)"]), border=1)
        pdf.cell(35, 5, status_clean, border=1)
        pdf.ln()

    # إرجاع مخرجات PDF بشكل آمن وثنائي (bytes) لتفادي أخطاء التشفير
    pdf_output = pdf.output()
    if isinstance(pdf_output, str):
        return pdf_output.encode("latin-1")
    elif isinstance(pdf_output, bytearray):
        return bytes(pdf_output)
    elif isinstance(pdf_output, bytes):
        return pdf_output
    else:
        return bytes(pdf_output)


try:
    pdf_bytes = generate_safe_pdf()
    st.download_button(
        label=(
            "🖨️ طباعة وتنزيل التقرير الفني الشامل بصيغة PDF (Download Report)"
        ),
        data=pdf_bytes,
        file_name=(
            f"Generator_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        ),
        mime="application/pdf",
        use_container_width=True,
    )
except Exception as e:
    st.error(f"حدث خطأ أثناء معالجة ملف PDF: {e}")
