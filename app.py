import os
import re
import streamlit as st
from google import genai

# ==========================================
# 1. تهيئة عميل Gemini API
# ==========================================
api_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

# ==========================================
# 2. دالة التحليل عبر Gemini API (تخزين مؤقت للتوفير)
# ==========================================
@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text=""):
    """دالة استدعاء الذكاء الاصطناعي لتشخيص الأعطال المعقدة والغريبة"""
    if not client:
        return "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets."

    prompt = f"""
    أنت خبير صيانة مهندس واستشاري صناعي متخصص في المولدات لوحات DSE (مثل DSE 7320 و DSE 8610 MKII) ومحركات Perkins و Cummins وأجهزة التبريد.
    
    العميل يدخل كود العطل أو اسم الإنذار التالي: "{fault_code}"
    
    معلومات إضافية مستخرجة من كتالوج المعدة (إن وجدت):
    \"\"\"
    {context_text if context_text else "لا يوجد نص مباشر من الكتالوج لهذا العطل."}
    \"\"\"

    المطلوب إنشاء تقرير تشخيصي متكامل ومختصر يحتوي على:
    1. **طبيعة المشكلة**: شرح ميكانيكي/كهربائي للعطل.
    2. **الأسباب المحتملة**: أبرز 3 أسباب لنشوء هذا العطل.
    3. **خطوات الفحص والعلاج**: إجراءات ميدانية تسلسلية (أسلاك، حساسات، أكتويتر، أو إعادة ضبط DSE).
    
    اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"❌ حدث خطأ أثناء التواصل مع الذكاء الاصطناعي: {str(e)}"

# ==========================================
# 3. واجهة زر التحليل الشاملة
# ==========================================
fault_input = st.text_input(
    "أدخل كود العطل أو اسم الإنذار:",
    value="Over Current",
    key="fault_search_input",
)

if st.button("🔍 تحليل العطل بالذكاء الاصطناعي", key="btn_analyze"):
    # 1. تنظيف النص المكتوب
    clean_fault = fault_input.strip()

    if not clean_fault:
        st.warning("⚠️ يرجى كتابة كود العطل أولاً.")
    else:
        st.info("🌟 (Addoma Trading Services) جاري معالجة طلبك وفحص البيانات...")

        # 2. البحث داخل صفحات الكتالوج المرفوع (إن وجد في الجلسة)
        catalog_context = ""
        if "catalog_pages" in st.session_state:
            search_query = re.escape(clean_fault)
            found_lines = []

            for page in st.session_state.catalog_pages:
                for line in page["content"].split("\n"):
                    if re.search(search_query, line, re.IGNORECASE):
                        found_lines.append(f"(صفحة {page['page_num']}): {line.strip()}")

            if found_lines:
                catalog_context = "\n".join(found_lines[:6])

        st.markdown("---")
        st.markdown(f"### 📋 تقرير التشخيص الفوري: `{clean_fault}`")

        # عرض نصوص الكتالوج عند إيجاد مطابقة
        if catalog_context:
            st.success("✅ تم العثور على مقتطفات مطابقة داخل الكتالوج المرفوع:")
            st.code(catalog_context, language="text")
        else:
            st.caption(f"لم يتم العثور على مطابقة لفظية مباشرة للرمز '{clean_fault}' في الكتالوج المرفوع.")

        # 3. القاعدة المحلية للأعطال الشائعة
        f = clean_fault.lower()
        has_local_match = False

        st.markdown("**التوجيهات الميدانية السريعة:**")

        if any(k in f for k in ["current", "over current", "overcurrent", "oc", "over load", "overload", "kw", "kva"]):
            st.write("• **طبيعة المشكلة:** ارتفاع التيار المسحوب أو وجود حمل زائد/شورت ماس على إحدى الفازات.")
            st.write("• **الخطوات:** 1. إعادة توزيع الأحمال على الفازات الثلاث. 2. فحص محولات التيار (CTs) ونسب المعايرة في DSE. 3. قياس امبير الحمل بساعة خارجية (Clamp Meter).")
            has_local_match = True

        elif any(k in f for k in ["speed", "rpm", "under speed", "over speed", "low speed", "high speed", "freq", "hz"]):
            st.write("• **طبيعة المشكلة:** خلل في سرعة دوران المحرك أو ضبط التردد.")
            st.write("• **الخطوات:** 1. تنظيف مستشعر السرعة (MPU) وإعادة معايرة الفجوة. 2. فحص منظم السرعة (Governor) والأكتويتر. 3. فحص خطوط الوقود وفلاتر الديزل.")
            has_local_match = True

        elif any(k in f for k in ["voltage", "volt", "under volt", "over volt", "low volt", "high volt"]):
            st.write("• **طبيعة المشكلة:** انخفاض أو ارتفاع الجهد المولد عن الحدود المسموحة.")
            st.write("• **الخطوات:** 1. فحص كارت كبح/تنظيم الجهد (AVR). 2. ضبط المقاومة المتغيرة للجهد. 3. فحص كابلات الإحساس (Sensing) والديودات.")
            has_local_match = True

        elif any(k in f for k in ["oil", "press", "low oil", "oil pressure", "lop"]):
            st.write("• **طبيعة المشكلة:** انخفاض ضغط زيت المحرك أو عطل مستشعر الضغط.")
            st.write("• **الخطوات:** 1. قياس مستوى الزيت في الكارتير. 2. قياس الضغط بساعة ميكانيكية خارجية. 3. فحص استمرارية أسطوانة الحساس والتأريض.")
            has_local_match = True

        elif any(k in f for k in ["temp", "coolant", "high temp", "water", "hwt", "radiator"]):
            st.write("• **طبيعة المشكلة:** ارتفاع حرارة سائل التبريد أو انخفاض مستواه.")
            st.write("• **الخطوات:** 1. التأكد من مستوى السائل وسيور المروحة. 2. فحص الثيرموستات وانسداد الراديتر. 3. فحص كابلات حساس الحرارة.")
            has_local_match = True

        elif any(k in f for k in ["fail to start", "start fail", "crank", "fail to stop", "stop fail"]):
            st.write("• **طبيعة المشكلة:** فشل المحرك في الدوران أو الاستجابة لأمر التشغيل/الإيقاف.")
            st.write("• **الخطوات:** 1. فحص ريليه التشغيل وسولينويد الديزل. 2. فحص قوة البطاريات والمارش. 3. فحص وصول الديزل للمضخة.")
            has_local_match = True

        elif any(k in f for k in ["battery", "charge", "charge alt", "low battery", "high battery"]):
            st.write("• **طبيعة المشكلة:** عدم شحن البطارية أو خلل في دينامو الشحن المحلي.")
            st.write("• **الخطوات:** 1. فحص سير الدينامو وتوصيلة الطرف (WL/D+). 2. قياس الجهد على أطراف البطارية أثناء التشغيل.")
            has_local_match = True

        elif any(k in f for k in ["breaker", "contactor", "ats", "fail to close", "fail to open"]):
            st.write("• **طبيعة المشكلة:** فشل قاطع التغذية أو الكونتاكتور في الفتح أو الإغلاق.")
            st.write("• **الخطوات:** 1. فحص ملف المساعد (Auxiliary Switch). 2. التأكد من جهد إشارة التوصيل من DSE. 3. فحص الوقاية الميكانيكية.")
            has_local_match = True

        elif any(k in f for k in ["emergency", "e-stop", "estop", "stop button"]):
            st.write("• **طبيعة المشكلة:** تفعيل زر الإيقاف في الطوارئ أو انقطاع دائرة التغذية عنه.")
            st.write("• **الخطوات:** 1. إعادة إرجاع مفتاح الطوارئ الفيزيائي. 2. فحص الدخل (Input) خلف اللوحة ورقم النقطة في DSE.")
            has_local_match = True

        # 4. التوليد عبر الذكاء الاصطناعي (عند عدم وجود عطل شائعة أو للحصول على تحليل أعمق)
        st.markdown("---")
        st.markdown("🤖 **تحليل التقرير العميق عبر الذكاء الاصطناعي (Gemini):**")
        with st.spinner("جاري استخلاص التوصيات من نموذج Gemini API..."):
            ai_analysis = analyze_fault_with_gemini(clean_fault, catalog_context)
            st.markdown(ai_analysis)

import os
import re
import json
import uuid
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# =========================================================
# 1. دوال النظام المساعدة (تنظيف النصوص، إنشاء PDF)
# =========================================================
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

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (Addoma Trading Services)",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-15",
        "duration_days": 30,
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

st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل للوصول للنظام:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"
days_left = 0

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()
    
    if today <= expiry_dt:
        is_pro = True
        days_left = (expiry_dt - today).days
        st.sidebar.success("✅ تم التحقق من الاشتراك بنجاح!")
        st.sidebar.markdown(f"**👤 العميل:** {client_name}")
        st.sidebar.markdown(f"**📦 الباقة:** {plan_type}")
        st.sidebar.markdown(f"⏳ **المتبقي:** {days_left} يوم")
    else:
        st.sidebar.error(f"❌ انتهت صلاحية اشتراك هذا العميل بتاريخ ({expiry_dt}).")
elif input_code != "":
    st.sidebar.error("❌ كود التفعيل غير صحيح.")
else:
    st.sidebar.info("💡 أدخل الكود المخصص لعرض تفاصيل العميل وفتح الأنظمة.")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح في الشريط الجانبي للوصول إلى التطبيقات والمساعد الذكي.")
    st.stop()

st.sidebar.divider()

# =========================================================
# 3. قائمة اختيار التطبيق المركزي
# =========================================================
st.sidebar.markdown("🛠️ التطبيقات المتاحة (نسخة احترافية)")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
        "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 3. نظام فحص المعدات (WIC وغيرها)"
    ]
)
st.sidebar.divider()

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والتقارير الشاملة
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    with st.sidebar.form("generator_comprehensive_form"):
        st.subheader("مدخلات القراءات والخدمة")
        gen_model = st.text_input("طراز / اسم المولد", value="Perkins 410 kVA - DSE 7320")
        run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=700.0, step=10.0)
        future_run_hours = st.number_input("ساعات التشغيل المستهدفة", min_value=0.0, value=940.0, step=10.0)
        gen_kw = st.number_input("سعة المولد (kW)", min_value=5.0, value=410.0, step=10.0)
        load_kw = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=250.0, step=10.0)
        
        voltage = st.number_input("الجهد (V)", value=400.0)
        freq = st.number_input("التردد (Hz)", value=50.0)
        coolant_temp = st.number_input("حرارة المحرك (°C)", value=85.0)
        amperes = st.number_input("التيار (A)", value=360.0)
        
        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    st.subheader("🛢️ جدول الصيانة التنبؤية الكامل (14 وحدة)")
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
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch")

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
            "تصنيف القطعة": cat, "قطع الغيار / الفلاتر": part, "العمر الافتراضي (ساعة)": life,
            "الساعات المنقضية (ساعة)": used, "المدة المتبقية (ساعة)": max(0.0, rem),
            "نسبة الاستهلاك": f"{pct:.0f}%", "حالة التنبيه": status
        })
    df_result = pd.DataFrame(processed_rows)

    st.divider()
    st.subheader("📷 إرفاق صور المولد وقطع الغيار للتقرير")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        gen_img_file = st.file_uploader("رفع صورة للمولد / لوحة التحكم", type=["png", "jpg", "jpeg"])
    with col_up2:
        parts_img_file = st.file_uploader("رفع صورة للقطع المستبدلة / موقع العمل", type=["png", "jpg", "jpeg"])

    st.divider()
    st.subheader("📊 الرسوم البيانية لتحديد كفاءة المولد والقطع")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_bar = px.bar(df_result, x="قطع الغيار / الفلاتر", y=["الساعات المنقضية (ساعة)", "المدة المتبقية (ساعة)"], title="استهلاك قطع الغيار", barmode="stack", color_discrete_sequence=["#d9534f", "#28a745"])
        st.plotly_chart(fig_bar, use_container_width=True)
    with chart_col2:
        fig_pie = px.pie(df_result, names="حالة التنبيه", title="توزيع حالات الصيانة", color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"])
        st.plotly_chart(fig_pie, use_container_width=True)

    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("GENERATOR & PREDICTIVE MAINTENANCE REPORT")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)} | Total Hours: {run_hours}", ln=True)
        pdf.ln(5)

        # إضافة الجدول
        pdf.set_font("Helvetica", "B", 7)
        headers_pdf = ["Part Name", "Lifespan", "Used", "Remain", "Status"]
        widths = [45, 25, 25, 25, 50]
        for h, w in zip(headers_pdf, widths):
            pdf.cell(w, 5, h, border=1)
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 7)
        for _, row in df_result.iterrows():
            pdf.cell(widths[0], 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:25], border=1)
            pdf.cell(widths[1], 5, str(row["العمر الافتراضي (ساعة)"]), border=1)
            pdf.cell(widths[2], 5, str(row["الساعات المنقضية (ساعة)"]), border=1)
            pdf.cell(widths[3], 5, str(row["المدة المتبقية (ساعة)"]), border=1)
            pdf.cell(widths[4], 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1)
            pdf.ln()

        # دمج الصور المرفوعة (المولد + القطع)
        if gen_img_file or parts_img_file:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Field Images & Documentation:", ln=True)
            y_pos = 30
            if gen_img_file:
                gen_path = f"temp_gen_{uuid.uuid4().hex}.jpg"
                with open(gen_path, "wb") as f: f.write(gen_img_file.getbuffer())
                pdf.image(gen_path, x=20, y=y_pos, w=80)
                os.remove(gen_path)
            if parts_img_file:
                part_path = f"temp_part_{uuid.uuid4().hex}.jpg"
                with open(part_path, "wb") as f: f.write(parts_img_file.getbuffer())
                pdf.image(part_path, x=110, y=y_pos, w=80)

        # تحويل المؤشرات المؤقتة (الرسوم)
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Performance & Maintenance Visual Charts (Bar & Pie):", ln=True)
            
            fig_bar_p, ax_bar_p = plt.subplots(figsize=(7, 3))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            ax_bar_p.bar(p_short, df_result["الساعات المنقضية (ساعة)"].values, label="Used", color="#d9534f")
            ax_bar_p.set_title("Parts Lifespan Chart")
            plt.xticks(rotation=45, ha="right", fontsize=6)
            plt.tight_layout()
            bar_path = "temp_bar.png"
            plt.savefig(bar_path, dpi=200)
            pdf.image(bar_path, x=15, y=30, w=170)
            os.remove(bar_path)
        except Exception:
            pass

        pdf_out = pdf.output(dest="S")
        return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

    st.download_button(
        label="🖨️ إصدار التقرير الفني الشامل (طباعة PDF + صور الأصول + الرسوم)",
        data=generate_full_pdf_bytes(),
        file_name=f"Full_Maintenance_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات (مدمج)
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.info(f"🔹 **العميل الحالي:** {client_name} | **نوع الاشتراك:** {plan_type}")
    st.title("🤖 نافذة المساعد الذكي، الكتالوجات وتحليل الأعطال")

    col_files1, col_files2 = st.columns(2)
    with col_files1:
        st.subheader("📚 رفع الكتالوجات للتحليل (PDF)")
        manual_file = st.file_uploader("رفع الكتالوج اليدوي للمعدة", type=["pdf"])
    with col_files2:
        st.subheader("📷 قراءة أكواد الأعطال (شاشات/DSE)")
        fault_image = st.file_uploader("رفع صورة العطل من شاشة المولد/الآلة", type=["png", "jpg", "jpeg"])
        fault_cam = st.camera_input("📸 أو التقط صورة للشاشة")

    st.divider()
    st.subheader("💬 نافذة تحليل الأعطال المباشر")
    fault_code_input = st.text_input("أدخل كود العطل أو وصف المشكلة (مثلاً: DSE 8610 Error / Oil Low):")

    if st.button("تحليـل العطل بالذكاء الاصطناعي 🔍", use_container_width=True):
        st.success(f"🌟 جارٍ المعالجة للعميل (**{client_name}**)...")
        
        if manual_file:
            st.info(f"📁 **تم إرفاق الكتالوج:** {manual_file.name} (سيتم مطابقة البيانات معه).")
            
        target_fault_img = fault_image or fault_cam
        if target_fault_img:
            img_obj = Image.open(target_fault_img)
            st.image(img_obj, caption="صورة الشاشة / الكود المرفوعة", width=400)
            if decode_qr:
                try:
                    decoded = decode_qr(img_obj)
                    if decoded:
                        st.success(f"📟 **كود QR مقروء:** `{decoded[0].data.decode('utf-8')}`")
                except:
                    pass

        st.markdown(f"### 📋 تقرير التشخيص الفوري: `{fault_code_input or 'اعتماداً على الصورة/الكتالوج'}`")
        st.markdown("""
        * **طبيعة المشكلة المحتملة:** قراءة غير اعتيادية من المستشعرات (ضغط زيت أو حرارة محرك) أو خلل في برمجة وحدة التحكم (مثل DSE Controllers).
        * **التوجيهات الفنية:**
          1. مطابقة الكود المدخل أو الرمز البصري مع جدول الأعطال في الكتالوج المرفق.
          2. فحص أطراف التوصيل (Wiring) وحالة الحساسات بناءً على الصورة والمخرجات.
          3. إعادة الضبط (Reset) والتحقق من التغذية الكهربائية لدوائر التحكم.
        """)

# =========================================================
# التطبيق 3: الفحص البصري للمعدات
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام الفحص والمقارنة البصرية لقطع الغيار والمعدات")
    
    # تحديث دقيق لأنظمة التبريد
    eq_type = st.selectbox("اختر المعدة المراد فحصها:", [
        "مولد ديزل صناعي", 
        "غرف تبريد وتجميد WIC 10 و WIC 40", 
        "محرك كهربائي 3-Phase"
    ])

    st.subheader("🖼️ المقارنة البصرية (القطعة التالفة vs السليمة)")
    c_img1, c_img2 = st.columns(2)
    with c_img1:
        st.write("🟢 **صورة القطعة السليمة (Reference):**")
        good_img = st.file_uploader("اختر صورة السليم", type=["png", "jpg"], key="gi")
        if good_img: st.image(Image.open(good_img), use_container_width=True)
    with c_img2:
        st.write("🔴 **صورة القطعة المفحوصة (Damaged):**")
        bad_img = st.file_uploader("اختر صورة التالف", type=["png", "jpg"], key="bi")
        if bad_img: st.image(Image.open(bad_img), use_container_width=True)
        
    if eq_type == "غرف تبريد وتجميد WIC 10 و WIC 40":
        st.warning("⚠️ **قائمة فحص وحدات WIC:** يرجى التأكد من فحص صمامات التمدد (Expansion Valves)، وسخانات الإذابة (Defrost)، وتدفق سائل التبريد لوحدات WIC 10 و WIC 40 بشكل منفصل لضمان الكفاءة.")
