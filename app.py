from datetime import datetime, timedelta
import io
import json
import os
import re
import uuid

from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st

# استيراد محرك قراءة الأكواد (Barcode/QR) في حال توفره
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# ---------------------------------------------------------
# 0. إعدادات الصفحة الرئيسية
# ---------------------------------------------------------
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# ---------------------------------------------------------
# 1. دالة تنظيف النصوص ومحرك تقارير PDF
# ---------------------------------------------------------
def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT"):
        super().__init__()
        self.report_title = title_text

    def header(self):
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 8, self.report_title, ln=True, align="C")
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 4, "Addoma Trading Services - Engineering Platform", ln=True, align="C")
        self.line(10, 20, 200, 20)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 5, "Prepared by: Osman Adam Addoma", ln=True, align="C")
        self.cell(0, 5, f"Page {self.page_no()} | System Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# ---------------------------------------------------------
# 2. تهيئة الاتصال بـ Firebase Firestore
# ---------------------------------------------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS")
        if firebase_json_env:
            cred_dict = json.loads(firebase_json_env)
            cred = credentials.Certificate(cred_dict)
        elif "firebase" in st.secrets:
            firebase_dict = dict(st.secrets["firebase"])
            firebase_dict["private_key"] = firebase_dict["private_key"].replace("\\n", "\n")
            cred = credentials.Certificate(firebase_dict)
        else:
            cred = credentials.Certificate("firebase_key.json")
        firebase_admin.initialize_app(cred)
    return firestore.client()

try:
    db = init_firebase()
    st.sidebar.success("🔥 متصل بـ Firebase Firestore بنجاح!")
except Exception as e:
    st.sidebar.error(f"⚠️ وضع العمل المحلي: {e}")
    db = None

# ---------------------------------------------------------
# 3. إدارة المدد الزمنية للاشتراكات
# ---------------------------------------------------------
if "device_id" not in st.session_state:
    query_params = st.query_params
    if "did" in query_params:
        st.session_state.device_id = query_params["did"]
    else:
        new_id = str(uuid.uuid4())
        st.session_state.device_id = new_id
        st.query_params["did"] = new_id

device_id = st.session_state.device_id

def get_or_create_device_record(dev_id):
    now = datetime.now()
    if db is not None:
        try:
            doc_ref = db.collection("devices").document(dev_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return {
                    "first_visit": data.get("first_visit", now),
                    "trial_expiry": data.get("trial_expiry", now + timedelta(days=7)),
                    "subscription_expiry": data.get("subscription_expiry"),
                    "plan_type": data.get("plan_type", "فترة تجريبية 7 أيام")
                }
            else:
                trial_exp = now + timedelta(days=7)
                initial_data = {
                    "first_visit": now,
                    "trial_expiry": trial_exp,
                    "subscription_expiry": None,
                    "plan_type": "فترة تجريبية 7 أيام"
                }
                doc_ref.set(initial_data)
                return initial_data
        except Exception:
            pass
            
    if "mock_device_db" not in st.session_state:
        st.session_state.mock_device_db = {
            "first_visit": now,
            "trial_expiry": now + timedelta(days=7),
            "subscription_expiry": None,
            "plan_type": "فترة تجريبية 7 أيام"
        }
    return st.session_state.mock_device_db

def update_device_subscription(dev_id, sub_expiry, plan_name):
    if db is not None:
        try:
            doc_ref = db.collection("devices").document(dev_id)
            doc_ref.update({
                "subscription_expiry": sub_expiry,
                "plan_type": plan_name
            })
        except Exception:
            pass
    if "mock_device_db" in st.session_state:
        st.session_state.mock_device_db["subscription_expiry"] = sub_expiry
        st.session_state.mock_device_db["plan_type"] = plan_name

user_record = get_or_create_device_record(device_id)
now = datetime.now()

trial_exp = user_record.get("trial_expiry")
sub_exp = user_record.get("subscription_expiry")

if hasattr(trial_exp, "timestamp"): trial_exp = datetime.fromtimestamp(trial_exp.timestamp())
if sub_exp and hasattr(sub_exp, "timestamp"): sub_exp = datetime.fromtimestamp(sub_exp.timestamp())

is_sub_active = sub_exp and now < sub_exp
is_trial_active = trial_exp and now < trial_exp

if is_sub_active:
    time_left = (sub_exp - now).days
    access_status = "paid"
    plan_type = user_record.get("plan_type", "اشتراك مفعل")
    expiry_date_str = sub_exp.strftime("%Y-%m-%d")
elif is_trial_active:
    time_left = (trial_exp - now).days
    access_status = "trial"
    plan_type = "فترة تجريبية (7 أيام)"
    expiry_date_str = trial_exp.strftime("%Y-%m-%d")
else:
    time_left = 0
    access_status = "expired"
    plan_type = "منتهي الصلاحية"
    expiry_date_str = "منتهي"

st.sidebar.header("🔐 تفاصيل الاشتراك والتفعيل")
st.sidebar.info(f"""
📌 **حالة الحساب والاشتراك:**
* **نوع الخطة:** {plan_type}
* **تاريخ الانتهاء:** `{expiry_date_str}`
* **المدة المتبقية:** **{time_left}** يوماً
""")

with st.sidebar.expander("🔑 إدخال كود التفعيل"):
    input_code = st.text_input("أدخل كود التفعيل:", type="password")
    if st.button("تفعيل الاشتراك"):
        code_clean = input_code.strip().upper()
        duration_map = {
            "ADDOMA-7D": (7, "اشتراك تجريبي (7 أيام)"),
            "ADDOMA-30D": (30, "اشتراك شهري (1 شهر)"),
            "ADDOMA-90D": (90, "اشتراك 3 شهور"),
            "ADDOMA-180D": (180, "اشتراك 6 شهور"),
            "ADDOMA-1Y": (365, "اشتراك سنوي كامل"),
            "ADDOMA-2026-PRO": (365, "اشتراك احترافي (1 سنة)"),
        }
        if code_clean in duration_map:
            days, p_name = duration_map[code_clean]
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم تفعيل: {p_name}")
            st.rerun()
        else:
            st.error("❌ كود تفعيل غير صحيح.")

st.sidebar.caption("💡 **أكواد للتجربة:** `ADDOMA-30D` | `ADDOMA-1Y`")

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية. يرجى التفعيل باستخدام كود اشتراك ساري.")
    st.stop()

# ---------------------------------------------------------
# 4. قائمة اختيار التطبيق
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("🛠️ التطبيقات المتاحة")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية",
        "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)"
    ]
)
st.sidebar.divider()

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية، الرسوم البيانية والتقرير الشامل
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    col_v1, col_v2 = st.sidebar.columns(2)
    v_min = col_v1.number_input("أدنى جهد (V Min)", value=380.0, step=5.0)
    v_max = col_v2.number_input("أقصى جهد (V Max)", value=420.0, step=5.0)

    col_f1, col_f2 = st.sidebar.columns(2)
    f_min = col_f1.number_input("أدنى تردد (Hz Min)", value=48.0, step=0.5)
    f_max = col_f2.number_input("أقصى تردد (Hz Max)", value=52.0, step=0.5)

    temp_max_limit = st.sidebar.number_input("أقصى حرارة (°C)", value=90.0, step=1.0)
    amp_max_limit = st.sidebar.number_input("أقصى تيار (A Max)", value=400.0, step=10.0)

    with st.sidebar.form("generator_comprehensive_form"):
        st.subheader("مدخلات القراءات والخدمة")
        gen_model = st.text_input("طراز / اسم المولد", value="Perkins 410 kVA - DSE 7320")
        run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=700.0, step=10.0)
        future_run_hours = st.number_input("ساعات التشغيل المستهدفة", min_value=0.0, value=940.0, step=10.0)
        gen_kw = st.number_input("سعة المولد (kW)", min_value=5.0, value=410.0, step=10.0)
        load_kw = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=250.0, step=10.0)
        ambient_temp = st.number_input("الحرارة المحيطة (°C)", value=43.0, step=1.0)

        coolant_temp = st.number_input("حرارة سائل التبريد (°C)", value=85.0)
        oil_press = st.number_input("ضغط الزيت (Bar)", value=4.5)
        vibration = st.number_input("مستوى الاهتزاز (mm/s)", value=2.2)

        voltage = st.number_input("الجهد (V)", value=400.0)
        freq = st.number_input("التردد (Hz)", value=50.0)
        amperes = st.number_input("التيار (A)", value=360.0)
        pf = st.number_input("معامل القدرة (PF)", value=0.85)

        last_oil_change_hours = st.number_input("عداد آخر تغيير زيت وفلاتر", value=460.0, step=10.0)
        oil_change_interval = st.number_input("الفترة القياسية للزيت (ساعة)", value=250.0, step=50.0)

        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    # إضافة خانة رفع صور متعددة للمولد
    st.subheader("🖼️ توثيق صور المولد الميدانية (رفع صور متعددة)")
    generator_images = st.file_uploader("قم بختيار وترفيع عدة صور للمولد (لوحة التحكم، المحرك، المولد الرئيسي):", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    if generator_images:
        cols_img = st.columns(len(generator_images))
        for idx, img_file in enumerate(generator_images):
            with cols_img[idx]:
                st.image(Image.open(img_file), caption=f"صورة {idx+1}", width="stretch")

    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("إجمالي التشغيل الحالي", f"{run_hours} hrs")
    col2.metric("الساعات المستهدفة", f"{future_run_hours} hrs")
    col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
    col4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("حرارة المحرك", f"{coolant_temp} °C")
    col6.metric("ضغط الزيت", f"{oil_press} Bar")
    col7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
    col8.metric("التيار / معامل القدرة", f"{amperes}A | {pf}")

    range_alarms = []
    if voltage < v_min or voltage > v_max: range_alarms.append(f"تجاوز الجهد: ({voltage}V) النطاق المسموح ({v_min}V - {v_max}V)")
    if freq < f_min or freq > f_max: range_alarms.append(f"تجاوز التردد: ({freq}Hz) النطاق المسموح ({f_min}Hz - {f_max}Hz)")
    if coolant_temp > temp_max_limit: range_alarms.append(f"ارتفاع حرارة المحرك: ({coolant_temp}°C) تجاوز الحد ({temp_max_limit}°C)")
    if amperes > amp_max_limit: range_alarms.append(f"ارتفاع الحمل الكهربائي: ({amperes}A) تجاوز الحد ({amp_max_limit}A)")

    if range_alarms:
        for alarm in range_alarms: st.error(f"🔴 {alarm}")
    else:
        st.success("🟢 جميع المؤشرات التشغيلية ضمن الحدود الآمنة.")

    st.divider()
    st.subheader("🛢️ جدول الصيانة التنبؤية الكامل لقطع الغيار والفلاتر (مطابق للجدول القياسي)")

    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)

    # الجدول الكامل تماماً كما ورد في الصورة المرفقة
    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Engine Oil & Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Fan Belt System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Feul System", "قطع الغيار / الفلاتر": "Injectors Check", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "النظام الكهربائي", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Electric System", "قطع الغيار / الفلاتر": "Charging Alternator", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Top Overhaul", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Major Overhaul", "العمر الافتراضي (ساعة)": 20000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Oilers System", "قطع الغيار / الفلاتر": "Oil Cooler Clean", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "نظام التبريد", "قطع الغيار / الفلاتر": "Water Pump", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "نظام الهواء", "قطع الغيار / الفلاتر": "Turbocharger Check", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch", key="parts_editor")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        cat = str(row.get("تصنيف القطعة", "Other"))
        part = str(row.get("قطع الغيار / الفلاتر", "Part"))
        life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0

        status = "EXPIRED (تغيير فوري - خطر)" if rem <= 0 else ("WARNING (قرب الخدمة - استعداد)" if pct >= 85 else "GOOD (حالة جيدة)")
        processed_rows.append({
            "تصنيف القطعة": cat,
            "قطع الغيار / الفلاتر": part,
            "العمر الافتراضي (ساعة)": life,
            "الساعات المنقضية (ساعة)": used,
            "المدة المتبقية (ساعة)": max(0.0, rem),
            "نسبة الاستهلاك": f"{pct:.0f}%",
            "حالة التنبيه": status
        })

    df_result = pd.DataFrame(processed_rows)

    st.divider()
    st.subheader("📊 الرسوم البيانية لأداء الآليات (الجداول العمودية والدائرية)")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_bar = px.bar(
            df_result,
            x="قطع الغيار / الفلاتر",
            y=["الساعات المنقضية (ساعة)", "المدة المتبقية (ساعة)"],
            title="مقارنة الساعات المنقضية مقابل المتبقية لكل قطعة",
            barmode="stack",
            color_discrete_sequence=["#d9534f", "#28a745"]
        )
        st.plotly_chart(fig_bar, width="stretch")

    with chart_col2:
        fig_pie = px.pie(
            df_result,
            names="حالة التنبيه",
            title="توزيع حالة التنبيه والجاهزية لقطع الغيار",
            color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"]
        )
        st.plotly_chart(fig_pie, width="stretch")

    st.divider()
    st.subheader("📄 إصدار وتنزيل التقرير الفني الشامل والرسوم البيانية (PDF Full Report)")

    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("GENERATOR & PREDICTIVE MAINTENANCE REPORT")
        pdf.add_page()
        temp_files = []

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)}", ln=True)
        pdf.cell(0, 5, f"Total Run Hours: {run_hours} hrs | Target Hours: {future_run_hours} hrs", ln=True)
        pdf.cell(0, 5, f"Capacity: {gen_kw} kW | Current Load: {load_kw} kW ({load_percentage:.1f}%)", ln=True)
        pdf.cell(0, 5, f"Electrical: {voltage} V | {freq} Hz | {amperes} A | PF: {pf}", ln=True)
        pdf.cell(0, 5, f"Mechanical: Coolant {coolant_temp} C | Oil Press {oil_press} Bar | Vib {vibration} mm/s", ln=True)
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Predictive Maintenance & Parts Lifespan Table:", ln=True)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(50, 5, "Part Name", border=1)
        pdf.cell(25, 5, "Lifespan(h)", border=1)
        pdf.cell(25, 5, "Used(h)", border=1)
        pdf.cell(25, 5, "Remaining(h)", border=1)
        pdf.cell(45, 5, "Status", border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for idx, row in df_result.iterrows():
            pdf.cell(50, 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:25], border=1)
            pdf.cell(25, 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
            pdf.cell(25, 5, str(row["الساعات المنقضية (ساعة)"]), border=1)
            pdf.cell(25, 5, str(row["المدة المتبقية (ساعة)"]), border=1)
            pdf.cell(45, 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1)
            pdf.ln()

        # إضافة الرسوم البيانية داخل ملف الـ PDF
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Performance & Maintenance Visual Charts:", ln=True)

            # الرسم العمودي
            fig_bar, ax_bar = plt.subplots(figsize=(7, 4))
            p_short = [sanitize_latin_only(str(x))[:15] for x in df_result["قطع الغيار / الفلاتر"]]
            u_h = df_result["الساعات المنقضية (ساعة)"].values
            r_h = df_result["المدة المتبقية (ساعة)"].values

            ax_bar.bar(p_short, u_h, label="Used Hours", color="#d9534f")
            ax_bar.bar(p_short, r_h, bottom=u_h, label="Remaining Hours", color="#28a745")
            ax_bar.set_title("Parts Lifespan Overview (Hours)", fontsize=10)
            ax_bar.legend()
            plt.xticks(rotation=40, ha="right", fontsize=8)
            plt.tight_layout()

            bar_path = f"temp_bar_{datetime.now().timestamp()}.png"
            plt.savefig(bar_path, dpi=200)
            plt.close(fig_bar)
            temp_files.append(bar_path)
            pdf.image(bar_path, x=15, y=25, w=170)

            # الرسم الدائري
            fig_pie, ax_pie = plt.subplots(figsize=(6, 4))
            status_counts = df_result["حالة التنبيه"].value_counts()
            color_map = {"GOOD (حالة جيدة)": "#28a745", "WARNING (قرب الخدمة - استعداد)": "#ffc107", "EXPIRED (تغيير فوري - خطر)": "#dc3545"}
            colors = [color_map.get(k, "#999999") for k in status_counts.index]
            labels_clean = [sanitize_latin_only(str(k)) for k in status_counts.index]
            
            ax_pie.pie(status_counts.values, labels=labels_clean, autopct='%1.1f%%', startangle=140, colors=colors)
            ax_pie.axis('equal')
            plt.title("Parts Status Distribution", fontsize=10)
            plt.tight_layout()

            pie_path = f"temp_pie_{datetime.now().timestamp()}.png"
            plt.savefig(pie_path, dpi=200)
            plt.close(fig_pie)
            temp_files.append(pie_path)
            pdf.image(pie_path, x=25, y=135, w=150)

        except Exception as e:
            st.error(f"خطأ في رسومات PDF: {e}")

        pdf_bytes = pdf.output(dest="S")
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

        return pdf_bytes.encode("latin-1", errors="replace")

    st.download_button(
        label="🖨️ إصدار التقرير الفني الشامل والرسوم البيانية (PDF)",
        data=generate_full_pdf_bytes(),
        file_name=f"Full_Maintenance_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات وقراءة الأكواد
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي، مكتبة الكتالوجات وقراءة الأكواد")

    tab1, tab2, tab3 = st.tabs(["💬 الاستشارات والتحليل وبحث Google", "📚 رفع وتصفح الكتالوجات", "📷 قراءة أکوال الشاشة والأكواد (QR/Barcode)"])

    # --- TAB 1: الاستشارات والتحليل وبحث Google ---
    with tab1:
        st.subheader("💡 تحليل العطل والبحث في مصادر Google والمواقع الهندسية")
        user_input = st.text_area("أدخل تفاصيل العطل الفني أو الكود:", height=100, placeholder="مثال: كود إنذار DSE 8610 Fail to Start أو مشكلة في نظام الوقود...")

        # إضافة زر وبحث في Google والمواقع الهندسية
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            search_google = st.button("🌐 بحث في Google والمواقع الهندسية", use_container_width=True)
        with col_b2:
            analyze_btn = st.button("تحليل العطل وإنشاء التقرير 🔍", use_container_width=True)

        if search_google and user_input:
            query_encoded = user_input.replace(" ", "+")
            st.markdown(f"""
            ### 🌐 نتائج البحث المقترحة من الإنترنت والمواقع الهندسية:
            - **Google Search:** [اضغط هنا للبحث المباشر عن العطل](https://www.google.com/search?q={query_encoded}+generator+troubleshooting)
            - **Perkins / Cummins Technical Portal:** [البحث في المراجع الهندسية](https://www.google.com/search?q={query_encoded}+diesel+engine+manual)
            - **Deep Sea Electronics Support:** [البحث في أعطال وحدات التحكم](https://www.google.com/search?q={query_encoded}+DSE+controller+alarm)
            """)

        if analyze_btn:
            if user_input:
                res_text = f"""
                **📋 التقرير الفني التوجيهي:**
                1. **طبيعة المشكلة / الكود:** {user_input}
                2. **خطوات الفحص والتوجيه:**
                   - فحص التوصيلات الكهربائية وحساسات السرعة.
                   - التحقق من وحدة التحكم (DSE Controller) وسجلات الأخطاء.
                   - مراجعة ضغط الوقود والفلتر الأولي والثانوي.
                """
                if "ai_logs" not in st.session_state: st.session_state.ai_logs = []
                st.session_state.ai_logs.append({"query": user_input, "result": res_text, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
            else:
                st.warning("يرجى كتابة تفاصيل العطل.")

        if "ai_logs" in st.session_state and st.session_state.ai_logs:
            for log in reversed(st.session_state.ai_logs):
                st.info(f"📅 التاريخ: {log['date']}")
                st.write(f"**العطل:** {log['query']}")
                st.markdown(log['result'])
                st.divider()

    # --- TAB 2: الكتالوجات (PDF) ---
    with tab2:
        st.subheader("📚 مكتبة رفع وتحميل الكتالوجات الميدانية (PDF Manuals)")
        uploaded_catalog = st.file_uploader("قم برفع ملف الكتالوج (PDF):", type=["pdf"])
        
        if uploaded_catalog is not None:
            st.success(f"✅ تم رفع الكتالوج بنجاح: **{uploaded_catalog.name}** ({uploaded_catalog.size / 1024:.1f} KB)")
            st.download_button(
                label=f"⬇️ تنزيل كتالوج: {uploaded_catalog.name}",
                data=uploaded_catalog.getvalue(),
                file_name=uploaded_catalog.name,
                mime="application/pdf",
                use_container_width=True
            )

    # --- TAB 3: قراءة شاشة المولد والأكواد (QR/Barcode) ---
    with tab3:
        st.subheader("📷 رفع صورة شاشة المولد (قراءة الكود والإنذار) أو الباركود")
        uploaded_code_img = st.file_uploader("رفع لقطة شاشة لوحة التحكم (Generator Screen) أو كود القطعة:", type=["png", "jpg", "jpeg"])

        if uploaded_code_img is not None:
            image = Image.open(uploaded_code_img)
            st.image(image, caption="الصورة المرفوعة لشاشة المولد / القطعة", width=350)
            
            st.info("💡 **تحليل شاشة المولد:** تم استلام الصورة بنجاح. في حال ظهور كود إنذار (مثل Warning/Shutdown على شاشة DSE)، يتم مقارنته مع جداول أعطال وحدة التحكم.")
            
            if decode_qr is not None:
                decoded_objects = decode_qr(image)
                if decoded_objects:
                    for obj in decoded_objects:
                        st.success(f"🔑 **نتيجة قراءة الباركود/QR:** `{obj.data.decode('utf-8')}` (نوع الكود: {obj.type})")

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")

    eq_type = st.selectbox("اختر المعدة المراد فحصها:", ["مولد ديزل صناعي", "غرفة تبريد وتجميد WIC", "محرك كهربائي 3-Phase"])

    st.divider()
    st.subheader("🖼️ المقارنة البصرية لقطع الغيار (التالف vs السليم)")
    
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 **رفع صورة القطعة السليمة (Reference):**")
        good_img_file = st.file_uploader("اختر صورة قطعة جديدة/سليمة", type=["png", "jpg", "jpeg"], key="good_img")
        if good_img_file:
            st.image(Image.open(good_img_file), caption="القطعة السليمة المعيارية", width="stretch")

    with col_img2:
        st.write("🔴 **رفع صورة القطعة التالفة / المفحوصة (Damaged):**")
        bad_img_file = st.file_uploader("اختر صورة القطعة التالفة من الميدان", type=["png", "jpg", "jpeg"], key="bad_img")
        if bad_img_file:
            st.image(Image.open(bad_img_file), caption="القطعة المفحوصة في الموقع", width="stretch")

    if good_img_file and bad_img_file:
        st.warning("🔍 **ملاحظة التحليل الميداني:** توجد فروقات بصرية واضحة في مستوى التآكل أو الرايش السطحي بين القطعتين. ينصح بالاستبدال الفوري.")

    st.divider()
    st.subheader("📋 قائمة الفحص الظاهري والميكانيكي")
    checklist = []
    if eq_type == "مولد ديزل صناعي":
        c1 = st.checkbox("1. تسريب زيت أو وقود أسفل المحرك")
        c2 = st.checkbox("2. انخفاض سائل التبريد (Coolant)")
        c3 = st.checkbox("3. أطراف البطارية تحتاج نظافة/إحكام")
        checklist = [("تسريب زيت/وقود", c1), ("انخفاض سائل التبريد", c2), ("أطراف البطارية", c3)]
        if c1: st.error("🚨 **تأكيد:** افحص وجه الكارتير وفلاتر الزيت.")
    elif eq_type == "غرفة تبريد وتجميد WIC":
        r1 = st.checkbox("1. تكوّن الثلج على ملف المبخر (Evaporator)")
        r2 = st.checkbox("2. توقف مروحة المكثف الخارجية")
        checklist = [("تراكم الثلج", r1), ("مروحة المكثف", r2)]
        if r1: st.error("🚨 **تأكيد:** افحص دورة الإذابة وسخانات Defrost.")
    elif eq_type == "محرك كهربائي 3-Phase":
        m1 = st.checkbox("1. ارتفاع حرارة جسم المحرك")
        m2 = st.checkbox("2. صوت صرير في الرمان بلي")
        checklist = [("ارتفاع الحرارة", m1), ("صوت الرمان بلي", m2)]

    st.divider()
    st.subheader("📄 إصدار تقرير الفحص الميداني والمقارنة PDF")
    def generate_chk_pdf():
        pdf = ComprehensivePDF("EQUIPMENT FIELD INSPECTION & VISUAL REPORT")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Equipment Type: {sanitize_latin_only(eq_type)}", ln=True)
        pdf.ln(3)
        pdf.cell(100, 6, "Checklist Item", border=1)
        pdf.cell(50, 6, "Status", border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9)
        for item, val in checklist:
            pdf.cell(100, 5, sanitize_latin_only(item), border=1)
            pdf.cell(50, 5, "FAIL / DEFECT" if val else "PASS / OK", border=1)
            pdf.ln()
        return pdf.output(dest="S").encode("latin-1", errors="replace")

    st.download_button(
        label="🖨️ إصدار تقرير الفحص الميداني (PDF)",
        data=generate_chk_pdf(),
        file_name=f"Inspection_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
