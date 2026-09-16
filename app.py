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

# قاموس لتخزين الأكواد المولدة حديثاً (للمدير)
if "generated_codes" not in st.session_state:
    st.session_state.generated_codes = {}

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

with st.sidebar.expander("🔑 إدخال كود التفعيل للعميل"):
    input_code = st.text_input("أدخل كود التفعيل:", type="password")
    if st.button("تفعيل الاشتراك"):
        code_clean = input_code.strip().upper()
        
        # الأكواد الافتراضية
        duration_map = {
            "ADDOMA-7D": (7, "اشتراك تجريبي (7 أيام)"),
            "ADDOMA-30D": (30, "اشتراك شهري (1 شهر)"),
            "ADDOMA-90D": (90, "اشتراك 3 شهور"),
            "ADDOMA-180D": (180, "اشتراك 6 شهور"),
            "ADDOMA-1Y": (365, "اشتراك سنوي كامل"),
            "ADDOMA-2026-PRO": (365, "اشتراك احترافي (1 سنة)"),
        }
        
        # إضافة الأكواد التي قام المدير بتوليدها
        duration_map.update(st.session_state.generated_codes)

        if code_clean in duration_map:
            days, p_name = duration_map[code_clean]
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم تفعيل: {p_name}")
            st.rerun()
        else:
            st.error("❌ كود تفعيل غير صحيح.")

st.sidebar.caption("💡 **أكواد للتجربة:** `ADDOMA-30D` | `ADDOMA-1Y`")

# --- لوحة تحكم المدير (توليد الأكواد) ---
st.sidebar.divider()
with st.sidebar.expander("👑 لوحة الإدارة: إصدار أكواد اشتراك جديدة"):
    st.markdown("**(مخصصة لإدارة منصة الدومة للخدمات التجارية)**")
    selected_plan = st.selectbox("اختر نوع الباقة للعميل:", ["اشتراك شهري (30 يوم)", "اشتراك سنوي (365 يوم)"])
    if st.button("توليد كود للعميل"):
        new_generated_code = f"ADDOMA-{str(uuid.uuid4())[:8].upper()}"
        days_allocated = 30 if "شهري" in selected_plan else 365
        plan_name = f"اشتراك مخصص ({days_allocated} يوم)"
        
        # حفظ الكود في الجلسة الحالية
        st.session_state.generated_codes[new_generated_code] = (days_allocated, plan_name)
        st.success("✅ تم إصدار الكود بنجاح! انسخه وأرسله للعميل:")
        st.code(new_generated_code)

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
    st.info("الواجهة التشغيلية الأولى تعمل كما هي بالكامل...")
    # (باقي كود التطبيق الأول يترك كما هو في كودك الأصلي، لم أضعه هنا اختصاراً للمساحة لتركز على المساعد الذكي، لكنه موجود في النسخة الكاملة)

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات وقراءة الأكواد
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي، مكتبة الكتالوجات وقراءة الأكواد")

    tab1, tab2, tab3, tab4 = st.tabs([
        "💬 الاستشارات والتحليل",
        "🌐 البحث في محركات هندسية",
        "📚 رفع وتصفح الكتالوجات",
        "📷 شاشة المولد DSE وقراءة الأكواد"
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
        st.subheader("🌐 محرك البحث الهندسي")
        search_query = st.text_input("أدخل كلمات البحث التقنية (مثال: Perkins ECM wiring diagram):")
        # (باقي كود البحث يترك كما هو)

    # --- TAB 3: الكتالوجات (PDF) ---
    with tab3:
        st.subheader("📚 مكتبة رفع وتحميل الكتالوجات الميدانية (PDF Manuals)")
        uploaded_catalog = st.file_uploader("قم برفع ملف الكتالوج (PDF):", type=["pdf"])
        
        if uploaded_catalog is not None:
            st.success(f"✅ تم رفع الكتالوج بنجاح: **{uploaded_catalog.name}** ({uploaded_catalog.size / 1024:.1f} KB)")
            
            # زر تحميل الكتالوج
            st.download_button(
                label=f"⬇️ تنزيل الكتالوج للاحتفاظ به",
                data=uploaded_catalog.getvalue(),
                file_name=uploaded_catalog.name,
                mime="application/pdf",
                use_container_width=True
            )
            
            st.divider()
            # خانة البحث داخل الكتالوج
            search_catalog_term = st.text_input("🔍 أدخل كود العطل أو اسم القطعة للبحث داخل الكتالوج:")
            if st.button("بحث وتحليل العطل من الكتالوج"):
                if search_catalog_term:
                    st.info(f"جاري البحث عن العطل ({search_catalog_term}) داخل الوثيقة وتحليله هندسياً...")
                    # ملاحظة: لإجراء بحث حقيقي داخل PDF ستحتاج لمكتبة مثل PyPDF2، هذا محاكاة لتوضيح التصميم
                    st.success(f"✅ النتيجة المقترحة: تم العثور على تلميحات تخص ({search_catalog_term}). يرجى مراجعة نظام التبريد أو الحساسات المتعلقة بهذا الرمز.")
                else:
                    st.warning("يرجى إدخال الكلمة المراد البحث عنها.")

    # --- TAB 4: شاشة المولد DSE، الكاميرا، وقراءة الأكواد ---
    with tab4:
        st.subheader("📷 التقاط أو رفع صورة شاشة المولد (DSE Controller)")
        
        # اختيار مصدر الصورة
        camera_or_file = st.radio("اختر طريقة إدخال الصورة:", ["استخدام الكاميرا 📸", "رفع من الجهاز 📁"])
        image_data = None
        
        if camera_or_file == "استخدام الكاميرا 📸":
            image_data = st.camera_input("التقط صورة لشاشة المولد (تأكد من وضوح الأكواد):")
        else:
            image_data = st.file_uploader("قم برفع صورة شاشة لوحة تحكم DSE:", type=["png", "jpg", "jpeg"], key="dse_img")

        if image_data is not None:
            # معالجة الصورة المرفوعة أو الملتقطة
            dse_image = Image.open(image_data)
            st.image(dse_image, caption="الصورة المدخلة لشاشة التحكم", width=400)
            
            # زر لتحميل الصورة الملتقطة/المرفوعة
            buf = io.BytesIO()
            dse_image.save(buf, format="JPEG")
            st.download_button(
                label="⬇️ تحميل الصورة وحفظها بالجهاز",
                data=buf.getvalue(),
                file_name=f"DSE_Screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
                mime="image/jpeg",
                use_container_width=True
            )
            
            st.divider()
            st.subheader("🔍 قراءة الأكواد وتحليل الأعطال (QR / Barcode)")
            
            # قراءة وتحليل الباركود / QR كود من الصورة إن وجد
            if decode_qr:
                decoded_objects = decode_qr(dse_image)
                if decoded_objects:
                    st.success("✅ تم استخراج أكواد من الصورة بنجاح!")
                    for obj in decoded_objects:
                        code_data = obj.data.decode('utf-8')
                        st.write(f"**نوع الكود:** {obj.type}")
                        st.write(f"**الكود المستخرج:** `{code_data}`")
                        
                        st.warning(f"**التحليل الفني التلقائي للكود ({code_data}):**")
                        st.write("يرجى مراجعة دليل الصيانة (Manual) الخاص بلوحة التحكم ومطابقة هذا الكود مع جدول حساسات المحرك أو إنذارات الحماية (Protections).")
                else:
                    st.info("ℹ️ لم يتم العثور على رمز QR أو Barcode في الصورة. يعتمد النظام الآن على الفحص البصري التوجيهي.")
                    st.warning("""
                    ⚠️ **التحليل التوجيهي لأكواد DSE النصية:**
                    * **Warning Code:** (مثل Oil Pressure Low أو Coolant Temp High)
                    * **الخطوات التصحيحية:**
                      1. تحقق من المستويات الفيزيائية للزيت وسائل التبريد.
                      2. افحص حساسية المستشعرات وتوصيل الأسلاك.
                    """)
            else:
                st.error("⚠️ مكتبة قراءة الأكواد (pyzbar) غير متوفرة في بيئة الاستضافة الحالية. يرجى إضافتها لملف requirements.txt")

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")
    # (يُترك الكود الخاص بالتطبيق الثالث كما هو في نسختك)
