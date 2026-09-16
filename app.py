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
        self.cell(0, 4, "Addoma Trading Services (الدومة للخدمات التجارية) - Engineering Platform", ln=True, align="C")
        self.line(10, 20, 200, 20)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 5, "Prepared by: Osman Adam Addoma (عثمان آدم أدومة)", ln=True, align="C")
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

# ---------------------------------------------------------
# لوحة عرض الاشتراكات
# ---------------------------------------------------------
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
# 4. قائمة اختيار التطبيق (3 في 1)
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
    st.subheader("🛢️ جدول خدمة زيت المحرك والمدد الافتراضية للفلاتر وقطع الغيار")

    effective_hours = future_run_hours if future_run_hours > 0 else run_hours
    hours_since_oil_change = max(0.0, effective_hours - last_oil_change_hours)
    hours_until_next_oil_change = oil_change_interval - hours_since_oil_change
    oil_usage_pct = (hours_since_oil_change / oil_change_interval) * 100 if oil_change_interval > 0 else 0

    col_o1, col_o2, col_o3 = st.columns(3)
    col_o1.metric("المدة المنقضية للزيت", f"{hours_since_oil_change:.1f} hrs")
    col_o2.metric("المدة المتبقية للخدمة", f"{max(0.0, hours_until_next_oil_change):.1f} hrs")
    col_o3.metric("نسبة استهلاك فترة الزيت", f"{oil_usage_pct:.0f}%")

    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Engine Oil & Filter", "العمر الافتراضي (ساعة)": float(oil_change_interval), "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": float(hours_since_oil_change)},
        {"تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": float(effective_hours)},
    ]

    df_parts_input = pd.DataFrame(base_parts_data)
    # استخدام width="stretch" بدلاً من use_container_width
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch", key="parts_editor")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        cat = str(row.get("تصنيف القطعة", "Other"))
        part = str(row.get("قطع الغيار / الفلاتر", "Part"))
        life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0

        status = "EXPIRED (انقضاء المدة)" if rem <= 0 else ("WARNING (اقتراب الخدمة)" if pct >= 90 else "GOOD (جيدة)")
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
    st.subheader("📊 رسومات وتأطير أداء الآليات وقطع الغيار")

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
            names="الحالة الفنية",
            title="توزيع جاهزية ونسبة سلامة قطع الغيار",
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
        pdf.cell(0, 6, "1. Oil & Filter Service Summary:", ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"- Default Oil Change Interval: {oil_change_interval} hrs", ln=True)
        pdf.cell(0, 5, f"- Hours Used on Oil: {hours_since_oil_change} hrs ({oil_usage_pct:.0f}%)", ln=True)
        pdf.cell(0, 5, f"- Remaining Hours to Change: {max(0.0, hours_until_next_oil_change)} hrs", ln=True)
        pdf.ln(3)

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "2. Predictive Maintenance & Parts Lifespan Table:", ln=True)
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

        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "3. Performance & Maintenance Visual Charts:", ln=True)

            fig, ax = plt.subplots(figsize=(6.5, 3))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            u_h = df_result["الساعات المنقضية (ساعة)"].values
            r_h = df_result["المدة المتبقية (ساعة)"].values

            ax.bar(p_short, u_h, label="Used Hours", color="#d9534f")
            ax.bar(p_short, r_h, bottom=u_h, label="Remaining Hours", color="#28a745")
            ax.set_title("Parts Lifespan Overview (Hours)", fontsize=9)
            plt.xticks(rotation=35, ha="right", fontsize=7)
            plt.tight_layout()

            chart_path = f"temp_chart_{datetime.now().timestamp()}.png"
            plt.savefig(chart_path, dpi=200)
            plt.close(fig)
            temp_files.append(chart_path)

            pdf.image(chart_path, x=15, y=30, w=170)
        except Exception:
            pass

        pdf_bytes = pdf.output(dest="S")
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

        return pdf_bytes.encode("latin-1", errors="replace")

    st.download_button(
        label="🖨️ إصدار التقرير الفني الشامل والرسوم البيانية (PDF)",
        data=generate_full_pdf_bytes(),
        file_name=f"Full_Maintenance_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf"
    )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات وقراءة الأكواد
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي، مكتبة الكتالوجات وقراءة الأكواد")

    tab1, tab2, tab3 = st.tabs(["💬 الاستشارات والتحليل", "📚 رفع وتصفح الكتالوجات", "📷 رفع وقراءة الأكواد (QR/Barcode)"])

    # --- TAB 1: الاستشارات والتحليل ---
    with tab1:
        st.subheader("💡 تحليل العطل واستخراج التقرير")
        user_input = st.text_area("أدخل تفاصيل العطل الفني:", height=100, placeholder="مثال: ارتفاع حرارة المحرك مع انخفاض ضغط الزيت...")

        if st.button("تحليل العطل وإنشاء التقرير 🔍"):
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

            st.subheader("📄 إصدار تقرير الاستشارات PDF")
            def generate_ai_pdf():
                pdf = ComprehensivePDF("AI DIAGNOSTIC & MAINTENANCE REPORT")
                pdf.add_page()
                pdf.set_font("Helvetica", "", 9)
                for log in st.session_state.ai_logs:
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(0, 5, f"Date: {log['date']}", ln=True)
                    pdf.set_font("Helvetica", "", 9)
                    pdf.cell(0, 5, f"Query: {sanitize_latin_only(log['query'])}", ln=True)
                    pdf.ln(3)
                return pdf.output(dest="S").encode("latin-1", errors="replace")

            st.download_button(
                label="🖨️ إصدار تقرير الاستشارات الفنية (PDF)",
                data=generate_ai_pdf(),
                file_name=f"AI_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf"
            )

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
                mime="application/pdf"
            )

    # --- TAB 3: قراءة الأكواد (QR/Barcode) ---
    with tab3:
        st.subheader("📷 رفع وتحليل صورة الكود (QR Code / Barcode)")
        uploaded_code_img = st.file_uploader("رفع صورة الكود أو الباركود الخارجي للقطعة:", type=["png", "jpg", "jpeg"])

        if uploaded_code_img is not None:
            image = Image.open(uploaded_code_img)
            # استبدال المعاملات القديمة لضبط عرض الصورة
            st.image(image, caption="الصورة المرفوعة للقطعة/الكود", width="stretch")
            
            if decode_qr is not None:
                decoded_objects = decode_qr(image)
                if decoded_objects:
                    for obj in decoded_objects:
                        st.success(f"🔑 **نتيجة قراءة الكود:** `{obj.data.decode('utf-8')}` (نوع الكود: {obj.type})")
                else:
                    st.warning("⚠️ لم يتم العثور على باركود أو QR ذكي واضح داخل الصورة، يمكنك إدخال الرقم يدوياً.")
            else:
                st.info("💡 **القراءة اليدوية:** تم رفع الصورة بنجاح. أداة تحليل الباركود التلقائي غير مفعلة في البيئة الحالية.")

# =========================================================
# التطبيق 3: فحص المعدات والمقارنة البصرية (تالف / سليم)
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات والمقارنة البصرية (تالف/سليم)":
    st.title("🔍 نظام فحص المعدات والمقارنة البصرية لقطع الغيار")

    # إضافة المعدات المحددة الخاصة بالعمل
    eq_type = st.selectbox("اختر المعدة المراد فحصها:", [
        "مولد ديزل صناعي (Perkins/Cummins)", 
        "غرفة تبريد Porkka WIC 10", 
        "غرفة تبريد Porkka WIC 40", 
        "محرك كهربائي 3-Phase"
    ])

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
    
    if "مولد" in eq_type:
        c1 = st.checkbox("1. تسريب زيت أو وقود أسفل المحرك")
        c2 = st.checkbox("2. انخفاض سائل التبريد (Coolant)")
        c3 = st.checkbox("3. أطراف البطارية تحتاج نظافة/إحكام")
        checklist = [("تسريب زيت/وقود", c1), ("انخفاض سائل التبريد", c2), ("أطراف البطارية", c3)]
        if c1: st.error("🚨 **تأكيد:** افحص وجه الكارتير وفلاتر الزيت.")
    
    elif "غرفة تبريد" in eq_type:
        r1 = st.checkbox("1. تكوّن الثلج على ملف المبخر (Evaporator)")
        r2 = st.checkbox("2. توقف مروحة المكثف الخارجية")
        checklist = [("تراكم الثلج", r1), ("مروحة المكثف", r2)]
        if r1: st.error("🚨 **تأكيد:** افحص دورة الإذابة وسخانات Defrost.")
    
    elif "محرك" in eq_type:
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
        mime="application/pdf"
    )
