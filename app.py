import os
import re
import io
import uuid
import time
import base64
import urllib.parse
from datetime import datetime, timedelta

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
from fpdf import FPDF
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS

# محاولة استيراد مكتبة قراءة الباركود (تتطلب حزمة libzbar0 في الخادم)
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
    page_icon="⚙️"
)

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الموقع الرئيسي - الخرطوم": {
            "address": "الخرطوم - المنطقة الصناعية",
            "generators": {
                "G1": {
                    "model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0,
                    "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.1, "current_max": 600.0, "current_measured": 360.0, "pf": 0.85, "ct_ratio": "600/5"},
                    "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 26.5, "ambient_temp": 43.0}
                },
                "G2": {
                    "model": "Cummins 250 kVA", "run_hours": 1200.0, "target": 1500.0, "kw": 250.0, "load": 180.0,
                    "calib_elec": {"v_nominal": 400.0, "v_measured": 402.0, "freq_nominal": 50.0, "freq_measured": 49.9, "current_max": 360.0, "current_measured": 260.0, "pf": 0.82, "ct_ratio": "400/5"},
                    "calib_engine": {"oil_press_bar": 4.2, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 25.8, "ambient_temp": 45.0}
                }
            }
        }
    }

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [{
        "timestamp": f"{today_str} 08:30:00", "date": today_str, "site": "الموقع الرئيسي - الخرطوم",
        "generator": "G1", "technician": "فني الصيانة", "run_hours": 700.0, "v_measured": 398.0,
        "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"
    }]

gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.error("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY.")

client = genai.Client(api_key=gemini_key) if gemini_key else None

def play_audio(text, loop=False):
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts = gTTS(text=text, lang='ar')
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_bytes = audio_data.getvalue()
        
        if loop:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            audio_html = f"""
                <audio autoplay loop controls style="width: 100%;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"خطأ في تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text=""):
    if not client:
        return "⚠️ الذكاء الاصطناعي غير مفعل لعدم وجود المفتاح."

    prompt = f"""
    أنت مهندس استشاري متخصص في الصيانة الميكانيكية والكهربائية (دبلوم هندسة الصيانة).
    خبير في أنظمة التزامن للمولدات عبر وحدات التحكم DSE 8610 MKII و DSE 7320 MKII ومحركات Perkins و Cummins،
    بالإضافة لغرف التبريد الصناعية كوحدتي WIC 10 و WIC 40.
    
    العميل يدخل كود العطل أو الإنذار التالي: "{fault_code}"
    
    نص مساعد من الكتالوج (إن وجد):
    \"\"\"{context_text}\"\"\"

    المطلوب إنشاء تقرير تشخيصي متكامل يحتوي على:
    1. **طبيعة المشكلة**: شرح هندسي مباشر للعطل.
    2. **الأسباب المحتملة**: أبرز 3 أسباب جذرية.
    3. **خطوات الفحص والمعالجة**: إجراءات تسلسلية دقيقة (أسلاك، حساسات، برمجة DSE).
    
    اكتب الإجابة بلغة عربية هندسية احترافية ومختصرة.
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if attempt < max_retries - 1:
                    time.sleep(2.5)
                    continue
                return "⚠️ الخادم يمر بضغط عالٍ حالياً. يرجى إعادة المحاولة."
            return f"❌ خطأ في الاتصال: {e}"

# =========================================================
# 1. دوال النظام المساعدة وتصميم تقرير الـ PDF المطور
# =========================================================
def sanitize_latin_only(text):
    return re.sub(r"[^\x00-\x7F]+", "", str(text)).strip() or "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path

    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        text_x = 40 if (self.logo_path and os.path.exists(self.logo_path)) else 10
        if text_x == 40: self.image(self.logo_path, x=10, y=12, w=25)
        
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
        self.line(10, 30, 200, 30)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_draw_color(200, 200, 200)
        self.line(10, 282, 200, 282)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, "Prepared by: Osman Adam Addoma | Manager", ln=True, align="C")
        self.cell(0, 4, f"Page {self.page_no()} | Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة (Addoma Trading Services)", "plan": "إداري (Admin)", "start_date": "2026-01-01", "duration_days": 3650},
    "CLIENT-M-881": {"name": "شركة النيل للصناعات الهندسية", "plan": "شهري (Monthly)", "start_date": "2026-09-01", "duration_days": 30},
}

st.sidebar.header("🔐 بوابة التفعيل")
input_code = st.sidebar.text_input("كود التفعيل:", type="password")

is_pro, client_name, plan_type = False, "زائر", "غير مفعل"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()
    
    if today <= expiry_dt:
        is_pro, client_name, plan_type = True, data["name"], data["plan"]
        st.sidebar.success(f"✅ أهلاً {client_name}")
    else:
        st.sidebar.error("❌ انتهت صلاحية الاشتراك.")
elif input_code:
    st.sidebar.error("❌ كود غير صحيح.")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح في الشريط الجانبي.")
    st.stop()

st.sidebar.divider()
selected_app = st.sidebar.radio("اختر النظام:", [
    "⚙️ 1. الصيانة التنبؤية والمولدات", 
    "📊 2. تقارير الإدارة والتذكيرات", 
    "🤖 3. المساعد الذكي والأعطال", 
    "🔍 4. نظام فحص المعدات (WIC وغيرها)"
])

# =========================================================
# النافذة المنبثقة (Modal) لإدخال البيانات
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد")
def edit_generator_modal(site_key, gen_key):
    gen_data = st.session_state.sites_data[site_key]["generators"][gen_key]
    elec, eng = gen_data.get("calib_elec", {}), gen_data.get("calib_engine", {})

    tech_name = st.text_input("اسم الفني:", value="عثمان أدومة")
    t1, t2, t3 = st.tabs(["🏷️ أساسيات", "⚡ كهرباء", "🔧 محرك"])

    with t1:
        new_model = st.text_input("الطراز", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("ساعات التشغيل", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("الهدف", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("السعة (kW)", value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("الحمولة (kW)", value=float(gen_data.get("load", 0.0)))
    with t2:
        v_nom, v_meas = st.number_input("V Nominal", value=float(elec.get("v_nominal", 400.0))), st.number_input("V Measured", value=float(elec.get("v_measured", 398.0)))
        f_nom, f_meas = st.number_input("Hz Nominal", value=float(elec.get("freq_nominal", 50.0))), st.number_input("Hz Measured", value=float(elec.get("freq_measured", 50.0)))
        c_max, c_meas = st.number_input("Max Amp", value=float(elec.get("current_max", 600.0))), st.number_input("Measured Amp", value=float(elec.get("current_measured", 360.0)))
        pf_val, ct_rat = st.number_input("PF", value=float(elec.get("pf", 0.85))), st.text_input("CT Ratio", value=str(elec.get("ct_ratio", "600/5")))
    with t3:
        o_press, c_temp = st.number_input("Oil (Bar)", value=float(eng.get("oil_press_bar", 4.5))), st.number_input("Coolant (°C)", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm, b_volt = st.number_input("RPM", value=float(eng.get("rpm", 1500.0))), st.number_input("Battery (V)", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("Ambient (°C)", value=float(eng.get("ambient_temp", 43.0)))

    if st.button("💾 حفظ البيانات", type="primary", use_container_width=True):
        errors = []
        if not (0 <= c_temp <= 125): errors.append("❌ حرارة المحرك غير منطقية.")
        if not (0 <= o_press <= 12): errors.append("❌ ضغط الزيت غير منطقي.")
        
        if errors:
            for e in errors: st.error(e)
        else:
            st.session_state.sites_data[site_key]["generators"][gen_key] = {
                "model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load,
                "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat},
                "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}
            }
            st.session_state.daily_logs.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d"),
                "site": site_key, "generator": gen_key, "technician": tech_name,
                "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "محدث"
            })
            st.toast("✅ تم الحفظ بنجاح!")
            time.sleep(1)
            st.rerun()

# =========================================================
# واجهات التطبيقات (توجيه العرض)
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات":
    st.title("⚙️ الصيانة التنبؤية ومراقبة المولدات")
    
    col_top1, col_top2 = st.columns([4, 1])
    with col_top2:
        if st.button("🔇 كتم/تفعيل الصوت", use_container_width=True):
            st.session_state.audio_muted = not st.session_state.audio_muted
            st.rerun()

    logo_file = st.sidebar.file_uploader("شعار التقرير", type=["png", "jpg"])
    
    c_site1, c_site2 = st.columns(2)
    with c_site1:
        new_site = st.text_input("اسم موقع جديد:")
        if st.button("➕ إضافة موقع") and new_site:
            st.session_state.sites_data[new_site] = {"address": "غير محدد", "generators": {}}
            st.rerun()
            
    site_list = list(st.session_state.sites_data.keys())
    if not site_list: st.stop()
    
    with c_site2:
        selected_site = st.selectbox("الموقع الحالي:", site_list)

    st.divider()
    c_gen1, c_gen2 = st.columns([3, 1])
    with c_gen1:
        new_gen = st.text_input("معرف المولد الجديد:")
    with c_gen2:
        st.write("")
        st.write("")
        if st.button("➕ إضافة مولد", use_container_width=True) and new_gen:
            st.session_state.sites_data[selected_site]["generators"][new_gen] = st.session_state.sites_data["الموقع الرئيسي - الخرطوم"]["generators"]["G1"].copy()
            st.rerun()

    gen_list = list(st.session_state.sites_data[selected_site]["generators"].keys())
    if gen_list:
        selected_gen = st.selectbox("اختر المولد:", gen_list)
        if st.button("📝 تحديث المعايرة (Modal)", type="primary"):
            edit_generator_modal(selected_site, selected_gen)
            
        gen_info = st.session_state.sites_data[selected_site]["generators"][selected_gen]
        calib_e = gen_info["calib_elec"]
        calib_m = gen_info["calib_engine"]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("الطراز", gen_info['model'], f"{gen_info['kw']} kW")
        c2.metric("الساعات", f"{gen_info['run_hours']} h", f"الهدف: {gen_info['target']} h")
        c3.metric("الجهد", f"{calib_e['v_measured']} V", f"الاسمي: {calib_e['v_nominal']} V")
        c4.metric("الحرارة", f"{calib_m['coolant_temp_c']} °C")

        # معالجة قطع الغيار والتقارير (مختصرة لتحسين الأداء)
        parts_key = f"parts_{selected_site}_{selected_gen}"
        if parts_key not in st.session_state:
            st.session_state[parts_key] = [
                {"القطعة": "Oil Filter", "الافتراضي": 250, "المنقضي": 180, "تصفير": False},
                {"القطعة": "Fuel Filter", "الافتراضي": 500, "المنقضي": 430, "تصفير": False},
            ]
            
        df_parts = pd.DataFrame(st.session_state[parts_key])
        edited_df = st.data_editor(df_parts, num_rows="dynamic", use_container_width=True)
        if st.button("🔄 تأكيد تحديث القطع"):
            for idx, row in edited_df.iterrows():
                if row.get("تصفير"):
                    edited_df.at[idx, "المنقضي"] = 0
                    edited_df.at[idx, "تصفير"] = False
            st.session_state[parts_key] = edited_df.to_dict('records')
            st.rerun()

elif selected_app == "📊 2. تقارير الإدارة والتذكيرات":
    st.title("📊 التقارير والتذكيرات")
    df_daily = pd.DataFrame(st.session_state.daily_logs)
    st.dataframe(df_daily, use_container_width=True)
    phone = st.text_input("رقم الفني للواتساب:", "249900000000")
    if st.button("💬 إرسال تذكير"):
        st.components.v1.html(f'<script>window.open("https://wa.me/{phone}?text=تذكير: يرجى تسجيل القراءات");</script>', height=0)

elif selected_app == "🤖 3. المساعد الذكي والأعطال":
    st.title("🤖 المساعد الذكي لـ DSE والمعدات")
    fault_code = st.text_input("أدخل كود العطل (مثال: DSE 8610 Overcurrent):")
    if st.button("🔍 تحليل", type="primary"):
        res = analyze_fault_with_gemini(fault_code)
        st.markdown(res)
        play_audio(res)

elif selected_app == "🔍 4. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام الفحص والمقارنة")
    eq = st.selectbox("المعدة:", ["غرف تبريد وتجميد WIC 10 و WIC 40", "محرك Perkins", "مولد Cummins"])
    if "WIC" in eq:
        st.info("💡 تم اختيار إعدادات غرف التبريد: يجب التأكد من إجراء الفحص على **كلا الوحدتين المنفصلتين (WIC 10 و WIC 40)** لضمان شمولية التقرير.")
