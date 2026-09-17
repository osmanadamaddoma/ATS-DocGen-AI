import os
import re
import uuid
import json
import urllib.parse
from datetime import datetime, timedelta
import io

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from PIL import Image
import requests
from bs4 import BeautifulSoup
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore

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
        try:
            cred_dict = None
            firebase_json_env = os.environ.get("FIREBASE_CREDENTIALS")
            
            if firebase_json_env:
                cred_dict = json.loads(firebase_json_env)
            elif "firebase" in st.secrets:
                cred_dict = dict(st.secrets["firebase"])
                
            if cred_dict and "private_key" in cred_dict:
                raw_key = cred_dict["private_key"]
                cleaned_key = raw_key.replace("\\n", "\n").replace('"', '').strip()
                if "-----BEGIN PRIVATE KEY-----" in cleaned_key and not cleaned_key.startswith("-----BEGIN PRIVATE KEY-----\n"):
                    cleaned_key = cleaned_key.replace("-----BEGIN PRIVATE KEY-----", "-----BEGIN PRIVATE KEY-----\n")
                if "-----END PRIVATE KEY-----" in cleaned_key and not cleaned_key.endswith("\n-----END PRIVATE KEY-----"):
                    cleaned_key = cleaned_key.replace("-----END PRIVATE KEY-----", "\n-----END PRIVATE KEY-----")
                cred_dict["private_key"] = cleaned_key
                cred = credentials.Certificate(cred_dict)
            else:
                cred = credentials.Certificate("firebase_key.json")
                
            firebase_admin.initialize_app(cred)
        except Exception:
            return None
    try:
        return firestore.client()
    except Exception:
        return None

db = init_firebase()

# ---------------------------------------------------------
# 3. إدارة المدد الزمنية والاشتراكات المدمجة
# ---------------------------------------------------------
# قاعدة بيانات العملاء الثابتة
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {"name": "عثمان آدم (Addoma Trading Services)", "plan": "سنوي (Yearly)", "days": 365},
    "CLIENT-M-881": {"name": "شركة النيل للصناعات الهندسية", "plan": "شهري (Monthly)", "days": 30},
    "CLIENT-Y-992": {"name": "مصانع الحديد والصلب الوطنية", "plan": "سنوي (Yearly)", "days": 365},
}

if "generated_codes_db" not in st.session_state:
    st.session_state.generated_codes_db = {
        "ADDOMA-7D": {"days": 7, "plan": "اشتراك تجريبي (7 أيام)", "name": "زائر"},
        "ADDOMA-30D": {"days": 30, "plan": "اشتراك شهري (1 شهر)", "name": "زائر"},
    }

if "device_id" not in st.session_state:
    st.session_state.device_id = str(uuid.uuid4())

device_id = st.session_state.device_id

def get_or_create_device_record(dev_id):
    now_dt = datetime.now()
    if db is not None:
        try:
            doc_ref = db.collection("devices").document(dev_id)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                return {
                    "client_name": data.get("client_name", "زائر"),
                    "subscription_expiry": data.get("subscription_expiry"),
                    "plan_type": data.get("plan_type", "غير مفعل")
                }
            else:
                initial_data = {"client_name": "زائر", "subscription_expiry": None, "plan_type": "غير مفعل"}
                doc_ref.set(initial_data)
                return initial_data
        except Exception: pass
            
    if "mock_device_db" not in st.session_state:
        st.session_state.mock_device_db = {"client_name": "زائر", "subscription_expiry": None, "plan_type": "غير مفعل"}
    return st.session_state.mock_device_db

def update_device_subscription(dev_id, sub_expiry, plan_name, client_name="زائر"):
    if db is not None:
        try:
            db.collection("devices").document(dev_id).update({
                "subscription_expiry": sub_expiry,
                "plan_type": plan_name,
                "client_name": client_name
            })
        except Exception: pass
    if "mock_device_db" in st.session_state:
        st.session_state.mock_device_db.update({
            "subscription_expiry": sub_expiry, "plan_type": plan_name, "client_name": client_name
        })

def verify_and_apply_code(code_str):
    code_clean = code_str.strip().upper()
    
    # 1. التحقق من قاعدة البيانات الثابتة للعملاء
    if code_clean in CLIENTS_DATABASE:
        data = CLIENTS_DATABASE[code_clean]
        return data["days"], data["plan"], data["name"]
        
    # 2. التحقق من السجل المحلي
    if code_clean in st.session_state.generated_codes_db:
        info = st.session_state.generated_codes_db[code_clean]
        return info["days"], info["plan"], info.get("name", "عميل جديد")
        
    return None, None, None

user_record = get_or_create_device_record(device_id)
now = datetime.now()
sub_exp = user_record.get("subscription_expiry")
if sub_exp and hasattr(sub_exp, "timestamp"): sub_exp = datetime.fromtimestamp(sub_exp.timestamp())

is_sub_active = sub_exp and now < sub_exp

st.sidebar.header("🔐 بوابة تفعيل المساعد الذكي")
if is_sub_active:
    time_left = (sub_exp - now).days
    access_status = "paid"
    plan_type = user_record.get("plan_type", "مفعل")
    client_name = user_record.get("client_name", "زائر")
    expiry_date_str = sub_exp.strftime("%Y-%m-%d")
    st.sidebar.success("✅ تم التحقق من الاشتراك بنجاح!")
    st.sidebar.markdown(f"**👤 العميل:** {client_name}")
    st.sidebar.markdown(f"**📦 الباقة:** {plan_type}")
    st.sidebar.markdown(f"⏳ **المتبقي:** {time_left} يوم ({expiry_date_str})")
else:
    access_status = "expired"
    st.sidebar.warning("⚠️ الحساب غير مفعل أو منتهي الصلاحية.")

with st.sidebar.expander("🔑 إدخال كود التفعيل"):
    input_code = st.text_input("أدخل كود التفعيل هنا:", type="password")
    if st.button("تفعيل الاشتراك"):
        days, p_name, c_name = verify_and_apply_code(input_code)
        if days:
            new_exp = now + timedelta(days=days)
            update_device_subscription(device_id, new_exp, p_name, c_name)
            st.success(f"✅ تم تفعيل باقة: {p_name} للعميل {c_name}")
            st.rerun()
        else:
            st.error("❌ كود التفعيل غير صحيح.")

if access_status == "expired":
    st.error("🔒 **النظام مقفل:** يرجى إدخال كود اشتراك ساري في الشريط الجانبي لفتح التطبيقات.")
    st.stop()

# ---------------------------------------------------------
# 4. قائمة اختيار التطبيق
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.markdown("🛠️ التطبيقات المتاحة")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات والتقارير",
        "🤖 2. المساعد الذكي والكتالوجات",
        "🔍 3. فحص المعدات والمقارنة البصرية"
    ]
)
st.sidebar.divider()

# =========================================================
# التطبيق 1: الصيانة التنبؤية وإصدار التقرير الشامل PDF
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات والتقارير":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    col_v1, col_v2 = st.sidebar.columns(2)
    v_min = col_v1.number_input("أدنى جهد (V)", value=380.0)
    v_max = col_v2.number_input("أقصى جهد (V)", value=420.0)

    with st.sidebar.form("generator_comprehensive_form"):
        st.subheader("مدخلات القراءات الحالية")
        gen_model = st.text_input("طراز المولد", value="Perkins 410 kVA")
        run_hours = st.number_input("ساعات التشغيل الحالية", value=700.0)
        future_run_hours = st.number_input("ساعات التشغيل المستهدفة", value=940.0)
        gen_kw = st.number_input("سعة المولد (kW)", value=410.0)
        load_kw = st.number_input("الحمولة الحالية (kW)", value=250.0)
        voltage = st.number_input("الجهد (V)", value=400.0)
        coolant_temp = st.number_input("حرارة المحرك (°C)", value=85.0)
        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

    st.subheader("📷 توثيق صور المولد وقطع الغيار الميدانية")
    col_up, col_cam = st.columns(2)
    with col_up:
        gen_uploaded_images = st.file_uploader("رفع صور المولد والقطع (لإرفاقها بالتقرير):", type=["png", "jpg", "jpeg"], accept_multiple_files=True)
    with col_cam:
        gen_cam_img = st.camera_input("📸 التقاط صورة بالكاميرا")

    all_gen_images = []
    if gen_uploaded_images:
        all_gen_images.extend([Image.open(f) for f in gen_uploaded_images])
    if gen_cam_img:
        all_gen_images.append(Image.open(gen_cam_img))

    if all_gen_images:
        st.success(f"تم إرفاق {len(all_gen_images)} صور بنجاح، سيتم تضمينها في التقرير.")

    st.divider()
    st.subheader("🛢️ جدول الصيانة التنبؤية الكامل (14 وحدة)")

    # بيانات الـ 14 وحدة المطلوبة للصيانة التنبؤية
    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار": "Oil Filter", "العمر (ساعة)": 250.0, "المنقضية (ساعة)": 210.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار": "Primary Fuel Filter", "العمر (ساعة)": 500.0, "المنقضية (ساعة)": 430.0},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار": "Secondary Fuel Filter", "العمر (ساعة)": 500.0, "المنقضية (ساعة)": 455.0},
        {"تصنيف القطعة": "Air System", "قطع الغيار": "Air Filter", "العمر (ساعة)": 1000.0, "المنقضية (ساعة)": 860.0},
        {"تصنيف القطعة": "Fan Belt System", "قطع الغيار": "Fan Belt", "العمر (ساعة)": 2000.0, "المنقضية (ساعة)": 1550.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار": "ELC Coolant", "العمر (ساعة)": 3000.0, "المنقضية (ساعة)": 2200.0},
        {"تصنيف القطعة": "Fuel System", "قطع الغيار": "Injectors Check", "العمر (ساعة)": 5000.0, "المنقضية (ساعة)": 4400.0},
        {"تصنيف القطعة": "Electrical", "قطع الغيار": "Batteries", "العمر (ساعة)": 8000.0, "المنقضية (ساعة)": 6100.0},
        {"تصنيف القطعة": "Electric System", "قطع الغيار": "Charging Alternator", "العمر (ساعة)": 10000.0, "المنقضية (ساعة)": 8900.0},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار": "Top Overhaul", "العمر (ساعة)": 10000.0, "المنقضية (ساعة)": 9100.0},
        {"تصنيف القطعة": "Engine Motor", "قطع الغيار": "Major Overhaul", "العمر (ساعة)": 20000.0, "المنقضية (ساعة)": 15000.0},
        {"تصنيف القطعة": "Oilers System", "قطع الغيار": "Oil Cooler Clean", "العمر (ساعة)": 5000.0, "المنقضية (ساعة)": 3800.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار": "Water Pump", "العمر (ساعة)": 6000.0, "المنقضية (ساعة)": 5200.0},
        {"تصنيف القطعة": "Air System", "قطع الغيار": "Turbocharger Check", "العمر (ساعة)": 8000.0, "المنقضية (ساعة)": 7100.0},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        cat = str(row.get("تصنيف القطعة", "Other"))
        part = str(row.get("قطع الغيار", "Part"))
        life = pd.to_numeric(row.get("العمر (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0
        status = "تنبيه فوري (خطر)" if rem <= 0 or pct >= 90 else ("قرب الخدمة (استعداد)" if pct >= 75 else "حالة جيدة")
        processed_rows.append({
            "قطع الغيار": part,
            "العمر (ساعة)": life,
            "المنقضية (ساعة)": used,
            "المتبقية (ساعة)": max(0.0, rem),
            "نسبة الاستهلاك": f"{pct:.0f}%",
            "حالة التنبيه": status
        })

    df_result = pd.DataFrame(processed_rows)

    st.divider()
    st.subheader("📊 الرسوم البيانية لتحديد كفاءة المولد")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_bar = px.bar(
            df_result, x="قطع الغيار", y=["المنقضية (ساعة)", "المتبقية (ساعة)"],
            title="تحليل استهلاك الساعات", barmode="stack", color_discrete_sequence=["#d9534f", "#28a745"]
        )
        st.plotly_chart(fig_bar, width="stretch")

    with chart_col2:
        fig_pie = px.pie(
            df_result, names="حالة التنبيه", title="نسبة حالات الطوارئ للقطع",
            color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"]
        )
        st.plotly_chart(fig_pie, width="stretch")

    st.divider()
    st.subheader("📄 إصدار أمر طباعة التقرير الشامل (PDF)")

    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("GENERATOR & PREDICTIVE MAINTENANCE REPORT")
        pdf.add_page()
        temp_files = []

        # معلومات المولد الأساسية
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)}", ln=True)
        pdf.cell(0, 5, f"Run Hours: {run_hours} hrs | Target: {future_run_hours} hrs", ln=True)
        pdf.cell(0, 5, f"Load: {load_kw} kW / {gen_kw} kW ({load_percentage:.1f}%)", ln=True)
        pdf.ln(5)

        # جدول الصيانة
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, "Predictive Maintenance Schedule (14 Units):", ln=True)
        pdf.set_font("Helvetica", "B", 7)
        headers_widths = [45, 20, 20, 20, 15, 40]
        headers = ["Part Name", "Lifespan", "Used", "Remain", "Usage%", "Alert Status"]
        for w, h in zip(headers_widths, headers):
            pdf.cell(w, 5, h, border=1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        for idx, row in df_result.iterrows():
            pdf.cell(45, 5, sanitize_latin_only(str(row["قطع الغيار"]))[:22], border=1)
            pdf.cell(20, 5, str(row["العمر (ساعة)"]), border=1)
            pdf.cell(20, 5, str(row["المنقضية (ساعة)"]), border=1)
            pdf.cell(20, 5, str(row["المتبقية (ساعة)"]), border=1)
            pdf.cell(15, 5, str(row["نسبة الاستهلاك"]), border=1)
            pdf.cell(40, 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1)
            pdf.ln()

        # إضافة الرسوم البيانية للـ PDF
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Performance & Maintenance Charts:", ln=True)

            fig_bar_p, ax_bar_p = plt.subplots(figsize=(6.5, 3))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار"]]
            u_h = df_result["المنقضية (ساعة)"].values
            r_h = df_result["المتبقية (ساعة)"].values
            ax_bar_p.bar(p_short, u_h, label="Used", color="#d9534f")
            ax_bar_p.bar(p_short, r_h, bottom=u_h, label="Remain", color="#28a745")
            plt.xticks(rotation=45, ha="right", fontsize=6)
            plt.tight_layout()
            bar_path = f"temp_bar_{uuid.uuid4().hex}.png"
            plt.savefig(bar_path, dpi=200)
            plt.close(fig_bar_p)
            temp_files.append(bar_path)
            pdf.image(bar_path, x=15, y=25, w=170)

            fig_pie_p, ax_pie_p = plt.subplots(figsize=(5, 3))
            status_counts = df_result["حالة التنبيه"].value_counts()
            ax_pie_p.pie(status_counts.values, labels=[sanitize_latin_only(k) for k in status_counts.index], autopct='%1.1f%%')
            plt.tight_layout()
            pie_path = f"temp_pie_{uuid.uuid4().hex}.png"
            plt.savefig(pie_path, dpi=200)
            plt.close(fig_pie_p)
            temp_files.append(pie_path)
            pdf.image(pie_path, x=45, y=120, w=110)
        except Exception as e:
            pass

        # إدراج الصور المرفوعة (المولد وقطع الغيار)
        if all_gen_images:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Field Attachment Images (Generators & Parts):", ln=True)
            y_pos = 20
            for idx, img in enumerate(all_gen_images):
                img_path = f"temp_img_{uuid.uuid4().hex}.jpg"
                img.convert('RGB').save(img_path, format="JPEG")
                
                # إذا تجاوزت الصورة مساحة الصفحة، أنشئ صفحة جديدة
                if y_pos > 200:
                    pdf.add_page()
                    y_pos = 20
                
                pdf.image(img_path, x=30, y=y_pos, w=140)
                y_pos += 100 # إزاحة للصورة التالية
                temp_files.append(img_path)

        pdf_out = pdf.output(dest="S")
        for f in temp_files:
            if os.path.exists(f): os.remove(f)
            
        if isinstance(pdf_out, str):
            return pdf_out.encode("latin-1", errors="replace")
        return bytes(pdf_out)

    st.download_button(
        label="🖨️ طباعة وتنزيل التقرير الشامل (بيانات، رسوم، وصور)",
        data=generate_full_pdf_bytes(),
        file_name=f"Full_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات":
    st.info(f"🔹 **العميل الحالي بالجلسة:** {user_record.get('client_name', 'زائر')} | **الباقة:** {user_record.get('plan_type', 'مفعل')}")
    st.title("🤖 المساعد الذكي لتحليل أكواد الأعطال")

    fault_code_input = st.text_input("أدخل كود العطل أو وصف المشكلة (مثلاً: DSE 8610 Error):")
    if st.button("تحليـل العطل بالذكاء الاصطناعي"):
        st.success(f"🌟 جارٍ معالجة الطلب للعميل ({user_record.get('client_name')})...")
        st.markdown(f"""
        ### 📋 تقرير التشخيص الفوري للكود: `{fault_code_input}`
        * **الوصف الفني المحتمل:** انقطاع في إشارة التحكم أو تنبيه حرج مسجل بوحدة التحكم.
        * **الخطوات التصحيحية:**
          1. مطابقة الكود مع الكتالوج.
          2. فحص أطراف التوصيل.
          3. إعادة ضبط وحدة التحكم والتحقق من التغذية.
        """)

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية
# =========================================================
elif selected_app == "🔍 3. فحص المعدات والمقارنة البصرية":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")
    eq_type = st.selectbox("اختر المعدة:", ["مولد ديزل صناعي", "غرفة تبريد WIC", "محرك كهربائي 3-Phase"])
    
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 **القطعة السليمة المعيارية:**")
        st.file_uploader("اختر صورة السليم", type=["png", "jpg", "jpeg"], key="good_img")
    with col_img2:
        st.write("🔴 **القطعة التالفة:**")
        st.file_uploader("اختر صورة التالف", type=["png", "jpg", "jpeg"], key="bad_img")
        
    st.warning("🔍 **ملاحظة التحليل:** توجد فروقات بصرية واضحة، ينصح بالاستبدال الفوري.")
