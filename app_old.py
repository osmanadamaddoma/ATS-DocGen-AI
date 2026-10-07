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
# 0. Main Page Config & AI/Audio/Language Initialization
# =========================================================
st.set_page_config(
    page_title="Comprehensive Industrial Complex - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "en" # Changed default to English

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "Khartoum (Main Menu)": {
            "Main Site - Kafouri (Sub-site)": {
                "address": "Khartoum - Industrial Area - Kafouri",
                "technician_name": "Eng. Osman Adam Addoma",
                "technician_whatsapp": "249912345678",
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
            "site": "Khartoum (Main Menu) - Main Site - Kafouri (Sub-site)",
            "generator": "G1",
            "technician": "Ahmed - Maintenance Tech",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "Normal"
        }
    ]

gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")

L = st.session_state.lang

if not gemini_key:
    st.warning("⚠️ GEMINI_API_KEY not found. Please add it to st.secrets." if L == "en" else "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

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
            st.success("✅ Application successfully connected and activated with Supabase database!" if L == "en" else "✅ التطبيق متصل ومُفعل بنجاح مع قاعدة بيانات Supabase!")
        except Exception as e:
            st.error(f"❌ Database connection failed: {e}" if L == "en" else f"❌ فشل الاتصال بقاعدة البيانات: {e}")
    else:
        st.info("💡 Supabase keys not found. Please add them." if L == "en" else "💡 لم يتم العثور على مفاتيح Supabase. يرجى إضافتها.")

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
        st.error(f"Audio playback error: {e}" if L == "en" else f"حدث خطأ في تشغيل الصوت: {e}")

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
        self.cell(0, 4, "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY", ln=True)
        self.set_x(text_x)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 4, f"SITE: {sanitize_latin_only(self.site_address)} | {sanitize_latin_only(self.main_site)} - {sanitize_latin_only(self.sub_site)}", ln=True)
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
        self.cell(0, 4, "Prepared by: Eng. Osman Adam Addoma | Power Systems Engineer", ln=True, align="C")
        self.cell(0, 4, f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Site: {sanitize_latin_only(self.site_address)}", align="C")

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
                if load == 0: continue
                sfc = float(row.get("SFC L/kWh", 0.24))
                def g_to_l(g):
                    try: return float(g) / 850.0
                    except: return sfc
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
            if table: return table
        except Exception as e:
            print(f"CSV parse error: {e}")
            return default_table
    return default_table

def calculate_fuel_consumption_and_emissions(kw_load, run_hours, gen_model="Perkins", kw_capacity=None, fuel_table=None):
    if fuel_table is None: fuel_table = get_fuel_table_from_csv()
    if kw_capacity and kw_capacity > 0:
        load_pct = (kw_load / kw_capacity) * 100.0
    else:
        load_pct = 100.0 if kw_load > 100 else kw_load
    load_pct = max(25.0, min(100.0, load_pct))
    model_key = "AVG"
    if "CAT" in str(gen_model).upper(): model_key = "CAT C32"
    elif "CUMMINS" in str(gen_model).upper() or "KTA" in str(gen_model).upper(): model_key = "Cummins KTA50"
    elif "PERKINS" in str(gen_model).upper(): model_key = "Perkins 2506"
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

CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "Eng. Osman Adam Addoma (Addoma Trading Services)",
        "plan": "Monthly",
        "start_date": "2026-09-15",
        "duration_days": 30,
    }
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

# Language Selector
st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["English", "العربية (Arabic)"], index=0 if st.session_state.lang == "en" else 1)
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
        clean_code = user_code.strip().upper()
        if clean_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = clean_code
            st.session_state.user_email = CLIENTS_DATABASE[clean_code]["name"]
            st.session_state.role = "admin" if clean_code in ADMIN_CODES else "client"
            expires_at = datetime.now() + timedelta(days=365)
            try:
                cookie_manager.set("activation_code_v5", clean_code, expires_at=expires_at)
            except: pass
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
            except: pass
            st.rerun()

input_code = st.session_state.get("active_code", "")
is_pro = False
if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()
    if today <= expiry_dt:
        is_pro = True
        st.sidebar.success("✅ Subscription Verified!" if L == "en" else "✅ تم التحقق من الاشتراك!")
    else:
        st.session_state.authenticated = False
        st.stop()

st.sidebar.divider()
st.sidebar.markdown(TXT["app_selection"])

apps_list_en = [
    "⚙️ 1. Predictive Maintenance & Gensets",
    "🎛 2. Remote Operations & Control Center",
    "📊 3. Daily Monitoring & Reminders",
    "🤖 4. AI Diagnostics & Catalog Reader",
    "🔍 5. Cold Room Inspection (WIC 10 & WIC 40)",
    "🧮 6. Smart Electrical & Carbon Calculator"
]
apps_list_ar = [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص معدات التبريد (WIC 10 & WIC 40)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات"
]

selected_app = st.sidebar.radio(
    TXT["choose_app"],
    apps_list_en if L == "en" else apps_list_ar,
    on_change=lambda: st.session_state.update(current_page="main_apps")
)

# [بقية الدوال والشاشات ستحافظ على نفس المنطق البرمجي، مع تفعيل الترجمة كالتالي]

if st.session_state.current_page == "chat":
    st.title("🤖 " + ("Smart AI Assistant" if L == "en" else "المساعد الذكي الهندسي"))
    user_query = st.chat_input("Ask a technical question..." if L == "en" else "اكتب استفسارك الهندسي هنا...")
    if user_query:
        st.chat_message("user").markdown(user_query)
        res = analyze_fault_with_gemini(user_query, language=L)
        st.chat_message("assistant").markdown(res)

elif "5." in selected_app:
    st.title("🔍 " + ("Cold Room Inspection (WIC 10 & WIC 40)" if L == "en" else "نظام فحص معدات التبريد (WIC 10 & WIC 40)"))
    col_wic1, col_wic2 = st.columns(2)
    wic_unit = col_wic1.radio("Select Unit:" if L == "en" else "اختر وحدة التبريد لفحصها:", ["WIC 10 Cold Room", "WIC 40 Cold Room"] if L == "en" else ["غرفة التبريد نموذج WIC 10", "غرفة التبريد نموذج WIC 40"])
    controller_type = col_wic2.selectbox("Controller Type:" if L == "en" else "نوع المتحكم المستخدم (Controller):", ["Emerson", "Dixell"])

elif "6." in selected_app:
    st.title("🧮 " + ("Smart Electrical & Carbon Calculator" if L == "en" else "الحاسبة الهندسية للكهرباء والانبعاثات"))
    tab_calc1, tab_calc2 = st.tabs(["⚡ Cable Voltage Drop" if L == "en" else "⚡ هبوط الجهد الكهربائي", "⛽ Fuel & Emissions" if L == "en" else "⛽ استهلاك الوقود والحمل"])
    with tab_calc2:
        col_c1, col_c2 = st.columns(2)
        gen_model_calc = col_c1.selectbox("Generator Model:" if L == "en" else "طراز المولد:", ["Perkins", "Cummins", "CAT"])
        pump_type = col_c2.selectbox("Fuel Pump System:" if L == "en" else "نوع نظام طلمبة الوقود:", [
            "Mechanical Fuel Pump (Normal)" if L == "en" else "طلمبة ديزل قلب عادية (ميكانيكية)", 
            "Electronic Injection (MEUI/ECM)" if L == "en" else "حقن إلكتروني (MEUI/ECM)"
        ])
