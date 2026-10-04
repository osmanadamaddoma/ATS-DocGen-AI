import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import threading
import io
import base64
import math
import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import pdfplumber
import streamlit as st
import extra_streamlit_components as stx # مكتبة إدارة الكوكيز المضافة
from google import genai
from gtts import gTTS

def get_fuel_table_from_csv(uploaded_file):
    # القيم الافتراضية لجدول الوقود والكفاءة في حال لم يرفع المستخدم ملف CSV
    default_data = {
        25: {"g_cat": 260, "g_cummins": 265, "g_perkins": 270, "AVG": 0.35, "eff": 28},
        50: {"g_cat": 220, "g_cummins": 225, "g_perkins": 230, "AVG": 0.28, "eff": 32},
        75: {"g_cat": 205, "g_cummins": 208, "g_perkins": 212, "AVG": 0.25, "eff": 38},
        100: {"g_cat": 200, "g_cummins": 202, "g_perkins": 205, "AVG": 0.24, "eff": 40}
    }
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            custom_data = {}
            for _, row in df.iterrows():
                load = int(row.get("Load %", 0))
                if load > 0:
                    custom_data[load] = {
                        "g_cat": row.get("CAT g/kWh", 205),
                        "g_cummins": row.get("Cummins", 208),
                        "g_perkins": row.get("Perkins", 212),
                        "AVG": row.get("SFC L/kWh", 0.25),
                        "eff": row.get("Eff %", 35)
                    }
            if custom_data:
                return custom_data
        except Exception:
            pass # في حال حدوث خطأ في القراءة، نعود للقيم الافتراضية
            
    return default_data

def calculate_fuel_consumption_and_emissions_v6(kw_load, hrs, model, rating_kw, fuel_table_live=None):
    try:
        kw_load = float(kw_load)
        hrs = float(hrs)
        rating_kw = float(rating_kw) if rating_kw else 410.0
        
        load_pct = (kw_load / rating_kw) * 100 if rating_kw > 0 else 0
        
        sfc = 0.25
        eff = 35
        
        if fuel_table_live:
            valid_keys = [k for k in fuel_table_live.keys() if isinstance(k, (int, float))]
            if valid_keys:
                closest_load = min(valid_keys, key=lambda x: abs(x - load_pct))
                sfc = fuel_table_live[closest_load].get("AVG", 0.25)
                eff = fuel_table_live[closest_load].get("eff", 35)
        
        liters = round(kw_load * sfc * hrs, 2)
        co2 = round(liters * 2.68, 2)
        
        return liters, co2, sfc, eff
        
    except Exception:
        return 0.0, 0.0, 0.25, 35

# محاولة استيراد مكتبة Supabase
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None

# استيراد مكتبة قاعدة بيانات إنترنت الأشياء الحية (IoT Database)
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت واللغة
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar"

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# تهيئة هيكل السجلات والمواقع
def get_default_sites_data():
    return {
        "الخرطوم (القائمة الرئيسية)": {
            "الموقع الرئيسي - كافوري (موقع فرعي)": {
                "address": "الخرطوم - المنطقة الصناعية - كافوري",
                "generators": {
                    "G1": {
                        "model": "Perkins 410 kVA",
                        "run_hours": 700.0,
                        "target": 940.0,
                        "kw": 410.0,
                        "load": 250.0,
                        "calib_elec": {
                            "v_nominal": 400.0, "v_measured": 398.0,
                            "freq_nominal": 50.0, "freq_measured": 50.1,
                            "current_max": 600.0, "current_measured": 360.0,
                            "pf": 0.85, "ct_ratio": "600/5"
                        },
                        "calib_engine": {
                            "oil_press_bar": 4.5, "coolant_temp_c": 85.0,
                            "rpm": 1500.0, "battery_v": 26.5,
                            "ambient_temp": 43.0
                        }
                    },
                    "G2": {
                        "model": "Cummins 250 kVA",
                        "run_hours": 1200.0,
                        "target": 1500.0,
                        "kw": 250.0,
                        "load": 180.0,
                        "calib_elec": {
                            "v_nominal": 400.0, "v_measured": 402.0,
                            "freq_nominal": 50.0, "freq_measured": 49.9,
                            "current_max": 360.0, "current_measured": 260.0,
                            "pf": 0.82, "ct_ratio": "400/5"
                        },
                        "calib_engine": {
                            "oil_press_bar": 4.2, "coolant_temp_c": 88.0,
                            "rpm": 1500.0, "battery_v": 25.8,
                            "ambient_temp": 45.0
                        }
                    }
                }
            }
        }
    }

if "sites_data" not in st.session_state or not st.session_state.sites_data:
    st.session_state.sites_data = get_default_sites_data()

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "الخرطوم (القائمة الرئيسية) - الموقع الرئيسي - كافوري (موقع فرعي)",
            "generator": "G1",
            "technician": "أحمد فني الصيانة",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "طبيعي"
        }
    ]

gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")

client = genai.Client(api_key=gemini_key) if gemini_key else None

supabase = None
if create_client:
    supabase_url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not supabase_url and "supabase" in st.secrets:
        supabase_url = st.secrets["supabase"].get("SUPABASE_URL")
        supabase_key = st.secrets["supabase"].get("SUPABASE_KEY")
    if supabase_url and supabase_key:
        try:
            supabase = create_client(supabase_url, supabase_key)
        except Exception:
            pass

def play_audio(text, lang='ar', loop=False):
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts_lang = 'en' if st.session_state.lang == 'en' or lang == 'en' else 'ar'
        tts = gTTS(text=text, lang=tts_lang)
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
    except Exception:
        pass

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client:
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY."
    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة."
    prompt = f"""
    You are an expert industrial consulting engineer specializing in generators, DSE control panels (DSE 7320, DSE 8610 MKII), Perkins & Cummins engines, and cooling systems.
    Fault Code / Alarm: "{fault_code}"
    Catalog Context:
    \"\"\"
    {context_text if context_text else "No specific catalog excerpt."}
    \"\"\"
    Provide a professional diagnostic report with:
    1. Technical Explanation / Fault Nature.
    2. Top 3 Probable Causes.
    3. Sequential Field Corrective Actions.
    {lang_instr}
    """
    try:
        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        return f"❌ Error: {e}"

# =========================================================
# 1. دوال النظام المساعدة وتصميم تقرير الـ PDF المطور
# =========================================================
def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
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
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=12, w=25)
            text_x = 40
        else:
            text_x = 10
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
        self.set_line_width(0.2)
        self.line(10, 282, 200, 282)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, "Prepared by: Osman Adam Addoma | Power Systems Engineer", ln=True, align="C")
        self.cell(0, 4, f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

def fetch_live_iot_data():
    import random
    today = datetime.now()
    data = []
    for i in range(20):
        t = today - timedelta(minutes=(20-i)*2)
        data.append({
            "_time": t,
            "temperature": 80.0 + random.uniform(-3, 6),
            "vibration": 3.2 + random.uniform(-0.5, 1.2),
            "pressure": 4.1 + random.uniform(-0.4, 0.4)
        })
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    rho_copper = 0.0178
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    v_drop_pct = (v_drop / 400.0) * 100
    return round(v_drop, 2), round(v_drop_pct, 2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    co2_kg = liters * 2.68
    return round(liters, 1), round(co2_kg, 1)

# =========================================================
# 2. نظام الاشتراكات والتحقق
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (Addoma Trading Services)",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-15",
        "duration_days": 365,
    }
}
ADMIN_CODES = ["ADDOMA-2026-PRO"]

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_persistent_final")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = True
    st.session_state.active_code = "ADDOMA-2026-PRO"
    st.session_state.user_email = CLIENTS_DATABASE["ADDOMA-2026-PRO"]["name"]
    st.session_state.role = "admin"

st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if "العربية" in selected_lang else "en"
L = st.session_state.lang

# خيار إعادة ضبط النظام لمسح أي بيانات عالقة
st.sidebar.divider()
if st.sidebar.button("🧹 مسح البيانات العالقة (Factory Reset)", type="secondary"):
    st.session_state.sites_data = get_default_sites_data()
    st.sidebar.success("✅ تم تصفير وإعادة ضبط السجلات والمواقع بنجاح!")
    st.rerun()

TXT = {
    "ar": {
        "nav_header": "⚙️ نظام الدومة للخدمات التجارية",
        "nav_status": "🟢 النظام متصل ومفعل",
        "btn_chat": "💬 المساعد الذكي الهندسي",
        "btn_dashboard": "📊 لوحة تحكم الأنظمة",
        "btn_apps": "🛠️ التطبيقات الهندسية الشاملة",
        "btn_logout": "🚪 تسجيل الخروج",
        "app_selection": "🛠️ التطبيقات المتاحة (نسخة احترافية)",
        "choose_app": "اختر النظام المطلوب:"
    },
    "en": {
        "nav_header": "⚙️ Addoma Trading Services System",
        "nav_status": "🟢 System Connected & Active",
        "btn_chat": "💬 Smart Engineering Assistant",
        "btn_dashboard": "📊 Systems Control Dashboard",
        "btn_apps": "🛠️ Engineering Apps Suite",
        "btn_logout": "🚪 Logout",
        "app_selection": "🛠️ Available Apps (Pro Version)",
        "choose_app": "Select System Module:"
    }
}[L]

with st.sidebar:
    st.header(TXT["nav_header"])
    st.success(TXT["nav_status"])
    st.write("---")
    if st.button(TXT["btn_chat"], use_container_width=True):
        st.session_state.current_page = "chat"
    if st.button(TXT["btn_dashboard"], use_container_width=True):
        st.session_state.current_page = "dashboard"
    if st.button(TXT["btn_apps"], use_container_width=True):
        st.session_state.current_page = "main_apps"

st.sidebar.divider()
st.sidebar.markdown(TXT["app_selection"])

def on_app_change():
    st.session_state.current_page = "main_apps"

apps_list_ar = [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص المعدات (WIC وغيرها)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)"
]
apps_list_en = [
    "⚙️ 1. Predictive Maintenance & Gensets",
    "🎛️ 2. Remote Operations & Control Center",
    "📊 3. Daily Monitoring & Reminders",
    "🤖 4. AI Diagnostics & Catalog Reader",
    "🔍 5. Equipment Inspection (WIC & Heavy Duty)",
    "🧮 6. Smart Electrical & Carbon Calculator"
]

selected_app = st.sidebar.radio(
    TXT["choose_app"],
    apps_list_ar if L == "ar" else apps_list_en,
    on_change=on_app_change
)

# =========================================================
# النافذة المنبثقة للتعديل
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة" if L == "ar" else "📝 Edit Generator & Calibration Data")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})
    st.markdown(f"### ⚙️ {gen_key} - Site: {sub_site}")
    tech_name = st.text_input("اسم الفني / Technician Name:", value="فني الصيانة المناوب")
    tab1, tab2, tab3 = st.tabs(["🏷️ Basic Data", "⚡ Electrical", "🔧 Engine"])
    with tab1:
        new_model = st.text_input("Model / الطراز", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("Run Hours / ساعات التشغيل", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours / الساعات المستهدفة", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("Capacity (kW) / السعة", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("Current Load (kW) / الحمولة", min_value=0.0, value=float(gen_data.get("load", 0.0)))
    with tab2:
        v_nom = st.number_input("Nominal Voltage (V)", value=float(elec.get("v_nominal", 400.0)))
        v_meas = st.number_input("Measured Voltage (V)", value=float(elec.get("v_measured", 398.0)))
        f_nom = st.number_input("Nominal Freq (Hz)", value=float(elec.get("freq_nominal", 50.0)))
        f_meas = st.number_input("Measured Freq (Hz)", value=float(elec.get("freq_measured", 50.0)))
        c_max = st.number_input("Max Current (A)", value=float(elec.get("current_max", 600.0)))
        c_meas = st.number_input("Measured Current (A)", value=float(elec.get("current_measured", 360.0)))
        pf_val = st.number_input("Power Factor (PF)", value=float(elec.get("pf", 0.85)))
        ct_rat = st.text_input("CT Ratio", value=str(elec.get("ct_ratio", "600/5")))
    with tab3:
        o_press = st.number_input("Oil Press (Bar)", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("Coolant Temp (°C)", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = st.number_input("Engine Speed (RPM)", value=float(eng.get("rpm", 1500.0)))
        b_volt = st.number_input("Battery (V)", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("Ambient Temp (°C)", value=float(eng.get("ambient_temp", 43.0)))
    if st.button("💾 Save Data / حفظ البيانات", use_container_width=True, type="primary"):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {
            "model": new_model,
            "run_hours": new_run_hours,
            "target": new_target,
            "kw": new_kw,
            "load": new_load,
            "calib_elec": {
                "v_nominal": v_nom, "v_measured": v_meas,
                "freq_nominal": f_nom, "freq_measured": f_meas,
                "current_max": c_max, "current_measured": c_meas,
                "pf": pf_val, "ct_ratio": ct_rat
            },
            "calib_engine": {
                "oil_press_bar": o_press, "coolant_temp_c": c_temp,
                "rpm": r_rpm, "battery_v": b_volt,
                "ambient_temp": ambient_t
            }
        }
        st.success("✅ Saved successfully!")
        st.rerun()

# =========================================================
# --- عرض الواجهات الرئيسية ---
# =========================================================
if st.session_state.current_page == "chat":
    st.title("🤖 " + ("المساعد الذكي الهندسي" if L == "ar" else "Smart AI Assistant"))
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحباً بك! كيف يمكنني مساعدتك اليوم؟"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    user_query = st.chat_input("اكتب استفسارك الهندسي هنا...")
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("assistant"):
            response_text = analyze_fault_with_gemini(user_query, language=L)
            st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})

elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("لوحة تحكم الأنظمة والمتابعة" if L == "ar" else "Systems Control Dashboard"))
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Generators Status", value="Stable / مستقرة", delta="Sync Ready")
    col2.metric(label="WIC Cold Rooms", value="2 Units (WIC10 & WIC40)", delta="-1°C", delta_color="inverse")
    col3.metric(label="Database Link", value="Supabase Online", delta="Ping 12ms")
    st.divider()

else:
    if "1." in selected_app:
        st.title("⚙️ " + ("نظام الصيانة التنبؤية ومراقبة المولدات" if L == "ar" else "Predictive Maintenance & Genset Monitoring"))
        
        st.sidebar.subheader("🎨 PDF Branding / الشعار")
        logo_file = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo_up")
        
        # إدارة الإضافة والحذف الصريحة للمولدات
        st.subheader("📍 Site Management / إدارة المواقع والمولدات")
        tab_manage1, tab_manage2 = st.tabs(["➕ إضافة سجل مولد جديد", "🗑️ مسح/إخراج مولد من الخدمة"])
        
        with tab_manage1:
            col_m1, col_m2, col_m3 = st.columns(3)
            add_main_s = col_m1.text_input("المنطقة الجغرافية / القائمة الرئيسية:", value="الخرطوم (القائمة الرئيسية)", key="inp_add_m")
            add_sub_s = col_m2.text_input("اسم الموقع الفرعي:", value="الموقع الرئيسي - كافوري (موقع فرعي)", key="inp_add_sub")
            add_gen_id = col_m3.text_input("رمز/معرف المولد الجديد:", value="G3", key="inp_add_gid")
            
            col_m4, col_m5 = st.columns(2)
            add_model = col_m4.text_input("طراز وموديل المولد:", value="Perkins 150 kVA", key="inp_add_mod")
            add_kw = col_m5.number_input("القدرة بالكيلوواط (kW):", min_value=1.0, value=150.0, key="inp_add_kw")
            
            if st.button("💾 حفظ المولد الجديد في النظام", type="primary", use_container_width=True):
                if add_main_s and add_sub_s and add_gen_id:
                    if add_main_s not in st.session_state.sites_data:
                        st.session_state.sites_data[add_main_s] = {}
                    if add_sub_s not in st.session_state.sites_data[add_main_s]:
                        st.session_state.sites_data[add_main_s][add_sub_s] = {"address": add_sub_s, "generators": {}}
                    
                    st.session_state.sites_data[add_main_s][add_sub_s]["generators"][add_gen_id] = {
                        "model": add_model,
                        "run_hours": 0.0,
                        "target": 250.0,
                        "kw": add_kw,
                        "load": 0.0,
                        "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                        "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                    }
                    st.success(f"✅ تم إضافة المولد {add_gen_id} إلى الموقع {add_sub_s} وحفظه بنجاح!")
                    st.rerun()

        with tab_manage2:
            main_sites_del = list(st.session_state.sites_data.keys())
            if main_sites_del:
                c_del1, c_del2, c_del3 = st.columns(3)
                del_main = c_del1.selectbox("اختر المنطقة:", main_sites_del, key="sb_del_m")
                sub_sites_del = list(st.session_state.sites_data[del_main].keys()) if del_main else []
                del_sub = c_del2.selectbox("اختر الموقع:", sub_sites_del, key="sb_del_s") if sub_sites_del else None
                gens_del = list(st.session_state.sites_data[del_main][del_sub]["generators"].keys()) if (del_main and del_sub) else []
                del_gen = c_del3.selectbox("اختر المولد للمسح:", gens_del, key="sb_del_g") if gens_del else None
                
                if st.button("🗑️ مسح وإزالة المولد المSelected", type="primary"):
                    if del_main and del_sub and del_gen:
                        del st.session_state.sites_data[del_main][del_sub]["generators"][del_gen]
                        st.success(f"✅ تم مسح المولد {del_gen} بنجاح من النظام!")
                        st.rerun()

        st.divider()
        st.markdown("### 📌 اختيار الموقع والمولد الحالي")
        main_sites = list(st.session_state.sites_data.keys())
        col_site1, col_site2 = st.columns(2)
        selected_main_site = col_site1.selectbox("🌍 اختر المنطقة الجغرافية:", main_sites) if main_sites else None
        
        if selected_main_site:
            sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
            selected_sub_site = col_site2.selectbox("📍 اختر الموقع:", sub_sites) if sub_sites else None
            current_site_address = st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", "") if selected_sub_site else ""
        else:
            selected_sub_site = None
            current_site_address = ""

        if not main_sites or not selected_main_site or not selected_sub_site:
            st.warning("Please add and select a main site and sub-site to manage generators.")
            st.stop()

        gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())
        if not gen_list:
            st.info("لا توجد مولدات في هذا الموقع. قم بإضافة مولد من الأعلى.")
        else:
            col_select_g, col_modal_btn = st.columns([2, 1])
            selected_gen = col_select_g.selectbox("Select Generator:", gen_list)
            if col_modal_btn.button("📝 Open Calibration Modal"):
                edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)

            gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            calib_e = gen_info.get("calib_elec", {})
            calib_m = gen_info.get("calib_engine", {})

            st.subheader(f"📊 Calibration Dashboard ({selected_gen})")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("Model & Capacity", f"{gen_info['model']}", f"{gen_info['kw']} kW")
            m_c2.metric("Run Hours / Target", f"{gen_info['run_hours']} hrs", f"Target: {gen_info['target']} hrs")
            m_c3.metric("Measured Voltage", f"{calib_e.get('v_measured', 0)} V", f"Nominal: {calib_e.get('v_nominal', 0)} V")
            m_c4.metric("Coolant / Ambient Temp", f"{calib_m.get('coolant_temp_c', 0)} °C", f"Ambient: {calib_m.get('ambient_temp', 0)} °C")

            # جدول الصيانة التنبؤية الـ 14 وحدة
            parts_key = f"parts_{selected_main_site}_{selected_sub_site}_{selected_gen}"
            if parts_key not in st.session_state:
                st.session_state[parts_key] = [
                    {"الوحدة": 1, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 180.0, "تجديد (تصفير)": False},
                    {"الوحدة": 2, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0, "تجديد (تصفير)": False},
                    {"الوحدة": 3, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 480.0, "تجديد (تصفير)": False},
                    {"الوحدة": 4, "تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": 650.0, "تجديد (تصفير)": False},
                    {"الوحدة": 5, "تصنيف القطعة": "Fan Belt System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": 1550.0, "تجديد (تصفير)": False},
                    {"الوحدة": 6, "تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": 2800.0, "تجديد (تصفير)": False},
                    {"الوحدة": 7, "تصنيف القطعة": "Fuel System", "قطع الغيار / الفلاتر": "Injectors Check", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 3200.0, "تجديد (تصفير)": False},
                    {"الوحدة": 8, "تصنيف القطعة": "النظام الكهربائي", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 6100.0, "تجديد (تصفير)": False},
                    {"الوحدة": 9, "تصنيف القطعة": "Electric System", "قطع الغيار / الفلاتر": "Charging Alternator", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 8900.0, "تجديد (تصفير)": False},
                    {"الوحدة": 10, "تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Top Overhaul", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 9200.0, "تجديد (تصفير)": False},
                    {"الوحدة": 11, "تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Major Overhaul", "العمر الافتراضي (ساعة)": 20000.0, "الساعات المنقضية (ساعة)": 11000.0, "تجديد (تصفير)": False},
                    {"الوحدة": 12, "تصنيف القطعة": "Oilers System", "قطع الغيار / الفلاتر": "Oil Cooler Clean", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 3800.0, "تجديد (تصفير)": False},
                    {"الوحدة": 13, "تصنيف القطعة": "نظام التبريد", "قطع الغيار / الفلاتر": "Water Pump", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": 5200.0, "تجديد (تصفير)": False},
                    {"الوحدة": 14, "تصنيف القطعة": "نظام الهواء", "قطع الغيار / الفلاتر": "Turbocharger Check", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 7100.0, "تجديد (تصفير)": False},
                ]

            st.subheader(f"🛢️ Predictive Maintenance Table (14 Parts) - {selected_gen}")
            df_parts_input = pd.DataFrame(st.session_state[parts_key])
            edited_df = st.data_editor(
                df_parts_input,
                num_rows="dynamic",
                width="stretch",
                column_config={"تجديد (تصفير)": st.column_config.CheckboxColumn("Reset Counter", default=False)}
            )

            if st.button("🔄 Update / Reset Checked Parts", type="primary"):
                new_data = []
                for idx, row in edited_df.iterrows():
                    item = row.to_dict()
                    if item.get("تجديد (تصفير)"):
                        item["الساعات المنقضية (ساعة)"] = 0.0
                        item["تجديد (تصفير)"] = False
                    new_data.append(item)
                st.session_state[parts_key] = new_data
                st.success("Updated Maintenance Schedule!")
                st.rerun()

            processed_rows = []
            bar_colors = []
            for idx, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
                cat = str(row.get("تصنيف القطعة", "Other"))
                part = str(row.get("قطع الغيار / الفلاتر", "Part"))
                life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
                used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
                rem = life - used
                pct = (used / life) * 100 if life > 0 else 0
                
                color_code = "#28a745" if pct < 70 else ("#ffc107" if pct < 90 else "#dc3545")
                status_str = "Good (<70%)" if pct < 70 else ("Warning (70-90%)" if pct < 90 else "Critical (>90%)")
                
                bar_colors.append(color_code)
                processed_rows.append({
                    "الوحدة": row.get("الوحدة", idx + 1),
                    "تصنيف القطعة": cat,
                    "قطع الغيار / الفلاتر": part,
                    "العمر الافتراضي (ساعة)": life,
                    "الساعات المنقضية (ساعة)": used,
                    "المدة المتبقية (ساعة)": max(0.0, rem),
                    "نسبة الاستهلاك (%)": round(pct, 1),
                    "حالة التنبيه": status_str,
                    "الكود الملون": color_code
                })

            df_result = pd.DataFrame(processed_rows)

            # دالة إخراج التقرير PDF الشامل المحدث
            def generate_full_pdf_bytes():
                temp_logo_path = None
                if logo_file:
                    temp_logo_path = f"temp_logo_{uuid.uuid4().hex}.png"
                    with open(temp_logo_path, "wb") as f:
                        f.write(logo_file.getbuffer())

                pdf = ComprehensivePDF("GENERATOR PREDICTIVE MAINTENANCE REPORT", logo_path=temp_logo_path)
                pdf.add_page()
                pdf.set_fill_color(245, 247, 250)
                pdf.rect(10, 35, 190, 45, "F")
                pdf.set_xy(12, 37)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 5, f"Generator Data Site Address: {sanitize_latin_only(current_site_address)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Main Site: {sanitize_latin_only(selected_main_site)} | Sub Site: {sanitize_latin_only(selected_sub_site)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | Capacity: {gen_info['kw']} kW", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Current Run Hours: {gen_info['run_hours']} hrs | Target Hours: {gen_info['target']} hrs", ln=True)
                
                amb_temp_val = calib_m.get('ambient_temp', 43.0)
                pdf.ln(2)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(200, 30, 30)
                pdf.cell(0, 5, "Engine Oil Recommendation based on Ambient Temperature:", ln=True)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(24, 43, 73)
                if amb_temp_val >= 45:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 20W50", ln=True)
                elif amb_temp_val >= 43:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 15W40", ln=True)
                else:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: USE STANDARD OIL SIZE 15W40", ln=True)

                pdf.ln(8)
                headers_pdf = ["#", "Part / Service Name", "Lifespan", "Used", "Remain", "Status"]
                widths = [10, 60, 25, 25, 25, 45]
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_fill_color(24, 43, 73)
                pdf.set_text_color(255, 255, 255)
                for h, w in zip(headers_pdf, widths):
                    pdf.cell(w, 6, h, border=1, fill=True, align="C")
                pdf.ln()

                pdf.set_font("Helvetica", "", 7)
                pdf.set_text_color(0, 0, 0)
                for i, row in df_result.iterrows():
                    fill = (i % 2 == 0)
                    pdf.set_fill_color(240, 243, 246) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.cell(widths[0], 5, str(row["الوحدة"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[1], 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:32], border=1, fill=fill)
                    pdf.cell(widths[2], 5, str(row["العمر الافتراضي (ساعة)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[3], 5, str(row["الساعات المنقضية (ساعة)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[4], 5, str(row["المدة المتبقية (ساعة)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[5], 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1, fill=fill)
                    pdf.ln()

                pdf_out = pdf.output(dest="S")
                return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

            st.download_button(
                label=f"🖨️ Download Full Report for ({selected_gen})",
                data=generate_full_pdf_bytes(),
                file_name=f"Comprehensive_Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    elif "2." in selected_app:
        st.title("🎛️ " + ("غرفة التحكم والتشغيل عن بُعد" if L == "ar" else "Remote Control Center (IoT & Telemetry)"))
        df_iot = fetch_live_iot_data()
        if not df_iot.empty:
            latest = df_iot.iloc[-1]
            col1, col2, col3 = st.columns(3)
            col1.metric("🌡️ Temp (°C)", f"{latest['temperature']:.1f}")
            col2.metric("〰️ Vibration (mm/s)", f"{latest['vibration']:.2f}")
            col3.metric("🗜️ Oil Press (Bar)", f"{latest['pressure']:.1f}")
            fig_temp = px.line(df_iot, x='_time', y='temperature', title="Live Sensor Trend")
            st.plotly_chart(fig_temp, use_container_width=True)

    elif "3." in selected_app:
        st.title("📊 " + ("المتابعة اليومية وتقارير الإدارة" if L == "ar" else "Daily Monitoring & Tech Reminders"))
        today_str = datetime.now().strftime("%Y-%m-%d")
        st.write(f"Date: {today_str}")

    elif "4." in selected_app:
        st.title("🤖 " + ("المساعد الذكي والكتالوجات وقراءة الأكواد" if L == "ar" else "AI Diagnostics & Fault Code Reader"))
        fault_input = st.text_input("Enter Fault Code:", value="Over Current")
        if st.button("🔍 Analyze Fault", use_container_width=True):
            st.markdown(analyze_fault_with_gemini(fault_input, language=L))

    elif "5." in selected_app:
        st.title("🔍 " + ("نظام فحص المعدات مقارنة بصرية" if L == "ar" else "Equipment Visual Inspection (WIC & Gensets)"))
        st.info("Visual Inspection Module Active")

    elif "6." in selected_app:
        st.title("🧮 " + ("الحاسبة الهندسية للكهرباء والانبعاثات" if L == "ar" else "Smart Electrical & Carbon Calculator"))
        fuel_table_live = get_fuel_table_from_csv(None)
        
        tab_calc1, tab_calc2 = st.tabs(["⚡ Cable Voltage Drop", "🌱 Fuel & Carbon Footprint"])
        with tab_calc1:
            i_amp = st.number_input("Current (Amperes):", value=250.0)
            dist_m = st.number_input("Cable Length (Meters):", value=120.0)
            c_size = st.selectbox("Cable Size (mm²):", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4)
            v_drop, v_drop_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size)
            st.metric("Voltage Drop", f"{v_drop} V", f"{v_drop_pct}%")

        with tab_calc2:
            kw_load = st.number_input("Running Load (kW):", value=200.0)
            hours_run = st.number_input("Operating Hours:", value=24.0)
            est_liters, est_co2 = calculate_fuel_consumption_and_emissions(kw_load, hours_run)
            st.metric("Estimated Diesel Used", f"{est_liters} Liters")
            st.metric("Estimated CO2 Output", f"{est_co2} kg")
