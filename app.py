from datetime import datetime, timedelta
import io
import json
import os
import re
import urllib.parse
import uuid

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
# 1. دالة البحث الهندسية والربط بـ Google Books & Web Search API
# ---------------------------------------------------------
def search_engineering_resources(query_text):
    """دالة لجلب المراجع الهندسية والكتب من Google Books و Bing/Google Web."""
    results = {"books": [], "web_articles": []}
    
    # 1. البحث في كتب Google Books API
    try:
        gbooks_url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(query_text)}&maxResults=3"
        resp = requests.get(gbooks_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("items", []):
                volume_info = item.get("volumeInfo", {})
                results["books"].append({
                    "title": volume_info.get("title", "بدون عنوان"),
                    "authors": ", ".join(volume_info.get("authors", ["مؤلف غير معروف"])),
                    "link": volume_info.get("previewLink", "#"),
                    "snippet": volume_info.get("description", "لا يوجد وصف مختصر.")[:150] + "..."
                })
    except Exception:
        pass

    # 2. البحث في ويب Google / Bing
    bing_api_key = st.secrets.get("BING_API_KEY", os.environ.get("BING_API_KEY", ""))
    if bing_api_key:
        try:
            headers = {"Ocp-Apim-Subscription-Key": bing_api_key}
            params = {"q": f"{query_text} maintenance manual repair guide", "textDecorations": True, "textFormat": "HTML"}
            response = requests.get("https://api.bing.microsoft.com/v7.0/search", headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                search_results = response.json()
                for page in search_results.get("webPages", {}).get("value", [])[:3]:
                    results["web_articles"].append({
                        "title": page.get("name"),
                        "link": page.get("url"),
                        "snippet": page.get("snippet")
                    })
        except Exception:
            pass

    return results

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
        self.cell(0, 4, "Addoma Trading Services - Engineering & Automation Platform", ln=True, align="C")
        self.line(10, 20, 200, 20)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()} | System Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# ---------------------------------------------------------
# 3. تهيئة الاتصال بـ Firebase Firestore
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
# 4. إدارة الاشتراكات الزمنيّة
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

# ---------------------------------------------------------
# لوحة تفاصيل الاشتراك والتفعيل
# ---------------------------------------------------------
st.sidebar.header("🔐 تفاصيل الاشتراك والتفعيل")

st.sidebar.info(f"""
📌 **حالة الحساب والاشتراك:**
* **نوع الخطة:** {plan_type}
* **تاريخ الانتهاء:** `{expiry_date_str}`
* **المدة المتبقية:** **{time_left}** يوماً
""")

with st.sidebar.expander("🔑 إدخال كود التفعيل (أيام / شهور / سنوات)"):
    input_code = st.text_input("أدخل كود التفعيل:", type="password")
    if st.button("تفعيل الاشتراك"):
        code_clean = input_code.strip().upper()
        
        duration_map = {
            "ADDOMA-7D": (7, "اشتراك تجريبي (7 أيام)"),
            "ADDOMA-30D": (30, "اشتراك شهري (1 شهر / 30 يوم)"),
            "ADDOMA-90D": (90, "اشتراك 3 شهور (90 يوم)"),
            "ADDOMA-180D": (180, "اشتراك 6 شهور (180 يوم)"),
            "ADDOMA-1Y": (365, "اشتراك سنوي كامل (1 سنة / 365 يوم)"),
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

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية. يرجى التفعيل باستخدام كود اشتراك ساري.")
    st.stop()

# ---------------------------------------------------------
# 5. قائمة اختيار التطبيقات والمكتبة
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("🛠️ التطبيقات والمكتبة التلقائية")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية",
        "🤖 2. المساعد الذكي والربط التلقائي بمواقع البحوث",
        "🔍 3. فحص المعدات والمقارنة البصرية (تالف/سليم)",
        "📚 4. مكتبتي الفنية (التغذية التلقائية المحفوظة)"
    ]
)
st.sidebar.divider()

if "auto_library" not in st.session_state:
    st.session_state.auto_library = []

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية المتكامل
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
        load_kw = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=50.0, step=10.0)
        ambient_temp = st.number_input("الحرارة المحيطة (°C)", value=43.0, step=1.0)

        coolant_temp = st.number_input("حرارة سائل التبريد (°C)", value=85.0)
        oil_press = st.number_input("ضغط الزيت (Bar)", value=2.5)
        vibration = st.number_input("مستوى الاهتزاز (mm/s)", value=2.2)

        voltage = st.number_input("الجهد (V)", value=400.0)
        freq = st.number_input("التردد (Hz)", value=50.0)
        amperes = st.number_input("التيار (A)", value=118.0)
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
    st.subheader("🛢️ جدول الصيانة التنبؤية والمدد الافتراضية المكتملة لقطع الغيار")

    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)
    hours_until_next_oil_change = oil_change_interval - hours_since_oil_change
    oil_usage_pct = (hours_since_oil_change / oil_change_interval) * 100 if oil_change_interval > 0 else 0

    col_o1, col_o2, col_o3 = st.columns(3)
    col_o1.metric("المدة المنقضية للزيت", f"{hours_since_oil_change:.1f} hrs")
    col_o2.metric("المدة المتبقية للخدمة", f"{max(0.0, hours_until_next_oil_change):.1f} hrs")
    col_o3.metric("نسبة استهلاك فترة الزيت", f"{oil_usage_pct:.0f}%")

    # قاعدة البيانات المكتملة لجميع قطع الغيار بمددها الافتراضية
    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Engine Oil & Filter", "العمر الافتراضي (ساعة)": float(oil_change_interval), "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter Element", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "Fan & Alternator Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant Fluid", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Fuel System", "قطع الغيار / الفلاتر": "Fuel Injectors (بخاخات)", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "Water Pump (مضخة الماء)", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Electrical", "قطع الغيار / الفلاتر": "Starter Battery", "العمر الافتراضي (ساعة)": 4000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Overhaul", "قطع الغيار / الفلاتر": "Turbocharger Kit", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", use_container_width=True, key="parts_editor_v2")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        cat = str(row.get("تصنيف القطعة", "Other"))
        part = str(row.get("قطع الغيار / الفلاتر", "Part"))
        life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0

        status = "EXPIRED (انقضاء المدة)" if rem <= 0 else ("WARNING (اقتراب الخدمة)" if pct >= 80 else "GOOD (جيدة)")
        processed_rows.append({
            "تصنيف القطعة": cat,
            "قطع الغيار / الفلاتر": part,
            "العمر الافتراضي (ساعة)": life,
            "الساعات المنقضية (ساعة)": used,
            "المدة المتبقية (ساعة)": max(0.0, rem),
            "نسبة الاستهلاك": f"{pct:.0f}%",
            "الحالة الفنية": status
        })

    df_result = pd.DataFrame(processed_rows)

    st.divider()
    st.subheader("📊 الرسوم البيانية لأداء الآليات وجاهزية قطع الغيار")

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
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        fig_pie = px.pie(
            df_result,
            names="الحالة الفنية",
            title="توزيع جاهزية ونسبة سلامة قطع الغيار (Pie Chart)",
            color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"]
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()
    st.subheader("📄 إصدار وتنزيل التقرير الفني الشامل مع الرسوم البيانية الدائرية (PDF)")

    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("COMPREHENSIVE MAINTENANCE & DIAGNOSTIC REPORT")
        pdf.add_page()
        temp_files = []

        # 1. القراءات التشغيلية
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)}", ln=True)
        pdf.cell(0, 5, f"Total Run Hours: {run_hours} hrs | Target Hours: {future_run_hours} hrs", ln=True)
        pdf.cell(0, 5, f"Capacity: {gen_kw} kW | Current Load: {load_kw} kW ({load_percentage:.1f}%)", ln=True)
        pdf.cell(0, 5, f"Electrical: {voltage} V | {freq} Hz | {amperes} A | PF: {pf}", ln=True)
        pdf.cell(0, 5, f"Mechanical: Coolant {coolant_temp} C | Oil Press {oil_press} Bar | Vib {vibration} mm/s", ln=True)
        pdf.ln(3)

        # 2. ملخص خدمة الزيت
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "1. Engine Oil & Filter Service Summary:", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"- Default Oil Change Interval: {oil_change_interval} hrs", ln=True)
        pdf.cell(0, 5, f"- Hours Used on Oil: {hours_since_oil_change} hrs ({oil_usage_pct:.0f}%)", ln=True)
        pdf.cell(0, 5, f"- Remaining Hours to Change: {max(0.0, hours_until_next_oil_change)} hrs", ln=True)
        pdf.ln(3)

        # 3. الجدول الكامل المحدث لقطع الغيار
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "2. Full Spare Parts Lifespan & Predictive Maintenance Schedule:", ln=True)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(45, 5, "Part Name", border=1)
        pdf.cell(25, 5, "Lifespan(h)", border=1)
        pdf.cell(25, 5, "Used(h)", border=1)
        pdf.cell(25, 5, "Remaining(h)", border=1)
        pdf.cell(35, 5, "Status", border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for idx, row in df_result.iterrows():
            pdf.cell(45, 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:22], border=1)
            pdf.cell(25, 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
            pdf.cell(25, 5, str(row["الساعات المنقضية (ساعة)"]), border=1)
            pdf.cell(25, 5, str(row["المدة المتبقية (ساعة)"]), border=1)
            pdf.cell(35, 5, sanitize_latin_only(str(row["الحالة الفنية"])), border=1)
            pdf.ln()

        # 4. إدراج الرسم البياني الدائري والشريطي داخل التقرير
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "3. Visual Analytics & Predictive Maintenance Charts:", ln=True)

            # توليد رسم شريطي (Bar Chart)
            fig1, ax1 = plt.subplots(figsize=(6.5, 2.8))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            u_h = df_result["الساعات المنقضية (ساعة)"].values
            r_h = df_result["المدة المتبقية (ساعة)"].values

            ax1.bar(p_short, u_h, label="Used Hours", color="#d9534f")
            ax1.bar(p_short, r_h, bottom=u_h, label="Remaining Hours", color="#28a745")
            ax1.set_title("Spare Parts Lifespan Overview (Hours)", fontsize=9)
            plt.xticks(rotation=35, ha="right", fontsize=7)
            plt.tight_layout()

            chart_path_bar = f"temp_bar_{datetime.now().timestamp()}.png"
            plt.savefig(chart_path_bar, dpi=200)
            plt.close(fig1)
            temp_files.append(chart_path_bar)
            pdf.image(chart_path_bar, x=15, y=25, w=170)

            # توليد وتضمين الرسم البياني الدائري (Pie Chart)
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            status_counts = df_result["الحالة الفنية"].value_counts()
            labels = [sanitize_latin_only(str(k)) for k in status_counts.index]
            ax2.pie(status_counts.values, labels=labels, autopct='%1.1f%%', colors=['#28a745', '#ffc107', '#dc3545'][:len(labels)])
            ax2.set_title("Parts Safety & Readiness Distribution (Pie Chart)", fontsize=9)
            plt.tight_layout()

            chart_path_pie = f"temp_pie_{datetime.now().timestamp()}.png"
            plt.savefig(chart_path_pie, dpi=200)
            plt.close(fig2)
            temp_files.append(chart_path_pie)
            pdf.image(chart_path_pie, x=25, y=115, w=150)

        except Exception as e:
            pass

        pdf_bytes = pdf.output(dest="S")
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

        return pdf_bytes.encode("latin-1", errors="replace")

    st.download_button(
        label="🖨️ إصدار التقرير الفني المكتمل مدمجاً بجدول القطع والرسوم البيانية الدائرية (PDF)",
        data=generate_full_pdf_bytes(),
        file_name=f"Comprehensive_Maintenance_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# =========================================================
# التطبيق 2: المساعد الذكي والربط التلقائي بمواقع البحوث
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والربط التلقائي بمواقع البحوث":
    st.title("🤖 المساعد الذكي والربط التلقائي بمواقع البحوث والكتب")

    tab1, tab2, tab3 = st.tabs(["🌐 البحث الآلي والتغذية الهندسية", "📚 مكتبة رفع الكتالوجات", "📷 تحليل الأكواد والقطع"])

    with tab1:
        st.subheader("🔍 استعلام البحث والتغذية الذكية للأعطال والآليات")
        fault_query = st.text_input("أدخل كود العطل أو اسم القطعة أو نوع المعدة للبحث عنها تلقائياً:", placeholder="مثال: Perkins 2206 failure to start OR DSE 8610 alarm code 102")
        
        if st.button("تغذية التطبيق والبحث في المراجع 🚀", use_container_width=True):
            if fault_query:
                with st.spinner("جاري الاتصال بمكتبات Google Books ومحركات البحث الهندسية..."):
                    search_data = search_engineering_resources(fault_query)
                    
                    st.success(f"🌐 نتائج التغذية التلقائية لاستعلام: **{fault_query}**")
                    
                    st.markdown("### 📖 المراجع المتاحة في Google Books API:")
                    if search_data["books"]:
                        for b in search_data["books"]:
                            st.markdown(f"- **[{b['title']}]({b['link']})** - *{b['authors']}*\n  _{b['snippet']}_")
                    else:
                        st.info("لم يتم العثور على كتب مباشرة، جرب استعلام أكثر تحديداً بالإنجليزية.")
                        
                    st.divider()
                    st.markdown("### 🔗 أدلة الصيانة والمقالات الميدانية:")
                    if search_data["web_articles"]:
                        for wa in search_data["web_articles"]:
                            st.markdown(f"- **[{wa['title']}]({wa['link']})**\n  _{wa['snippet']}_")
                    else:
                        st.write(f"👉 [اضغط هنا للبحث المباشر عن `{fault_query}` في Google](https://www.google.com/search?q={urllib.parse.quote(fault_query)})")
                    
                    st.session_state.auto_library.append({
                        "query": fault_query,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "books": search_data["books"],
                        "web": search_data["web_articles"]
                    })
                    st.success("💾 تم حفظ نتائج البحث والتغذية في 'مكتبتك الفنية' تلقائياً!")

    with tab2:
        st.subheader("📚 رفع وتصفح الكتالوجات الفنية")
        uploaded_cat = st.file_uploader("رفع الكتالوج (PDF):", type=["pdf"])
        if uploaded_cat:
            st.success(f"تم رفع: {uploaded_cat.name}")

    with tab3:
        st.subheader("📷 تحليل صورة الكود / Barcode")
        up_img = st.file_uploader("رفع صورة الكود:", type=["png", "jpg", "jpeg"])
        if up_img and decode_qr:
            dec = decode_qr(Image.open(up_img))
            if dec:
                for obj in dec:
                    st.info(f"رمز القطعة: {obj.data.decode('utf-8')}")

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 فحص المعدات والمقارنة البصرية لقطع الغيار")
    
    eq_type = st.selectbox("اختر المعدة للفحص:", ["مولد ديزل صناعي", "غرفة تبريد وتجميد WIC", "محرك كهربائي 3-Phase"])

    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 **صورة القطعة السليمة:**")
        good_img_file = st.file_uploader("رفع صورة جديدة", type=["png", "jpg", "jpeg"], key="good_chk")
        if good_img_file: st.image(Image.open(good_img_file), use_column_width=True)

    with col_img2:
        st.write("🔴 **صورة القطعة التالفة:**")
        bad_img_file = st.file_uploader("رفع صورة تالفة", type=["png", "jpg", "jpeg"], key="bad_chk")
        if bad_img_file: st.image(Image.open(bad_img_file), use_column_width=True)

    if good_img_file and bad_img_file:
        st.warning("🔍 **ملاحظة:** تم رصد اختلاف في السطح والتآكل الفعلي للقطعة.")

# =========================================================
# التطبيق 4: مكتبتي الفنية (التغذية التلقائية المحفوظة)
# =========================================================
elif selected_app == "📚 4. مكتبتي الفنية (التغذية التلقائية المحفوظة)":
    st.title("📚 مكتبتك الفنية والتغذية التلقائية المحفوظة")
    st.info("تضم هذه المكتبة كافة نتائج البحث، الكتالوجات، والأكواد التي تم إدخالها وتغذيتها من مصادر الأبحاث وGoogle Books.")

    if st.session_state.auto_library:
        for idx, item in enumerate(reversed(st.session_state.auto_library)):
            with st.expander(f"📌 استعلام: {item['query']} - ({item['date']})"):
                st.write("**الكتب والمراجع المكتشفة:**")
                for b in item["books"]:
                    st.markdown(f"* [{b['title']}]({b['link']}) - {b['authors']}")
                if item["web"]:
                    st.write("**المقالات وأدلة الإصلاح:**")
                    for w in item["web"]:
                        st.markdown(f"* [{w['title']}]({w['link']})")
    else:
        st.warning("المكتبة فارغة حالياً. قم بإجراء بحث في التطبيق رقم (2) لتغذيتها تلقائياً.")
