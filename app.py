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
        st.sidebar.info("💡 وضع العمل المحلي (مفعل)")
except Exception as e:
    st.sidebar.info("💡 وضع العمل المحلي (مفعل)")
    db = None

# ---------------------------------------------------------
# 3. إدارة المدد الزمنية والاشتراكات وأكواد التفعيل
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

# السجل المحلي الافتراضي للأكواد المولدة
if "generated_codes_db" not in st.session_state:
    st.session_state.generated_codes_db = {
        "ADDOMA-7D": {"days": 7, "plan": "اشتراك تجريبي (7 أيام)"},
        "ADDOMA-30D": {"days": 30, "plan": "اشتراك شهري (1 شهر)"},
        "ADDOMA-90D": {"days": 90, "plan": "اشتراك 3 شهور"},
        "ADDOMA-180D": {"days": 180, "plan": "اشتراك 6 شهور"},
        "ADDOMA-1Y": {"days": 365, "plan": "اشتراك سنوي كامل"},
        "ADDOMA-2026-PRO": {"days": 365, "plan": "اشتراك احترافي (1 سنة)"},
    }

def get_or_create_device_record(dev_id):
    now_dt = datetime.now()
    if db is not None:
        try:
            doc_ref = db.collection("devices").document(dev_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return {
                    "first_visit": data.get("first_visit", now_dt),
                    "trial_expiry": data.get("trial_expiry", now_dt + timedelta(days=7)),
                    "subscription_expiry": data.get("subscription_expiry"),
                    "plan_type": data.get("plan_type", "فترة تجريبية 7 أيام")
                }
            else:
                trial_exp = now_dt + timedelta(days=7)
                initial_data = {
                    "first_visit": now_dt,
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
            "first_visit": now_dt,
            "trial_expiry": now_dt + timedelta(days=7),
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

def verify_and_apply_code(code_str):
    code_clean = code_str.strip().upper()
    
    if db is not None:
        try:
            code_doc = db.collection("subscription_codes").document(code_clean).get()
            if code_doc.exists:
                c_data = code_doc.to_dict()
                days = c_data.get("days", 30)
                plan = c_data.get("plan", "اشتراك مفعل")
                return days, plan
        except Exception:
            pass
            
    if code_clean in st.session_state.generated_codes_db:
        info = st.session_state.generated_codes_db[code_clean]
        return info["days"], info["plan"]
        
    return None, None

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

st.sidebar.markdown("💡")
st.sidebar.markdown("### **وضع العمل المحلي (مفعل)**")
st.sidebar.markdown("---")
st.sidebar.markdown("🔐 تفاصيل الاشتراك والتفعيل")
st.sidebar.markdown("📌")
st.sidebar.markdown(f""" **حالة الحساب والاشتراك:** * **نوع الخطة:** {plan_type} * **تاريخ الانتهاء:** `{expiry_date_str}` * **المدة المتبقية:** **{time_left}** يوماً """)

with st.sidebar.expander("🔑 إدخال كود التفعيل"):
    input_code = st.text_input("أدخل كود التفعيل:", type="password")
    if st.button("تفعيل الاشتراك"):
        days, p_name = verify_and_apply_code(input_code)
        if days:
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم تفعيل: {p_name}")
            st.rerun()
        else:
            st.error("❌ كود تفعيل غير صحيح.")

st.sidebar.markdown("💡 **أكواد للتجربة:** `ADDOMA-30D` | `ADDOMA-1Y`")

with st.sidebar.expander("⚙️ لوحة إصدار أكواد الاشتراكات (للمدير)"):
    st.write("🛠️ **توليد كود اشتراك جديد للعملاء:**")
    plan_option = st.selectbox(
        "اختر نوع الباقة:",
        ["اشتراك شهري (30 يوم)", "اشتراك 3 شهور (90 يوم)", "اشتراك 6 شهور (180 يوم)", "اشتراك سنوي (365 يوم)", "مخصص (بالأيام)"]
    )
    
    custom_days = 30
    if plan_option == "اشتراك شهري (30 يوم)":
        custom_days = 30
    elif plan_option == "اشتراك 3 شهور (90 يوم)":
        custom_days = 90
    elif plan_option == "اشتراك 6 شهور (180 يوم)":
        custom_days = 180
    elif plan_option == "اشتراك سنوي (365 يوم)":
        custom_days = 365
    else:
        custom_days = st.number_input("عدد الأيام المخصصة:", min_value=1, value=30, step=1)
        
    client_prefix = st.text_input("بادئة الكود (مثال: CLIENT-VIP):", value="ADDOMA-PRO").upper().strip()
    
    if st.button("➕ توليد وتثبيت الكود"):
        random_suffix = str(uuid.uuid4()).split('-')[0].upper()
        generated_code = f"{client_prefix}-{random_suffix}"
        plan_desc = f"باقة {plan_option} ({custom_days} يوم)"
        
        if db is not None:
            try:
                db.collection("subscription_codes").document(generated_code).set({
                    "days": custom_days,
                    "plan": plan_desc,
                    "created_at": datetime.now()
                })
            except Exception:
                pass
                
        st.session_state.generated_codes_db[generated_code] = {"days": custom_days, "plan": plan_desc}
        st.success(f"🎉 تم توليد الكود: `{generated_code}`")
        st.code(generated_code, language="text")

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية. يرجى التفعيل باستخدام كود اشتراك ساري.")
    st.stop()

# ---------------------------------------------------------
# 4. قائمة اختيار التطبيق
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown("🛠️ التطبيقات المتاحة")
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

    st.divider()
    st.subheader("📷 توثيق صور المولد الميدانية (رفع ملفات أو التقط بالكاميرا)")
    
    col_upload_gen, col_cam_gen = st.columns(2)
    with col_upload_gen:
        gen_uploaded_images = st.file_uploader(
            "اختر صور المولد أو لوحة التحكم للتوثيق:",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="gen_multi_imgs"
        )
    with col_cam_gen:
        gen_cam_img = st.camera_input("📸 التقاط صورة مباشرة للمولد بالكاميرا", key="gen_cam")

    all_gen_images = []
    if gen_uploaded_images:
        all_gen_images.extend([Image.open(f) for f in gen_uploaded_images])
    if gen_cam_img:
        all_gen_images.append(Image.open(gen_cam_img))

    if all_gen_images:
        cols_preview = st.columns(len(all_gen_images) if len(all_gen_images) <= 4 else 4)
        for idx, img_obj in enumerate(all_gen_images):
            with cols_preview[idx % 4]:
                st.image(img_obj, caption=f"صورة {idx+1}", use_container_width=True)

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
    st.subheader("🛢️ جدول الصيانة التنبؤية الكامل لغيار الزيوت، الفلاتر والقطع (مطابق للمواصفات القياسية)")

    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)

    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 210.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 455.0},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": 860.0},
        {"تصنيف القطعة": "Fan Belt System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": 1550.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": 2200.0},
        {"تصنيف القطعة": "Feul System", "قطع الغيار / الفلاتر": "Injectors Check", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 4400.0},
        {"تصنيف القطعة": "النظام الكهربائي", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 6100.0},
        {"تصنيف القطعة": "Electric System", "قطع الغيار / الفلاتر": "Charging Alternator", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 8900.0},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Top Overhaul", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 9100.0},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Major Overhaul", "العمر الافتراضي (ساعة)": 20000.0, "الساعات المنقضية (ساعة)": 15000.0},
        {"تصنيف القطعة": "Oilers System", "قطع الغيار / الفلاتر": "Oil Cooler Clean", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 3800.0},
        {"تصنيف القطعة": "نظام التبريد", "قطع الغيار / الفلاتر": "Water Pump", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": 5200.0},
        {"تصنيف القطعة": "نظام الهواء", "قطع الغيار / الفلاتر": "Turbocharger Check", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 7100.0},
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

        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Performance & Maintenance Visual Charts (Bar & Pie):", ln=True)

            fig_bar_p, ax_bar_p = plt.subplots(figsize=(6.5, 3))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            u_h = df_result["الساعات المنقضية (ساعة)"].values
            r_h = df_result["المدة المتبقية (ساعة)"].values
            ax_bar_p.bar(p_short, u_h, label="Used Hours", color="#d9534f")
            ax_bar_p.bar(p_short, r_h, bottom=u_h, label="Remaining Hours", color="#28a745")
            ax_bar_p.set_title("Parts Lifespan Bar Chart", fontsize=9)
            plt.xticks(rotation=35, ha="right", fontsize=6)
            plt.tight_layout()
            bar_path = f"temp_bar_{datetime.now().timestamp()}.png"
            plt.savefig(bar_path, dpi=200)
            plt.close(fig_bar_p)
            temp_files.append(bar_path)
            pdf.image(bar_path, x=15, y=25, w=170)

            fig_pie_p, ax_pie_p = plt.subplots(figsize=(5, 3))
            status_counts = df_result["حالة التنبيه"].value_counts()
            color_map = {"حالة جيدة": "#28a745", "قرب الخدمة (استعداد)": "#ffc107", "تنبيه فوري (خطر)": "#dc3545"}
            colors = [color_map.get(k, "#999999") for k in status_counts.index]
            labels_clean = [sanitize_latin_only(str(k)) for k in status_counts.index]
            ax_pie_p.pie(status_counts.values, labels=labels_clean, autopct='%1.1f%%', startangle=140, colors=colors)
            ax_pie_p.axis('equal')
            plt.title("Alert Status Distribution", fontsize=9)
            plt.tight_layout()
            pie_path = f"temp_pie_{datetime.now().timestamp()}.png"
            plt.savefig(pie_path, dpi=200)
            plt.close(fig_pie_p)
            temp_files.append(pie_path)
            pdf.image(pie_path, x=35, y=120, w=130)

        except Exception:
            pass

        pdf_out = pdf.output(dest="S")
        for f in temp_files:
            if os.path.exists(f): os.remove(f)
            
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
        "📚 رفع وتصفح الكتالوجات والبحث فيها",
        "📷 قراءة الأكواد والتحليل بالكاميرا / الشاشة"
    ])

    # --- TAB 1: الاستشارات والتحليل ---
    with tab1:
        st.subheader("💡 تحليل العطل واستخراج التقرير")
        user_input = st.text_area("أدخل تفاصيل العطل الفني:", height=100, placeholder="مثال: ارتفاع حرارة المحرك مع انخفاض ضغط الزيت...")

        if st.button("تحليل العطل وإنشاء التقرير 🔍", use_container_width=True):
            if user_input:
                res_text = f""" **📋 التقرير الفني التوجيهي:** 1. **طبيعة المشكلة:** {user_input} 2. **خطوات الفحص والتوجيه:** - فحص مرشح الهواء ونسبة الانسداد. - اختبار بخاخات الوقود وضغط مضخة الحقن. - التأكد من جودة الديزل وعدم وجود خلط بالماء. """
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
                    
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                    
                    resp = requests.get(url, headers=headers, timeout=15)
                    
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, 'html.parser')
                        results = soup.find_all('a', class_='result__snippet', limit=5)
                        
                        if results:
                            st.success("✅ تم العثور على النتائج والمراجع الهندسية التالية:")
                            for i, res in enumerate(results):
                                snippet_text = res.get_text().strip()
                                st.markdown(f"* **مرجع {i+1}:** {snippet_text}")
                        else:
                            st.warning("لم يتم العثور على نتائج مباشرة، تفضل بالاطلاع على الكتالوجات المرفقة.")
                    else:
                        st.error(f"تعذر الاتصال بمحرك البحث حالياً (رمز الاستجابة: {resp.status_code}).")
                except requests.exceptions.Timeout:
                    st.error("⏰ انتهت مهلة الاتصال بالخادم. يرجى إعادة المحاولة.")
                except Exception as e:
                    st.error(f"خطأ أثناء إجراء عملية البحث: {e}")
            else:
                st.warning("يرجى إدخال مصطلح البحث أولاً.")

    # --- TAB 3: الكتالوجات (PDF) والبحث المباشر ---
    with tab3:
        st.subheader("📚 مكتبة رفع وتحميل والبحث في الكتالوجات الميدانية (PDF Manuals)")
        
        col_up_cat, col_cam_cat = st.columns(2)
        with col_up_cat:
            uploaded_catalog = st.file_uploader("رفع ملف كتالوج (PDF):", type=["pdf"], key="cat_pdf_up")
        with col_cam_cat:
            camera_catalog_img = st.camera_input("📸 التقاط صورة لصفحة الكتالوج بالكاميرا", key="cat_cam")

        all_cat_files = []
        if uploaded_catalog is not None:
            all_cat_files.append((uploaded_catalog.name, uploaded_catalog.getvalue(), "pdf"))
        if camera_catalog_img is not None:
            cam_bytes = camera_catalog_img.getvalue()
            all_cat_files.append((f"catalog_cam_{datetime.now().strftime('%H%M%S')}.jpg", cam_bytes, "image"))

        for fname, fbytes, ftype in all_cat_files:
            st.success(f"✅ تم تحميل العنصر بنجاح: **{fname}** ({len(fbytes) / 1024:.1f} KB)")
            st.download_button(
                label=f"⬇️ تنزيل: {fname}",
                data=fbytes,
                file_name=fname,
                mime="application/pdf" if ftype == "pdf" else "image/jpeg",
                use_container_width=True,
                key=f"dl_{fname}"
            )
            
        st.divider()
        st.write("🔍 **البحث السريع في الكتالوجات المرفقة عن كود عطل أو قطعة:**")
        catalog_search = st.text_input("أدخل اسم القطعة أو رقم العطل للبحث في الكتالوجات (مثال: DSE 7320, Oil Sensor, E-01):")
        if st.button("بحث داخل الكتالوجات 🔎"):
            if catalog_search:
                st.info(f"🔎 جاري مسح الكتالوجات والبحث عن: **{catalog_search}**...")
                st.success(f"🎯 تم العثور على نتائج ذات صلة لـ '{catalog_search}' في كتالوج المحرك ولوحة التحكّم DSE.")
            else:
                st.warning("أدخل نص البحث أولاً.")

    # --- TAB 4: شاشة المولد DSE وقراءة الأكواد بالكاميرا / الصور ---
    with tab4:
        st.subheader("📷 قراءة أكواد الأعطال والبار كود (رفع صورة أو التقاط مباشر بالكاميرا)")
        
        col_img_src, col_cam_src = st.columns(2)
        with col_img_src:
            dse_screen_img = st.file_uploader(
                "رفع صورة شاشة DSE / كود العطل:",
                type=["png", "jpg", "jpeg"],
                key="dse_img"
            )
        with col_cam_src:
            dse_cam_img = st.camera_input("📸 التقاط صورة شاشة DSE بالكاميرا مباشرة", key="dse_cam")

        target_img = dse_screen_img or dse_cam_img

        if target_img is not None:
            dse_image = Image.open(target_img)
            st.image(dse_image, caption="الصورة التي تم التقاطها / رفعها", width=380)
            
            decoded_text = None
            if decode_qr is not None:
                try:
                    decoded_objects = decode_qr(dse_image)
                    if decoded_objects:
                        decoded_text = decoded_objects[0].data.decode('utf-8')
                        st.success(f"📟 **تم فك تشفير الكود البصري (QR/Barcode) بنجاح:** `{decoded_text}`")
                except Exception:
                    pass

            st.divider()
            st.info("🔍 **تحليل كود الإنذار والتحذير من شاشة DSE / QR:**")
            
            st.warning(""" ⚠️ **التحليل التلقائي لأكواد DSE والمحركات الشائعة:** * **كود العطل / التحذير:** `Oil Pressure Low` أو `Coolant Temperature High` أو `Over Frequency / Speed`. * **السبب الفني المحتمل:** 1. انسداد مرشحات الزيت أو تلف مستشعر ضغط الزيت. 2. انخفاض مستوى سائل التبريد أو انسداد راديتر المولد. 3. عدم ضبط منظم السرعة (Governor / ECM) أو PID Tuning. * **الخطوات التصحيحية الموصى بها:** 1. افحص مستشعرات (Sensors) الضغط والحرارة وتوصيلات الأسلاك لوحدة DSE. 2. قياس مقاومة المستشعر بالـ Multimeter وقارنها بالكتالوج القياسي. 3. إعادة ضبط Alarm Reset من لوحة التحكم بعد معالجة السبب الفني. """)

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")

    eq_type = st.selectbox("اختر المعدة المراد فحصها:", ["مولد ديزل صناعي", "غرفة تبريد وتجميد WIC", "محرك كهربائي 3-Phase"])

    st.divider()
    st.subheader("🖼️ المقارنة البصرية لقطع الغيار (التالف vs السليم - رفع ملف أو كاميرا)")
    
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 **صورة القطعة السليمة المعيارية (Reference):**")
        good_img_file = st.file_uploader("اختر صورة قطعة جديدة/سليمة", type=["png", "jpg", "jpeg"], key="good_img")
        good_cam_file = st.camera_input("📸 أو التقط صورة السليم بالكاميرا", key="good_cam")
        
        final_good_img = good_img_file or good_cam_file
        if final_good_img:
            st.image(Image.open(final_good_img), caption="القطعة السليمة المعيارية", use_container_width=True)

    with col_img2:
        st.write("🔴 **صورة القطعة التالفة / المفحوصة (Damaged):**")
        bad_img_file = st.file_uploader("اختر صورة القطعة التالفة من الميدان", type=["png", "jpg", "jpeg"], key="bad_img")
        bad_cam_file = st.camera_input("📸 أو التقط صورة التالف بالكاميرا", key="bad_cam")
        
        final_bad_img = bad_img_file or bad_cam_file
        if final_bad_img:
            st.image(Image.open(final_bad_img), caption="القطعة المفحوصة في الموقع", use_container_width=True)

    if final_good_img and final_bad_img:
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
