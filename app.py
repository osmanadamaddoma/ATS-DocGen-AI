import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import io
import base64
import math
import random

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
# 0. إعدادات الصفحة
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
    }

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [{
        "timestamp": f"{today_str} 08:30:00", "date": today_str,
        "site": "الخرطوم - كافوري", "generator": "G1",
        "technician": "أحمد فني الصيانة", "run_hours": 700.0,
        "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"
    }]

# Gemini & Supabase Keys
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
        except Exception as e:
            st.error(f"❌ فشل Supabase: {e}")

def play_audio(text, lang='ar', loop=False):
    if st.session_state.get("audio_muted", False): return
    try:
        tts_lang = 'en' if st.session_state.lang == 'en' or lang == 'en' else 'ar'
        tts = gTTS(text=text, lang=tts_lang)
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_bytes = audio_data.getvalue()
        if loop:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            audio_html = f'<audio autoplay loop controls style="width: 100%;"><source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3"></audio>'
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"Audio error: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client:
        return "⚠️ GEMINI_API_KEY missing" if language == "en" else "⚠️ مفتاح Gemini غير موجود"
    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة."
    prompt = f"""
    You are an expert industrial consulting engineer specializing in generators, DSE control panels (DSE 7320, DSE 8610 MKII), Perkins & Cummins engines.
    Fault Code / Alarm: "{fault_code}"
    Catalog Context: {context_text[:3000] if context_text else "No catalog"}
    Provide: 1. Technical Explanation 2. Top 3 Probable Causes 3. Sequential Field Corrective Actions.
    {lang_instr}
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return response.text
        except Exception as e:
            err_msg = str(e)
            if "503" in err_msg or "UNAVAILABLE" in err_msg:
                if attempt < max_retries - 1: time.sleep(2); continue
                else: return "⚠️ High load (503). Retry." if language == "en" else "⚠️ ضغط عالي (503). حاول مرة أخرى."
            return f"❌ Error: {err_msg}"

def sanitize_latin_only(text):
    if not isinstance(text, str): text = str(text)
    return re.sub(r"[^\x00-\x7F]+", "", text).strip() or "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path
    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        text_x = 40 if self.logo_path and os.path.exists(self.logo_path) else 10
        if self.logo_path and os.path.exists(self.logo_path):
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
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, f"Prepared by: Osman Adam Addoma | Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

def fetch_live_iot_data():
    today = datetime.now()
    data = []
    for i in range(20):
        t = today - timedelta(minutes=(20-i)*2)
        data.append({"_time": t, "temperature": 80.0 + random.uniform(-3, 6), "vibration": 3.2 + random.uniform(-0.5, 1.2), "pressure": 4.1 + random.uniform(-0.4, 0.4)})
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    rho_copper = 0.0178
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    return round(v_drop, 2), round((v_drop / 400.0) * 100, 2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    return round(liters, 1), round(liters * 2.68, 1)

# --- نظام الاشتراكات ---
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة", "plan": "شهري", "start_date": "2026-09-15", "duration_days": 30},
    }
CLIENTS_DATABASE = st.session_state.clients_db

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager")
    return st.session_state["cookie_manager"]
cookie_manager = get_cookie_manager()
saved_code = cookie_manager.get(cookie="activation_code")
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if saved_code and not st.session_state.authenticated and saved_code in CLIENTS_DATABASE:
    st.session_state.authenticated = True
    st.session_state.active_code = saved_code

@st.dialog("🔑 إصدار كود اشتراك جديد")
def generate_subscription_modal():
    client_name = st.text_input("اسم العميل:")
    plan_type = st.selectbox("نوع الباقة:", ["شهري (Monthly)", "سنوي (Yearly)", "تجريبي (Trial)"])
    default_duration = 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("مدة الاشتراك (أيام):", value=default_duration, min_value=1)
    if st.button("🚀 إصدار الكود", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            today_str = datetime.now().strftime("%Y-%m-%d")
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_type, "start_date": today_str, "duration_days": custom_duration}
            st.success(f"✅ الكود: {new_code}")
        else:
            st.error("❌ أدخل اسم العميل")

st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar
