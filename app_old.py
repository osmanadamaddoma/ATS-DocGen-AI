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
import extra_streamlit_components as stx
from google import genai
from gtts import gTTS

def get_fuel_table_from_csv(uploaded_file):
    default_data = {
        25: {"g_cat": 260, "g_cummins": 265, "g_perkins": 270, "AVG": 0.35, "eff": 28},
        50: {"g_cat": 220, "g_cummins": 225, "g_perkins": 230, "AVG": 0.28, "eff": 32},
        75: {"g_cat": 205, "g_cummins": 208, "g_perkins": 212, "AVG": 0.25, "eff": 38},
        100: {"g_cat": 200, "g_cummins": 202, "g_perkins": 205, "AVG": 0.24, "eff": 40}
    }
    
    if uploaded_file is not None:
        try:
            import pandas as pd
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
            pass
            
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

try:
    from supabase import create_client, Client
except ImportError:
    create_client = None

try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None

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

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
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
if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

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
            response = supabase.table("subscriptions").select("*").limit(1).execute()
        except Exception as e:
            st.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")

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
                    Your browser does not support audio playback.
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"حدث خطأ في تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client:
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY."
    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة."
    prompt = f"""
    You are an expert industrial consulting engineer specializing in generators, DSE control panels, engines, and cooling systems.
    Fault Code / Alarm: "{fault_code}"
    Catalog Context: "{context_text if context_text else "No specific catalog excerpt."}"
    Provide a diagnostic report with Technical Explanation, Top 3 Causes, and Actions.
    {lang_instr}
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
            err_msg = str(e)
            if "503" in err_msg or "UNAVAILABLE" in err_msg:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return "⚠️ High server load (503). Please retry in a few seconds." if language == "en" else "⚠️ الخادم يمر بضغط عالٍ حالياً."
            return f"❌ Error: {err_msg}"

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
    if not InfluxDBClient or "influxdb" not in st.secrets:
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
        df = pd.DataFrame(data).sort_values("_time")
        return df
    try:
        cfg = st.secrets["influxdb"]
        client_iot = InfluxDBClient(url=cfg["url"], token=cfg["token"], org=cfg["org"])
        query_api = client_iot.query_api()
        flux_query = f'''
        from(bucket: "{cfg["bucket"]}")
            |> range(start: -30m)
            |> filter(fn: (r) => r["_measurement"] == "generator_01")
            |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        '''
        df_db = query_api.query_data_frame(flux_query)
        if not df_db.empty:
            df_db['_time'] = pd.to_datetime(df_db['_time'])
            return df_db
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    rho_copper = 0.0178
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    v_drop_pct = (v_drop / 400.0) * 100
    return round(v_drop, 2), round(v_drop_pct, 2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    co2_kg = liters * 2.68
    return round(liters, 1), round(co2_kg, 1)

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
}

ADMIN_CODES = ["ADDOMA-2026-PRO"]
if supabase:
    try:
        res_load = supabase.table("subscriptions").select("*").execute()
        for row in res_load.data:
            c = str(row.get("code","")).strip().upper()
            if c:
                CLIENTS_DATABASE[c] = {
                    "name": row.get("client_name", "عميل"),
                    "plan": row.get("plan", "شهري (Monthly)"),
                    "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                    "duration_days": int(row.get("duration_days", 30)),
                }
    except Exception as e:
        print(f"Load subscriptions error: {e}")

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_persistent_final")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
query_params = st.query_params
code_from_url = query_params.get("code", None)
saved_code = None
try:
    saved_code = cookie_manager.get(cookie="activation_code_v5")
    if not saved_code:
        saved_code = cookie_manager.get(cookie="activation_code")
except:
    saved_code = None
final_saved = code_from_url if code_from_url else saved_code

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if final_saved and not st.session_state.authenticated:
    clean_saved = str(final_saved).strip().upper()
    if clean_saved in CLIENTS_DATABASE:
        st.session_state.authenticated = True
        st.session_state.active_code = clean_saved
        st.session_state.user_email = CLIENTS_DATABASE[clean_saved]["name"]
        st.session_state.role = "admin" if clean_saved in ADMIN_CODES else "client"

st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if "العربية" in selected_lang else "en"
L = st.session_state.lang

TXT = {
    "ar": {
        "title": "🔐 بوابة تفعيل النظام الموحد",
        "code_input": "كود التفعيل:",
        "btn_activate": "تفعيل",
        "invalid_code": "❌ كود التفعيل غير صحيح.",
        "warning_auth": "🔒 يرجى إدخال كود اشتراك صالح للوصول إلى التطبيقات.",
        "nav_header": "⚙️ نظام الدومة للخدمات التجارية",
        "nav_status": "🟢 النظام متصل ومفعل",
        "btn_chat": "💬 المساعد الذكي الهندسي",
        "btn_dashboard": "📊 لوحة تحكم الأنظمة",
        "btn_apps": "🛠️ التطبيقات الهندسية الشاملة",
        "btn_logout": "🚪 تسجيل الخروج / مسح التفعيل",
        "client": "👤 العميل:",
        "plan": "📦 الباقة:",
        "remaining": "⏳ المتبقي:",
        "days": "يوم",
        "app_selection": "🛠️ التطبيقات المتاحة (نسخة احترافية)",
        "choose_app": "اختر النظام المطلوب:"
    },
    "en": {
        "title": "🔐 Unified Activation Portal",
        "code_input": "Activation Code:",
        "btn_activate": "Activate",
        "invalid_code": "❌ Invalid activation code.",
        "warning_auth": "🔒 Please enter a valid activation code to access.",
        "nav_header": "⚙️ Addoma Trading Services System",
        "nav_status": "🟢 Connected & Active",
        "btn_chat": "💬 Smart Engineering Assistant",
        "btn_dashboard": "📊 Systems Dashboard",
        "btn_apps": "🛠️ Engineering Apps Suite",
        "btn_logout": "🚪 Logout",
        "client": "👤 Client:",
        "plan": "📦 Plan:",
        "remaining": "⏳ Days Left:",
        "days": "days",
        "app_selection": "🛠️ Available Apps",
        "choose_app": "Select System Module:"
    }
}[L]

if not st.session_state.authenticated:
    st.title(TXT["title"])
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")
    if st.sidebar.button(TXT["btn_activate"]):
        clean_code = user_code.strip().upper()
        if clean_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = clean_code
            st.session_state.user_email = CLIENTS_DATABASE[clean_code]["name"]
            st.session_state.role = "admin" if clean_code in ADMIN_CODES else "client"
            expires_at = datetime.now() + timedelta(days=365)
            try:
                cookie_manager.set("activation_code_v5", clean_code, expires_at=expires_at)
                cookie_manager.set("activation_code", clean_code, expires_at=expires_at)
            except:
                pass
            st.query_params["code"] = clean_code
            st.rerun()
        else:
            st.sidebar.error(TXT["invalid_code"])
    st.warning(TXT["warning_auth"])
    st.stop()
else:
    with st.sidebar:
        st.header(TXT["nav_header"])
        st.success(TXT["nav_status"])
        st.write("---")
        if st.button(TXT["btn_chat"], use_container_width=True): st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True): st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True): st.session_state.current_page = "main_apps"
        st.write("---")
        if st.button(TXT["btn_logout"], type="primary", use_container_width=True):
            st.session_state.authenticated = False
            try:
                cookie_manager.delete("activation_code_v5")
                cookie_manager.delete("activation_code")
            except:
                pass
            if "code" in st.query_params: del st.query_params["code"]
            if "active_code" in st.session_state: del st.session_state["active_code"]
            st.rerun()

input_code = st.session_state.get("active_code", "")
is_pro = False
if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    if datetime.now().date() <= expiry_dt:
        is_pro = True
        st.sidebar.success("✅ Subscription Verified!")
        st.sidebar.markdown(f"**{TXT['client']}** {data['name']}")
    else:
        st.sidebar.error(f"❌ License expired.")
        st.session_state.authenticated = False
        st.stop()
if not is_pro: st.stop()

st.sidebar.divider()
st.sidebar.markdown(TXT["app_selection"])
def on_app_change(): st.session_state.current_page = "main_apps"
apps_list_ar = [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص المعدات (WIC وغيرها)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)"
]
apps_list_en = ["⚙️ 1. Predictive Maintenance", "🎛️ 2. Remote Operations", "📊 3. Daily Monitoring", "🤖 4. AI Diagnostics", "🔍 5. Equipment Inspection", "🧮 6. Smart Calculator"]
selected_app = st.sidebar.radio(TXT["choose_app"], apps_list_ar if L == "ar" else apps_list_en, on_change=on_app_change)
st.sidebar.divider()

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
        new_run_hours = st.number_input("Run Hours", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("Capacity (kW)", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("Current Load (kW)", min_value=0.0, value=float(gen_data.get("load", 0.0)))
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
            "model": new_model, "run_hours": new_run_hours, "target": new_target,
            "kw": new_kw, "load": new_load,
            "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat},
            "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}
        }
        st.success("✅ Saved successfully!")
        time.sleep(1)
        st.rerun()

if st.session_state.current_page == "chat":
    st.title("🤖 " + ("المساعد الذكي الهندسي" if L == "ar" else "Smart AI Assistant"))
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحباً بك! كيف يمكنني مساعدتك اليوم؟"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    user_query = st.chat_input("اكتب استفسارك الهندسي هنا...")
    if user_query:
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"): st.markdown(user_query)
        with st.chat_message("assistant"):
            response_text = analyze_fault_with_gemini(user_query, language=L) if client else "API Key missing."
            st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})

elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("لوحة تحكم الأنظمة والمتابعة" if L == "ar" else "Systems Control Dashboard"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Generators Status", "Stable")
    col2.metric("WIC Cold Rooms", "2 Units (WIC10 & WIC40)")
    col3.metric("Database Link", "Online")
else:
    if "1." in selected_app:
        st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")
        col_top_audio1, col_top_audio2 = st.columns([3, 1])
        with col_top_audio2:
            mute_label = "🔇 Mute" if not st.session_state.audio_muted else "🔊 Unmute"
            if st.button(mute_label, use_container_width=True):
                st.session_state.audio_muted = not st.session_state.audio_muted
                st.rerun()
        
        st.sidebar.subheader("🎨 PDF Branding / الشعار")
        logo_file = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo_up")
        
        st.subheader("📍 Site Management / إدارة المواقع والمولدات")
        with st.expander("➕ إضافة منطقة وموقع ومولدات يدوياً (يُحفظ فوراً في الذاكرة)", expanded=False):
            geo_region = st.text_input("عنوان المنطقة الجغرافية (مثال: الخرطوم):", key="geo_reg_input")
            site_name = st.text_input("اسم الموقع [مثال: مصنع كافوري]:", key="site_name_input")
            site_address = st.text_input("عنوان الموقع التفصيلي:", key="site_add_input")
            num_gens = st.number_input("عدد المولدات في الموقع:", min_value=1, max_value=20, value=1, step=1)
            gen_inputs = []
            for i in range(int(num_gens)):
                st.markdown(f"**المولد رقم {i+1}**")
                col_g1, col_g2, col_g3 = st.columns(3)
                gen_inputs.append({
                    "id": col_g1.text_input(f"رمز المولد", value=f"G{i+1}", key=f"g_id_{i}"),
                    "model": col_g2.text_input(f"موديل المولد", value="Perkins", key=f"g_mod_{i}"),
                    "kw": col_g3.number_input(f"السعة (kW)", min_value=0.0, value=100.0, step=10.0, key=f"g_kw_{i}")
                })
            if st.button("💾 حفظ بيانات الموقع والمولدات", type="primary"):
                if geo_region and site_name:
                    if geo_region not in st.session_state.sites_data:
                        st.session_state.sites_data[geo_region] = {}
                    st.session_state.sites_data[geo_region][site_name] = {"address": site_address if site_address else "N/A", "generators": {}}
                    for gen in gen_inputs:
                        if gen["id"]:
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {
                                "model": gen["model"], "run_hours": 0.0, "target": 250.0, "kw": gen["kw"], "load": 0.0,
                                "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                                "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                            }
                    st.success("تم الحفظ بنجاح وتحديث النظام!")
                    time.sleep(1)
                    st.rerun()

        main_sites = list(st.session_state.sites_data.keys())
        col_site1, col_site2 = st.columns(2)
        with col_site1:
            selected_main_site = st.selectbox("🌍 اختر المنطقة الجغرافية:", main_sites) if main_sites else None
        with col_site2:
            if selected_main_site:
                sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
                selected_sub_site = st.selectbox("📍 اختر الموقع:", sub_sites) if sub_sites else None
                current_site_address = st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", "") if selected_sub_site else ""
        
        if not main_sites or not selected_main_site or not selected_sub_site:
            st.warning("الرجاء إضافة منطقة وموقع لإدارة المولدات.")
            st.stop()
            
        st.divider()
        st.markdown(f"### ⚙️ المولدات في [ {selected_main_site} 🔗 {selected_sub_site} ]")
        gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())
        
        if not gen_list:
            st.info("لا توجد مولدات في هذا الموقع. يمكنك الإضافة من النموذج أعلاه.")
        else:
            col_select_g, col_modal_btn, col_del_btn = st.columns([2, 1, 1])
            with col_select_g:
                selected_gen = st.selectbox("اختر المولد للمراجعة:", gen_list)
            with col_modal_btn:
                st.write("")
                st.write("")
                if st.button("📝 تحديث المعايرة (Modal)", use_container_width=True):
                    edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)
            with col_del_btn:
                st.write("")
                st.write("")
                if st.button("🗑️ مسح/إيقاف المولد", use_container_width=True):
                    del st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
                    st.success(f"تم مسح بيانات المولد {selected_gen} بشكل نهائي من السجل!")
                    time.sleep(1)
                    st.rerun()

            if selected_gen not in st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"]:
                st.stop()

            gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            calib_e = gen_info.get("calib_elec", {})
            calib_m = gen_info.get("calib_engine", {})
            
            st.subheader(f"📊 Calibration Dashboard ({selected_gen})")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("Model & Capacity", f"{gen_info['model']}", f"{gen_info['kw']} kW")
            m_c2.metric("Run Hours / Target", f"{gen_info['run_hours']} hrs", f"Target: {gen_info['target']} hrs")
            m_c3.metric("Measured Voltage", f"{calib_e.get('v_measured', 0)} V", f"Nominal: {calib_e.get('v_nominal', 0)} V")
            m_c4.metric("Coolant Temp", f"{calib_m.get('coolant_temp_c', 0)} °C")
            
            parts_key = f"parts_{selected_main_site}_{selected_sub_site}_{selected_gen}"
            if parts_key not in st.session_state:
                st.session_state[parts_key] = [
                    {"الوحدة": 1, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 180.0, "تجديد (تصفير)": False},
                    {"الوحدة": 2, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0, "تجديد (تصفير)": False},
                ]
            
            st.subheader(f"🛢️ جدول الصيانة التنبؤية (Predictive Maintenance)")
            df_parts_input = pd.DataFrame(st.session_state[parts_key])
            edited_df = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch", column_config={"تجديد (تصفير)": st.column_config.CheckboxColumn("Reset Counter", default=False)})
            
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
            for idx, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
                life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
                used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
                pct = (used / life) * 100 if life > 0 else 0
                status_str = "Good" if pct < 70 else "Warning" if pct < 90 else "Critical"
                processed_rows.append({
                    "الوحدة": row.get("الوحدة", idx + 1), "قطع الغيار / الفلاتر": row.get("قطع الغيار / الفلاتر", "Part"),
                    "العمر الافتراضي (ساعة)": life, "الساعات المنقضية (ساعة)": used, "المدة المتبقية (ساعة)": max(0.0, life - used),
                    "حالة التنبيه": status_str
                })
            df_result = pd.DataFrame(processed_rows)

            st.divider()
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                gen_img_file = st.file_uploader("📸 تحميل صورة المولد (تُدرج في التقرير)", type=["png", "jpg", "jpeg"])
            with col_up2:
                parts_img_file = st.file_uploader("📸 تحميل صورة الصيانة/الأعطال (تُدرج في التقرير)", type=["png", "jpg", "jpeg"])

            def generate_full_pdf_bytes():
                temp_files_to_delete = []
                temp_logo_path = None
                if logo_file:
                    temp_logo_path = f"temp_logo_{uuid.uuid4().hex}.png"
                    with open(temp_logo_path, "wb") as f: f.write(logo_file.getbuffer())
                    temp_files_to_delete.append(temp_logo_path)
                    
                pdf = ComprehensivePDF("GENERATOR COMPREHENSIVE REPORT", logo_path=temp_logo_path)
                pdf.add_page()
                pdf.set_fill_color(245, 247, 250)
                pdf.rect(10, 35, 190, 45, "F")
                pdf.set_xy(12, 37)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(24, 43, 73)
                
                pdf.cell(0, 5, f"Site Address: {sanitize_latin_only(current_site_address)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Main Site: {sanitize_latin_only(selected_main_site)} | Sub Site: {sanitize_latin_only(selected_sub_site)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | Capacity: {gen_info['kw']} kW", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Current Run Hours: {gen_info['run_hours']} hrs | Target Hours: {gen_info['target']} hrs", ln=True)
                
                pdf.ln(8)
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 6, "1. Predictive Maintenance Spare Parts Table", ln=True)
                headers_pdf = ["#", "Part Name", "Lifespan", "Used", "Remain", "Status"]
                widths = [10, 60, 25, 25, 25, 45]
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_fill_color(24, 43, 73)
                pdf.set_text_color(255, 255, 255)
                for h, w in zip(headers_pdf, widths): pdf.cell(w, 6, h, border=1, fill=True, align="C")
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

                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "2. Oil Change Schedule", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(0, 0, 0)
                amb = calib_m.get('ambient_temp', 43.0)
                oil_rec = "20W50" if amb >= 45 else "15W40"
                pdf.cell(0, 5, f"- Engine Oil Recommended (Based on Ambient {amb} C): {oil_rec}", ln=True)
                pdf.cell(0, 5, "- Replace Engine Oil and Oil Filters strictly every 250 Run Hours.", ln=True)
                
                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "3. Electro-Mechanical Calculator & Synced Fuel Consumption", ln=True)
                pdf.set_font("Helvetica", "", 9)
                pdf.set_text_color(0, 0, 0)
                c_load = float(gen_info['load'])
                est_liters, est_co2 = calculate_fuel_consumption_and_emissions(c_load, 24)
                pdf.cell(0, 5, f"- Electrical Load Registered: {c_load} kW ({round((c_load/gen_info['kw'])*100, 1) if gen_info['kw'] > 0 else 0}% of Max Capacity)", ln=True)
                pdf.cell(0, 5, f"- Estimated Daily Diesel Consumption @ Current Load: {est_liters} Liters / Day", ln=True)
                pdf.cell(0, 5, f"- Estimated Daily Carbon (CO2) Emissions: {est_co2} Kg / Day", ln=True)

                pdf.ln(5)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "4. Generator Performance Graph & Inspection Photos", ln=True)
                
                # إنشاء الرسم البياني برمجياً وحفظه
                fig, ax = plt.subplots(figsize=(4, 3))
                current_h = float(gen_info["run_hours"])
                target_h = float(gen_info["target"])
                rem_h = max(0.0, target_h - current_h)
                ax.pie([current_h, rem_h], labels=['Elapsed Hrs', 'Target Rem'], autopct='%1.1f%%', colors=['#182b49', '#28a745'])
                ax.set_title("Run Hours Ratio")
                temp_chart = f"temp_chart_{uuid.uuid4().hex}.png"
                fig.savefig(temp_chart)
                plt.close(fig)
                temp_files_to_delete.append(temp_chart)
                
                y_pos = pdf.get_y() + 5
                pdf.image(temp_chart, x=10, y=y_pos, w=60)
                
                img_x = 75
                if gen_img_file:
                    temp_gen = f"temp_gen_{uuid.uuid4().hex}.png"
                    with open(temp_gen, "wb") as f: f.write(gen_img_file.getbuffer())
                    pdf.image(temp_gen, x=img_x, y=y_pos, w=50)
                    temp_files_to_delete.append(temp_gen)
                    img_x += 55
                    
                if parts_img_file:
                    temp_part = f"temp_part_{uuid.uuid4().hex}.png"
                    with open(temp_part, "wb") as f: f.write(parts_img_file.getbuffer())
                    pdf.image(temp_part, x=img_x, y=y_pos, w=50)
                    temp_files_to_delete.append(temp_part)

                pdf_out = pdf.output(dest="S")
                
                for file_path in temp_files_to_delete:
                    if os.path.exists(file_path): os.remove(file_path)
                    
                return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

            st.download_button(
                label=f"🖨️ استخراج التقرير الشامل PDF للمولد ({selected_gen})",
                data=generate_full_pdf_bytes(),
                file_name=f"Comprehensive_Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    elif "2." in selected_app:
        st.title("🎛️ غرفة التحكم والتشغيل عن بُعد (Remote Control Center)")
        st.info("نظام التحكم قيد العمل والمراقبة اللحظية.")
    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية وتقارير الإدارة")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs), use_container_width=True)
    elif "4." in selected_app:
        st.title("🤖 المساعد الذكي والكتالوجات وقراءة الأكواد")
        st.info("قم برفع الكتالوجات للتشخيص الذكي للأعطال.")
    elif "5." in selected_app:
        st.title("🔍 نظام فحص المعدات (WIC وغيرها)")
        st.info("نظام المقارنة البصرية للمعدات وغرف التبريد.")
    elif "6." in selected_app:
        st.title("🧮 الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)")
        tab_calc1, tab_calc2 = st.tabs(["⚡ هبوط الجهد", "🌱 وقود وانبعاثات كربونية"])
        with tab_calc1:
            st.subheader("حاسبة هبوط الجهد الكهربائي")
            i_amp = st.number_input("التيار (Amperes):", value=250.0)
            dist_m = st.number_input("طول الكابل (Meters):", value=120.0)
            c_size = st.selectbox("مقطع الكابل (mm²):", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4)
            v_drop, v_drop_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size)
            st.metric("هبوط الجهد", f"{v_drop} V", f"{v_drop_pct}%")
        with tab_calc2:
            st.subheader("حاسبة الانبعاثات والوقود التقديرية")
            load_kw = st.number_input("الحمل الفعلي (kW):", value=200.0)
            hours_run = st.number_input("ساعات التشغيل:", value=24.0)
            est_liters, est_co2 = calculate_fuel_consumption_and_emissions(load_kw, hours_run)
            c1, c2 = st.columns(2)
            c1.metric("استهلاك الديزل المقدر", f"{est_liters} لتر")
            c2.metric("انبعاثات CO2 المقدرة", f"{est_co2} كجم")
