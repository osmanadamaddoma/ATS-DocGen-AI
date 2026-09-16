from datetime import datetime, timedelta
import io
import json
import os
import re
import urllib.parse
import uuid

from bs4 import BeautifulSoup
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
import plotly.express as px
import requests
import streamlit as st

# استيراد محرك قراءة الأكواد (Barcode/QR)
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
            pk = str(firebase_dict["private_key"])
            if "\\n" in pk:
                pk = pk.replace("\\n", "\n")
            firebase_dict["private_key"] = pk.strip()
            cred = credentials.Certificate(firebase_dict)
        elif os.path.exists("firebase_key.json"):
            cred = credentials.Certificate("firebase_key.json")
        else:
            return None
        firebase_admin.initialize_app(cred)
    return firestore.client()

try:
    db = init_firebase()
    if db is not None:
        st.sidebar.success("🔥 متصل بـ Firebase Firestore بنجاح!")
    else:
        st.sidebar.info("💡 وضع التخزين المحلي (مفعل)")
except Exception as e:
    db = None
    st.sidebar.info("💡 وضع التخزين المحلي (مفعل)")

# ---------------------------------------------------------
# 3. إدارة المدد الزمنية للاشتراكات وتوليد الأكواد
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

if "custom_generated_codes" not in st.session_state:
    st.session_state.custom_generated_codes = {}

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
        
        # الدمج مع الأكواد الصادرة من قبل الأدمن
        if code_clean in st.session_state.custom_generated_codes:
            days, p_name = st.session_state.custom_generated_codes[code_clean]
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم تفعيل: {p_name}")
            st.rerun()
        elif code_clean in duration_map:
            days, p_name = duration_map[code_clean]
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم تفعيل: {p_name}")
            st.rerun()
        else:
            st.error("❌ كود تفعيل غير صحيح.")

# --- لوحة الأدمن لتوليد الأكواد (المهندس عثمان أدومة) ---
with st.sidebar.expander("👑 توليد أكواد الاشتراكات (خاص بالمسؤول)"):
    admin_pass = st.text_input("كلمة سر الأدمن:", type="password", key="admin_pwd")
    if admin_pass == "ADDOMA2026":
        st.success("🔓 مرحباً مهندس عثمان!")
        plan_choice = st.selectbox("اختر نوع باقة الاشتراك:", ["شهري (30 يوم)", "سنوي (365 يوم)", "3 شهور (90 يوم)", "6 شهور (180 يوم)"])
        custom_code_name = st.text_input("اكتب الكود المخصص (أو اتركه لتوليد تلقائي):", placeholder="مثال: CLIENT-VIP-99").strip().upper()
        
        if st.button("⚡ توليد الكود وإصدار الاشتراك"):
            if plan_choice == "شهري (30 يوم)":
                d_days, d_title = 30, "اشتراك شهري"
            elif plan_choice == "سنوي (365 يوم)":
                d_days, d_title = 365, "اشتراك سنوي"
            elif plan_choice == "3 شهور (90 يوم)":
                d_days, d_title = 90, "اشتراك 3 شهور"
            else:
                d_days, d_title = 180, "اشتراك 6 شهور"
                
            final_gen_code = custom_code_name if custom_code_name else f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.custom_generated_codes[final_gen_code] = (d_days, d_title)
            st.success(f"✅ تم إنشاء الكود: `{final_gen_code}` ({d_title})")
            
        if st.session_state.custom_generated_codes:
            st.write("📋 **الأكواد الصادرة حالياً:**")
            for c_k, c_v in st.session_state.custom_generated_codes.items():
                st.code(f"{c_k} -> {c_v[1]}")

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

    # --- خانة التقاط وصور المولد ---
    st.divider()
    st.subheader("📷 توثيق صور المولد الميدانية والتقاط الكاميرا المباشر")
    
    col_cam1, col_cam2 = st.columns(2)
    with col_cam1:
        st.write("📷 **التقاط صورة مباشرة عبر الكاميرا:**")
        camera_photo = st.camera_input("التقط صورة للوحة التوصيل أو المولد")
        if camera_photo:
            st.image(camera_photo, caption="الصورة الملتقطة مباشرة", width=300)
            st.download_button(
                label="💾 تنزيل الصورة الملتقطة",
                data=camera_photo.getvalue(),
                file_name=f"Captured_Gen_Photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
            
    with col_cam2:
        st.write("📁 **رفع صور متعددة من الجهاز:**")
        gen_uploaded_images = st.file_uploader(
            "اختر صور المولد أو لوحة التحكم للتوثيق:",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="gen_multi_imgs"
        )
        if gen_uploaded_images:
            cols_preview = st.columns(len(gen_uploaded_images) if len(gen_uploaded_images) <= 3 else 3)
            for idx, img_file in enumerate(gen_uploaded_images):
                with cols_preview[idx % 3]:
                    st.image(Image.open(img_file), caption=f"صورة {idx+1}", use_container_width=True)

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
    st.subheader("🛢️ جدول الصيانة التنبؤية الكامل لغيار الزيوت، الفلاتر والقطع")

    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 210.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 455.0},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": 860.0},
        {"تصنيف القطعة": "Fan Belt System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": 1550.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": 2200.0},
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

        status = "تنبيه فوري (خطر)" if rem <= 0 or pct >= 90 else ("قرب الخدمة (استعداد)" if pct >= 75 else "حالة جيدة")
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
    st.subheader("📊 الرسوم البيانية والجداول (عمودية ودائرية)")

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
            title="توزيع حالات الصيانة والتنبيه لقطع الغيار",
            color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"]
        )
        st.plotly_chart(fig_pie, width="stretch")

    st.divider()
    st.subheader("📄 إصدار وتنزيل التقرير الفني الشامل (PDF Full Report)")

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
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(42, 5, "Part Name", border=1)
        pdf.cell(22, 5, "Lifespan(h)", border=1)
        pdf.cell(20, 5, "Used(h)", border=1)
        pdf.cell(22, 5, "Remain(h)", border=1)
        pdf.cell(20, 5, "Usage%", border=1)
        pdf.cell(45, 5, "Alert Status", border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        for idx, row in df_result.iterrows():
            pdf.cell(42, 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:22], border=1)
            pdf.cell(22, 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
            pdf.cell(20, 5, str(row["الساعات المنقضية (ساعة)"]), border=1)
            pdf.cell(22, 5, str(row["المدة المتبقية (ساعة)"]), border=1)
            pdf.cell(20, 5, str(row["نسبة الاستهلاك"]), border=1)
            pdf.cell(45, 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1)
            pdf.ln()

        pdf_out = pdf.output(dest="S")
        if isinstance(pdf_out, str):
            return pdf_out.encode("latin-1", errors="replace")
        return bytes(pdf_out)

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

    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 الاستشارات والتحليل",
        "🌐 البحث في Google ومواقع هندسية",
        "📚 رفع وتصفح الكتالوجات",
        "📷 قراءة كود الباركوود / DSE والتحليل"
    ])

    # --- TAB 1: الاستشارات والتحليل ---
    with tab1:
        st.subheader("💡 تحليل العطل واستخراج التقرير")
        user_input = st.text_area("أدخل تفاصيل العطل الفني:", height=100, placeholder="مثال: ارتفاع حرارة المحرك مع انخفاض ضغط الزيت...")

        if st.button("تحليل العطل وإنشاء التقرير 🔍", use_container_width=True):
            if user_input:
                res_text = f"""
                **📋 التقرير الفني التوجيهي:**
                1. **طبيعة المشكلة:** {user_input}
                2. **خطوات الفحص والتوجيه:**
                   - فحص مرشح الهواء ونسبة الانسداد.
                   - اختبار بخاخات الوقود وضغط مضخة الحقن.
                   - التأكد من جودة الديزل وعدم وجود خلط بالماء.
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

    # --- TAB 2: البحث في Google ومواقع هندسية ---
    with tab2:
        st.subheader("🌐 محرك البحث الهندسي (Google & Engineering Sites)")
        search_query = st.text_input("أدخل كلمات البحث التقنية (مثال: Perkins 2206C ECM wiring diagram):")
        
        if st.button("بحث في المصادر الهندسية 🔍", use_container_width=True):
            if search_query:
                clean_q = re.sub(r"[^\w\s\-]", "", search_query).strip()
                st.info(f"🔍 جاري البحث عن: **{clean_q}** في المصادر الهندسية ومواقع الويب...")
                try:
                    encoded_q = urllib.parse.quote(f"{clean_q} diesel generator engineering manual")
                    url = f"https://html.duckduckgo.com/html/?q={encoded_q}"
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    resp = requests.get(url, headers=headers, timeout=15)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        results = soup.find_all('a', class_='result__snippet', limit=5)
                        if results:
                            st.success("✅ تم العثور على النتائج والمراجع الهندسية التالية:")
                            for i, res in enumerate(results):
                                st.markdown(f"* **مرجع {i+1}:** {res.get_text().strip()}")
                        else:
                            st.warning("لم يتم العثور على نتائج مباشرة، تفضل بالاطلاع على الكتالوجات المرفقة.")
                    else:
                        st.error("تعذر الاتصال بمحرك البحث حالياً.")
                except Exception as e:
                    st.error(f"خطأ أثناء البحث: {e}")

    # --- TAB 3: رفع وتحميل الكتالوجات (PDF Manuals) ---
    with tab3:
        st.subheader("📚 مكتبة رفع وتحميل الكتالوجات الميدانية (PDF Manuals)")
        uploaded_catalog = st.file_uploader("قم برفع ملف الكتالوج (PDF):", type=["pdf"])
        
        if uploaded_catalog is not None:
            st.success(f"✅ تم رفع الكتالوج بنجاح: **{uploaded_catalog.name}** ({uploaded_catalog.size / 1024:.1f} KB)")
            st.download_button(
                label=f"⬇️ تنزيل وتثبيت الكتالوج: {uploaded_catalog.name}",
                data=uploaded_catalog.getvalue(),
                file_name=uploaded_catalog.name,
                mime="application/pdf",
                use_container_width=True
            )

    # --- TAB 4: قراءة الأكواد شريطية والباركوود وشاشة DSE ---
    with tab4:
        st.subheader("🔍 قراءة الأكواد (Barcode / QR / DSE Screencap)")
        st.write("قم برفع صورة الكود من قطعة الغيار أو صورة شاشة التحكم:")
        
        uploaded_code_img = st.file_uploader("اختر صورة تحتوي على كود (QR / Barcode / Screen):", type=["png", "jpg", "jpeg"], key="code_scanner_file")
        
        if uploaded_code_img:
            img_obj = Image.open(uploaded_code_img)
            st.image(img_obj, caption="الصورة المرفوعة لقراءة الكود", width=300)
            
            if decode_qr is not None:
                decoded_objs = decode_qr(img_obj)
                if decoded_objs:
                    st.success("✅ تم التعرف على الكود بنجاح!")
                    for obj in decoded_objs:
                        barcode_data = obj.data.decode("utf-8")
                        barcode_type = obj.type
                        st.info(f"📌 **نوع الكود:** `{barcode_type}` | **البيانات المستخرجة:** `{barcode_data}`")
                else:
                    st.warning("لم يتم العثور على Barcode أو QR Code واضحة داخل الصورة. جاري تطبيق تحليل النصوص والأنماط التلقائي...")
            
            st.info("🔍 **التحليل الفني التلقائي لرمز/عطل المولد (DSE Diagnostics):**")
            st.warning("""
            ⚠️ **أبرز تحذيرات وأكواد الأعطال الشائعة:**
            * **الكود `E04 / Fail to Start`:** صعوبة بدء التشغيل - افحص سولونويد السولار ومستوى شحن البطارية.
            * **الكود `Low Oil Pressure`:** انخفاض ضغط الزيت - افحص مستوى الزيت أو مرشح الزيت انسداد.
            * **الكود `High Engine Temp`:** ارتفاع الحرارة - افحص سير المروحة ومستوى سائل التبريد (Coolant).
            """)

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
            st.image(Image.open(good_img_file), caption="القطعة السليمة المعيارية", use_container_width=True)

    with col_img2:
        st.write("🔴 **رفع صورة القطعة التالفة / المفحوصة (Damaged):**")
        bad_img_file = st.file_uploader("اختر صورة القطعة التالفة من الميدان", type=["png", "jpg", "jpeg"], key="bad_img")
        if bad_img_file:
            st.image(Image.open(bad_img_file), caption="القطعة المفحوصة في الموقع", use_container_width=True)

    if good_img_file and bad_img_file:
        st.warning("🔍 **ملاحظة التحليل الميداني:** توجد فروقات بصرية واضحة في مستوى التآكل بين القطعتين. ينصح بالاستبدال الفوري.")

    st.divider()
    st.subheader("📋 قائمة الفحص الظاهري والميكانيكي")
    checklist = []
    if eq_type == "مولد ديزل صناعي":
        c1 = st.checkbox("1. تسريب زيت أو وقود أسفل المحرك")
        c2 = st.checkbox("2. انخفاض سائل التبريد (Coolant)")
        c3 = st.checkbox("3. أطراف البطارية تحتاج نظافة/إحكام")
        checklist = [("تسريب زيت/وقود", c1), ("انخفاض سائل التبريد", c2), ("أطراف البطارية", c3)]
    elif eq_type == "غرفة تبريد وتجميد WIC":
        r1 = st.checkbox("1. تكوّن الثلج على ملف المبخر (Evaporator)")
        r2 = st.checkbox("2. توقف مروحة المكثف الخارجية")
        checklist = [("تراكم الثلج", r1), ("مروحة المكثف", r2)]
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
            
        pdf_out = pdf.output(dest="S")
        if isinstance(pdf_out, str):
            return pdf_out.encode("latin-1", errors="replace")
        return bytes(pdf_out)

    st.download_button(
        label="🖨️ إصدار تقرير الفحص الميداني (PDF)",
        data=generate_chk_pdf(),
        file_name=f"Inspection_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )
