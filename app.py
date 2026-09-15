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

# ---------------------------------------------------------
# 0. إعدادات الصفحة الرئيسية
# ---------------------------------------------------------
st.set_page_config(
    page_title="المجمع الصناعي الشامل - الصيانة والفحص والمساعد الذكي",
    layout="wide",
)

# ---------------------------------------------------------
# 1. تهيئة الاتصال بـ Firebase Firestore
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
# 2. إدارة التفعيل والاشتراكات السحابية
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

def verify_and_apply_activation_code(code_str, dev_id):
    code_str = code_str.strip().upper()
    now = datetime.now()
    
    default_codes = {
        "ADDOMA-2026-PRO": {"days": 365, "name": "اشتراك سنوي (Yearly - 1 Year)"},
        "CLIENT-M-30D": {"days": 30, "name": "اشتراك شهري (Monthly - 30 Days)"},
        "TRIAL-EXT-7D": {"days": 7, "name": "تمديد تجريبي (7 Days Extension)"},
    }
    
    if code_str in default_codes:
        cfg = default_codes[code_str]
        expiry = now + timedelta(days=cfg["days"])
        update_device_subscription(dev_id, expiry, cfg["name"])
        return True, f"✅ تم تفعيل الاشتراك بنجاح: {cfg['name']}"
        
    return False, "❌ كود التفعيل غير صحيح."

user_record = get_or_create_device_record(device_id)
now = datetime.now()

trial_exp = user_record.get("trial_expiry")
sub_exp = user_record.get("subscription_expiry")

if hasattr(trial_exp, "timestamp"):
    trial_exp = datetime.fromtimestamp(trial_exp.timestamp())
if sub_exp and hasattr(sub_exp, "timestamp"):
    sub_exp = datetime.fromtimestamp(sub_exp.timestamp())

is_sub_active = sub_exp and now < sub_exp
is_trial_active = trial_exp and now < trial_exp

if is_sub_active:
    time_left = (sub_exp - now).days
    access_status = "paid"
    plan_type = user_record.get("plan_type", "اشتراك مدفوع")
elif is_trial_active:
    time_left = (trial_exp - now).days
    access_status = "trial"
    plan_type = "فترة تجريبية مجانية (7 أيام)"
else:
    time_left = 0
    access_status = "expired"
    plan_type = "منتهي الصلاحية"

client_name = f"مستخدم جهاز ({device_id[:8]})"

st.sidebar.header("🔐 بوابة التفعيل")
input_code = st.sidebar.text_input("كود التفعيل:", type="password")
if st.sidebar.button("تفعيل الكود"):
    if input_code:
        success, msg = verify_and_apply_activation_code(input_code, device_id)
        if success:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية. استخدم الكود `ADDOMA-2026-PRO` لتفعيل الوصول.")
    st.stop()

# ---------------------------------------------------------
# 3. القائمة الرئيسية للتنقل بين التطبيقات الثلاثة
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("🛠️ قائمة التطبيقات المتاحة")
selected_app = st.sidebar.radio(
    "اختر التطبيق للعمل عليه:",
    [
        "⚙️ نظام الصيانة التنبؤية والمولدات",
        "🤖 المساعد الذكي لتقارير الصيانة والتوجيه",
        "🔍 نظام فحص المعدات وشجرة التشخيص"
    ]
)
st.sidebar.divider()

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والمولدات
# =========================================================
if selected_app == "⚙️ نظام الصيانة التنبؤية والمولدات":
    st.title("⚙️ نظام الصيانة التنبؤية والتقارير الشاملة للمولدات الصناعية")
    
    col_v1, col_v2 = st.sidebar.columns(2)
    v_min = col_v1.number_input("أدنى جهد (V Min)", value=380.0, step=5.0)
    v_max = col_v2.number_input("أقصى جهد (V Max)", value=420.0, step=5.0)

    col_f1, col_f2 = st.sidebar.columns(2)
    f_min = col_f1.number_input("أدنى تردد (Hz Min)", value=48.0, step=0.5)
    f_max = col_f2.number_input("أقصى تردد (Hz Max)", value=52.0, step=0.5)

    temp_max_limit = st.sidebar.number_input("أقصى حرارة (°C)", value=90.0, step=1.0)
    amp_max_limit = st.sidebar.number_input("أقصى تيار (A Max)", value=400.0, step=10.0)

    with st.sidebar.form("generator_comprehensive_form"):
        st.subheader("مدخلات التشغيل")
        gen_model = st.text_input("طراز / اسم المولد", value="Perkins 410 kVA - DSE 7320")
        run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=700.0, step=10.0)
        future_run_hours = st.number_input("ساعات التشغيل المستهدفة القادمة", min_value=0.0, value=940.0, step=10.0)
        gen_kw = st.number_input("سعة المولد (kW)", min_value=5.0, value=410.0, step=10.0)
        load_kw = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=50.0, step=10.0)
        ambient_temp = st.number_input("الحرارة المحيطة (°C)", value=43.0, step=1.0)

        coolant_temp = st.number_input("حرارة سائل التبريد (°C)", value=85.0)
        oil_press = st.number_input("ضغط الزيت (Bar)", value=2.5)
        vibration = st.number_input("مستوى الاهتزاز (mm/s)", value=2.2)

        voltage = st.number_input("الجهد (V)", value=400.0)
        freq = st.number_input("التردد (Hz)", value=50.0)
        amperes = st.number_input("التيار (A)", value=118.0)
        pf = st.number_input("معامل القدرة (PF)", value=0.85)

        last_oil_change_hours = st.number_input("ساعات آخر غيار زيت", value=460.0, step=10.0)
        oil_change_interval = st.number_input("فترة غيار الزيت القياسية (ساعة)", value=250.0, step=50.0)

        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    uploaded_image = st.sidebar.file_uploader("رفع صورة المولد:", type=["png", "jpg", "jpeg"])

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
    if voltage < v_min or voltage > v_max: range_alarms.append(f"الجهد خارج النطاق: {voltage}V")
    if freq < f_min or freq > f_max: range_alarms.append(f"التردد خارج النطاق: {freq}Hz")
    if coolant_temp > temp_max_limit: range_alarms.append(f"ارتفاع حرارة المحرك: {coolant_temp}°C")
    if amperes > amp_max_limit: range_alarms.append(f"ارتفاع الحمل الكهربائي: {amperes}A")

    if range_alarms:
        for alarm in range_alarms: st.error(f"🔴 {alarm}")
    else:
        st.success("🟢 جميع المؤشرات التشغيلية ضمن النطاق الآمن.")

    st.divider()
    st.subheader("🛢️ جدول خدمة زيت المحرك")
    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)
    hours_until_next_oil_change = oil_change_interval - hours_since_oil_change
    oil_usage_pct = (hours_since_oil_change / oil_change_interval) * 100 if oil_change_interval > 0 else 0

    col_o1, col_o2, col_o3 = st.columns(3)
    col_o1.metric("المدة المنقضية للزيت", f"{hours_since_oil_change:.1f} hrs")
    col_o2.metric("المدة المتبقية للخدمة", f"{max(0.0, hours_until_next_oil_change):.1f} hrs")
    col_o3.metric("نسبة الاستهلاك", f"{oil_usage_pct:.0f}%")

    st.divider()
    st.subheader("🔧 العمر الافتراضي لقطع الغيار والفلاتر")
    base_parts = [
        {"قطع الغيار / الفلاتر": "Engine Oil & Filter", "العمر الافتراضي (ساعة)": float(oil_change_interval), "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"قطع الغيار / الفلاتر": "Fuel Filters", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
    ]
    df_parts = pd.DataFrame(base_parts)
    df_parts["المدة المتبقية (ساعة)"] = df_parts["العمر الافتراضي (ساعة)"] - df_parts["الساعات المنقضية (ساعة)"]
    st.dataframe(df_parts, use_container_width=True)

# =========================================================
# التطبيق 2: المساعد الذكي لتقارير الصيانة والتوجيه
# =========================================================
elif selected_app == "🤖 المساعد الذكي لتقارير الصيانة والتوجيه":
    st.title("🤖 المساعد الذكي لتشخيص الأعطال وإعداد التوجيهات الفنية")
    st.write("أدخل وصف العطـل أو المشكلة الفنية للحصول على خطوات التشخيص والإصلاح الموصى بها.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    user_query = st.text_area("وصف العطل / الاستفسار الفني:", placeholder="مثال: محرك المولد يعمل ولكن لا يولد كهرباء، أو وجود دخان أسود كثيف...")

    col_btn1, col_btn2 = st.columns([1, 4])
    if col_btn1.button("تحليل العطل 🔍", use_container_width=True):
        if user_query:
            # محاكاة تحليل العطل الذكي
            response = ""
            query_lower = user_query.lower()

            if "دخان أسود" in query_lower or "black smoke" in query_lower:
                response = """
                **📋 التقرير التشخيصي: خروج دخان أسود كثيف**
                1. **السبب المحتمل:** انسداد فلتر الهواء، زيادة تزويد الوقود (مشكلة بخاخات)، أو حمل زائد على المحرك.
                2. **خطوات الإصلاح:**
                   - تفقد ونظّف/استبدل فلتر الهواء.
                   - افحص البخاخات ومضخة الوقود (Fuel Injectors & Injection Pump).
                   - التأكد من عدم تجاوز الحمل الكلي للقدرة الاسمية.
                """
            elif "حرارة" in query_lower or "overheat" in query_lower:
                response = """
                **📋 التقرير التشخيصي: ارتفاع درجة حرارة المحرك**
                1. **السبب المحتمل:** نقص سائل التبريد، ارتخاء سير المروحة، أو انسداد الراديتر.
                2. **خطوات الإصلاح:**
                   - افحص مستوى سائل التبريد (Coolant Level).
                   - اضبط شد قشاط/سير المروحة (Fan Belt Tension).
                   - نظف زعانف المشعاع (Radiator Fins) من الأتربة.
                """
            else:
                response = f"""
                **📋 التقرير التشخيصي العام للاستفسار:**
                - **تحليل العطل:** تم استقبال البلاغ للتحقق من: "{user_query}".
                - **الإجراء الموصى به:**
                  1. إجراء الفحص الظاهري والتأكد من لوحة التحكم وقراءات الحساسات.
                  2. مراجعة ضغط الزيت ودرجة الحرارة والجهد الكهربائي.
                  3. التأكد من سلامة التوصيلات الكهربائية والفلاتر.
                """

            st.session_state.chat_history.append({"user": user_query, "assistant": response})
        else:
            st.warning("يرجى كتابة وصف العطل أولاً.")

    st.divider()
    st.subheader("📜 سجل التشخيص والاستشارات السابقة")
    for chat in reversed(st.session_state.chat_history):
        st.chat_message("user").write(chat["user"])
        st.chat_message("assistant").write(chat["assistant"])

# =========================================================
# التطبيق 3: نظام فحص المعدات وشجرة التشخيص
# =========================================================
elif selected_app == "🔍 نظام فحص المعدات وشجرة التشخيص":
    st.title("🔍 نظام فحص المعدات البصري وقائمة مراجعة الأعطال (Checklist)")

    st.subheader("📋 قائمة الفحص الميداني للمعدة (Inspection Checklist)")

    equipment_type = st.selectbox("اختر نوع المعدة للفحص:", ["مولد ديزل صناعي", "غرفة تبريد وتجميد", "محرك كهربائي 3-Phase"])

    if equipment_type == "مولد ديزل صناعي":
        c1 = st.checkbox("1. تسريب زيت أو وقود تحت المحرك")
        c2 = st.checkbox("2. انخفاض مستوى سائل التبريد (Radiator Coolant)")
        c3 = st.checkbox("3. ضعف أو تأكل كوابل البطارية")
        c4 = st.checkbox("4. انسداد أو اتساخ فلتر الهواء")
        c5 = st.checkbox("5. وجود اهتزازات غير طبيعية أثناء التشغيل")

        st.divider()
        st.subheader("🌳 شجرة القرار والتوجيه التلقائي (Fault Tree Navigation)")
        if c1:
            st.error("⚠️ **تنبيه تسريب:** افحص وجه الكارتير، فلتر الزيت، وأنابيب الوقود قبل البدء.")
        if c2:
            st.warning("⚠️ **تنبيه التبريد:** قُم بتعبئة خزان التبريد بسائل ELC معتمد وتفقد خرطوم الردياتير.")
        if c3:
            st.warning("⚠️ **تنبيه الكهرباء:** قم بتنظيف أطراف البطارية وإحكام التوصيل وافحص دينامو الشحن.")
        if not c1 and not c2 and not c3 and not c4 and not c5:
            st.success("🟢 جميع بنود الفحص الظاهري سليمة وجاهزة للتشغيل.")

    elif equipment_type == "غرفة تبريد وتجميد":
        r1 = st.checkbox("1. تكوّن ثلج على ملف المبخر (Evaporator Coils)")
        r2 = st.checkbox("2. ارتفاع ضغط السحب (Low Pressure Cutout Triggered)")
        r3 = st.checkbox("3. توقف مروحة المكثف الخارجية")

        if r1:
            st.error("🚨 **عطل التجميد:** افحص دورة الإذابة (Defrost Cycle) وسخانات الذوبان.")
        if r3:
            st.error("🚨 **عطل التبريد:** تحقق من الكونتاكتور والموتور الخاص بمروحة المكثف.")

    elif equipment_type == "محرك كهربائي 3-Phase":
        m1 = st.checkbox("1. ارتفاع حرارة جسم المحرك بشكل غير طبيعي")
        m2 = st.checkbox("2. صوت صرير أو ضوضاء من الرولمان بلي (Bearings)")
        m3 = st.checkbox("3. عدم توازن الأمبير بين الأوجه الثلاثة (Phase Imbalance)")

        if m1 or m3:
            st.error("🚨 **خطر احتراق الملفات:** افحص جهد الفازات وقس مقاومة العزل (Megger Test).")
        if m2:
            st.warning("🔧 **صيانة ميكانيكية:** يلزم تشحيم أو استبدال رولمان البلي.")
