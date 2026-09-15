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

st.set_page_config(
    page_title="Addoma Industrial Unified Platform",
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
    firebase_status = True
except Exception:
    db = None
    firebase_status = False

# ---------------------------------------------------------
# 2. إدارة معرف الجهاز والاشتراكات السحابية (7 أيام تجريبية + تفعيل)
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
    
    if db is not None:
        try:
            code_ref = db.collection("activation_codes").document(code_str)
            code_doc = code_ref.get()
            if code_doc.exists:
                code_data = code_doc.to_dict()
                duration_days = code_data.get("duration_days", 30)
                plan_name = code_data.get("plan_name", f"اشتراك لمدة {duration_days} يوم")
                if code_data.get("is_active", True):
                    expiry = now + timedelta(days=duration_days)
                    update_device_subscription(dev_id, expiry, plan_name)
                    return True, f"✅ تم تفعيل الاشتراك بنجاح: {plan_name}"
                else:
                    return False, "❌ عذراً، هذا الكود معطل حالياً."
        except Exception:
            pass
            
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
        
    return False, "❌ كود التفعيل غير صحيح أو منتهي الصلاحية."

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

# ---------------------------------------------------------
# الشريط الجانبي الموحد لاختيار المهمة والتحقق
# ---------------------------------------------------------
st.sidebar.title("🛠️ منصة الدومة المتكاملة")
st.sidebar.caption("إدارة المولدات، المساعد الذكي، وتقييم المعدات")

if firebase_status:
    st.sidebar.success("🔥 متصل بـ Firebase بنجاح")
else:
    st.sidebar.warning("⚠️ وضع التشغيل المحلي (بدون اتصال سحابي)")

st.sidebar.divider()
st.sidebar.header("📌 اختيار المهمة (App Navigation)")
app_mode = st.sidebar.selectbox(
    "اختر النظام المطلوب:",
    [
        "1. الصيانة التنبؤية للمولدات (Predictive Maintenance)",
        "2. المساعد الذكي الفني (AI Technical Assistant)",
        "3. فحص وتقييم المعدات الصناعية (Equipment Audit)"
    ]
)

st.sidebar.divider()
st.sidebar.header("🔐 بوابة التفعيل")
input_code = st.sidebar.text_input("أدخل كود الاشتراك:", type="password")
if st.sidebar.button("تفعيل الكود"):
    if input_code:
        success, msg = verify_and_apply_activation_code(input_code, device_id)
        if success:
            st.sidebar.success(msg)
            st.rerun()
        else:
            st.sidebar.error(msg)
    else:
        st.sidebar.warning("⚠️ أدخل الكود أولاً.")

if access_status == "paid":
    st.sidebar.success(f"🌟 اشتراك مفعل: {plan_type} (متبقي {time_left} يوم)")
elif access_status == "trial":
    st.sidebar.info(f"⏳ فترة تجريبية (متبقي {time_left} يوم)")
else:
    st.sidebar.error("⚠️ انتهت الفترة التجريبية.")
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية. يرجى إدخال كود التفعيل في الشريط الجانبي.")
    st.stop()

# ---------------------------------------------------------
# دالة مساعدة لحفظ السجلات في Firebase
# ---------------------------------------------------------
def save_log_to_firestore(client_id, gen_id, readings_data, parts_status):
    if db is None:
        return False
    try:
        doc_ref = db.collection("generators").document(str(gen_id)).collection("maintenance_logs").document()
        doc_ref.set({
            "timestamp": firestore.SERVER_TIMESTAMP,
            "client_name": str(client_id),
            "generator_id": str(gen_id),
            "readings": readings_data,
            "parts_status": parts_status,
        })
        return True
    except Exception:
        return False

# =========================================================
# الخيار الأول: نظام الصيانة التنبؤية للمولدات
# =========================================================
if "1." in app_mode:
    st.title("⚙️ نظام الصيانة التنبؤية والتقارير الشاملة للمولدات الصناعية")
    
    st.sidebar.header("🎯 ضبط حدود المعايير")
    col_v1, col_v2 = st.sidebar.columns(2)
    v_min = col_v1.number_input("أدنى جهد (V Min)", value=380.0, step=5.0)
    v_max = col_v2.number_input("أقصى جهد (V Max)", value=420.0, step=5.0)
    
    col_f1, col_f2 = st.sidebar.columns(2)
    f_min = col_f1.number_input("أدنى تردد (Hz Min)", value=48.0, step=0.5)
    f_max = col_f2.number_input("أقصى تردد (Hz Max)", value=52.0, step=0.5)
    
    col_t1, col_amp = st.sidebar.columns(2)
    temp_max_limit = col_t1.number_input("أقصى حرارة (°C)", value=90.0, step=1.0)
    amp_max_limit = col_amp.number_input("أقصى تيار (A Max)", value=400.0, step=10.0)
    
    st.sidebar.header("📥 إدخال قراءات المولد")
    with st.sidebar.form("gen_form"):
        gen_model = st.text_input("طراز المولد", value="Perkins 410 kVA - DSE 7320")
        run_hours = st.number_input("ساعات التشغيل الحالية", value=700.0, step=10.0)
        future_run_hours = st.number_input("ساعات التشغيل المستهدفة", value=940.0, step=10.0)
        gen_kw = st.number_input("سعة المولد (kW)", value=410.0, step=10.0)
        load_kw = st.number_input("الحمولة الحالية (kW)", value=50.0, step=10.0)
        ambient_temp = st.number_input("الحرارة المحيطة (°C)", value=43.0, step=1.0)
        
        coolant_temp = st.number_input("حرارة سائل التبريد (°C)", value=85.0)
        oil_press = st.number_input("ضغط الزيت (Bar)", value=2.5)
        vibration = st.number_input("مستوى الاهتزاز (mm/s)", value=2.2)
        
        voltage = st.number_input("الجهد (V)", value=400.0)
        freq = st.number_input("التردد (Hz)", value=50.0)
        amperes = st.number_input("التيار (A)", value=118.0)
        pf = st.number_input("معامل القدرة (PF)", value=0.85)
        
        last_oil_change_hours = st.number_input("ساعات آخر تغيير زيت", value=460.0, step=10.0)
        oil_change_interval = st.number_input("الفترة القياسية للزيت", value=250.0, step=50.0)
        
        submit_btn = st.form_submit_button("تحليل وتحديث القراءات")
        
    uploaded_image = st.sidebar.file_uploader("رفع صورة المولد", type=["png", "jpg", "jpeg"])
    
    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0
    
    if uploaded_image:
        st.image(uploaded_image, caption=f"المولد: {gen_model}", width=300)
        
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("إجمالي التشغيل", f"{run_hours} hrs")
    c2.metric("الساعات المستهدفة", f"{future_run_hours} hrs")
    c3.metric("الحمولة", f"{load_kw} kW", f"{load_percentage:.1f}%")
    c4.metric("الحرارة المحيطة", f"{ambient_temp} °C")
    
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("حرارة المحرك", f"{coolant_temp} °C")
    c6.metric("ضغط الزيت", f"{oil_press} Bar")
    c7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
    c8.metric("التيار / المعامل", f"{amperes}A | {pf}")
    
    st.divider()
    st.subheader("🚨 إنذارات الحدود التشغيلية")
    range_alarms = []
    if voltage < v_min or voltage > v_max: range_alarms.append(f"Voltage Out of Range: {voltage}V")
    if freq < f_min or freq > f_max: range_alarms.append(f"Frequency Out of Range: {freq} Hz")
    if coolant_temp > temp_max_limit: range_alarms.append(f"Overheat Alert: {coolant_temp}C")
    if amperes > amp_max_limit: range_alarms.append(f"Overcurrent Alert: {amperes}A")
    
    if range_alarms:
        for al in range_alarms: st.error(f"🔴 {al}")
    else:
        st.success("🟢 جميع القراءات الكهربائية والميكانيكية ضمن الحدود الآمنة.")
        
    st.divider()
    st.subheader("🛢️ جدول خدمة زيت المحرك")
    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil = max(0.0, effective_hours - last_oil_change_hours)
    oil_rem = oil_change_interval - hours_since_oil
    oil_pct = (hours_since_oil / oil_change_interval) * 100 if oil_change_interval > 0 else 0
    
    rec_oil = "20W50 (Extreme Hot)" if ambient_temp >= 45 else "15W40 (Standard)"
    
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("الساعات المنقضية للزيت", f"{hours_since_oil:.1f} hrs")
    o2.metric("الفترة القياسية", f"{oil_change_interval} hrs")
    o3.metric("المتبقي للخدمة", f"{max(0, oil_rem):.1f} hrs", f"{oil_pct:.0f}%")
    o4.metric("اللزوجة الموصى بها", rec_oil)
    
    if oil_pct >= 100:
        st.error("🚨 تحذير حرج: تجاوزت فترة غيار الزيت المقررة! يرجى الاستبدال الفوري.")
    elif oil_pct >= 90:
        st.warning("⚠️ تنبيه: اقترب موعد غيار الزيت والفلاتر.")
        
    st.divider()
    st.subheader("🔧 جدول تتبع قطع الغيار والفلاتر التنبؤية")
    parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Engine Oil & Filter", "العمر الافتراضي (ساعة)": float(oil_change_interval), "المدة المنقضية (ساعة)": float(hours_since_oil)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "المدة المنقضية (ساعة)": float(hours_since_oil)},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "المدة المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "المدة المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Electrical", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي (ساعة)": 8000.0, "المدة المنقضية (ساعة)": float(effective_hours)},
    ]
    df_parts = pd.DataFrame(parts_data)
    edited_parts = st.data_editor(df_parts, use_container_width=True)
    
    processed_rows = []
    for _, row in edited_parts.iterrows():
        life = float(row["العمر الافتراضي (ساعة)"])
        used = float(row["المدة المنقضية (ساعة)"])
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0
        st_text = "GOOD (جيدة)"
        if rem <= 0: st_text = "EXPIRED (منتهي)"
        elif pct >= 90: st_text = "WARNING (تحذير)"
        
        processed_rows.append({
            "تصنيف القطعة": row["تصنيف القطعة"],
            "قطع الغيار / الفلاتر": row["قطع الغيار / الفلاتر"],
            "العمر الافتراضي (ساعة)": life,
            "المدة المنقضية (ساعة)": used,
            "نسبة الاستهلاك": f"{pct:.0f}%",
            "المدة المتبقية (ساعة)": max(0, rem),
            "الحالة الفنية": st_text
        })
    df_result = pd.DataFrame(processed_rows)
    
    if st.button("💾 حفظ السجلات في قاعدة بيانات Firebase", use_container_width=True):
        payload = {"run_hours": run_hours, "voltage": voltage, "freq": freq, "coolant_temp": coolant_temp}
        if save_log_to_firestore(client_name, gen_model, payload, df_result.to_dict("records")):
            st.success("✅ تم الحفظ السحابي بنجاح!")
        else:
            st.warning("⚠️ تعذر الحفظ السحابي، تحقق من اتصال قاعدة البيانات.")

# =========================================================
# الخيار الثاني: المساعد الذكي الفني (AI Technical Assistant)
# =========================================================
elif "2." in app_mode:
    st.title("🤖 المساعد الذكي الفني لأعطال المولدات وأنظمة التبريد")
    st.markdown("اسأل عن أكواد أعطال محركات بيركنز، كمبيوترات DSE، أو وحدات التبريد Porkka WIC.")
    
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {"role": "assistant", "content": "مرحباً بك مهندس عثمان. أنا مساعدك الفني الذكي لصيانة المولدات وأنظمة التبريد. كيف يمكنني مساعدتك اليوم؟"}
        ]
        
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    user_query = st.chat_input("اكتب استفسارك الفني هنا (مثال: أسباب خطأ Failure to Start في بيركنز)...")
    if user_query:
        st.session_state.chat_history.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)
            
        # استجابة ذكية تحليلية مبنية على السياق الهندسي
        q_lower = user_query.lower()
        if "start" in q_lower or "بدء" in q_lower or "تشغيل" in q_lower:
            reply = "🔧 **تشخيص عطل عدم الإقلاع (Failure to Start):**\n1. تحقق من وقود الخط ومحبس الإمداد.\n2. افحص فيوزات وحدة التحكم DSE 7320 / 8610.\n3. تأكد من سلامة حساس سرعة الدوران (Magnetic Speed Sensor) ونظافته."
        elif "wic" in q_lower or "تبريد" in q_lower or "ثلاجة" in q_lower:
            reply = "❄️ **صيانة وحدات التبريد Porkka WIC (WIC 10 / WIC 40):**\n1. تحقق من قراءات وحدة تحكم Emerson وضبط صمام التمدد (Expansion Valve).\n2. تأكد من نظافة المبخر والمكثف وعدم وجود انسداد في الفلتر دรายر (Filter Drier).\n3. افحص شحنة الفريون وضغوط السحب والطرد."
        elif "perkins" in q_lower or "بيركنز" in q_lower:
            reply = "⚙️ **معلومات محركات Perkins (مثل سلسلة 2206C):**\n- تأكد من ضغط الزيت الطبيعي (2.5 إلى 4 بار).\n- افحص تمديدات وموصلات وحدة التحكم الإلكترونية (ECM) وضفيرة الأسلاك."
        else:
            reply = f"💡 استناداً إلى خبرتك في صيانة المولدات والأنظمة الكهروميكانيكية: بالنسبة لـ ({user_query})، أنصح بمراجعة المخططات الكهربائية الخاصة بلوحة التحكم والقياس باستخدام متعد القياس (Multimeter) للتأكد من استمرارية الدوائر."
            
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        with st.chat_message("assistant"):
            st.markdown(reply)

# =========================================================
# الخيار الثالث: فحص وتقييم المعدات الصناعية (Equipment Audit)
# =========================================================
else:
    st.title("📋 نظام فحص وتقييم المعدات والمنشآت الصناعية")
    st.markdown("إجراء قائمة تدقيق تقييمية (Audit Checklist) لخطوط الإنتاج، المولدات، والمعدات التالفة أو الخدمية.")
    
    col_a, col_b = st.columns(2)
    site_name = col_a.text_input("اسم المنشأة / الموقع الصناعي", value="موقع التعدين - محطة التوليد الرئيسية")
    auditor_name = col_b.text_input("اسم الفاحص / الاستشاري", value="مهندس عثمان آدم")
    
    st.subheader("بنود قائمة الفحص الفني والتقييمي")
    audit_items = [
        {"Category": "Electrical", "Item": "لوحات التحكم والربط الآلي (DSE Synchronizing Panels)", "Status": "جيد", "Notes": "تعمل بكفاءة"},
        {"Category": "Mechanical", "Item": "نظام حقن الوقود والفلاتر الأساسية", "Status": "يحتاج صيانة", "Notes": "استبدال الفلتر الأولي مطلوب"},
        {"Category": "Cooling", "Item": "رادياتير التبريد والمراوح ونسبة السائل (ELC)", "Status": "جيد", "Notes": "المستوى طبيعي"},
        {"Category": "Refrigeration", "Item": "وحدات التبريد Porkka WIC 10 / WIC 40", "Status": "ممتاز", "Notes": "درجات الحرارة مستقرة"},
        {"Category": "Safety", "Item": "أنظمة الحماية الأرضية وفصل الطوارئ (Emergency Stop)", "Status": "جيد", "Notes": "تم الاختبار بنجاح"}
    ]
    
    df_audit = pd.DataFrame(audit_items)
    edited_audit = st.data_editor(df_audit, use_container_width=True, key="audit_editor")
    
    general_eval = st.text_area("التقييم العام والتوصيات الهندسية النهائية:", value="المعدات تعمل بصورة مرضية مع ضرورة تنفيذ جدول صيانة الفلاتر الدورية في الموعد القادم.")
    
    if st.button("🖨️ إصدار وحفظ تقرير التدقيق الفني", use_container_width=True):
        st.success(f"✅ تم اعتماد تقرير الفحص للموقع: {site_name} بواسطة الاستشاري {auditor_name} بنجاح!")
        st.info("💡 يمكنك العودة لنظام الصيانة التنبؤية أو المساعد الذكي في أي وقت عبر القائمة الجانبية.")
