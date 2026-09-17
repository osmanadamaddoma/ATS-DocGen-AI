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
# 1. قاعدة بيانات العملاء الثابتة (من المساعد الذكي)
# ---------------------------------------------------------
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (الدومة للخدمات التجارية)",
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
    "CLIENT-Y-992": {
        "name": "مصانع الحديد والصلب الوطنية",
        "plan": "سنوي (Yearly)",
        "start_date": "2026-03-15",
        "duration_days": 365,
    },
}

# ---------------------------------------------------------
# 2. دالة تنظيف النصوص ومحرك تقارير PDF
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
# 3. تهيئة الاتصال بـ Firebase Firestore
# ---------------------------------------------------------
@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        try:
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
        except Exception:
            return None
    try:
        return firestore.client()
    except:
        return None

db = init_firebase()

# ---------------------------------------------------------
# 4. إدارة المدد الزمنية والاشتراكات وأكواد التفعيل الموحدة
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

# السجل المحلي الافتراضي للأكواد المولدة (الديناميكية)
if "generated_codes_db" not in st.session_state:
    st.session_state.generated_codes_db = {
        "ADDOMA-7D": {"days": 7, "plan": "اشتراك تجريبي (7 أيام)"},
        "ADDOMA-30D": {"days": 30, "plan": "اشتراك شهري (1 شهر)"},
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
                    "plan_type": data.get("plan_type", "فترة تجريبية 7 أيام"),
                    "client_name": data.get("client_name", "زائر (Visitor)")
                }
            else:
                trial_exp = now_dt + timedelta(days=7)
                initial_data = {
                    "first_visit": now_dt,
                    "trial_expiry": trial_exp,
                    "subscription_expiry": None,
                    "plan_type": "فترة تجريبية 7 أيام",
                    "client_name": "زائر (Visitor)"
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
            "plan_type": "فترة تجريبية 7 أيام",
            "client_name": "زائر (Visitor)"
        }
    return st.session_state.mock_device_db

def update_device_subscription(dev_id, sub_expiry, plan_name, client_name="زائر مفعل"):
    if db is not None:
        try:
            doc_ref = db.collection("devices").document(dev_id)
            doc_ref.update({
                "subscription_expiry": sub_expiry,
                "plan_type": plan_name,
                "client_name": client_name
            })
        except Exception:
            pass
    if "mock_device_db" in st.session_state:
        st.session_state.mock_device_db["subscription_expiry"] = sub_expiry
        st.session_state.mock_device_db["plan_type"] = plan_name
        st.session_state.mock_device_db["client_name"] = client_name

def verify_and_apply_code(code_str):
    code_clean = code_str.strip().upper()
    
    # 1. فحص قاعدة بيانات العملاء الثابتة أولاً (CLIENTS_DATABASE)
    if code_clean in CLIENTS_DATABASE:
        data = CLIENTS_DATABASE[code_clean]
        start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d")
        expiry_dt = start_dt + timedelta(days=data["duration_days"])
        if datetime.now() <= expiry_dt:
            return expiry_dt, data["plan"], data["name"]
        else:
            return None, "منتهي الصلاحية", data["name"]

    # 2. فحص الأكواد السحابية (Firebase)
    if db is not None:
        try:
            code_doc = db.collection("subscription_codes").document(code_clean).get()
            if code_doc.exists:
                c_data = code_doc.to_dict()
                days = c_data.get("days", 30)
                plan = c_data.get("plan", "اشتراك مفعل")
                return datetime.now() + timedelta(days=days), plan, "عميل مفعل (سحابي)"
        except Exception:
            pass
            
    # 3. فحص الأكواد المحلية (Session State)
    if code_clean in st.session_state.generated_codes_db:
        info = st.session_state.generated_codes_db[code_clean]
        return datetime.now() + timedelta(days=info["days"]), info["plan"], "عميل مفعل (محلي)"
        
    return None, None, None

user_record = get_or_create_device_record(device_id)
now = datetime.now()

trial_exp = user_record.get("trial_expiry")
sub_exp = user_record.get("subscription_expiry")
current_client_name = user_record.get("client_name", "زائر (Visitor)")

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

# الشريط الجانبي (Sidebar)
st.sidebar.header("🔐 بوابة التفعيل والاشتراكات")
st.sidebar.markdown(f"**👤 اسم العميل:** {current_client_name}")
st.sidebar.markdown(f"**📦 نوع الباقة:** {plan_type}")
st.sidebar.markdown(f"⏳ **المتبقي:** {time_left} يوم (ينتهي في {expiry_date_str})")

if db is not None:
    st.sidebar.success("🔥 متصل بـ السحابة بنجاح!")
else:
    st.sidebar.info("💡 وضع العمل المحلي (مفعل)")

with st.sidebar.expander("🔑 إدخال كود التفعيل للعميل"):
    input_code = st.text_input("أدخل كود التفعيل:", type="password")
    if st.button("تحقق وتفعيل"):
        new_exp, p_name, c_name = verify_and_apply_code(input_code)
        if new_exp:
            update_device_subscription(device_id, new_exp, p_name, c_name)
            st.success(f"✅ تم تفعيل اشتراك العميل: {c_name}")
            st.rerun()
        elif p_name == "منتهي الصلاحية":
            st.error(f"❌ انتهت صلاحية اشتراك العميل ({c_name}).")
        else:
            st.error("❌ كود التفعيل غير صحيح.")

with st.sidebar.expander("⚙️ لوحة إصدار أكواد الاشتراكات (للمدير)"):
    plan_option = st.selectbox(
        "اختر نوع الباقة:",
        ["اشتراك شهري (30 يوم)", "اشتراك سنوي (365 يوم)", "مخصص (بالأيام)"]
    )
    custom_days = 30 if "شهري" in plan_option else (365 if "سنوي" in plan_option else st.number_input("عدد الأيام:", min_value=1, value=30))
    client_prefix = st.text_input("بادئة الكود:", value="ADDOMA-PRO").upper().strip()
    
    if st.button("➕ توليد الكود"):
        random_suffix = str(uuid.uuid4()).split('-')[0].upper()
        generated_code = f"{client_prefix}-{random_suffix}"
        plan_desc = f"باقة {plan_option} ({custom_days} يوم)"
        
        if db is not None:
            try:
                db.collection("subscription_codes").document(generated_code).set({
                    "days": custom_days, "plan": plan_desc, "created_at": datetime.now()
                })
            except: pass
        st.session_state.generated_codes_db[generated_code] = {"days": custom_days, "plan": plan_desc}
        st.success(f"🎉 الكود: `{generated_code}`")

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** انتهت صلاحية الاشتراك. يرجى إدخال كود اشتراك ساري في الشريط الجانبي.")
    st.stop()

# ---------------------------------------------------------
# 5. قائمة التطبيقات المركزية
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown("🛠️ **التطبيقات الهندسية المتاحة**")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية",
        "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)"
    ]
)

st.info(f"🔹 **الجلسة الحالية:** {current_client_name} | **الاشتراك:** {plan_type} | **الوصول:** مسموح ✅")

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية، الرسوم البيانية والتقرير الشامل
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    col_v1, col_v2 = st.sidebar.columns(2)
    v_min = col_v1.number_input("أدنى جهد", value=380.0, step=5.0)
    v_max = col_v2.number_input("أقصى جهد", value=420.0, step=5.0)

    col_f1, col_f2 = st.sidebar.columns(2)
    f_min = col_f1.number_input("أدنى تردد", value=48.0, step=0.5)
    f_max = col_f2.number_input("أقصى تردد", value=52.0, step=0.5)

    temp_max_limit = st.sidebar.number_input("أقصى حرارة (°C)", value=90.0, step=1.0)
    amp_max_limit = st.sidebar.number_input("أقصى تيار (A)", value=400.0, step=10.0)

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
        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("التشغيل الحالي", f"{run_hours} hrs")
    col2.metric("الساعات المستهدفة", f"{future_run_hours} hrs")
    col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
    col4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("حرارة المحرك", f"{coolant_temp} °C")
    col6.metric("ضغط الزيت", f"{oil_press} Bar")
    col7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
    col8.metric("التيار / PF", f"{amperes}A | {pf}")

    st.divider()
    range_alarms = []
    if voltage < v_min or voltage > v_max: range_alarms.append(f"الجهد ({voltage}V) خارج النطاق المسموح.")
    if freq < f_min or freq > f_max: range_alarms.append(f"التردد ({freq}Hz) خارج النطاق المسموح.")
    if coolant_temp > temp_max_limit: range_alarms.append(f"حرارة المحرك مرتفعة ({coolant_temp}°C).")
    if amperes > amp_max_limit: range_alarms.append(f"تيار زائد ({amperes}A).")

    if range_alarms:
        for alarm in range_alarms: st.error(f"🔴 {alarm}")
    else:
        st.success("🟢 جميع المؤشرات التشغيلية ضمن الحدود الآمنة.")

    st.divider()
    st.subheader("🛢️ جدول الصيانة التنبؤية لقطع الغيار")
    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    
    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 210.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": 2200.0},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0
        status = "تنبيه فوري (خطر)" if rem <= 0 or pct >= 90 else ("قرب الخدمة" if pct >= 75 else "حالة جيدة")
        
        processed_rows.append({
            "قطع الغيار": row.get("قطع الغيار / الفلاتر"),
            "المتبقي": max(0.0, rem),
            "الاستهلاك": f"{pct:.0f}%",
            "الحالة": status
        })

    df_result = pd.DataFrame(processed_rows)
    st.dataframe(df_result, use_container_width=True)

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات وقراءة الأكواد
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي لتحليل أكواد الأعطال")

    tab1, tab2, tab3 = st.tabs([
        "💬 تحليل الأعطال (AI)", 
        "📚 الكتالوجات (PDF)", 
        "📷 قراءة شاشة DSE"
    ])

    with tab1:
        st.subheader("💡 نافذة تحليل أكواد الأعطال والاستشارات الهندسية")
        fault_code_input = st.text_area("أدخل كود العطل أو وصف المشكلة (مثلاً: DSE 8610 Error - Low Oil Pressure):", height=100)

        if st.button("تحليـل العطل بالذكاء الاصطناعي ✨", use_container_width=True):
            if fault_code_input:
                st.success(f"🌟 جارٍ معالجة وتحليل الطلب للعميل (**{current_client_name}**)...")
                st.markdown(f"### 📋 تقرير التشخيص الفوري للكود: `{fault_code_input}`")
                st.markdown("""
                * **الوصف الفني المحتمل:** انقطاع في إشارة التحكم، أو قراءة حرجة مسجلة بوحدة التحكم.
                * **الخطوات التصحيحية المقترحة:**
                  1. مطابقة الكود مع صفحة التشخيص في الكتالوج المعياري.
                  2. فحص أطراف التوصيل (Wiring) وحالة الحساسات.
                  3. إعادة ضبط (Reset) وحدة التحكم والتحقق من التغذية الكهربائية.
                """)
            else:
                st.warning("يرجى كتابة تفاصيل العطل.")

    with tab2:
        st.subheader("📚 رفع وتصفح الكتالوجات الميدانية (PDF Manuals)")
        manual_file = st.file_uploader("رفع الكتالوج اليدوي (Manual PDF)", type=["pdf"])
        if manual_file is not None:
            st.success(f"✅ تم تحميل الكتالوج بنجاح: **{manual_file.name}**")
            st.info("سيعتمد المساعد الذكي على هذا الملف في تحليلاته القادمة ضمن الجلسة.")

    with tab3:
        st.subheader("📷 قراءة أكواد الأعطال من شاشة المولد")
        fault_image = st.file_uploader("رفع صورة العطل من الشاشة", type=["png", "jpg", "jpeg"])
        if fault_image is not None:
            st.image(fault_image, caption="الصورة المرفوعة", width=400)
            st.info("🔍 تحليل أولي: تأكد من مراجعة قيم (Pressure / Temperature) الظاهرة على الشاشة ومطابقتها.")

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")

    eq_type = st.selectbox("اختر المعدة المراد فحصها:", ["مولد ديزل صناعي", "غرفة تبريد وتجميد WIC", "محرك كهربائي 3-Phase"])
    st.divider()
    
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 **القطعة السليمة المعيارية (Reference):**")
        good_img_file = st.file_uploader("اختر صورة قطعة جديدة", type=["png", "jpg", "jpeg"], key="good_img")
        if good_img_file: st.image(Image.open(good_img_file), use_container_width=True)

    with col_img2:
        st.write("🔴 **القطعة المفحوصة في الموقع (Damaged):**")
        bad_img_file = st.file_uploader("اختر صورة القطعة التالفة", type=["png", "jpg", "jpeg"], key="bad_img")
        if bad_img_file: st.image(Image.open(bad_img_file), use_container_width=True)

    st.subheader("📋 قائمة الفحص الظاهري والميكانيكي")
    if eq_type == "مولد ديزل صناعي":
        c1 = st.checkbox("تسريب زيت أو وقود أسفل المحرك")
        c2 = st.checkbox("انخفاض سائل التبريد (Coolant)")
        if c1: st.error("🚨 **تنبيه:** افحص وجه الكارتير وفلاتر الزيت.")
    elif eq_type == "غرفة تبريد وتجميد WIC":
        r1 = st.checkbox("تكوّن الثلج على ملف المبخر (Evaporator)")
        if r1: st.error("🚨 **تنبيه:** افحص دورة الإذابة وسخانات Defrost.")
