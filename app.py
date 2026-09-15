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
    results = {"books": [], "web_articles": []}
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
    plan_type = user_record.get("plan_type", "اشتراك مفعل")
    expiry_date_str = sub_exp.strftime("%Y-%m-%d")
elif is_trial_active:
    time_left = (trial_exp - now).days
    plan_type = "فترة تجريبية (7 أيام)"
    expiry_date_str = trial_exp.strftime("%Y-%m-%d")
else:
    time_left = 0
    plan_type = "منتهي الصلاحية"
    expiry_date_str = "منتهي"

st.sidebar.header("🔐 تفاصيل الاشتراك والتفعيل")
st.sidebar.info(f"""
📌 **حالة الحساب:**
* **الخطة:** {plan_type}
* **الانتهاء:** `{expiry_date_str}`
* **المتبقي:** **{time_left}** يوماً
""")

with st.sidebar.expander("🔑 إدخال كود التفعيل"):
    input_code = st.text_input("كود التفعيل:", type="password")
    if st.button("تفعيل"):
        duration_map = {
            "ADDOMA-7D": (7, "7 أيام"),
            "ADDOMA-30D": (30, "30 يوم"),
            "ADDOMA-90D": (90, "90 يوم"),
            "ADDOMA-1Y": (365, "سنة كاملة")
        }
        code_clean = input_code.strip().upper()
        if code_clean in duration_map:
            days, p_name = duration_map[code_clean]
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name)
            st.success(f"✅ تم التفعيل بنجاح!")
            st.rerun()
        else:
            st.error("❌ كود غير صحيح.")

if time_left <= 0 and not is_sub_active and not is_trial_active:
    st.error("🔒 **النظام مقفل:** انتهت الفترة التجريبية.")
    st.stop()

st.sidebar.divider()
st.sidebar.header("🛠️ التطبيقات والمكتبة")
selected_app = st.sidebar.radio(
    "اختر النظام:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية",
        "🤖 2. المساعد الذكي والبحث الآلي",
        "🔍 3. فحص المعدات ورفع الصور",
        "📚 4. مكتبتي الفنية المحفوظة"
    ]
)

if "auto_library" not in st.session_state:
    st.session_state.auto_library = []

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والمتكامل مع رفع وتحميل الصور
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات والرسوم البيانية":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

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

    # قسم رفع وتحميل الصور
    st.subheader("📷 إدارة وتوثيق صور المولد وقطع الغيار")
    uploaded_part_image = st.file_uploader("رفع صورة المولد أو قطعة الغيار للتقرير:", type=["png", "jpg", "jpeg"], key="gen_part_img")
    
    saved_img_path = None
    if uploaded_part_image:
        img_pil = Image.open(uploaded_part_image)
        st.image(img_pil, caption="معاينة الصورة المرفوعة", width=350)
        
        buf = io.BytesIO()
        img_pil.save(buf, format="PNG")
        st.download_button(
            label="⬇️ تحميل الصورة المرفوعة للجهاز",
            data=buf.getvalue(),
            file_name=f"generator_part_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png",
            mime="image/png"
        )
        
        saved_img_path = f"temp_uploaded_{uuid.uuid4().hex}.png"
        img_pil.save(saved_img_path)

    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("إجمالي التشغيل الحالي", f"{run_hours} hrs")
    col2.metric("الساعات المستهدفة", f"{future_run_hours} hrs")
    col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
    col4.metric("حرارة المحرك", f"{coolant_temp} °C")

    st.divider()
    st.subheader("🛢️ جدول الصيانة التنبؤية المعتمد (14 بنداً كاملاً)")

    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)

    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services (الصيانة الدورية)", "قطع الغيار / الفلاتر": "فلتر زيت (Oil Filter)", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services (الصيانة الدورية)", "قطع الغيار / الفلاتر": "فلتر وقود - أولي (Primary Fuel Filter)", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services (الصيانة الدورية)", "قطع الغيار / الفلاتر": "فلتر وقود - ثانوي (Secondary Fuel Filter)", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Air System (نظام الهواء)", "قطع الغيار / الفلاتر": "فلتر هواء (Air Filter)", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Fan Belt System (نظام التبريد)", "قطع الغيار / الفلاتر": "قشاط المروحة (Fan Belt)", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Coolant System (نظام التبريد)", "قطع الغيار / الفلاتر": "سائل تبريد (ELC Coolant)", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Feul System (نظام الوقود)", "قطع الغيار / الفلاتر": "بخاخات الوقود (Injectors Check)", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "النظام الكهربائي", "قطع الغيار / الفلاتر": "بطاريات (Batteries)", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Electric System (النظام الكهربائي)", "قطع الغيار / الفلاتر": "دينامو الشحن (Charging Alternator)", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Engine Motor (المحرك - ميكانيك)", "قطع الغيار / الفلاتر": "طقم عمرة رأس (Top Overhaul)", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Engine Motor (المحرك - ميكانيك)", "قطع الغيار / الفلاتر": "عمرة كاملة (Major Overhaul)", "العمر الافتراضي (ساعة)": 20000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Oilers System (نظام التزييت)", "قطع الغيار / الفلاتر": "مبرد الزيت (Oil Cooler Clean)", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "نظام التبريد", "قطع الغيار / الفلاتر": "مضخة الماء (Water Pump)", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "نظام الهواء", "قطع الغيار / الفلاتر": "تيربو (Turbocharger Check)", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", use_container_width=True, key="parts_editor_v6")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        cat = str(row.get("تصنيف القطعة", "Other"))
        part = str(row.get("قطع الغيار / الفلاتر", "Part"))
        life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0
        status = "EXPIRED" if rem <= 0 else ("WARNING" if pct >= 80 else "GOOD")
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
    st.subheader("📊 الرسوم البيانية (الشريطي والدائري)")

    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_bar = px.bar(df_result, x="قطع الغيار / الفلاتر", y=["الساعات المنقضية (ساعة)", "المدة المتبقية (ساعة)"], title="مقارنة الساعات المنقضية والمتبقية", barmode="stack")
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_col2:
        fig_pie = px.pie(df_result, names="الحالة الفنية", title="توزيع حالة الجاهزية (Pie Chart)", color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"])
        st.plotly_chart(fig_pie, use_container_width=True)

    st.divider()

    # دالة توليد التقرير المضمونة والآمنة 100% والمتوافقة مع FPDF2
    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("COMPREHENSIVE MAINTENANCE REPORT")
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)}", ln=True)
        pdf.cell(0, 5, f"Total Run Hours: {run_hours} hrs | Target Hours: {future_run_hours} hrs", ln=True)
        pdf.cell(0, 5, f"Capacity: {gen_kw} kW | Current Load: {load_kw} kW ({load_percentage:.1f}%)", ln=True)
        pdf.ln(3)

        # إضافة صورة المولد أو قطعة الغيار المرفوعة من الذاكرة
        if saved_img_path and os.path.exists(saved_img_path):
            try:
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 5, "Attached Equipment / Part Photo:", ln=True)
                pdf.image(saved_img_path, x=60, y=pdf.get_y(), w=90)
                pdf.ln(55)
            except Exception:
                pass

        # إضافة جدول قطع الغيار
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "Approved Spare Parts Lifespan & Maintenance Schedule:", ln=True)
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

        # إضافة الرسوم البيانية باستخدام BytesIO مباشرة بدون ملفات مؤقتة
        try:
            pdf.add_page()
            
            # الرسم البياني الشريطي
            fig1, ax1 = plt.subplots(figsize=(6.5, 2.5))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            ax1.bar(p_short, df_result["الساعات المنقضية (ساعة)"].values, label="Used", color="#d9534f")
            ax1.bar(p_short, df_result["المدة المتبقية (ساعة)"].values, bottom=df_result["الساعات المنقضية (ساعة)"].values, label="Remaining", color="#28a745")
            ax1.set_title("Spare Parts Lifespan Overview", fontsize=9)
            plt.xticks(rotation=35, ha="right", fontsize=7)
            plt.tight_layout()
            
            buf_bar = io.BytesIO()
            plt.savefig(buf_bar, format='png', dpi=200)
            plt.close(fig1)
            buf_bar.seek(0)
            
            # حفظ مؤقت للرسم البياني لإدراجه
            c_bar_path = f"temp_bar_{uuid.uuid4().hex}.png"
            with open(c_bar_path, "wb") as f:
                f.write(buf_bar.read())
            pdf.image(c_bar_path, x=15, y=20, w=170)
            if os.path.exists(c_bar_path):
                os.remove(c_bar_path)

            # الرسم البياني الدائري
            fig2, ax2 = plt.subplots(figsize=(5, 2.5))
            sc = df_result["الحالة الفنية"].value_counts()
            ax2.pie(sc.values, labels=[sanitize_latin_only(k) for k in sc.index], autopct='%1.1f%%', colors=['#28a745', '#ffc107', '#dc3545'])
            ax2.set_title("Parts Readiness Distribution (Pie Chart)", fontsize=9)
            plt.tight_layout()
            
            buf_pie = io.BytesIO()
            plt.savefig(buf_pie, format='png', dpi=200)
            plt.close(fig2)
            buf_pie.seek(0)

            c_pie_path = f"temp_pie_{uuid.uuid4().hex}.png"
            with open(c_pie_path, "wb") as f:
                f.write(buf_pie.read())
            pdf.image(c_pie_path, x=25, y=105, w=150)
            if os.path.exists(c_pie_path):
                os.remove(c_pie_path)

        except Exception:
            pass

        # تنظيف صورة المولد المرفوعة المؤقتة
        if saved_img_path and os.path.exists(saved_img_path):
            try:
                os.remove(saved_img_path)
            except Exception:
                pass

        # إرجاع مخرجات الـ PDF بشكل آمن ومتوافق مع جميع إصدارات FPDF
        out = pdf.output()
        if isinstance(out, (bytes, bytearray)):
            return bytes(out)
        else:
            return out.encode('latin1')

    # --- زر التجهيز والتنزيل المباشر لمنع الخطأ في الجوال ---
    st.divider()
    
    col_prep, col_down = st.columns([1, 2])
    
    with col_prep:
        if st.button("🔄 تجهيز ملف التقرير (PDF)", use_container_width=True):
            with st.spinner("جاري إعداد التقرير والتأكد من البيانات..."):
                st.session_state.pdf_data = generate_full_pdf_bytes()
                st.success("✅ تم تجهيز التقرير بنجاح! يمكنك التنزيل الآن.")

    with col_down:
        if "pdf_data" in st.session_state and st.session_state.pdf_data:
            st.download_button(
                label="🖨️ تنزيل التقرير الفني الشامل المعتمد (PDF)",
                data=st.session_state.pdf_data,
                file_name=f"Comprehensive_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.info("💡 يرجى الضغط على 'تجهيز ملف التقرير' أولاً لتوليد الملف ثم تنزيله.")

# =========================================================
# التطبيق 2: المساعد الذكي
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والبحث الآلي":
    st.title("🤖 المساعد الذكي للبحث الهندسي")
    q = st.text_input("أدخل كود العطل أو اسم القطعة:")
    if st.button("بحث في المصادر"):
        if q:
            res = search_engineering_resources(q)
            st.success("نتائج البحث:")
            for b in res["books"]:
                st.markdown(f"- **[{b['title']}]({b['link']})**")
            for w in res["web_articles"]:
                st.markdown(f"- **[{w['title']}]({w['link']})**")

# =========================================================
# التطبيق 3: فحص المعدات ورفع الصور
# =========================================================
elif selected_app == "🔍 3. فحص المعدات ورفع الصور":
    st.title("🔍 فحص المعدات والمقارنة البصرية")
    img_up = st.file_uploader("رفع صورة الفحص:", type=["png", "jpg", "jpeg"])
    if img_up:
        st.image(Image.open(img_up), caption="الصورة المرفوعة للفحص")

# =========================================================
# التطبيق 4: مكتبتي الفنية
# =========================================================
elif selected_app == "📚 4. مكتبتي الفنية المحفوظة":
    st.title("📚 مكتبتك الفنية المحفوظة")
    st.info("سجل المحفوظات الفنية فارغ حالياً.")
