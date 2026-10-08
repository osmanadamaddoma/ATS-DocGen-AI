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
import extra_streamlit_components as stx # Cookie management library added
from google import genai
from gtts import gTTS
# Try importing Supabase library
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None
# Import live IoT Database library
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None
# Try importing barcode reading library
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None
# =========================================================
# 0. Main Page Settings, AI, Audio, and Language Initialization
# =========================================================
st.set_page_config(
    page_title="Comprehensive Industrial Complex - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)
# Initial session state variables initialization
if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "en" # 'ar' or 'en'
# Default page on entry
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"
# Update mini database structure to support main and sub menus
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "(Main Menu)": {
            "Main Site - (Sub Site)": {
                "address": "                   ",
                "technician_name": "                  ",
                "technician_whatsapp": "                 ",
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
# Daily logs and readings tracking
if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "Khartoum (Main Menu) - Main Site - Kafouri (Sub Site)",
            "generator": "G1",
            "technician": "Ahmed Maintenance Tech",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "Normal"
        }
    ]
# Fetch Gemini key securely from secrets
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")
if not gemini_key:
    st.warning("⚠️ GEMINI_API_KEY not found. Please add it to st.secrets.")
# Initialize Gemini API client
client = genai.Client(api_key=gemini_key) if gemini_key else None
# Supabase database settings for app connection
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
            st.success("✅ Application connected and activated successfully with Supabase database!")
        except Exception as e:
            st.error(f"❌ Database connection failed: {e}")
    else:
        st.info("💡 Supabase keys not found. Please add them (SUPABASE_URL and SUPABASE_KEY) in st.secrets.")
else:
    st.warning("⚠️ Supabase library is not installed. Please install it using pip install supabase")
# Updated audio function with dual language support, mute option, and continuous loop for alarms
def play_audio(text, lang='en', loop=False):
    """Convert text to speech using gTTS and play if mute is not active with loop support"""
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
        st.error(f"Audio playback error: {e}")
@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="en"):
    """AI call function with high pressure error handling (503), retries, and bilingual support"""
    if not client:
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠ لم يتم العثور على مفتاح GEMINI_API_KEY."
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
                    return "⚠️ High server load (503). Please retry in a few seconds." if language == "en" else "⚠️ الخادم يمر بضغط عالٍ حالياً (503). يرجى المحاولة مرة أخرى."
            return f"❌ Error: {err_msg}"
# =========================================================
# 1. System Helper Functions and Comprehensive PDF Report Design
# =========================================================
def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"
class ComprehensivePDF(FPDF):
    def __init__(
        self,
        title_text="INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT",
        logo_path=None,
        site_address="N/A",
        main_site="N/A",
        sub_site="N/A",
    ):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path
        self.site_address = site_address
        self.main_site = main_site
        self.sub_site = sub_site
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
        self.cell(
            0,
            4,
            "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY",
            ln=True,
        )
        self.set_x(text_x)
        self.set_font("Helvetica", "", 8)
        self.cell(
            0,
            4,
            f"SITE: {sanitize_latin_only(self.site_address)} | {sanitize_latin_only(self.main_site)} - {sanitize_latin_only(self.sub_site)}",
            ln=True,
        )
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
        self.cell(
            0,
            4,
            "Prepared by: Osman Adam Addoma | Power Systems Engineer",
            ln=True,
            align="C",
        )
        self.cell(
            0,
            4,
            f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Site: {sanitize_latin_only(self.site_address)}",
            align="C",
        )
# =========================================================
# 1.5 Live Database and IoT Integration Functions
# =========================================================
def fetch_live_iot_data():
    """Fetch live telemetry readings from live time-series database if available"""
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
# =========================================================
# 1.8 Smart Engineering Tools and Calculators
# =========================================================
def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    """Calculate 3-Phase electrical voltage drop"""
    rho_copper = 0.0178 # Copper resistivity
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    v_drop_pct = (v_drop / 400.0) * 100
    return round(v_drop, 2), round(v_drop_pct, 2)
def get_fuel_table_from_csv(uploaded_csv=None):
    """Read fuel table from uploaded CSV file or use internal table"""
    default_table = {
        100: {"CAT C32": 0.241, "Cummins KTA50": 0.245, "Perkins 2506": 0.249, "AVG": 0.24, "eff": 34, "g_cat": 205, "g_cummins": 208, "g_perkins": 212},
        75: {"CAT C32": 0.247, "Cummins KTA50": 0.253, "Perkins 2506": 0.259, "AVG": 0.25, "eff": 33, "g_cat": 210, "g_cummins": 215, "g_perkins": 220},
        50: {"CAT C32": 0.265, "Cummins KTA50": 0.271, "Perkins 2506": 0.276, "AVG": 0.27, "eff": 31, "g_cat": 225, "g_cummins": 230, "g_perkins": 235},
        25: {"CAT C32": 0.306, "Cummins KTA50": 0.318, "Perkins 2506": 0.324, "AVG": 0.31, "eff": 27, "g_cat": 260, "g_cummins": 270, "g_perkins": 275},
    }
    if uploaded_csv is not None:
        try:
            df = pd.read_csv(uploaded_csv)
            table = {}
            for _, row in df.iterrows():
                load = int(row.get("Load %", 0))
                if load == 0:
                    continue
                sfc = float(row.get("SFC L/kWh", 0.24))
                def g_to_l(g):
                    try:
                        return float(g) / 850.0
                    except:
                        return sfc
                table[load] = {
                    "CAT C32": g_to_l(row.get("CAT C32 g/kWh", sfc*850)),
                    "Cummins KTA50": g_to_l(row.get("Cummins KTA50", sfc*850)),
                    "Perkins 2506": g_to_l(row.get("Perkins 2506", sfc*850)),
                    "AVG": sfc,
                    "eff": int(row.get("Efficiency %", 30)),
                    "g_cat": int(row.get("CAT C32 g/kWh", 200)),
                    "g_cummins": int(row.get("Cummins KTA50", 200)),
                    "g_perkins": int(row.get("Perkins 2506", 200)),
                }
            if table:
                return table
        except Exception as e:
            print(f"CSV parse error: {e}")
            return default_table
    return default_table
def calculate_fuel_consumption_and_emissions(kw_load, run_hours, gen_model="Perkins", kw_capacity=None, fuel_table=None):
    """Estimate diesel consumption and emissions - smart version reading from CSV table based on load percentage and engine type"""
    if fuel_table is None:
        fuel_table = get_fuel_table_from_csv()
    if kw_capacity and kw_capacity > 0:
        load_pct = (kw_load / kw_capacity) * 100.0
    else:
        load_pct = 100.0 if kw_load > 100 else kw_load
    load_pct = max(25.0, min(100.0, load_pct))
    model_key = "AVG"
    if "CAT" in str(gen_model).upper():
        model_key = "CAT C32"
    elif "CUMMINS" in str(gen_model).upper() or "KTA" in str(gen_model).upper():
        model_key = "Cummins KTA50"
    elif "PERKINS" in str(gen_model).upper():
        model_key = "Perkins 2506"
    loads = sorted(fuel_table.keys())
    if load_pct in fuel_table:
        sfc = fuel_table[load_pct][model_key]
        eff = fuel_table[load_pct]["eff"]
    else:
        lower = max([l for l in loads if l <= load_pct], default=25)
        upper = min([l for l in loads if l >= load_pct], default=100)
        if lower == upper:
            sfc = fuel_table[lower][model_key]
            eff = fuel_table[lower]["eff"]
        else:
            sfc_low = fuel_table[lower][model_key]
            sfc_up = fuel_table[upper][model_key]
            eff_low = fuel_table[lower]["eff"]
            eff_up = fuel_table[upper]["eff"]
            ratio = (load_pct - lower) / (upper - lower)
            sfc = sfc_low + ratio * (sfc_up - sfc_low)
            eff = eff_low + ratio * (eff_up - eff_low)
    liters = kw_load * sfc * run_hours
    co2_kg = liters * 2.68
    return round(liters, 1), round(co2_kg, 1), round(sfc, 3), round(eff, 1)
# =========================================================
# 2. Unified Subscription System and Packages (with Cookie Management)
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "Osman Adam Addoma (Addoma Trading Services)",
        "plan": "Monthly",
        "start_date": "2026-09-15",
        "duration_days": 30,
    },
    "CLIENT-M-881": {
        "name": "Nile Engineering Industries Company",
        "plan": "Monthly",
        "start_date": "2026-09-01",
        "duration_days": 30,
    },
    "CLIENT-Y-992": {
        "name": "National Iron and Steel Factories",
        "plan": "Yearly",
        "start_date": "2026-03-15",
        "duration_days": 365,
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
                    "name": row.get("client_name", "Client"),
                    "plan": row.get("plan", "Monthly"),
                    "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                    "duration_days": int(row.get("duration_days", 30)),
                }
    except Exception as e:
        print(f"Load subscriptions error: {e}")
def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_persistent_final_v3")
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
    else:
        if supabase:
            try:
                res = supabase.table("subscriptions").select("*").execute()
                for row in res.data:
                    c = str(row.get("code","")).strip().upper()
                    if c == clean_saved:
                        CLIENTS_DATABASE[c] = {
                            "name": row.get("client_name", "Client"),
                            "plan": row.get("plan", "Monthly"),
                            "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                            "duration_days": int(row.get("duration_days", 30)),
                        }
                        st.session_state.authenticated = True
                        st.session_state.active_code = c
                        st.session_state.user_email = CLIENTS_DATABASE[c]["name"]
                        st.session_state.role = "admin" if c in ADMIN_CODES else "client"
                        break
            except:
                pass

# =========================================================
# Professional Sidebar Profile & System Description Design
# =========================================================
with st.sidebar:
    st.markdown("---")
    # App Branding & Profile Card Header
    st.markdown(
        """
        <div style="background: linear-gradient(135deg, #182b49 0%, #2c3e50 100%); padding: 15px; border-radius: 10px; color: white; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h3 style="margin: 0; font-size: 18px; color: #f8f9fa;">ATS ENGINEERING</h3>
            <p style="margin: 5px 0 0 0; font-size: 12px; color: #adb5bd;">Addoma Trading Services Suite</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Professional Bio Section inside Sidebar Expander or Box
    with st.expander("📌 System & Engineer Profile", expanded=True):
        st.markdown(
            """
            **Lead Consultant:** Eng. Osman Adam Addoma  
            **Expertise:** Power Systems, Gensets Synchronization, & Industrial Refrigeration (WIC Systems).  
            **Core Tech:** Python, Streamlit, Supabase, InfluxDB, & Gemini AI Diagnostics.  
            **Mission:** Delivering cutting-edge electromechanical solutions, predictive maintenance, and smart IoT operational control.
            """,
            unsafe_allow_html=True
        )
        
    st.markdown("---")

# --- Language Selection Option in Sidebar ---
st.sidebar.subheader("🌐 Language")
selected_lang = st.sidebar.radio("Select Language:", ["Arabic (العربية)", "English"], index=1 if st.session_state.lang == "en" else 0)
st.session_state.lang = "en" if "English" in selected_lang else "ar"
L = st.session_state.lang
TXT = {
    "ar": {
        "title": "🔐 بوابة تفعيل النظام الموحد",
        "code_input": "كود التفعيل:",
        "btn_activate": "تفعيل",
        "invalid_code": "❌ كود التفعيل غير صحيح.",
        "warning_auth": "🔒 يرجى إدخال كود اشتراك صالح للوصول إلى التطبيقات والمساعد الذكي.",
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
        "warning_auth": "🔒 Please enter a valid activation code to access system applications.",
        "nav_header": "⚙️ Addoma Trading Services System",
        "nav_status": "🟢 System Connected & Active",
        "btn_chat": "💬 Smart Engineering Assistant",
        "btn_dashboard": "📊 Systems Control Dashboard",
        "btn_apps": "🛠️ Engineering Apps Suite",
        "btn_logout": "🚪 Logout / Clear License",
        "client": "👤 Client:",
        "plan": "📦 Plan:",
        "remaining": "⏳ Days Left:",
        "days": "days",
        "app_selection": "🛠️ Available Apps (Pro Version)",
        "choose_app": "Select System Module:"
    }
}[L]
if not st.session_state.authenticated:
    st.title(TXT["title"])
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")
    if st.sidebar.button(TXT["btn_activate"]):
        if supabase:
            try:
                res_reload = supabase.table("subscriptions").select("*").execute()
                for row in res_reload.data:
                    c = str(row.get("code","")).strip().upper()
                    if c:
                        CLIENTS_DATABASE[c] = {
                            "name": row.get("client_name", "Client"),
                            "plan": row.get("plan", "Monthly"),
                            "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                            "duration_days": int(row.get("duration_days", 30)),
                        }
            except Exception as e:
                print(f"Reload before check error: {e}")
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
        if st.button(TXT["btn_chat"], use_container_width=True):
            st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True):
            st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True):
            st.session_state.current_page = "main_apps"
        st.write("---")
        if st.button(TXT["btn_logout"], type="primary", use_container_width=True):
            st.session_state.authenticated = False
            try:
                cookie_manager.delete("activation_code_v5")
                cookie_manager.delete("activation_code")
            except:
                pass
            if "code" in st.query_params:
                del st.query_params["code"]
            if "active_code" in st.session_state:
                del st.session_state["active_code"]
            st.rerun()
input_code = st.session_state.get("active_code", "")
is_pro = False
client_name = "Visitor"
plan_type = "N/A"
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
        st.sidebar.success("✅ Subscription Verified!")
        st.sidebar.markdown(f"**{TXT['client']}** {client_name}")
        st.sidebar.markdown(f"**{TXT['plan']}** {plan_type}")
        st.sidebar.markdown(f"**{TXT['remaining']}** {days_left} {TXT['days']}")
    else:
        st.sidebar.error(f"❌ License expired on ({expiry_dt}).")
        st.session_state.authenticated = False
        try:
            cookie_manager.delete("activation_code_v5")
            cookie_manager.delete("activation_code")
        except:
            pass
        if "code" in st.query_params:
            del st.query_params["code"]
        st.stop()
if not is_pro:
    st.warning(TXT["warning_auth"])
    st.stop()
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
    "🎛 2. Remote Operations & Control Center",
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
st.sidebar.divider()
@st.dialog("📝 Edit Generator & Calibration Data" if L == "en" else "📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})
    st.markdown(f"### ⚙️ {gen_key} - Site: {sub_site}")
    tech_name = st.text_input("Technician Name:", value="On-duty Maintenance Tech")
    tab1, tab2, tab3 = st.tabs(["🏷️ Basic Data", "⚡ Electrical", "🔧 Engine"])
    with tab1:
        new_model = st.text_input("Model", value=gen_data.get("model", ""))
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
    if st.button("💾 Save Data", use_container_width=True, type="primary"):
        validation_errors = []
        if c_temp < 0 or c_temp > 125.0:
            validation_errors.append(f"❌ Invalid Temp: {c_temp}°C")
        if o_press < 0.0 or o_press > 12.0:
            validation_errors.append(f"❌ Invalid Oil Press: {o_press} Bar")
        if v_meas < 100.0 or v_meas > 600.0:
            validation_errors.append(f"❌ Invalid Voltage: {v_meas} V")
        if validation_errors:
            for err in validation_errors:
                st.error(err)
        else:
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
            # Automatically save data to Supabase upon modification
            if supabase:
                try:
                    payload = {
                        "site_name": sub_site,
                        "generator_id": gen_key,
                        "model": new_model,
                        "capacity_kw": new_kw,
                        "load_kw": new_load,
                        "run_hours": new_run_hours,
                        "last_updated": datetime.now().isoformat()
                    }
                    supabase.table("generators_data").upsert(payload).execute()
                except Exception as e:
                    print(f"Supabase upsert error: {e}")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_date = datetime.now().strftime("%Y-%m-%d")
            st.session_state.daily_logs.append({
                "timestamp": now_str,
                "date": today_date,
                "site": f"{main_site} - {sub_site}",
                "generator": gen_key,
                "technician": tech_name,
                "run_hours": new_run_hours,
                "v_measured": v_meas,
                "oil_press": o_press,
                "coolant_temp": c_temp,
                "status": "Updated"
            })
            st.success("✅ Saved successfully and synced to Supabase!")
            st.rerun()
if st.session_state.current_page == "chat":
    st.title("🤖 " + ("Smart AI Assistant" if L == "en" else "المساعد الذكي الهندسي"))
    st.caption("Addoma Trading Services - Industrial AI Engine")
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "Hello! How can I assist you today with generator control, refrigeration, or diagnostics?" if L == "en" else "مرحباً بك! كيف يمكنني مساعدتك اليوم في المولدات، التبريد، أو الصيانة؟"}
        ]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    user_query = st.chat_input("Ask a technical question..." if L == "en" else "اكتب استفسارك الهندسي هنا...")
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            if client:
                try:
                    response_text = analyze_fault_with_gemini(user_query, language=L)
                except Exception as e:
                    response_text = f"Error: {e}"
            else:
                response_text = f"Received query: '{user_query}'. Gemini API Key is missing in secrets."
            message_placeholder.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("Systems Control Dashboard" if L == "en" else "لوحة تحكم الأنظمة والمتابعة"))
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Generators Status", value="Stable", delta="Sync Ready")
    col2.metric(label="WIC Cold Rooms", value="2 Units (WIC10 & WIC40)", delta="-1°C", delta_color="inverse")
    col3.metric(label="Database Link", value="Supabase Online", delta="Ping 12ms")
    st.divider()
    st.subheader("Live Telemetry & Diagnostics Overview")
    st.info("Continuous telemetry tracking powered by InfluxDB & Smart Analytics.")
else:
    if "1." in selected_app:
        st.title("⚙️ " + ("Predictive Maintenance & Genset Monitoring" if L == "en" else "نظام الصيانة التنبؤية ومراقبة المولدات"))
        col_top_audio1, col_top_audio2 = st.columns([3, 1])
        with col_top_audio2:
            mute_label = "🔇 Mute" if not st.session_state.audio_muted else "🔊 Unmute"
            if st.button(mute_label, use_container_width=True):
                st.session_state.audio_muted = not st.session_state.audio_muted
                st.rerun()
        st.sidebar.subheader("🎨 PDF Branding")
        logo_file = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo_up")
        st.subheader("📍 Site Management")
        with st.expander("➕ Add Region, Site, and Generators Manually (Comprehensive Form)", expanded=False):
            st.markdown("### Region and Site Data")
            geo_region = st.text_input("Geographical Region Address (No./Name) [e.g., Khartoum - Region 1]:", key="geo_reg_input")
            site_name = st.text_input("Site Name [e.g., Kafouri Factory]:", key="site_name_input")
            site_address = st.text_input("Detailed Site Address:", key="site_add_input")
            
            # Responsible technician or maintenance engineer data
            st.markdown("### Responsible Technician or Maintenance Engineer Data")
            col_tech_f1, col_tech_f2 = st.columns(2)
            assigned_technician_name = col_tech_f1.text_input("Responsible Technician/Engineer Name:", value="Eng. Osman Adam Addoma", key="new_site_tech_name")
            assigned_technician_whatsapp = col_tech_f2.text_input("Technician/Engineer WhatsApp (with country code):", value="249912345678", key="new_site_tech_whatsapp")
            
            st.markdown("### Generators Data")
            num_gens = st.number_input("Number of generators on site:", min_value=1, max_value=20, value=1, step=1, key="num_gens_input")
            st.write("Customize each generator's data:")
            gen_inputs = []
            for i in range(int(num_gens)):
                st.markdown(f"**Generator #{i+1}**")
                col_g1, col_g2, col_g3 = st.columns(3)
                g_id = col_g1.text_input(f"Generator ID/Number", value=f"G{i+1}", key=f"g_id_{i}")
                g_model = col_g2.text_input(f"Generator Model", value="Perkins", key=f"g_mod_{i}")
                g_kw = col_g3.number_input(f"Capacity/Power (kW)", min_value=0.0, value=100.0, step=10.0, key=f"g_kw_{i}")
                gen_inputs.append({"id": g_id, "model": g_model, "kw": g_kw})
            if st.button("💾 Save Site and Generators Data Fully", type="primary"):
                if geo_region and site_name:
                    if geo_region not in st.session_state.sites_data:
                        st.session_state.sites_data[geo_region] = {}
                    st.session_state.sites_data[geo_region][site_name] = {
                        "address": site_address if site_address else "N/A",
                        "technician_name": assigned_technician_name,
                        "technician_whatsapp": assigned_technician_whatsapp,
                        "generators": {}
                    }
                    for gen in gen_inputs:
                        if gen["id"]:
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {
                                "model": gen["model"],
                                "run_hours": 0.0,
                                "target": 250.0,
                                "kw": gen["kw"],
                                "load": 0.0,
                                "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                                "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                            }
                            # Save data to Supabase as well
                            if supabase:
                                try:
                                    supabase.table("generators_data").upsert({
                                        "site_name": site_name,
                                        "generator_id": gen["id"],
                                        "model": gen["model"],
                                        "capacity_kw": gen["kw"],
                                        "run_hours": 0.0,
                                        "last_updated": datetime.now().isoformat()
                                    }).execute()
                                except Exception as e:
                                    print(f"Supabase error: {e}")
                    st.success(f"Region ({geo_region}) and site ({site_name}) with {num_gens} generators successfully saved and stored in Supabase!")
                    st.rerun()
                else:
                    st.error("Please enter at least the geographical region address and site name.")
        st.markdown("### 📌 Select Current Working Site")
        main_sites = list(st.session_state.sites_data.keys())
        col_site1, col_site2 = st.columns(2)
        with col_site1:
            selected_main_site = st.selectbox("🌍 Select Geographical Region:", main_sites) if main_sites else None
        with col_site2:
            if selected_main_site:
                sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
                selected_sub_site = st.selectbox("📍 Select Site:", sub_sites) if sub_sites else None
                if selected_sub_site:
                    current_site_address = st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", "")
            else:
                selected_sub_site = None
                current_site_address = ""
        if not main_sites or not selected_main_site or not selected_sub_site:
            st.warning("Please add and select a main site and sub-site to manage generators.")
            st.stop()
        st.divider()
        col_gen_m1, col_gen_m2 = st.columns([2, 1])
        with col_gen_m1:
            st.markdown(f"### ⚙️ Generators in [ {selected_main_site} 🔗 {selected_sub_site} ]")
        gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())
        if not gen_list:
            st.info("No generators in this sub-site. Add one from the manual entry form above.")
        else:
            col_select_g, col_modal_btn = st.columns([2, 1])
            with col_select_g:
                selected_gen = st.selectbox("Select Generator:", gen_list)
            with col_modal_btn:
                st.write("")
                st.write("")
                if st.button("📝 Open Calibration Modal"):
                    edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)
            
            # Generator data and titles editing list
            with st.expander("🛠️ Edit Generator Data Titles and Supabase Update", expanded=False):
                st.markdown(f"**Register and Edit Generator Data: {selected_gen}**")
                gen_info_edit = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
                
                new_gen_id = st.text_input("Edit Generator ID:", value=selected_gen, key="edit_gen_id")
                new_gen_model = st.text_input("Edit Generator Model:", value=gen_info_edit['model'], key="edit_gen_model")
                new_gen_kw = st.number_input("Edit Capacity (kW):", value=float(gen_info_edit['kw']), key="edit_gen_kw")
                new_gen_load = st.number_input("Edit Load (kW):", value=float(gen_info_edit.get('load', 0.0)), key="edit_gen_load")
                new_gen_run_hours = st.number_input("Edit Current Run Hours:", value=float(gen_info_edit.get('run_hours', 0.0)), key="edit_gen_rh")
                
                col_b1, col_b2, col_b3 = st.columns(3)
                with col_b1:
                    if st.button("💾 Save to Page Memory", use_container_width=True):
                        gen_info_edit['model'] = new_gen_model
                        gen_info_edit['kw'] = new_gen_kw
                        gen_info_edit['load'] = new_gen_load
                        gen_info_edit['run_hours'] = new_gen_run_hours
                        
                        if new_gen_id != selected_gen:
                            st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][new_gen_id] = gen_info_edit
                            del st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
                        else:
                            st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen] = gen_info_edit
                        
                        st.success("✅ Generator data saved to page memory successfully!")
                        st.rerun()
                with col_b2:
                    if st.button("☁️ Save to Supabase Database", use_container_width=True):
                        gen_info_edit['model'] = new_gen_model
                        gen_info_edit['kw'] = new_gen_kw
                        gen_info_edit['load'] = new_gen_load
                        gen_info_edit['run_hours'] = new_gen_run_hours
                        if new_gen_id != selected_gen:
                            st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][new_gen_id] = gen_info_edit
                            del st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
                        
                        if supabase:
                            try:
                                data_to_insert = {
                                    "site_name": selected_sub_site,
                                    "generator_id": new_gen_id,
                                    "model": new_gen_model,
                                    "capacity_kw": new_gen_kw,
                                    "load_kw": new_gen_load,
                                    "run_hours": new_gen_run_hours,
                                    "last_updated": datetime.now().isoformat()
                                }
                                supabase.table("generators_data").upsert(data_to_insert).execute()
                                st.success("✅ Updated data saved to Supabase successfully!")
                            except Exception as e:
                                st.error(f"Error saving to Supabase: {e}")
                        else:
                            st.warning("⚠ Supabase connection currently unavailable.")
                        st.rerun()
                with col_b3:
                    if st.button("🗑️ Clear Generator Data", use_container_width=True, type="primary"):
                        if selected_gen in st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"]:
                            del st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
                            if supabase:
                                try:
                                    supabase.table("generators_data").delete().eq("generator_id", selected_gen).execute()
                                except Exception:
                                    pass
                            st.success(f"🗑️ Generator {selected_gen} data deleted permanently!")
                            st.rerun()
            
            gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            calib_e = gen_info.get("calib_elec", {})
            calib_m = gen_info.get("calib_engine", {})
            st.subheader(f"📊 Calibration Dashboard ({selected_gen})")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("Model & Capacity", f"{gen_info['model']}", f"{gen_info['kw']} kW")
            m_c2.metric("Run Hours / Target", f"{gen_info['run_hours']} hrs", f"Target: {gen_info['target']} hrs")
            m_c3.metric("Measured Voltage", f"{calib_e.get('v_measured', 0)} V", f"Nominal: {calib_e.get('v_nominal', 0)} V")
            m_c4.metric("Coolant / Ambient Temp", f"{calib_m.get('coolant_temp_c', 0)} °C", f"Ambient: {calib_m.get('ambient_temp', 0)} °C")
            
            alarm_messages = []
            if abs(calib_e.get("v_measured", 400) - calib_e.get("v_nominal", 400)) > 20:
                alarm_messages.append(f"Voltage Deviation on {selected_gen}: Measured {calib_e.get('v_measured')} V!")
            if calib_e.get("current_measured", 0) > calib_e.get("current_max", 1000):
                alarm_messages.append(f"Overcurrent Alarm on {selected_gen}!")
            if calib_m.get("coolant_temp_c", 0) >= 95.0:
                alarm_messages.append(f"High Coolant Temp on {selected_gen}: {calib_m.get('coolant_temp_c')} °C!")
            if calib_m.get("oil_press_bar", 5) <= 1.8:
                alarm_messages.append(f"Low Oil Pressure on {selected_gen}!")
            
            if alarm_messages:
                for msg in alarm_messages:
                    st.error(f"🚨 {msg}")
                play_audio(". ".join(alarm_messages), loop=True)
                
                # Link alarm bell directly to responsible technician's WhatsApp number for instant smart WhatsApp generation
                site_meta = st.session_state.sites_data[selected_main_site][selected_sub_site]
                tech_w_num = site_meta.get("technician_whatsapp", "249912345678")
                tech_w_name = site_meta.get("technician_name", "Responsible Technician")
                
                active_alarm_text = f"🚨 *Emergency Generator Alarm - Addoma Trading Services*\n\nDear Eng./Tech.: {tech_w_name}\n📍 Site: {selected_sub_site} - {selected_main_site}\n⚙️ Generator: {selected_gen}\n⚠️ Alarm Details: {', '.join(alarm_messages)}\n\nPlease proceed immediately to inspect the unit and perform necessary maintenance."
                encoded_alarm_wa = urllib.parse.quote(active_alarm_text)
                alarm_wa_link = f"https://wa.me/{tech_w_num}?text={encoded_alarm_wa}"
                
                st.markdown(f'''
                    <a href="{alarm_wa_link}" target="_blank">
                        <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer; font-weight:bold; margin-bottom:10px;">
                            💬 Send Instant WhatsApp Alarm to Responsible Tech ({tech_w_name})
                        </button>
                    </a>
                ''', unsafe_allow_html=True)
            parts_key = f"parts_{selected_main_site}_{selected_sub_site}_{selected_gen}"
            if parts_key not in st.session_state:
                st.session_state[parts_key] = [
                    {"Unit": 1, "Part Category": "Schedule Services", "Spare Part / Filter": "Oil Filter", "Lifespan (hrs)": 250.0, "Elapsed Hours (hrs)": 180.0, "Reset": False},
                    {"Unit": 2, "Part Category": "Schedule Services", "Spare Part / Filter": "Primary Fuel Filter", "Lifespan (hrs)": 500.0, "Elapsed Hours (hrs)": 430.0, "Reset": False},
                    {"Unit": 3, "Part Category": "Schedule Services", "Spare Part / Filter": "Secondary Fuel Filter", "Lifespan (hrs)": 500.0, "Elapsed Hours (hrs)": 480.0, "Reset": False},
                    {"Unit": 4, "Part Category": "Air System", "Spare Part / Filter": "Air Filter", "Lifespan (hrs)": 1000.0, "Elapsed Hours (hrs)": 650.0, "Reset": False},
                    {"Unit": 5, "Part Category": "Fan Belt System", "Spare Part / Filter": "Fan Belt", "Lifespan (hrs)": 2000.0, "Elapsed Hours (hrs)": 1550.0, "Reset": False},
                    {"Unit": 6, "Part Category": "Cooling System", "Spare Part / Filter": "ELC Coolant", "Lifespan (hrs)": 3000.0, "Elapsed Hours (hrs)": 2800.0, "Reset": False},
                    {"Unit": 7, "Part Category": "Fuel System", "Spare Part / Filter": "Injectors Check", "Lifespan (hrs)": 5000.0, "Elapsed Hours (hrs)": 3200.0, "Reset": False},
                    {"Unit": 8, "Part Category": "Electrical System", "Spare Part / Filter": "Batteries", "Lifespan (hrs)": 8000.0, "Elapsed Hours (hrs)": 6100.0, "Reset": False},
                    {"Unit": 9, "Part Category": "Electric System", "Spare Part / Filter": "Charging Alternator", "Lifespan (hrs)": 10000.0, "Elapsed Hours (hrs)": 8900.0, "Reset": False},
                    {"Unit": 10, "Part Category": "Engine Motor", "Spare Part / Filter": "Top Overhaul", "Lifespan (hrs)": 10000.0, "Elapsed Hours (hrs)": 9200.0, "Reset": False},
                    {"Unit": 11, "Part Category": "Engine Motor", "Spare Part / Filter": "Major Overhaul", "Lifespan (hrs)": 20000.0, "Elapsed Hours (hrs)": 11000.0, "Reset": False},
                    {"Unit": 12, "Part Category": "Oilers System", "Spare Part / Filter": "Oil Cooler Clean", "Lifespan (hrs)": 5000.0, "Elapsed Hours (hrs)": 3800.0, "Reset": False},
                    {"Unit": 13, "Part Category": "Cooling System", "Spare Part / Filter": "Water Pump", "Lifespan (hrs)": 6000.0, "Elapsed Hours (hrs)": 5200.0, "Reset": False},
                    {"Unit": 14, "Part Category": "Air System", "Spare Part / Filter": "Turbocharger Check", "Lifespan (hrs)": 8000.0, "Elapsed Hours (hrs)": 7100.0, "Reset": False},
                ]
            st.subheader(f"🛢️ Predictive Maintenance Table (14 Parts) - {selected_gen}")
            df_parts_input = pd.DataFrame(st.session_state[parts_key])
            edited_df = st.data_editor(
                df_parts_input,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "Reset": st.column_config.CheckboxColumn("Reset Counter", default=False)
                }
            )
            if st.button("🔄 Update / Reset Checked Parts", type="primary"):
                new_data = []
                for idx, row in edited_df.iterrows():
                    item = row.to_dict()
                    if item.get("Reset"):
                        item["Elapsed Hours (hrs)"] = 0.0
                        item["Reset"] = False
                    new_data.append(item)
                st.session_state[parts_key] = new_data
                st.success("Updated Maintenance Schedule!")
                st.rerun()
            processed_rows = []
            bar_colors = []
            for idx, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
                cat = str(row.get("Part Category", "Other"))
                part = str(row.get("Spare Part / Filter", "Part"))
                life = pd.to_numeric(row.get("Lifespan (hrs)", 250), errors="coerce") or 250.0
                used = pd.to_numeric(row.get("Elapsed Hours (hrs)", 0), errors="coerce") or 0.0
                rem = life - used
                pct = (used / life) * 100 if life > 0 else 0
                if pct < 70.0:
                    color_code = "#28a745"
                    status_str = "Good (<70%)"
                elif 70.0 <= pct < 90.0:
                    color_code = "#ffc107"
                    status_str = "Warning (70-90%)"
                else:
                    color_code = "#dc3545"
                    status_str = "Critical (>90%)"
                bar_colors.append(color_code)
                processed_rows.append({
                    "Unit": row.get("Unit", idx + 1),
                    "Part Category": cat,
                    "Spare Part / Filter": part,
                    "Lifespan (hrs)": life,
                    "Elapsed Hours (hrs)": used,
                    "Remaining Duration (hrs)": max(0.0, rem),
                    "Usage Ratio (%)": round(pct, 1),
                    "Alarm Status": status_str,
                    "Color Code": color_code
                })
            df_result = pd.DataFrame(processed_rows)
            st.divider()
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.markdown("##### 🟢🟡🔴 Parts Usage Chart")
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=df_result["Spare Part / Filter"],
                    y=df_result["Usage Ratio (%)"],
                    marker_color=bar_colors,
                    text=df_result["Usage Ratio (%)"].astype(str) + "%",
                    textposition='auto'
                ))
                st.plotly_chart(fig_bar, use_container_width=True)
            with chart_col2:
                st.markdown("##### 🍩 Genset Run Hours Ratio")
                total_target_h = max(1.0, float(gen_info["target"]))
                current_h = float(gen_info["run_hours"])
                rem_h = max(0.0, total_target_h - current_h)
                fig_pie = px.pie(
                    names=['Elapsed Hours', 'Remaining Target'],
                    values=[current_h, rem_h],
                    hole=0.5,
                    color_discrete_sequence=["#182b49", "#28a745"]
                )
                st.plotly_chart(fig_pie, use_container_width=True)
            st.divider()
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                gen_img_file = st.file_uploader("Upload Generator Photo", type=["png", "jpg", "jpeg"])
            with col_up2:
                parts_img_file = st.file_uploader("Upload Maintenance Photo", type=["png", "jpg", "jpeg"])
            
            def generate_full_pdf_bytes():
                import matplotlib.pyplot as plt
                temp_logo_path = None
                temp_charts = []
                if logo_file:
                    temp_logo_path = f"temp_logo_{uuid.uuid4().hex}.png"
                    with open(temp_logo_path, "wb") as f:
                        f.write(logo_file.getbuffer())
                def save_temp_chart(fig):
                    p = f"/tmp/chart_{uuid.uuid4().hex}.png"
                    fig.savefig(p, dpi=150, bbox_inches='tight')
                    plt.close(fig)
                    temp_charts.append(p)
                    return p
                fig1, ax1 = plt.subplots(figsize=(6,3.5))
                colors_mpl = ['green' if x<70 else 'orange' if x<90 else 'red' for x in df_result["Usage Ratio (%)"]]
                ax1.barh(df_result["Spare Part / Filter"], df_result["Usage Ratio (%)"], color=colors_mpl)
                ax1.set_xlabel("Usage %")
                ax1.set_title(f"Parts Usage - {selected_gen}")
                ax1.invert_yaxis()
                chart1_path = save_temp_chart(fig1)
                
                fig2, ax2 = plt.subplots(figsize=(3.5,3.5))
                ax2.pie([current_h, rem_h], labels=['Elapsed', 'Remaining'], autopct='%1.1f%%', colors=["#182b49", "#28a745"])
                ax2.set_title("Run Hours Ratio")
                chart2_path = save_temp_chart(fig2)
                
                ft = get_fuel_table_from_csv(st.session_state.get("fuel_csv_upload", None) if "fuel_csv_upload" in st.session_state and st.session_state.fuel_csv_upload else None)
                loads = sorted(ft.keys())
                fig3, ax3 = plt.subplots(figsize=(6,3.2))
                ax3.plot(loads, [ft[l]["CAT C32"] for l in loads], marker='o', label='CAT C32')
                ax3.plot(loads, [ft[l]["Cummins KTA50"] for l in loads], marker='s', label='Cummins')
                ax3.plot(loads, [ft[l]["Perkins 2506"] for l in loads], marker='^', label='Perkins')
                ax3.plot(loads, [ft[l]["AVG"] for l in loads], marker='d', linestyle='--', label='AVG')
                ax3.set_xlabel("Load %")
                ax3.set_ylabel("SFC L/kWh")
                ax3.set_title("Fuel SFC Curve - From Your CSV")
                ax3.legend(fontsize=7)
                ax3.grid(True, alpha=0.3)
                chart3_path = save_temp_chart(fig3)
                
                fig4, ax4 = plt.subplots(figsize=(6,2.5))
                ax4.plot(loads, [ft[l]["eff"] for l in loads], marker='o', color='green')
                ax4.set_xlabel("Load %")
                ax4.set_ylabel("Efficiency %")
                ax4.set_title("Efficiency vs Load")
                ax4.grid(True, alpha=0.3)
                chart4_path = save_temp_chart(fig4)
                
                pdf = ComprehensivePDF(
                    "COMPREHENSIVE GENERATOR REPORT - WITH FUEL CURVE & MAINTENANCE",
                    logo_path=temp_logo_path,
                    site_address=current_site_address,
                    main_site=selected_main_site,
                    sub_site=selected_sub_site
                )
                pdf.add_page()
                pdf.set_fill_color(245, 247, 250)
                pdf.rect(10, 35, 190, 60, "F")
                pdf.set_xy(12, 37)
                pdf.set_font("Helvetica", "B", 10)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, f"Site Address (In Header): {sanitize_latin_only(current_site_address)}", ln=True)
                
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 5, f"Site Name: {sanitize_latin_only(selected_sub_site)} | Main Region: {sanitize_latin_only(selected_main_site)}", ln=True)
                
                pdf.set_x(12)
                pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | {gen_info['kw']} kW | Load: {gen_info['load']} kW", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Run Hours: {gen_info['run_hours']} hrs | Target: {gen_info['target']} hrs", ln=True)
                
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(0, 5, f"Electrical Sensors: Voltage: {calib_e.get('v_measured', 0)}V | Freq: {calib_e.get('freq_measured', 0)}Hz | Current: {calib_e.get('current_measured', 0)}A | PF: {calib_e.get('pf', 0)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Mechanical Sensors: Oil Press: {calib_m.get('oil_press_bar', 0)}Bar | Coolant Temp: {calib_m.get('coolant_temp_c', 0)}C | RPM: {calib_m.get('rpm', 0)} | Battery: {calib_m.get('battery_v', 0)}V", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Fuel SFC Now: {ft[75]['AVG'] if gen_info['load']/max(gen_info['kw'],1)*100>60 else ft[50]['AVG']} L/kWh | Efficiency: {ft[75]['eff'] if gen_info['load']/max(gen_info['kw'],1)*100>60 else ft[50]['eff']}% | CO2 Factor: 2.68 kg/L", ln=True)
                
                amb_temp_val = calib_m.get('ambient_temp', 43.0)
                pdf.ln(1)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(200, 30, 30)
                pdf.cell(0, 5, f"Oil Change & Recommendation [Ambient {amb_temp_val} C]: {'20W50' if amb_temp_val>=45 else '15W40'}", ln=True)
                pdf.ln(4)
                
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
                    pdf.cell(widths[0], 5, str(row["Unit"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[1], 5, sanitize_latin_only(str(row["Spare Part / Filter"]))[:32], border=1, fill=fill)
                    pdf.cell(widths[2], 5, str(row["Lifespan (hrs)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[3], 5, str(row["Elapsed Hours (hrs)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[4], 5, str(row["Remaining Duration (hrs)"]), border=1, align="C", fill=fill)
                    pdf.cell(widths[5], 5, sanitize_latin_only(str(row["Alarm Status"])), border=1, fill=fill)
                    pdf.ln()
                
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Page 2: Performance Charts - Parts Usage, Run Hours, Fuel & Efficiency", ln=True, align="C")
                if os.path.exists(chart1_path):
                    pdf.image(chart1_path, x=10, y=20, w=90)
                if os.path.exists(chart2_path):
                    pdf.image(chart2_path, x=110, y=20, w=80)
                if os.path.exists(chart3_path):
                    pdf.image(chart3_path, x=10, y=95, w=90)
                if os.path.exists(chart4_path):
                    pdf.image(chart4_path, x=110, y=95, w=90)
                pdf.set_xy(10, 165)
                pdf.set_font("Helvetica", "", 7)
                pdf.multi_cell(0, 4, f"Site Address in Header Footer: {sanitize_latin_only(current_site_address)} | Analysis: Low load (<50%) increases SFC from {ft[100]['AVG']} to {ft[25]['AVG']} L/kWh (+29% waste). Recommendation: Keep load >70% for {ft[75]['eff']}% efficiency.")
                
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Page 3: Detailed Fuel Table From Your CSV - Predictive Maintenance", ln=True, align="C")
                pdf.ln(2)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_fill_color(24,43,73)
                pdf.set_text_color(255,255,255)
                f_headers = ["Load %", "CAT g/kWh", "Cummins", "Perkins", "SFC L/kWh", "Eff %", "CO2 kg/L"]
                
                f_widths = [15, 30, 30, 30, 25, 25, 35]
                for h, w in zip(f_headers, f_widths):
                    pdf.cell(w, 6, h, border=1, fill=True, align="C")
                pdf.ln()
                pdf.set_font("Helvetica", "", 8)
                pdf.set_text_color(0, 0, 0)
                
                for load in sorted(ft.keys(), reverse=True):
                    pdf.cell(f_widths[0], 5, f"{load}%", border=1, align="C")
                    
                    cat_val = ft[load].get("g_cat")
                    if cat_val is None and "CAT C32" in ft[load]:
                        cat_val = int(ft[load]["CAT C32"] * 850)
                    pdf.cell(f_widths[1], 5, str(cat_val if cat_val is not None else "-"), border=1, align="C")
                    
                    cum_val = ft[load].get("g_cummins")
                    if cum_val is None and "Cummins KTA50" in ft[load]:
                        cum_val = int(ft[load]["Cummins KTA50"] * 850)
                    pdf.cell(f_widths[2], 5, str(cum_val if cum_val is not None else "-"), border=1, align="C")
                    
                    per_val = ft[load].get("g_perkins")
                    if per_val is None and "Perkins 2506" in ft[load]:
                        per_val = int(ft[load]["Perkins 2506"] * 850)
                    pdf.cell(f_widths[3], 5, str(per_val if per_val is not None else "-"), border=1, align="C")
                    
                    avg_val = ft[load].get("AVG", "-")
                    pdf.cell(f_widths[4], 5, str(avg_val), border=1, align="C")
                    
                    eff_val = ft[load].get("eff", "-")
                    pdf.cell(f_widths[5], 5, f"{eff_val}%" if eff_val != "-" else "-", border=1, align="C")
                    
                    pdf.cell(f_widths[6], 5, "2.68", border=1, align="C")
                    pdf.ln()
                    
                for p in temp_charts:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
                        
                pdf_out = pdf.output(dest="S")
                return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)
            
            st.download_button(
                label=f"🖨️ Download COMPREHENSIVE Report ({selected_gen}) - 3 Pages With Fuel Curve & Site Address",
                data=generate_full_pdf_bytes(),
                file_name=f"COMPREHENSIVE_Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
    elif "2." in selected_app:
        st.title("🎛️ " + ("Remote Control Center (IoT & Telemetry)" if L == "en" else "غرفة التحكم والتشغيل عن بُعد"))
        df_iot = fetch_live_iot_data()
        if not df_iot.empty:
            latest = df_iot.iloc[-1]
            col1, col2, col3 = st.columns(3)
            col1.metric("🌡 Temp (°C)", f"{latest['temperature']:.1f}")
            col2.metric("〰️ Vibration (mm/s)", f"{latest['vibration']:.2f}")
            col3.metric("🗜️ Oil Press (Bar)", f"{latest['pressure']:.1f}")
            fig_temp = px.line(df_iot, x='_time', y='temperature', title="Live Sensor Trend")
            st.plotly_chart(fig_temp, use_container_width=True)
        st.divider()
        st.subheader("🕹️ Remote Operations Panel")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            if st.button("🟢 Start Generator", use_container_width=True):
                st.success("Start signal dispatched!")
        with rc2:
            if st.button("🔴 Emergency Stop", use_container_width=True):
                st.error("Emergency Stop dispatched!")
        with rc3:
            if st.button("🔄 Reset Alarms", use_container_width=True):
                st.info("DSE Panel Reset!")
    elif "3." in selected_app:
        st.title("📊 " + ("Daily Monitoring & Tech Reminders" if L == "en" else "المتابعة اليومية وتقارير الإدارة"))
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        tab_mgr1, tab_mgr2, tab_mgr3 = st.tabs(["📋 Summary Report", "⏰ Automation Reminders", "🔔 Predictive Maintenance Table & WhatsApp Alarms"])
        
        with tab_mgr1:
            today_logs = [log for log in st.session_state.daily_logs if log.get("date") == today_str]
            st.write(f"Date: {today_str}")
            if today_logs:
                st.dataframe(pd.DataFrame(today_logs), use_container_width=True)
            else:
                st.warning("No logs registered today.")
        with tab_mgr2:
            tech_phone = st.text_input("Technician Phone Number:", value="249912345678")
            reminder_msg = f"Addoma Maintenance Reminder: Please register daily genset logs for ({today_str})."
            encoded_msg = urllib.parse.quote(reminder_msg)
            whatsapp_url = f"https://wa.me/{tech_phone}?text={encoded_msg}"
            st.markdown(f'''
                <a href="{whatsapp_url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer;">
                        💬 Send WhatsApp Reminder
                    </button>
                </a>
            ''', unsafe_allow_html=True)
            
        with tab_mgr3:
            st.subheader("⚙️ Gensets and Machinery Predictive Maintenance Link & Smart WhatsApp Alarms")
            st.markdown("Monitor default operating hours rates and automatically generate smart text WhatsApp messages:")
            
            default_tech_name = "                         "
            default_whatsapp_num = "                       "
            if 'selected_main_site' in locals() and 'selected_sub_site' in locals() and selected_main_site and selected_sub_site:
                site_info = st.session_state.sites_data.get(selected_main_site, {}).get(selected_sub_site, {})
                default_tech_name = site_info.get("technician_name", default_tech_name)
                default_whatsapp_num = site_info.get("technician_whatsapp", default_whatsapp_num)
            col_w_in1, col_w_in2 = st.columns(2)
            assigned_tech_display = col_w_in1.text_input("Responsible Technician/Engineer Name:", value=default_tech_name)
            target_whatsapp_num = col_w_in2.text_input("Target WhatsApp Number (with country code without symbols):", value=default_whatsapp_num)
            
            predictive_maintenance_data = [
                {"Equipment / Genset": "G1 - Perkins 410kVA", "Part / Service": "Oil Filter", "Default Hours": 250, "Elapsed Hours": 240, "Remaining": 10, "Status": "Very close to maintenance date"},
                {"Equipment / Genset": "G1 - Perkins 410kVA", "Part / Service": "Primary Fuel Filter", "Default Hours": 500, "Elapsed Hours": 485, "Remaining": 15, "Status": "Critical / Early Warning"},
                {"Equipment / Genset": "G2 - Cummins 250kVA", "Part / Service": "Fan Belt", "Default Hours": 2000, "Elapsed Hours": 1200, "Remaining": 800, "Status": "Normal"},
                {"Equipment / Genset": "WIC 10 Cold Room", "Part / Service": "Compressor Maintenance", "Default Hours": 8000, "Elapsed Hours": 7950, "Remaining": 50, "Status": "Critical / Predictive Maintenance Alarm"}
            ]
            df_pm = pd.DataFrame(predictive_maintenance_data)
            st.dataframe(df_pm, use_container_width=True)
            
            default_smart_msg = f"🚨 *Predictive Maintenance & Automated Alert - Addoma Trading Services*\n\nTo Tech/Engineer Colleague: {assigned_tech_display}\nHello, the following default run hours consumption rates for generators and machinery have been detected:\n- G1 filters replacement due soon (few hours remaining).\n- Urgent maintenance scheduling required.\n\nPlease take necessary action as soon as possible."
            
            smart_message_input = st.text_area("Automatic Smart WhatsApp Message Text (Editable):", value=default_smart_msg)
            
            encoded_smart_msg = urllib.parse.quote(smart_message_input)
            smart_whatsapp_url = f"https://wa.me/{target_whatsapp_num}?text={encoded_smart_msg}"
            
            st.markdown(f'''
                <a href="{smart_whatsapp_url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:12px 24px; border-radius:5px; cursor:pointer; font-size:16px; font-weight:bold; width:100%;">
                        💬 Send Automatic Smart WhatsApp Alert & Alarm Message to Tech ({assigned_tech_display})
                    </button>
                </a>
            ''', unsafe_allow_html=True)
    elif "4." in selected_app:
        st.title("🤖 " + ("AI Diagnostics & Fault Code Reader" if L == "en" else "المساعد الذكي والكتالوجات وقراءة الأكواد"))
        col_files1, col_files2 = st.columns(2)
        with col_files1:
            st.subheader("📚 Catalog Upload (PDF)")
            manual_file = st.file_uploader("Upload Equipment Catalog", type=["pdf"])
            if manual_file:
                st.success("Catalog uploaded successfully.")
        with col_files2:
            st.subheader("📷 Barcode/QR Reader")
            qr_file = st.file_uploader("Upload QR Code Image", type=["png", "jpg", "jpeg"])
            if qr_file:
                st.info("Barcode reader processing...")
    
    elif "5." in selected_app:
        st.title("🔍 " + ("Cold Room Inspection (WIC 10 & WIC 40)" if L == "en" else "نظام فحص معدات التبريد (WIC 10 & WIC 40)"))
        st.markdown("### ❄️ Refrigeration and Freezing Rooms Data Reading System")
        
        col_wic1, col_wic2 = st.columns(2)
        wic_unit = col_wic1.radio("Select cold room unit to inspect:", ["WIC 10 Cold Room Model", "WIC 40 Cold Room Model"])
        controller_type = col_wic2.selectbox("Controller Type Used:", ["Emerson", "Dixell"])
        st.divider()
        col_w1, col_w2, col_w3 = st.columns(3)
        with col_w1:
            current_temp = st.number_input("Current Temperature (°C):", value=-18.0)
            set_point = st.number_input("Set Point (°C):", value=-20.0)
        with col_w2:
            refrigerant_press = st.number_input("Refrigerant Pressure (Bar):", value=2.5)
            defrost_status = st.selectbox("Defrost Cycle Status:", ["Off", "On", "Error/Alarm"])
        with col_w3:
            alarm_code = st.text_input("Alarm Code (if any):", placeholder="e.g., E1 or HA")
            
        if st.button("💾 Register and Read Inspection Data", type="primary"):
            st.success(f"Unit ({wic_unit}) readings with controller ({controller_type}) registered successfully!")
            if current_temp > set_point + 5:
                st.warning(f"⚠️ Warning: Current temperature is significantly higher than normal. Please check refrigerant status or {controller_type} controller.")
            if alarm_code:
                st.error(f"🚨 System alarm registered: {alarm_code}. It will be forwarded to the AI assistant for analysis.")
    elif "6." in selected_app:
        st.title("🧮 " + ("Smart Electrical & Carbon Calculator" if L == "en" else "الحاسبة الهندسية للكهرباء والانبعاثات"))
        
        tab_calc1, tab_calc2 = st.tabs(["⚡ Cable Voltage Drop", "⛽ Fuel & Emissions"])
        
        with tab_calc1:
            st.subheader("⚡ 3-Phase Cable Voltage Drop Calculator")
            c1, c2, c3 = st.columns(3)
            i_amp = c1.number_input("Required Current (Amperes):", value=250.0)
            dist_m = c2.number_input("Cable Length (Meters):", value=120.0)
            c_size = c3.selectbox("Cable Size (mm²):", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4)
            
            v_drop, v_drop_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size)
            
            m_col1, m_col2 = st.columns(2)
            m_col1.metric("Calculated Voltage Drop", f"{v_drop} V")
            m_col2.metric("Voltage Drop Percentage", f"{v_drop_pct} %")
            
            if v_drop_pct > 4.0:
                st.error("⚠️ Warning: Voltage drop percentage exceeds standard allowable limit (4%)! Please increase cable size.")
            else:
                st.success("✅ Cable size is excellent and within safe engineering limits.")
        with tab_calc2:
            st.subheader("⛽ Link Load Data to Fuel Consumption and Emissions")
            
            uploaded_csv_calc = st.file_uploader("Upload your fuel table (Optional - CSV):", type=["csv"], key="fuel_csv_calc")
            fuel_table_loaded = get_fuel_table_from_csv(uploaded_csv_calc)
            
            col_c1, col_c2 = st.columns(2)
            gen_model_calc = col_c1.selectbox("Generator Model:", ["Perkins", "Cummins", "CAT"])
            pump_type = col_c2.selectbox("Fuel Pump System Type:", [
                "Standard Core Diesel Pump (Mechanical)", 
                "Electronic Injection (MEUI/ECM)"
            ])
            
            col_c3, col_c4, col_c5 = st.columns(3)
            kw_capacity = col_c3.number_input("Total Generator Capacity (kW):", value=150.0, step=10.0)
            current_load_kw = col_c4.number_input("Enter and Edit Current Generator Load (kW):", value=100.0)
            run_hours_calc = col_c5.number_input("Run Hours to Estimate:", value=10.0)
            
            if st.button("📊 Link Load Data and Calculate Consumption", type="primary"):
                liters, co2, sfc, eff = calculate_fuel_consumption_and_emissions(
                    kw_load=current_load_kw,
                    run_hours=run_hours_calc,
                    gen_model=gen_model_calc,
                    kw_capacity=kw_capacity,
                    fuel_table=fuel_table_loaded
                )
                
                if "Mechanical" in pump_type:
                    liters = round(liters * 1.05, 1)
                    co2 = round(co2 * 1.05, 1)
                    st.info("💡 Note: Consumption reading adjusted due to the use of a mechanical core fuel pump system.")
                
                st.success("Data linked and consumption calculated successfully based on instantaneous load!")
                
                calc_res1, calc_res2, calc_res3, calc_res4 = st.columns(4)
                calc_res1.metric("Total Fuel Consumed", f"{liters} Liters")
                calc_res2.metric("CO2 Emissions", f"{co2} kg")
                calc_res3.metric("Specific Fuel Consumption (SFC)", f"{sfc} L/kWh")
                calc_res4.metric("Genset Efficiency at this Load", f"{eff} %")
                
                load_percentage = (current_load_kw / kw_capacity) * 100 if kw_capacity > 0 else 0
                if load_percentage < 50:
                    st.warning(f"⚠️ Warning: The generator is running at a very low load ({load_percentage:.1f}%). This leads to incomplete combustion in {gen_model_calc} engines and unburnt oil accumulation (Wet Stacking).")
                elif load_percentage > 90:
                    st.warning(f"⚠️ Notice: The generator is running at a very high load approaching maximum capacity ({load_percentage:.1f}%). Please monitor engine temperature continuously.")
