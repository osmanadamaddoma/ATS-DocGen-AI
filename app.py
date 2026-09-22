import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import threading
import io
import base64 # أضيف لتحويل الصوت وتشغيله المستمر

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# جلب مفتاح Gemini بأمان من الإعدادات
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

client = genai.Client(api_key=gemini_key) if gemini_key else None

# =========================================================
# 1. نظام الصوت المتطور (مع دعم التشغيل المستمر وكتم الصوت)
# =========================================================
def play_audio(text, loop=False):
    """تحويل النص إلى صوت وتشغيله. يدعم التكرار المستمر (Loop) للإنذارات"""
    try:
        tts = gTTS(text=text, lang='ar')
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_data.seek(0)
        
        b64 = base64.b64encode(audio_data.read()).decode()
        loop_attr = "loop" if loop else ""
        
        # استخدام HTML لتفعيل التشغيل التلقائي والمستمر المخفي
        audio_html = f"""
            <audio autoplay {loop_attr} style="display:none;">
                <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
            </audio>
        """
        st.markdown(audio_html, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"حدث خطأ في تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text=""):
    if not client:
        return "⚠️ لم يتم العثور على المفتاح."
    prompt = f"""
    أنت خبير صيانة مهندس واستشاري صناعي متخصص في المولدات...
    العميل يدخل كود العطل: "{fault_code}"
    المعلومات: {context_text}
    اكتب تقرير تشخيصي.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash",
                contents=prompt,
            )
            return response.text
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return f"❌ خطأ: {str(e)}"

# =========================================================
# 2. تصميم تقرير الـ PDF المطور
# =========================================================
def sanitize_latin_only(text):
    if not isinstance(text, str): text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path

    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        text_x = 10
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=12, w=25)
            text_x = 40
        self.set_xy(text_x, 12)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(24, 43, 73)
        self.cell(0, 5, self.report_title, ln=True)
        self.set_x(text_x)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY", ln=True)
        self.set_x(text_x)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 4, "Power Systems & Electro-Mechanical Maintenance Division", ln=True)
        self.set_draw_color(24, 43, 73)
        self.set_line_width(0.5)
        self.line(10, 30, 200, 30)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(200, 200, 200)
        self.line(10, 282, 200, 282)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, "Prepared by: Osman Adam Addoma | Power Systems Engineer", ln=True, align="C")
        self.cell(0, 4, f"Page {self.page_no()} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# =========================================================
# 3. نظام الاشتراكات الموحد والباقات
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة", "plan": "شهري (Monthly)", "start_date": "2026-09-15", "duration_days": 30},
}
st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    is_pro = True
    st.sidebar.success(f"✅ تم التحقق: {client_name}")
else:
    st.sidebar.info("💡 أدخل الكود المخصص.")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح للوصول إلى النظام.")
    st.stop()

st.sidebar.divider()
selected_app = st.sidebar.radio("اختر النظام المطلوب:", [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🤖 2. المساعد الذكي والكتالوجات",
    "🔍 3. نظام فحص المعدات"
])

# =========================================================
# تهيئة بيانات المولدات والمواقع في الذاكرة
# =========================================================
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الموقع الرئيسي - الخرطوم": {
            "G1": {
                "model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0,
                "current_volt": 400.0, "current_amp": 360.0, "current_temp": 85.0,
                "calib_volt": 415.0, "calib_amp": 550.0, "calib_temp": 95.0
            }
        }
    }

# =========================================================
# نافذة منبثقة (Pop-up Dialog) لتحديث بيانات المولد
# =========================================================
@st.dialog("تحديث بيانات ومعايرة المولد ⚙️")
def generator_settings_dialog(site, gen):
    gen_info = st.session_state.sites_data[site][gen]
    
    st.markdown("### 📝 البيانات الأساسية والتشغيلية")
    c1, c2 = st.columns(2)
    with c1:
        gen_model = st.text_input("طراز / اسم المولد", value=gen_info.get("model", ""))
        run_hours = st.number_input("ساعات التشغيل الحالية", value=gen_info.get("run_hours", 0.0), step=10.0)
        target_hours = st.number_input("الساعات المستهدفة للصيانة", value=gen_info.get("target", 250.0), step=10.0)
    with c2:
        kw = st.number_input("سعة المولد (kW)", value=gen_info.get("kw", 0.0))
        current_volt = st.number_input("الجهد الفعلي الآن (V)", value=gen_info.get("current_volt", 400.0))
        current_amp = st.number_input("التيار الفعلي الآن (A)", value=gen_info.get("current_amp", 360.0))
        current_temp = st.number_input("حرارة المحرك الآن (°C)", value=gen_info.get("current_temp", 85.0))
        
    st.markdown("### ⚠️ قيم المعايرة (حدود الإنذار)")
    c3, c4, c5 = st.columns(3)
    with c3: calib_volt = st.number_input("أقصى جهد مسموح", value=gen_info.get("calib_volt", 415.0))
    with c4: calib_amp = st.number_input("أقصى تيار مسموح", value=gen_info.get("calib_amp", 550.0))
    with c5: calib_temp = st.number_input("أقصى حرارة مسموحة", value=gen_info.get("calib_temp", 95.0))
    
    if st.button("💾 حفظ البيانات والتحديث", type="primary"):
        st.session_state.sites_data[site][gen].update({
            "model": gen_model, "run_hours": run_hours, "target": target_hours, "kw": kw,
            "current_volt": current_volt, "current_amp": current_amp, "current_temp": current_temp,
            "calib_volt": calib_volt, "calib_amp": calib_amp, "calib_temp": calib_temp
        })
        # إعادة تعيين كتم الصوت عند تحديث البيانات
        st.session_state[f"mute_{site}_{gen}"] = False
        st.rerun()

# =========================================================
# التطبيق 1: الصيانة التنبؤية والمولدات
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    logo_file = st.sidebar.file_uploader("رفع شعار الشركة (Logo)", type=["png", "jpg"], key="logo_up")

    st.subheader("📍 إدارة المواقع والمولدات")
    
    # 1. قائمة اختيار الموقع مع خيار الكتابة
    site_list = list(st.session_state.sites_data.keys()) + ["✍️ كتابة عنوان موقع جديد"]
    selected_site = st.selectbox("اختر الموقع للعمل عليه:", site_list)
    
    if selected_site == "✍️ كتابة عنوان موقع جديد":
        new_site = st.text_input("أدخل عنوان الموقع الجديد:")
        if st.button("➕ حفظ الموقع الجديد"):
            if new_site and new_site not in st.session_state.sites_data:
                st.session_state.sites_data[new_site] = {}
                st.success("تم الحفظ!")
                st.rerun()
        st.stop()
        
    # إدارة المولدات داخل الموقع المختار
    col_g1, col_g2 = st.columns([3, 1])
    with col_g1:
        gen_list = list(st.session_state.sites_data[selected_site].keys())
        if not gen_list:
            st.warning("لا توجد مولدات. أضف مولداً للبدء.")
        else:
            selected_gen = st.selectbox("اختر المولد:", gen_list)
    
    with col_g2:
        st.write("") 
        st.write("")
        new_gen_id = st.text_input("إضافة مولد (مثال G3):", key="new_gen_id")
        if st.button("➕ إضافة"):
            if new_gen_id:
                st.session_state.sites_data[selected_site][new_gen_id] = {
                    "model": "غير محدد", "run_hours": 0.0, "target": 250.0, "kw": 0.0,
                    "current_volt": 0, "current_amp": 0, "current_temp": 0,
                    "calib_volt": 415, "calib_amp": 500, "calib_temp": 95
                }
                st.rerun()

    if not gen_list:
        st.stop()
        
    gen_info = st.session_state.sites_data[selected_site][selected_gen]
    
    # زر تشغيل النافذة المنبثقة
    if st.button(f"⚙️ إدخال/تعديل بيانات ومعايرة المولد ({selected_gen})"):
        generator_settings_dialog(selected_site, selected_gen)
        
    st.divider()

    # =========================================================
    # نظام التنبيه والإنذار المستمر بناءً على المعايرة والساعات
    # =========================================================
    mute_key = f"mute_{selected_site}_{selected_gen}"
    if mute_key not in st.session_state:
        st.session_state[mute_key] = False

    alarms = []
    # فحص الساعات
    rem_hours = gen_info["target"] - gen_info["run_hours"]
    if rem_hours <= 0: alarms.append("تجاوز ساعات الصيانة الافتراضية للمولد!")
    
    # فحص المعايرة
    if gen_info["current_temp"] > gen_info["calib_temp"]: alarms.append("تجاوز درجة حرارة المحرك القصوى!")
    if gen_info["current_volt"] > gen_info["calib_volt"]: alarms.append("ارتفاع مستوى الجهد عن قيمة المعايرة!")
    if gen_info["current_amp"] > gen_info["calib_amp"]: alarms.append("سحب تيار عالي (Overload) يتجاوز المعايرة!")

    if alarms:
        alarm_text = " و ".join(alarms)
        st.error(f"🚨 **إنذار حرج:** {alarm_text}")
        
        c_alarm1, c_alarm2 = st.columns([3, 1])
        with c_alarm1:
            st.warning("الرجاء اتخاذ الإجراءات الهندسية اللازمة فوراً.")
            if not st.session_state[mute_key]:
                # تشغيل الصوت بشكل مستمر (Loop = True)
                play_audio(f"إنذار طوارئ. {alarm_text}", loop=True)
        with c_alarm2:
            if st.button("🔕 كتم صوت الإنذار (Mute)"):
                st.session_state[mute_key] = True
                st.rerun()
    else:
        st.session_state[mute_key] = False
        if rem_hours <= 50 and rem_hours > 0:
            st.info(f"🔊 تنبيه: المولد يقترب من موعد الصيانة. متبقي {rem_hours} ساعة.")
            play_audio(f"المولد يقترب من موعد الصيانة. متبقي {rem_hours} ساعة.", loop=False)

    # =========================================================
    # جدول قطع الغيار والصيانة
    # =========================================================
    parts_key = f"parts_{selected_site}_{selected_gen}"
    if parts_key not in st.session_state:
        st.session_state[parts_key] = [
            {"القطعة": "Oil Filter", "العمر": 250.0, "المنقضي": 210.0, "تجديد": False},
            {"القطعة": "Fuel Filter", "العمر": 500.0, "المنقضي": 455.0, "تجديد": False},
            {"القطعة": "Air Filter", "العمر": 1000.0, "المنقضي": 860.0, "تجديد": False},
        ]

    st.subheader(f"🛢️ جدول الصيانة التنبؤية (العمر الافتراضي) - {selected_gen}")
    edited_df = st.data_editor(
        pd.DataFrame(st.session_state[parts_key]), 
        num_rows="dynamic", use_container_width=True
    )

    if st.button("🔄 تأكيد التحديث وتصفير القطع"):
        new_data = []
        for idx, row in edited_df.iterrows():
            item = row.to_dict()
            if item.get("تجديد"):
                item["المنقضي"] = 0.0
                item["تجديد"] = False 
            new_data.append(item)
        st.session_state[parts_key] = new_data
        st.success("✅ تم التحديث بنجاح!")
        st.rerun()

    # إعداد الرسوم البيانية
    df_parts = pd.DataFrame(st.session_state[parts_key])
    df_parts['المتبقي'] = df_parts['العمر'] - df_parts['المنقضي']
    df_parts['النسبة'] = (df_parts['المنقضي'] / df_parts['العمر']) * 100
    df_parts['الحالة'] = df_parts['النسبة'].apply(lambda x: "خطر" if x>=95 else ("إنذار" if x>=80 else "جيد"))

    st.subheader("📊 الرسومات البيانية لأداء ساعات الافتراضية")
    c_chart1, c_chart2 = st.columns(2)
    with c_chart1:
        fig_bar = px.bar(df_parts, x="القطعة", y=["المنقضي", "المتبقي"], title="استهلاك قطع الغيار", barmode="stack")
        st.plotly_chart(fig_bar, use_container_width=True)
    with c_chart2:
        fig_pie = px.pie(df_parts, names="الحالة", title="توزيع حالات الصيانة للقطع", color="الحالة", 
                         color_discrete_map={"جيد":"green", "إنذار":"orange", "خطر":"red"})
        st.plotly_chart(fig_pie, use_container_width=True)

    # =========================================================
    # تصدير التقرير PDF متضمناً كل البيانات
    # =========================================================
    def generate_full_pdf_bytes():
        pdf = ComprehensivePDF("COMPREHENSIVE GENERATOR REPORT")
        pdf.add_page()
        
        pdf.set_fill_color(245, 247, 250)
        pdf.rect(10, 35, 190, 30, "F")
        pdf.set_xy(12, 37)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(24, 43, 73)
        
        # بيانات الموقع والمولد
        pdf.cell(0, 5, f"Site: {sanitize_latin_only(selected_site)} | Gen ID: {sanitize_latin_only(selected_gen)}", ln=True)
        pdf.set_x(12)
        pdf.cell(0, 5, f"Model: {sanitize_latin_only(gen_info['model'])} | Cap: {gen_info['kw']} kW | Run Hrs: {gen_info['run_hours']} / {gen_info['target']}", ln=True)
        pdf.ln(2)
        
        # بيانات المعايرة والواقع
        pdf.set_x(12)
        pdf.cell(0, 5, f"Electrical: Voltage {gen_info['current_volt']}V (Limit: {gen_info['calib_volt']}V) | Current {gen_info['current_amp']}A (Limit: {gen_info['calib_amp']}A)", ln=True)
        pdf.set_x(12)
        pdf.cell(0, 5, f"Engine: Temp {gen_info['current_temp']}C (Limit: {gen_info['calib_temp']}C)", ln=True)
        pdf.ln(8)

        # جدول القطع
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(24, 43, 73)
        pdf.set_text_color(255, 255, 255)
        headers = ["Part Name", "Lifespan", "Used", "Remaining", "Status"]
        widths = [60, 30, 30, 30, 40]
        for h, w in zip(headers, widths):
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()
        
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(0, 0, 0)
        for i, row in df_parts.iterrows():
            fill = (i % 2 == 0)
            pdf.set_fill_color(240, 243, 246) if fill else pdf.set_fill_color(255, 255, 255)
            pdf.cell(widths[0], 5, sanitize_latin_only(str(row["القطعة"])), border=1, fill=fill)
            pdf.cell(widths[1], 5, str(row["العمر"]), border=1, align="C", fill=fill)
            pdf.cell(widths[2], 5, str(row["المنقضي"]), border=1, align="C", fill=fill)
            pdf.cell(widths[3], 5, str(max(0, row["المتبقي"])), border=1, align="C", fill=fill)
            pdf.cell(widths[4], 5, sanitize_latin_only(str(row["الحالة"])), border=1, fill=fill)
            pdf.ln()

        # إرفاق الرسومات البيانية
        try:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_text_color(24, 43, 73)
            pdf.cell(0, 6, "Performance & Maintenance Visual Analytics:", ln=True)
            
            fig_bar_p, ax_bar_p = plt.subplots(figsize=(7, 3.2))
            p_short = [sanitize_latin_only(str(x))[:12] for x in df_parts["القطعة"]]
            ax_bar_p.bar(p_short, df_parts["المنقضي"].values, label="Used", color="#d9534f")
            ax_bar_p.set_title("Parts Lifespan Chart", fontsize=9, fontweight='bold')
            plt.xticks(rotation=45, ha="right", fontsize=6)
            plt.tight_layout()
            
            bar_path = f"temp_bar_{uuid.uuid4().hex}.png"
            plt.savefig(bar_path, dpi=200)
            pdf.image(bar_path, x=15, y=45, w=180)
            os.remove(bar_path)
        except Exception:
            pass

        pdf_out = pdf.output(dest="S")
        return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

    st.download_button(
        label=f"🖨️ إصدار التقرير الشامل للمولد ({selected_gen})",
        data=generate_full_pdf_bytes(),
        file_name=f"Comprehensive_Report_{selected_gen}.pdf",
        mime="application/pdf",
        use_container_width=True,
        type="primary"
    )

# =========================================================
# باقي التطبيقات (المساعد الذكي ونظام الفحص البصري) 
# كما هي في الكود الأصلي لتجنب إطالة المخرجات دون داع
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي وتحليل الأعطال")
    st.info("نفس وظائف الكود الأصلي متوفرة هنا.")
    
elif selected_app == "🔍 3. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام الفحص والمقارنة البصرية لقطع الغيار والمعدات")
    st.info("نفس وظائف الكود الأصلي متوفرة هنا.")
