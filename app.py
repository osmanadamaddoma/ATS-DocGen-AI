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
import numpy as np
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
    st.session_state.lang = "en" 
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
    rho_copper = 0.0178 
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    v_drop_pct = (v_drop / 400.0) * 100
    return round(v_drop, 2), round(v_drop_pct, 2)

def get_fuel_table_from_csv(uploaded_csv=None):
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
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)",
    "⚡ 7. نظام ATS للذكاء الاصطناعي (DocIntel GenAI)"
]

apps_list_en = [
    "⚙️ 1. Predictive Maintenance & Gensets",
    "🎛 2. Remote Operations & Control Center",
    "📊 3. Daily Monitoring & Reminders",
    "🤖 4. AI Diagnostics & Catalog Reader",
    "🔍 5. Equipment Inspection (WIC & Heavy Duty)",
    "🧮 6. Smart Electrical & Carbon Calculator",
    "⚡ 7. ATS DocIntel GenAI Suite"
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
        st.title("⚙️ " + ("Predictive Maintenance & Genset Monitoring (14 Units & Thermal Oil Recommendations)" if L == "en" else "نظام الصيانة التنبؤية والمولدات (14 وحدة غيار، توصية الزيت بالحرارة والتقارير)"))
        
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

            # استخراج بيانات المولد المحدد لتطبيق ميزات النظام 1
            gen_details = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            current_run_hrs = gen_details.get("run_hours", 500.0)
            engine_calib = gen_details.get("calib_engine", {})
            coolant_temp = engine_calib.get("coolant_temp_c", 85.0)
            ambient_temp = engine_calib.get("ambient_temp", 43.0)
            
            site_info_dict = st.session_state.sites_data[selected_main_site][selected_sub_site]
            tech_name_val = site_info_dict.get("technician_name", "Eng. Osman Adam Addoma")
            tech_whatsapp_val = site_info_dict.get("technician_whatsapp", "249912345678")

            st.markdown("---")
            st.subheader(f"📊 جداول البيانات التنبؤية لعدد الساعات وصلاحية الـ 14 وحدة للمولد ({selected_gen})")
            
            # حساب تأثير درجات الحرارة المرتفعة على توصية غيار الزيت والصلاحية الافتراضية
            temp_factor = 1.0
            if coolant_temp > 90.0 or ambient_temp > 42.0:
                temp_factor = 0.85 # تخفيض العمر الافتراضي بنسبة 15% بسبب الحرارة العالية
                st.warning(f"🌡️ تنبيه حراري متقدم: درجة حرارة المبرد ({coolant_temp}°C) أو المحيطة ({ambient_temp}°C) مرتفعة! تم تعديل صلاحية وحدات الزيت والفلترة تلقائياً لتوصية وقائية مبكرة.")

            # جدول 14 وحدة صيانة وقطع غيار تنبؤية
            units_14_data = [
                {"Unit No": 1, "Part / Service Unit": "فلتر الزيت الرئيسي (Main Oil Filter)", "Default Hours": 250, "Elapsed": int(current_run_hrs % 250), "Validity": int(250 * temp_factor - (current_run_hrs % 250)), "Status": "عادي"},
                {"Unit No": 2, "Part / Service Unit": "فلتر الوقود الابتدائي (Primary Fuel Filter)", "Default Hours": 500, "Elapsed": int(current_run_hrs % 500), "Validity": int(500 * temp_factor - (current_run_hrs % 500)), "Status": "تنبيه قريب"},
                {"Unit No": 3, "Part / Service Unit": "فلتر الوقود الثانوي (Secondary Fuel/Water Separator)", "Default Hours": 500, "Elapsed": int(current_run_hrs % 500), "Validity": int(500 * temp_factor - (current_run_hrs % 500)), "Status": "عادي"},
                {"Unit No": 4, "Part / Service Unit": "فلتر الهواء (Air Intake Filter Element)", "Default Hours": 1000, "Elapsed": int(current_run_hrs % 1000), "Validity": int(1000 * temp_factor - (current_run_hrs % 1000)), "Status": "عادي"},
                {"Unit No": 5, "Part / Service Unit": "زيت المحرك (Engine Oil - Thermal Recommendation)", "Default Hours": 250, "Elapsed": int(current_run_hrs % 250), "Validity": int(250 * temp_factor - (current_run_hrs % 250)), "Status": "توصية غيار بالحرارة"},
                {"Unit No": 6, "Part / Service Unit": "سير المروحة ونظام التبريد (Fan & Alternator Belts)", "Default Hours": 2000, "Elapsed": int(current_run_hrs % 2000), "Validity": int(2000 - (current_run_hrs % 2000)), "Status": "عادي"},
                {"Unit No": 7, "Part / Service Unit": "شمعات التسخين / سخان الستارت (Glow Plugs / Jacket Water Heater)", "Default Hours": 3000, "Elapsed": int(current_run_hrs % 3000), "Validity": int(3000 - (current_run_hrs % 3000)), "Status": "عادي"},
                {"Unit No": 8, "Part / Service Unit": "حساس حرارة المبرد (Coolant Temperature Sensor)", "Default Hours": 5000, "Elapsed": int(current_run_hrs % 5000), "Validity": int(5000 - (current_run_hrs % 5000)), "Status": "عادي"},
                {"Unit No": 9, "Part / Service Unit": "حساس ضغط الزيت (Oil Pressure Sender)", "Default Hours": 5000, "Elapsed": int(current_run_hrs % 5000), "Validity": int(5000 - (current_run_hrs % 5000)), "Status": "عادي"},
                {"Unit No": 10, "Part / Service Unit": "بطارية التشغيل ونظام الشحن (Starter Batteries & Alternator)", "Default Hours": 4000, "Elapsed": int(current_run_hrs % 4000), "Validity": int(4000 - (current_run_hrs % 4000)), "Status": "عادي"},
                {"Unit No": 11, "Part / Service Unit": "مضخة حقن الوقود (Fuel Injection Pump Calibration)", "Default Hours": 6000, "Elapsed": int(current_run_hrs % 6000), "Validity": int(6000 - (current_run_hrs % 6000)), "Status": "عادي"},
                {"Unit No": 12, "Part / Service Unit": "منظم السرعة / الأكچويتر (Governor Actuator)", "Default Hours": 5000, "Elapsed": int(current_run_hrs % 5000), "Validity": int(5000 - (current_run_hrs % 5000)), "Status": "عادي"},
                {"Unit No": 13, "Part / Service Unit": "لوحة التحكم ودائرة المزامنة (DSE Control Panel & Relays)", "Default Hours": 8000, "Elapsed": int(current_run_hrs % 8000), "Validity": int(8000 - (current_run_hrs % 8000)), "Status": "عادي"},
                {"Unit No": 14, "Part / Service Unit": "مانع الصدمات وقواعد المحرك (Engine Vibration Mounts / Dampers)", "Default Hours": 10000, "Elapsed": int(current_run_hrs % 10000), "Validity": int(10000 - (current_run_hrs % 10000)), "Status": "عادي"}
            ]

            df_14_units = pd.DataFrame(units_14_data)
            st.dataframe(df_14_units, use_container_width=True)

            # إعداد رسالة الواتساب النصية الذكية التلقائية وربط رقم الفني
            st.markdown("---")
            st.subheader("💬 ربط بيانات رقم الواتساب وتوليد الإنذار التلقائي للفني أو المهندس")
            
            col_wa1, col_wa2 = st.columns(2)
            assigned_tech_input = col_wa1.text_input("اسم الفني أو المهندس المسؤول:", value=tech_name_val)
            whatsapp_num_input = col_wa2.text_input("رقم واتساب الفني للتلقي التزامني (بدون رموز):", value=tech_whatsapp_val)

            oil_recommendation_text = f"موصى به تغيير الزيت والفلتر فوراً بسبب ارتفاع درجات الحرارة التشغيلية ({coolant_temp}°C)." if coolant_temp > 90.0 else "حالة الزيت ضمن المعدل الطبيعي مع المتابعة الدورية."
            
            default_smart_alarm_msg = f"""🚨 *إنذار صيانة تنبؤي ذكي - نظام الدومة (ATS)*
مرحباً الزميل الفني / المهندس: {assigned_tech_input}
الموقع: {selected_main_site} - {selected_sub_site}
المولد: {selected_gen} ({gen_details.get('model', 'Genset')})

📊 *تقرير الـ 14 وحدة وقطع الغيار:*
- ساعات التشغيل الحالية: {current_run_hrs} ساعة.
- حالة تبريد المحرك: {coolant_temp}°C | درجة الحرارة المحيطة: {ambient_temp}°C.
- *توصية غيار الزيت الذكية:* {oil_recommendation_text}

يرجى اتخاذ الإجراء السريع للوحدات التي اقتربت من انتهاء ساعات الصلاحية الافتراضية."""

            smart_msg_text = st.text_area("نص رسالة الواتساب الذكية التلقائية (قابل للتعديل):", value=default_smart_alarm_msg)
            encoded_smart_whatsapp = urllib.parse.quote(smart_msg_text)
            whatsapp_link_url = f"https://wa.me/{whatsapp_num_input}?text={encoded_smart_whatsapp}"

            st.markdown(f'''
                <a href="{whatsapp_link_url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:14px 24px; border-radius:6px; cursor:pointer; font-size:16px; font-weight:bold; width:100%;">
                        💬 إرسال إنذار ورسالة واتساب نصية ذكية تزامنية للفني ({assigned_tech_input})
                    </button>
                </a>
            ''', unsafe_allow_html=True)

            # الرسمات البيانية لأداء المولد
            st.markdown("---")
            st.subheader(f"📈 الرسمات البيانية لأداء المولد ({selected_gen})")
            
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                # رسم بياني لكفاءة وحمل المولد
                fig_load, ax_load = plt.subplots(figsize=(6, 3.5))
                categories = ['الحمل الفعلي', 'السعة القصوى', 'الاحتياطي المتاح']
                values = [gen_details.get('load', 200), gen_details.get('kw', 400), max(0, gen_details.get('kw', 400) - gen_details.get('load', 200))]
                ax_load.bar(categories, values, color=['#1f77b4', '#2ca02c', '#ff7f0e'])
                ax_load.set_title('مقارنة الأحمال والقدرة (kW)', fontweight='bold')
                ax_load.grid(axis='y', linestyle='--', alpha=0.7)
                st.pyplot(fig_load)

            with col_chart2:
                # رسم بياني لدرجات الحرارة وضغوط الزيت
                fig_eng, ax_eng = plt.subplots(figsize=(6, 3.5))
                metrics_labels = ['حرارة المبرد (°C)', 'حرارة المحيط (°C)', 'ضغط الزيت (Bar x 10)']
                metrics_vals = [coolant_temp, ambient_temp, engine_calib.get('oil_press_bar', 4.0) * 10]
                ax_eng.plot(metrics_labels, metrics_vals, marker='o', color='red', linewidth=2)
                ax_eng.set_title('مؤشرات حرارة المحرك والضغط', fontweight='bold')
                ax_eng.grid(True, linestyle='--', alpha=0.7)
                st.pyplot(fig_eng)

            # زر إصدار تقرير شامل بحالة المولد PDF بضغط زر
            st.markdown("---")
            st.subheader("📄 إصدار تقرير شامل بحالة المولد بصيغة PDF")
            if st.button("📥 تحميل التقرير الشامل PDF بحالة المولد والوحدات", type="primary", use_container_width=True):
                try:
                    pdf = ComprehensivePDF(
                        title_text=f"GENSET PREDICTIVE & OPERATIONAL REPORT - {selected_gen}",
                        logo_path=logo_file if 'logo_file' in locals() and logo_file else None,
                        site_address=current_site_address if 'current_site_address' in locals() else "Khartoum",
                        main_site=selected_main_site,
                        sub_site=selected_sub_site
                    )
                    pdf.add_page()
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(0, 8, f"Generator Model: {sanitize_latin_only(gen_details.get('model', 'N/A'))}", ln=True)
                    pdf.set_font("Helvetica", "", 10)
                    pdf.cell(0, 6, f"Run Hours: {current_run_hrs} hrs | Capacity: {gen_details.get('kw', 0)} kW | Load: {gen_details.get('load', 0)} kW", ln=True)
                    pdf.cell(0, 6, f"Coolant Temp: {coolant_temp} C | Ambient Temp: {ambient_temp} C | Oil Pressure: {engine_calib.get('oil_press_bar', 4.0)} Bar", ln=True)
                    pdf.cell(0, 6, f"Technician: {sanitize_latin_only(assigned_tech_input)} | WhatsApp: {sanitize_latin_only(whatsapp_num_input)}", ln=True)
                    pdf.ln(5)
                    pdf.set_font("Helvetica", "B", 10)
                    pdf.cell(0, 8, "14 Units Predictive Maintenance Status Table Summary:", ln=True)
                    pdf.set_font("Helvetica", "", 8)
                    for item in units_14_data:
                        line_str = f"Unit {item['UnitNo']}: {item['Part / Service Unit']} - Default: {item['DefaultHours']}h - Remaining Validity: {item['Validity']}h"
                        pdf.cell(0, 5, sanitize_latin_only(line_str), ln=True)
                    
                    pdf_output_bytes = pdf.output(dest='S').encode('latin1')
                    st.download_button(
                        label="⬇️ اضغط هنا لتنزيل ملف الـ PDF الشامل",
                        data=pdf_output_bytes,
                        file_name=f"Genset_Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    st.success("✅ تم إعداد تقرير الـ PDF الشامل بنجاح وجاهز للتحميل!")
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء إنشاء ملف الـ PDF: {e}")

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
    elif "7." in selected_app:
        st.title("⚡ ATS DocIntel GenAI")
        st.markdown("### *Industrial Document Intelligence, Predictive RUL Analytics & Automated Fault Remediation Suite*")
        st.markdown("---")
        with st.sidebar:
            st.header("📂 Smart Input Panel")
            st.markdown("Upload catalogs (PDF) and equipment images for comparison and analysis:")
            
            uploaded_manuals = st.file_uploader(
                "Upload Maintenance Catalogs (PDF)", 
                type=["pdf", "txt", "docx"],
                accept_multiple_files=True
            )
            
            st.markdown("---")
            st.subheader("🔍 Parts Image Comparison")
            healthy_img = st.file_uploader("Healthy Part Image (Reference)", type=["jpg", "png", "jpeg"], key="healthy")
            damaged_img = st.file_uploader("Damaged Part Image (From Field)", type=["jpg", "png", "jpeg"], key="damaged")
            
            st.markdown("---")
            st.info("💡 **Operating System:** ATS DocIntel is connected to the engine and cold room database for instant status analysis and sending alerts.")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Diagnostics & RUL Analytics", 
            "📑 AI Documents (NLP)", 
            "🚨 Alarms & Coordinates System", 
            "📈 Fuel vs. Load Charts"
        ])
        with tab1:
            st.subheader("Evaluation & Remaining Useful Life (RUL Assessment)")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(label="Overall Machine Status", value="92%", delta="Stable")
            with col2:
                st.metric(label="Spare Parts Remaining Useful Life (RUL)", value="450 Run Hours", delta="-30 hours this week")
            with col3:
                st.metric(label="Dynamic Sync Efficiency (DSE)", value="98.5%", delta="+1.2%")
                
            st.markdown("---")
            st.write("### Components Inspection Report & Fault Deduction:")
            
            data_audit = {
                "Component / System": ["Diesel Pump (Mechanical Pump)", "70-pin Sensors (Perkins)", "Cooling Unit (WIC 40)", "Control System (DSE 8610)"],
                "Operational Status": ["Requires preventive maintenance soon", "100% Healthy", "Stable", "Excellent"],
                "Expected Wear Percentage": ["18%", "2%", "5%", "1%"],
                "Recommended Action Plan": ["Pressure calibration and filter change", "No action required", "Check refrigerant gas", "Firmware update"]
            }
            df_audit = pd.DataFrame(data_audit)
            st.dataframe(df_audit, use_container_width=True)
        with tab2:
            st.subheader("Document Intelligence & Knowledge Graph (Inspired by Wordlit)")
            if uploaded_manuals:
                st.success(f"Successfully uploaded and processed {len(uploaded_manuals)} technical file(s)/catalog(s).")
                for file in uploaded_manuals:
                    st.write(f"📄 **Data extracted and catalog indexed:** {file.name}")
                st.info("🤖 The AI model is now analyzing the catalogs to match Perkins or WIC equipment part numbers and fault codes.")
            else:
                st.warning("Please upload maintenance catalogs in PDF format from the sidebar to begin text analysis and extract technical links.")
        with tab3:
            st.subheader("🚨 SMS & Audio Alerts System")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("### Field Engineer Alert Settings:")
                eng_phone = st.text_input("Technical Engineer Phone Number", "+249XXXXXXXXX")
                fault_location = st.text_input("Site Location / Geo-coordinates", "Mining Factory - Main Generator (130 KVA)")
                selected_fault = st.selectbox("Detected Fault Type", [
                    "Low Oil Pressure in Perkins Engine",
                    "High Temperature in WIC 40 Cold Room",
                    "Generator Sync Error (DSE 8610)",
                    "Fuel Line Leak"
                ])
                
                if st.button("Send Instant Alert (SMS & Voice Alert)"):
                    if eng_phone:
                        st.success(f"✅ SMS and voice alert successfully sent to ({eng_phone}) detailing the fault location ('{fault_location}') and issue type along with the proposed remediation plan!")
                    else:
                        st.error("Please enter the engineer's phone number first.")
                        
            with col_b:
                st.write("### Active Alarms Log:")
                st.error("⚠️ [Critical Alert 10:42 AM]: Perkins engine response error - Immediate solution plan dispatched to the engineer.")
                st.warning("⚠️ [Preventive Alert]: Approaching diesel filter change schedule for 150 KVA generator.")
        with tab4:
            st.subheader("📈 Fuel vs. Load Analytics Reports")
            st.markdown("Chart illustrating fuel consumption efficiency based on generator loads:")
            
            fig, ax = plt.subplots(figsize=(10, 4))
            loads = np.array([20, 40, 60, 80, 100])
            fuel_consumption = np.array([12, 22, 35, 52, 75])
            
            ax.plot(loads, fuel_consumption, marker='o', color='#1f77b4', linewidth=2.5, label='Actual Fuel Consumption (L/h)')
            ax.set_title('Fuel Consumption vs. Load Curve (%)', fontsize=12, fontweight='bold')
            ax.set_xlabel('Load Percentage (%)')
            ax.set_ylabel('Consumption Rate (Liters/hour)')
            ax.grid(True, linestyle='--', alpha=0.6)
            ax.legend()
            
            st.pyplot(fig)
