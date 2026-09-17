import os
import re
import json
import uuid
import urllib.parse
import base64
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
        "plan": "احترافي (Pro)",
        "start_date": "2026-01-01",
        "duration_days": 365,
    }
}

st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل للوصول للنظام:", type="password", value="ADDOMA-2026-PRO")

# إعداد مفتاح API لـ Gemini
st.sidebar.divider()
st.sidebar.header("🧠 إعداد محرك الذكاء الاصطناعي")
gemini_api_key = st.sidebar.text_input("أدخل مفتاح Google Gemini API:", type="password")

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
    else:
        st.sidebar.error("❌ انتهت صلاحية الاشتراك.")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح.")
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
        submit_btn = st.form_submit_button("تحديث وتحليل البيانات")

    # قاعدة بيانات افتراضية لقطع الغيار
    base_parts_data = [
        {"تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي": 250.0, "الساعات المنقضية": 210.0},
        {"تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "Water Pump", "العمر الافتراضي": 6000.0, "الساعات المنقضية": 5200.0},
        {"تصنيف القطعة": "Electric System", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي": 8000.0, "الساعات المنقضية": 7900.0}
    ]
    df_parts_input = pd.DataFrame(base_parts_data)
    edited_table = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch")

    processed_rows = []
    for idx, row in edited_table.iterrows():
        part = str(row.get("قطع الغيار / الفلاتر", "Part"))
        life = pd.to_numeric(row.get("العمر الافتراضي", 250), errors="coerce") or 250.0
        used = pd.to_numeric(row.get("الساعات المنقضية", 0), errors="coerce") or 0.0
        rem = life - used
        pct = (used / life) * 100 if life > 0 else 0
        status = "Critical Alert" if rem <= 0 or pct >= 90 else ("Standby" if pct >= 75 else "Good")
        processed_rows.append({
            "قطع الغيار / الفلاتر": part, "العمر الافتراضي": life, "الساعات المنقضية": used, 
            "المدة المتبقية": max(0.0, rem), "حالة التنبيه": status
        })
    df_result = pd.DataFrame(processed_rows)

    st.divider()
    st.subheader("📷 إرفاق صور المولد وقطع الغيار للتقرير (اختياري)")
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        st.markdown("**صورة المولد / لوحة التحكم**")
        gen_img_file = st.file_uploader("رفع من الجهاز (المولد)", type=["png", "jpg", "jpeg"], key="g_up")
        gen_cam = st.camera_input("📸 التقاط بالكاميرا (المولد)", key="g_cam")
        final_gen_img = gen_img_file or gen_cam

    with col_up2:
        st.markdown("**صورة القطع المستبدلة**")
        parts_img_file = st.file_uploader("رفع من الجهاز (القطع)", type=["png", "jpg", "jpeg"], key="p_up")
        parts_cam = st.camera_input("📸 التقاط بالكاميرا (القطع)", key="p_cam")
        final_parts_img = parts_img_file or parts_cam

    st.divider()
    st.subheader("📊 الرسوم البيانية التفاعلية")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_bar = px.bar(df_result, x="قطع الغيار / الفلاتر", y=["الساعات المنقضية", "المدة المتبقية"], title="استهلاك قطع الغيار")
        st.plotly_chart(fig_bar, use_container_width=True)
    with chart_col2:
        fig_pie = px.pie(df_result, names="حالة التنبيه", title="توزيع حالات الصيانة")
        st.plotly_chart(fig_pie, use_container_width=True)

    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("GENERATOR & PREDICTIVE MAINTENANCE REPORT")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)} | Total Hours: {run_hours}", ln=True)
        pdf.ln(5)

        # إضافة الجدول
        pdf.set_font("Helvetica", "B", 8)
        headers_pdf = ["Part Name", "Lifespan", "Used", "Remain", "Status"]
        widths = [45, 25, 25, 25, 40]
        for h, w in zip(headers_pdf, widths):
            pdf.cell(w, 5, h, border=1)
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 8)
        for _, row in df_result.iterrows():
            pdf.cell(widths[0], 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:25], border=1)
            pdf.cell(widths[1], 5, str(row["العمر الافتراضي"]), border=1)
            pdf.cell(widths[2], 5, str(row["الساعات المنقضية"]), border=1)
            pdf.cell(widths[3], 5, str(row["المدة المتبقية"]), border=1)
            pdf.cell(widths[4], 5, str(row["حالة التنبيه"]), border=1)
            pdf.ln()

        # دمج صورتي الرسم البياني (العمودية والدائرية) باستخدام Matplotlib
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Performance & Maintenance Visual Charts:", ln=True)
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
            
            # الرسم العمودي
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
            ax1.bar(p_short, df_result["الساعات المنقضية"].values, label="Used Hours", color="#d9534f")
            ax1.set_title("Parts Lifespan Overview")
            ax1.tick_params(axis='x', rotation=45)
            
            # الرسم الدائري
            status_counts = df_result["حالة التنبيه"].value_counts()
            ax2.pie(status_counts, labels=status_counts.index, autopct='%1.1f%%', startangle=90, colors=['#28a745', '#ffc107', '#dc3545'])
            ax2.set_title("Maintenance Status Distribution")
            
            plt.tight_layout()
            charts_path = f"temp_charts_{uuid.uuid4().hex}.png"
            plt.savefig(charts_path, dpi=300)
            pdf.image(charts_path, x=10, y=30, w=190)
            os.remove(charts_path)
        except Exception as e:
            st.warning(f"تعذر إنشاء الرسوم للـ PDF: {e}")

        # دمج الصور المرفوعة للمولد والقطع
        if final_gen_img or final_parts_img:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 6, "Field Images & Documentation:", ln=True)
            y_pos = 20
            if final_gen_img:
                gen_path = f"temp_gen_{uuid.uuid4().hex}.jpg"
                with open(gen_path, "wb") as f: f.write(final_gen_img.getbuffer())
                pdf.image(gen_path, x=15, y=y_pos, w=85)
                os.remove(gen_path)
            if final_parts_img:
                part_path = f"temp_part_{uuid.uuid4().hex}.jpg"
                with open(part_path, "wb") as f: f.write(final_parts_img.getbuffer())
                pdf.image(part_path, x=110, y=y_pos, w=85)

        pdf_out = pdf.output(dest="S")
        return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

    st.download_button(
        label="🖨️ إصدار التقرير الفني الشامل (طباعة PDF مع الرسوم والصور)",
        data=generate_full_pdf_bytes(),
        file_name=f"Full_Maintenance_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        mime="application/pdf",
        use_container_width=True
    )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات (بدون مكتبات خارجية)
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 مساعد الأعطال الذكي (مدعوم بـ Google Gemini)")

    col_files1, col_files2 = st.columns(2)
    with col_files1:
        st.subheader("📚 رفع الكتالوجات / النصوص")
        manual_file = st.file_uploader("رفع ملف وصفي للعطل (txt/csv)", type=["txt", "csv"])
    with col_files2:
        st.subheader("📷 إرفاق صورة العطل (شاشة DSE / جزء تالف)")
        fault_image = st.file_uploader("رفع من الجهاز", type=["png", "jpg", "jpeg"], key="f_up")
        fault_cam = st.camera_input("📸 التقاط بالكاميرا", key="f_cam")
        target_fault_img = fault_image or fault_cam

    st.divider()
    fault_code_input = st.text_area("أدخل كود العطل أو وصف المشكلة هنا:")

    if st.button("تحليـل العطل بالذكاء الاصطناعي 🔍", use_container_width=True):
        if not gemini_api_key:
            st.error("⚠️ يرجى إدخال مفتاح API الخاص بـ Google Gemini في الشريط الجانبي أولاً.")
        elif not fault_code_input and not target_fault_img:
            st.warning("⚠️ يرجى إدخال وصف للعطل أو إرفاق صورة للتحليل.")
        else:
            with st.spinner("جارٍ معالجة البيانات عبر محرك Gemini المتقدم..."):
                try:
                    prompt_text = f"""أنت مهندس كهروميكانيكا واستشاري صيانة محترف، متخصص في أنظمة الطاقة، المولدات (مثل Perkins، Cummins)، وأنظمة التحكم الصناعي (مثل DSE 8610 MKII).
                    بناءً على المعطيات التالية:
                    وصف المشكلة: {fault_code_input}
                    يرجى تقديم:
                    1. التشخيص المحتمل للعطل (Root Cause Analysis).
                    2. خطوات الفحص والصيانة مرتبة.
                    3. احتياطات الأمان أو التوصيات التشغيلية.
                    اعتمد أسلوباً فنياً دقيقاً باللغة العربية."""

                    # تجهيز أجزاء الطلب
                    contents_parts = [{"text": prompt_text}]

                    # تحويل الصورة إلى Base64 في حال وجودها
                    if target_fault_img:
                        img_bytes = target_fault_img.getvalue()
                        base64_image = base64.b64encode(img_bytes).decode('utf-8')
                        mime_type = target_fault_img.type or "image/jpeg"
                        contents_parts.append({
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64_image
                            }
                        })
                        st.image(target_fault_img, caption="الصورة المرسلة للتحليل", width=300)

                    # إرسال الطلب المباشر عبر API
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-pro:generateContent?key={gemini_api_key}"
                    headers = {'Content-Type': 'application/json'}
                    payload = {"contents": [{"parts": contents_parts}]}

                    response = requests.post(url, headers=headers, json=payload)
                    res_json = response.json()

                    if response.status_code == 200 and "candidates" in res_json:
                        ai_text = res_json["candidates"][0]["content"]["parts"][0]["text"]
                        st.success("✅ اكتمل تحليل الذكاء الاصطناعي!")
                        st.markdown("### 📋 التقرير الفني للعطل:")
                        st.write(ai_text)
                    else:
                        st.error(f"❌ خطأ في الاستجابة: {res_json.get('error', {}).get('message', 'تعذر معالجة الطلب')}")

                except Exception as e:
                    st.error(f"حدث خطأ أثناء الاتصال بمحرك الذكاء الاصطناعي: {str(e)}")

# =========================================================
# التطبيق 3: الفحص البصري للمعدات
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام الفحص والمقارنة البصرية لقطع الغيار والمعدات")
    eq_type = st.selectbox("اختر المعدة المراد فحصها:", [
        "مولد ديزل صناعي", 
        "غرف تبريد وتجميد WIC 10 و WIC 40", 
        "محرك كهربائي 3-Phase"
    ])

    st.subheader("🖼️ المقارنة البصرية (القطعة التالفة vs السليمة)")
    c_img1, c_img2 = st.columns(2)
    with c_img1:
        st.write("🟢 **القطعة السليمة (Reference):**")
        good_img = st.file_uploader("رفع صورة السليم", type=["png", "jpg"])
        good_cam = st.camera_input("كاميرا للقطعة السليمة")
        final_good = good_img or good_cam
        if final_good: st.image(Image.open(final_good), use_container_width=True)
    with c_img2:
        st.write("🔴 **القطعة المفحوصة (Damaged):**")
        bad_img = st.file_uploader("رفع صورة التالف", type=["png", "jpg"])
        bad_cam = st.camera_input("كاميرا للقطعة التالفة")
        final_bad = bad_img or bad_cam
        if final_bad: st.image(Image.open(final_bad), use_container_width=True)
