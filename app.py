import os
import re
import io
import uuid
import time
import base64
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from PIL import Image
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS
from fpdf import FPDF

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# التهيئة المبدئية لمتغيرات حالة الجلسة (Session State)
if "mute_alarm" not in st.session_state:
    st.session_state.mute_alarm = False
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الموقع الرئيسي - الخرطوم": {
            "address": "المنطقة الصناعية - الخرطوم",
            "generators": {
                "G1": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0, "voltage": 400.0, "freq": 50.0, "temp": 85.0, "oil_press": 4.5, "amp": 360.0},
            }
        }
    }

# جلب مفتاح Gemini
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في الإعدادات.")

client = genai.Client(api_key=gemini_key) if gemini_key else None

# 1. دالة الصوت المطورة مع دعم التكرار المستمر والكتم
def play_audio_html(text, continuous=False):
    """تشغيل الصوت في الخلفية باستخدام HTML مع خيار التكرار المستمر (Loop)"""
    if st.session_state.mute_alarm:
        return  # تجاوز التشغيل إذا كان الإنذار مكتوماً
    
    try:
        tts = gTTS(text=text, lang='ar')
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_data.seek(0)
        b64 = base64.b64encode(audio_data.read()).decode()
        
        loop_attr = "loop" if continuous else ""
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
        return "⚠️ لم يتم العثور على مفتاح API."

    prompt = f"""
    أنت خبير صيانة مهندس واستشاري صناعي متخصص في المولدات لوحات DSE ومحركات Perkins و Cummins وأجهزة التبريد.
    العميل يدخل كود العطل أو اسم الإنذار: "{fault_code}"
    المعلومات الإضافية:
    \"\"\"
    {context_text}
    \"\"\"
    أعطني تقريراً تشخيصياً باللغة العربية يشمل طبيعة المشكلة، الأسباب، وخطوات الفحص.
    """
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(2)
                continue
            return f"❌ خطأ: {e}"

# =========================================================
# دوال إنشاء التقرير (PDF)
# =========================================================
def sanitize_latin_only(text):
    clean_text = re.sub(r"[^\x00-\x7F]+", "", str(text)).strip()
    return clean_text if clean_text else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path

    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        text_x = 40 if (self.logo_path and os.path.exists(self.logo_path)) else 10
        if text_x == 40:
            self.image(self.logo_path, x=10, y=12, w=25)

        self.set_xy(text_x, 12)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(24, 43, 73)
        self.cell(0, 5, self.report_title, ln=True)

        self.set_x(text_x)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY", ln=True)
        
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
        self.cell(0, 4, f"Page {self.page_no()} | Date: {datetime.now().strftime('%Y-%m-%d')}", align="C")

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (Addoma Trading Services)",
        "plan": "مفتوح (Pro)",
        "start_date": "2026-01-01",
        "duration_days": 365,
    }
}

st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل للوصول للنظام:", type="password")

is_pro = False
client_name = "زائر (Visitor)"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    is_pro = True
    st.sidebar.success("✅ تم التحقق من الاشتراك بنجاح!")
    st.sidebar.markdown(f"**👤 العميل:** {client_name}")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح للوصول إلى النظام.")
    st.stop()

st.sidebar.divider()

# =========================================================
# 3. النافذة المنبثقة (Popup) لإدخال بيانات المعايرة
# =========================================================
@st.dialog("⚙️ إدخال بيانات المولد وقيم لوحة المعايرة")
def generator_data_dialog(site_name, gen_id):
    gen_data = st.session_state.sites_data[site_name]["generators"][gen_id]
    
    st.markdown(f"**الموقع:** {site_name} | **المولد:** {gen_id}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.write("🔌 **البيانات الكهربائية والأحمال**")
        gen_model = st.text_input("طراز المولد", value=gen_data.get("model", ""))
        gen_kw = st.number_input("سعة المولد (kW)", value=float(gen_data.get("kw", 0)))
        load_kw = st.number_input("الحمولة الحالية (kW)", value=float(gen_data.get("load", 0)))
        voltage = st.number_input("الجهد الكهربائي (V)", value=float(gen_data.get("voltage", 400)))
        freq = st.number_input("التردد (Hz)", value=float(gen_data.get("freq", 50)))
        amp = st.number_input("التيار (Amperes)", value=float(gen_data.get("amp", 0)))

    with col2:
        st.write("⚙️ **بيانات المحرك وساعات العمل**")
        run_hours = st.number_input("ساعات التشغيل الحالية", value=float(gen_data.get("run_hours", 0)))
        target_hours = st.number_input("ساعات التشغيل المستهدفة", value=float(gen_data.get("target", 250)))
        temp = st.number_input("حرارة المحرك (°C)", value=float(gen_data.get("temp", 85)))
        oil_press = st.number_input("ضغط الزيت (Bar)", value=float(gen_data.get("oil_press", 4.5)))

    if st.button("💾 حفظ البيانات وإغلاق النافذة"):
        st.session_state.sites_data[site_name]["generators"][gen_id].update({
            "model": gen_model, "kw": gen_kw, "load": load_kw, "voltage": voltage,
            "freq": freq, "amp": amp, "run_hours": run_hours, "target": target_hours,
            "temp": temp, "oil_press": oil_press
        })
        st.success("تم الحفظ بنجاح!")
        st.rerun()

# =========================================================
# 4. اختيار التطبيق
# =========================================================
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    ["⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)", "🤖 2. المساعد الذكي وتحليل الأعطال", "🔍 3. نظام فحص المعدات (WIC)"]
)

if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    # إدارة المواقع وعناوينها
    st.subheader("📍 إدارة المواقع وعناوينها")
    col_site1, col_site2 = st.columns(2)
    with col_site1:
        with st.form("add_site_form", clear_on_submit=True):
            new_site_name = st.text_input("اسم الموقع الجديد:")
            new_site_address = st.text_input("عنوان الموقع بالتفصيل:")
            if st.form_submit_button("➕ أضف الموقع"):
                if new_site_name and new_site_name not in st.session_state.sites_data:
                    st.session_state.sites_data[new_site_name] = {"address": new_site_address, "generators": {}}
                    st.success(f"تم إضافة الموقع: {new_site_name}")
                    st.rerun()

    site_list = list(st.session_state.sites_data.keys())
    if not site_list:
        st.warning("الرجاء إضافة موقع للبدء.")
        st.stop()
        
    selected_site = st.selectbox("اختر الموقع للعمل عليه:", site_list)
    site_address = st.session_state.sites_data[selected_site].get("address", "غير محدد")
    st.caption(f"**عنوان الموقع:** {site_address}")

    with col_site2:
        new_gen_id = st.text_input(f"إضافة مولد جديد في ({selected_site}):", placeholder="مثال: G3")
        if st.button("➕ أضف المولد"):
            if new_gen_id and new_gen_id not in st.session_state.sites_data[selected_site]["generators"]:
                st.session_state.sites_data[selected_site]["generators"][new_gen_id] = {
                    "model": "غير محدد", "run_hours": 0.0, "target": 250.0, "kw": 0.0, "load": 0.0,
                    "voltage": 400.0, "freq": 50.0, "temp": 85.0, "oil_press": 4.5, "amp": 0.0
                }
                st.rerun()

    gen_list = list(st.session_state.sites_data[selected_site]["generators"].keys())
    if not gen_list:
         st.info("لا توجد مولدات في هذا الموقع. قم بإضافة مولد.")
    else:
        selected_gen = st.selectbox("اختر المولد:", gen_list)
        gen_info = st.session_state.sites_data[selected_site]["generators"][selected_gen]

        # استدعاء النافذة المنبثقة
        if st.button("📝 إدخال / تعديل بيانات المولد والمعايرة (نافذة منبثقة)", type="primary"):
            generator_data_dialog(selected_site, selected_gen)
            
        # =========================================================
        # نظام التنبيهات والإنذارات (كهرباء، محرك، ساعات)
        # =========================================================
        st.divider()
        alarm_triggered = False
        alert_messages = []

        # فحص قيم المعايرة
        v, f, t, p = gen_info.get("voltage", 400), gen_info.get("freq", 50), gen_info.get("temp", 85), gen_info.get("oil_press", 4.5)
        if v > 425 or v < 375: alert_messages.append(f"الجهد الكهربائي خارج النطاق ({v} V)")
        if f > 52.5 or f < 47.5: alert_messages.append(f"التردد خارج النطاق ({f} Hz)")
        if t > 95: alert_messages.append(f"حرارة المحرك مرتفعة جداً ({t} °C)")
        if p < 2.5: alert_messages.append(f"ضغط الزيت منخفض ({p} Bar)")

        # فحص الساعات
        rem_hours = gen_info["target"] - gen_info["run_hours"]
        if rem_hours <= 0: alert_messages.append("تجاوز المولد الساعات الافتراضية المجدولة للصيانة!")
        elif rem_hours <= 50: alert_messages.append(f"اقتراب موعد الصيانة (متبقي {rem_hours} ساعة)")

        if alert_messages:
            alarm_triggered = True
            st.error("🚨 **تحذيرات النظام:**")
            for msg in alert_messages: st.write(f"- {msg}")
            
            col_mute1, col_mute2 = st.columns([1, 4])
            with col_mute1:
                if st.button("🔇 إيقاف صوت الإنذار (Mute)"):
                    st.session_state.mute_alarm = True
                    st.rerun()
            with col_mute2:
                if st.button("🔊 تفعيل الصوت"):
                    st.session_state.mute_alarm = False
                    st.rerun()

            # تشغيل إنذار مستمر إذا لم يتم كتمه
            if not st.session_state.mute_alarm:
                combined_msg = "إنذار في المولد. " + " و ".join(alert_messages)
                play_audio_html(combined_msg, continuous=True)

        # =========================================================
        # جدول قطع الغيار والصيانة (14 وحدة متكاملة)
        # =========================================================
        parts_key = f"parts_{selected_site}_{selected_gen}"
        if parts_key not in st.session_state:
            st.session_state[parts_key] = [
                {"الوحدة": 1, "القطعة": "Oil Filter", "العمر": 250, "المنقضي": 150, "تجديد": False},
                {"الوحدة": 2, "القطعة": "Primary Fuel Filter", "العمر": 250, "المنقضي": 230, "تجديد": False},
                {"الوحدة": 3, "القطعة": "Secondary Fuel Filter", "العمر": 500, "المنقضي": 450, "تجديد": False},
                {"الوحدة": 4, "القطعة": "Air Filter", "العمر": 1000, "المنقضي": 950, "تجديد": False},
                {"الوحدة": 5, "القطعة": "Fan Belt", "العمر": 2000, "المنقضي": 1550, "تجديد": False},
                {"الوحدة": 6, "القطعة": "ELC Coolant", "العمر": 3000, "المنقضي": 2200, "تجديد": False},
                {"الوحدة": 7, "القطعة": "Injectors Check", "العمر": 5000, "المنقضي": 4900, "تجديد": False},
                {"الوحدة": 8, "القطعة": "Batteries", "العمر": 8000, "المنقضي": 6100, "تجديد": False},
                {"الوحدة": 9, "القطعة": "Charging Alternator", "العمر": 10000, "المنقضي": 9800, "تجديد": False},
                {"الوحدة": 10, "القطعة": "Top Overhaul", "العمر": 10000, "المنقضي": 9100, "تجديد": False},
                {"الوحدة": 11, "القطعة": "Major Overhaul", "العمر": 20000, "المنقضي": 15000, "تجديد": False},
                {"الوحدة": 12, "القطعة": "Oil Cooler Clean", "العمر": 5000, "المنقضي": 3800, "تجديد": False},
                {"الوحدة": 13, "القطعة": "Water Pump", "العمر": 6000, "المنقضي": 5200, "تجديد": False},
                {"الوحدة": 14, "القطعة": "Turbocharger Check", "العمر": 8000, "المنقضي": 7100, "تجديد": False},
            ]

        st.subheader("🛢️ جدول الصيانة التنبؤية (14 وحدة قطع غيار)")
        df_parts = pd.DataFrame(st.session_state[parts_key])
        
        edited_df = st.data_editor(
            df_parts, 
            num_rows="dynamic", 
            width="stretch",
            column_config={
                "تجديد": st.column_config.CheckboxColumn("تجديد (تصفير)", default=False)
            }
        )

        if st.button("🔄 تأكيد التحديث للقطع المحددة", type="primary"):
            new_data = []
            for _, row in edited_df.iterrows():
                item = row.to_dict()
                if item.get("تجديد"):
                    item["المنقضي"] = 0
                    item["تجديد"] = False 
                new_data.append(item)
            st.session_state[parts_key] = new_data
            st.rerun()

        # حساب النسب وتلوين الحالات
        processed = []
        for _, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
            part = row["القطعة"]
            life = float(row["العمر"])
            used = float(row["المنقضي"])
            pct = (used / life) * 100 if life > 0 else 0
            rem = max(0, life - used)
            
            # تصنيف لوني دقيق حسب طلبك
            if pct >= 100: status, color_name = "خطر (متجاوز 100%)", "أحمر"
            elif pct >= 90: status, color_name = "تحذير (تجاوز 90%)", "أصفر"
            elif pct >= 70: status, color_name = "مستقر (تجاوز 70%)", "أخضر"
            else: status, color_name = "ممتاز (أقل من 70%)", "أخضر"

            processed.append({
                "القطعة": part, "العمر الافتراضي": life, "الساعات المنقضية": used, 
                "المتبقي": rem, "نسبة الأداء": pct, "الحالة": status, "اللون": color_name
            })
        
        df_res = pd.DataFrame(processed)

        # =========================================================
        # الرسوم البيانية الدائرية والعمودية بالنسب المطلوبة
        # =========================================================
        st.subheader("📊 الرسوم البيانية لكفاءة وأداء الساعات الافتراضية")
        
        color_map = {
            "ممتاز (أقل من 70%)": "#28a745", # أخضر
            "مستقر (تجاوز 70%)": "#28a745", # أخضر
            "تحذير (تجاوز 90%)": "#ffc107", # أصفر
            "خطر (متجاوز 100%)": "#dc3545"   # أحمر
        }

        col_chart1, col_chart2 = st.columns(2)
        with col_chart1:
            fig_bar = px.bar(
                df_res, x="القطعة", y="نسبة الأداء", color="الحالة", 
                title="نسبة الاستهلاك من الساعات الافتراضية لكل قطعة", 
                color_discrete_map=color_map, template="plotly_white"
            )
            fig_bar.add_hline(y=100, line_dash="dot", annotation_text="100% الحد الأقصى", line_color="red")
            fig_bar.add_hline(y=90, line_dash="dot", annotation_text="90% تنبيه", line_color="orange")
            fig_bar.add_hline(y=70, line_dash="dot", annotation_text="70% أمان", line_color="green")
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_chart2:
            fig_pie = px.pie(
                df_res, names="الحالة", color="الحالة", 
                title="توزيع حالة الأداء للقطع (نسبة الدائرة)", 
                color_discrete_map=color_map, hole=0.4
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # =========================================================
        # تصدير التقرير PDF باسمك الرسمي
        # =========================================================
        def generate_pdf():
            pdf = ComprehensivePDF("COMPREHENSIVE GENERATOR REPORT")
            pdf.add_page()
            
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(24, 43, 73)
            pdf.cell(0, 5, f"Site Address: {sanitize_latin_only(site_address)} | Gen ID: {sanitize_latin_only(selected_gen)}", ln=True)
            pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_info.get('model'))} | Current Hours: {gen_info.get('run_hours')} hrs", ln=True)
            pdf.cell(0, 5, f"Voltage: {gen_info.get('voltage')}V | Freq: {gen_info.get('freq')}Hz | Temp: {gen_info.get('temp')}C", ln=True)
            pdf.ln(10)
            
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(24, 43, 73)
            pdf.set_text_color(255, 255, 255)
            
            headers = ["Part Name", "Lifespan", "Used", "Remaining", "Status"]
            widths = [55, 25, 25, 25, 60]
            for h, w in zip(headers, widths):
                pdf.cell(w, 6, h, border=1, fill=True, align="C")
            pdf.ln()
            
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(0, 0, 0)
            
            for i, row in df_res.iterrows():
                fill = (i % 2 == 0)
                pdf.set_fill_color(240, 243, 246) if fill else pdf.set_fill_color(255, 255, 255)
                pdf.cell(widths[0], 5, sanitize_latin_only(row["القطعة"]), border=1, fill=fill)
                pdf.cell(widths[1], 5, str(row["العمر الافتراضي"]), border=1, align="C", fill=fill)
                pdf.cell(widths[2], 5, str(row["الساعات المنقضية"]), border=1, align="C", fill=fill)
                pdf.cell(widths[3], 5, str(row["المتبقي"]), border=1, align="C", fill=fill)
                pdf.cell(widths[4], 5, sanitize_latin_only(row["الحالة"]), border=1, fill=fill)
                pdf.ln()

            out = pdf.output(dest="S")
            return out.encode("latin-1", errors="replace") if isinstance(out, str) else bytes(out)

        st.download_button(
            label="🖨️ تصدير التقرير المعتمد (PDF)",
            data=generate_pdf(),
            file_name=f"Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

elif selected_app == "🤖 2. المساعد الذكي وتحليل الأعطال":
    st.title("🤖 المساعد الذكي لقراءة الأكواد وتحليل الأعطال")
    fault_code = st.text_input("أدخل كود العطل (مثال: Over Current / High Temp):")
    if st.button("تحليل العطل"):
        with st.spinner("جاري التحليل..."):
            res = analyze_fault_with_gemini(fault_code)
            st.markdown(res)
            play_audio_html(res)

elif selected_app == "🔍 3. نظام فحص المعدات (WIC)":
    st.title("🔍 نظام الفحص البصري للمعدات الصناعية والتبريد")
    eq_type = st.selectbox("اختر المعدة للفحص:", [
        "غرف تبريد وتجميد WIC 10 و WIC 40", 
        "مولد ديزل صناعي",
        "محركات ثلاثية الطور"
    ])
    
    if "WIC" in eq_type:
        st.info("💡 **توجيهات الفحص:** يرجى التأكد من معايرة صمامات التمدد، وسخانات الإذابة لوحدتي WIC 10 و WIC 40 والتأكد من ضغط غاز التبريد وحالة متحكمات Emerson بشكل دقيق.")
    
    col_img1, col_img2 = st.columns(2)
    with col_img1:
        st.write("🟢 القطعة المرجعية (السليمة)")
        st.file_uploader("رفع الصورة المرجعية", type=["png", "jpg"], key="ref")
    with col_img2:
        st.write("🔴 القطعة المفحوصة")
        st.file_uploader("رفع صورة الفحص", type=["png", "jpg"], key="insp")
