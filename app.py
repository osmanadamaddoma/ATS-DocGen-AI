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
    st.session_state.daily_logs = [{"timestamp": f"{today_str} 08:30:00", "date": today_str, "site": "الخرطوم (القائمة الرئيسية) - الموقع الرئيسي - كافوري (موقع فرعي)", "generator": "G1", "technician": "أحمد فني الصيانة", "run_hours": 700.0, "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"}]

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
            st.error(f"Supabase error: {e}")

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
        return "GEMINI_API_KEY not found" if language == "en" else "لم يتم العثور على مفتاح GEMINI_API_KEY."
    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة."
    prompt = f"""You are expert industrial consulting engineer specializing in generators, DSE 7320, DSE 8610 MKII, Perkins & Cummins.
    Fault: "{fault_code}"
    Context: {context_text[:3000] if context_text else "No catalog"}
    Provide: 1. Explanation 2. Top 3 Causes 3. Corrective Actions. {lang_instr}"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(2)
                continue
            return f"Error: {e}"

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
        data.append({"_time": t, "temperature": 80.0 + random.uniform(-3, 6), "vibration": 3.2 + random.uniform(-0.5, 1.2), "pressure": 4.1 + random.uniform(-0.4, 0.4)})
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

if "clients_db" not in st.session_state:
    st.session_state.clients_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة (Addoma Trading Services)", "plan": "شهري (Monthly)", "start_date": "2026-09-15", "duration_days": 30},
        "CLIENT-M-881": {"name": "شركة النيل للصناعات الهندسية", "plan": "شهري (Monthly)", "start_date": "2026-09-01", "duration_days": 30},
        "CLIENT-Y-992": {"name": "مصانع الحديد والصلب الوطنية", "plan": "سنوي (Yearly)", "start_date": "2026-03-15", "duration_days": 365},
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

@st.dialog("Generate New Subscription Code")
def generate_subscription_modal():
    client_name = st.text_input("اسم العميل / الشركة:")
    plan_type = st.selectbox("نوع الباقة:", ["شهري (Monthly)", "سنوي (Yearly)", "تجريبي (Trial)"])
    default_duration = 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("مدة الاشتراك (بالأيام):", value=default_duration, min_value=1)
    if st.button("اصدار الكود", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            today_str = datetime.now().strftime("%Y-%m-%d")
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_type, "start_date": today_str, "duration_days": custom_duration}
            st.success(f"تم اصدار الكود: {new_code}")
        else:
            st.error("ادخل اسم العميل")

# ===== FIXED - NO MORE SYNTAX ERROR HERE =====
st.sidebar.subheader("Language / اللغة")
lang_options = ["Arabic", "English"]
selected_lang = st.sidebar.radio("Select Language", lang_options, index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang

TXT = {
    "ar": {"title": "بوابة تفعيل النظام الموحد", "code_input": "كود التفعيل:", "btn_activate": "تفعيل", "invalid_code": "كود غير صحيح", "warning_auth": "ادخل كود صالح", "nav_header": "نظام الدومة", "nav_status": "النظام مفعل", "btn_chat": "المساعد الذكي", "btn_dashboard": "لوحة التحكم", "btn_apps": "التطبيقات", "btn_logout": "خروج", "client": "العميل:", "plan": "الباقة:", "remaining": "المتبقي:", "days": "يوم", "app_selection": "التطبيقات المتاحة", "choose_app": "اختر النظام:"},
    "en": {"title": "Unified Activation Portal", "code_input": "Activation Code:", "btn_activate": "Activate", "invalid_code": "Invalid code", "warning_auth": "Enter valid code", "nav_header": "Addoma System", "nav_status": "System Active", "btn_chat": "AI Assistant", "btn_dashboard": "Dashboard", "btn_apps": "Apps", "btn_logout": "Logout", "client": "Client:", "plan": "Plan:", "remaining": "Days Left:", "days": "days", "app_selection": "Available Apps", "choose_app": "Select System:"}
}[L]

if not st.session_state.authenticated:
    st.title(TXT["title"])
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")
    if st.sidebar.button(TXT["btn_activate"]):
        if user_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            cookie_manager.set("activation_code", user_code, expires_at=datetime.now()+timedelta(days=30))
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
            cookie_manager.delete("activation_code")
            if "active_code" in st.session_state:
                del st.session_state["active_code"]
            st.rerun()
        st.write("---")
        if st.button("اصدار اشتراك جديد (Admin)", use_container_width=True):
            generate_subscription_modal()

input_code = st.session_state.get("active_code", "")
is_pro = False
if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    if datetime.now().date() <= expiry_dt:
        is_pro = True
        days_left = (expiry_dt - datetime.now().date()).days
        st.sidebar.success("Verified!")
        st.sidebar.markdown(f"**{TXT['client']}** {data['name']}")
        st.sidebar.markdown(f"**{TXT['plan']}** {data['plan']} - {days_left} {TXT['days']}")
    else:
        st.sidebar.error(f"Expired on {expiry_dt}")
        st.session_state.authenticated = False
        st.stop()
if not is_pro:
    st.warning(TXT["warning_auth"])
    st.stop()

st.sidebar.divider()
st.sidebar.markdown(TXT["app_selection"])
def on_app_change():
    st.session_state.current_page = "main_apps"
apps_list_ar = ["1. الصيانة التنبؤية والمولدات", "2. غرفة التحكم عن بعد", "3. المتابعة اليومية", "4. المساعد الذكي والكتالوجات", "5. نظام فحص المعدات (WIC وغيرها)", "6. الحاسبة الهندسية"]
apps_list_en = ["1. Predictive Maintenance & Gensets", "2. Remote Control Center", "3. Daily Monitoring", "4. AI Diagnostics & Catalog Reader", "5. Equipment Inspection (WIC & Heavy Duty)", "6. Smart Calculator"]
selected_app = st.sidebar.radio(TXT["choose_app"], apps_list_ar if L == "ar" else apps_list_en, on_change=on_app_change)
st.sidebar.divider()

@st.dialog("Edit Generator Data")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})
    st.markdown(f"### {gen_key} - {sub_site}")
    tech_name = st.text_input("Technician Name:", value="فني الصيانة")
    tab1, tab2, tab3 = st.tabs(["Basic", "Electrical", "Engine"])
    with tab1:
        new_model = st.text_input("Model", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("Run Hours", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("Capacity kW", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("Load kW", min_value=0.0, value=float(gen_data.get("load", 0.0)))
    with tab2:
        v_nom = st.number_input("Nominal V", value=float(elec.get("v_nominal", 400.0)))
        v_meas = st.number_input("Measured V", value=float(elec.get("v_measured", 398.0)))
        f_nom = st.number_input("Nominal Hz", value=float(elec.get("freq_nominal", 50.0)))
        f_meas = st.number_input("Measured Hz", value=float(elec.get("freq_measured", 50.0)))
        c_max = st.number_input("Max A", value=float(elec.get("current_max", 600.0)))
        c_meas = st.number_input("Measured A", value=float(elec.get("current_measured", 360.0)))
        pf_val = st.number_input("PF", value=float(elec.get("pf", 0.85)))
        ct_rat = st.text_input("CT Ratio", value=str(elec.get("ct_ratio", "600/5")))
    with tab3:
        o_press = st.number_input("Oil Press Bar", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("Coolant Temp C", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = st.number_input("RPM", value=float(eng.get("rpm", 1500.0)))
        b_volt = st.number_input("Battery V", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("Ambient Temp C", value=float(eng.get("ambient_temp", 43.0)))
    if st.button("Save Data", use_container_width=True, type="primary"):
        if c_temp < 0 or c_temp > 125 or o_press < 0 or o_press > 12 or v_meas < 100 or v_meas > 600:
            st.error("Invalid values")
        else:
            st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {"model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load, "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat}, "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}}
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.session_state.daily_logs.append({"timestamp": now_str, "date": datetime.now().strftime("%Y-%m-%d"), "site": f"{main_site} - {sub_site}", "generator": gen_key, "technician": tech_name, "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "Updated"})
            st.success("Saved!")
            st.rerun()

if st.session_state.current_page == "chat":
    st.title("AI Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحبا! كيف اساعدك في المولدات؟" if L == "ar" else "Hello! How can I help with generators?"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    user_query = st.chat_input("Ask..." if L == "en" else "اكتب استفسارك...")
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.messages.append({"role": "user", "content": user_query})
        with st.chat_message("assistant"):
            response_text = analyze_fault_with_gemini(user_query, language=L) if client else "Add GEMINI_API_KEY"
            st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})

elif st.session_state.current_page == "dashboard":
    st.title("Systems Dashboard")
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Generators Status", value="Stable", delta="Sync Ready")
    col2.metric(label="WIC Cold Rooms", value="2 Units", delta="-1C")
    col3.metric(label="Database", value="Supabase Online" if supabase else "Offline", delta="Ping 12ms")
    st.divider()
    st.info("Telemetry powered by InfluxDB & Analytics")

else:
    if "1." in selected_app:
        st.title("Predictive Maintenance & Gensets")
        col_top1, col_top2 = st.columns([3, 1])
        with col_top2:
            mute_label = "Mute" if not st.session_state.audio_muted else "Unmute"
            if st.button(mute_label, use_container_width=True):
                st.session_state.audio_muted = not st.session_state.audio_muted
                st.rerun()
        logo_file = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo_up")
        st.subheader("Site Management")
        with st.expander("Add Area / Site / Generators", expanded=False):
            geo_region = st.text_input("Area Name (e.g., Khartoum):", key="geo_reg_input")
            site_name = st.text_input("Site Name (e.g., Kafouri):", key="site_name_input")
            site_address = st.text_input("Site Address:", key="site_add_input")
            num_gens = st.number_input("Number of Generators:", min_value=1, max_value=20, value=1, step=1, key="num_gens_input")
            gen_inputs = []
            for i in range(int(num_gens)):
                st.markdown(f"**Generator {i+1}**")
                col_g1, col_g2, col_g3 = st.columns(3)
                g_id = col_g1.text_input(f"ID", value=f"G{i+1}", key=f"g_id_{i}")
                g_model = col_g2.text_input(f"Model", value="Perkins", key=f"g_mod_{i}")
                g_kw = col_g3.number_input(f"kW", min_value=0.0, value=100.0, step=10.0, key=f"g_kw_{i}")
                gen_inputs.append({"id": g_id, "model": g_model, "kw": g_kw})
            if st.button("Save Site Data", type="primary"):
                if geo_region and site_name:
                    if geo_region not in st.session_state.sites_data:
                        st.session_state.sites_data[geo_region] = {}
                    st.session_state.sites_data[geo_region][site_name] = {"address": site_address if site_address else "N/A", "generators": {}}
                    for gen in gen_inputs:
                        if gen["id"]:
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {"model": gen["model"], "run_hours": 0.0, "target": 250.0, "kw": gen["kw"], "load": 0.0, "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"}, "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}}
                    st.success(f"Saved {geo_region} - {site_name}")
                    st.rerun()
                else:
                    st.error("Enter Area and Site name")
        main_sites = list(st.session_state.sites_data.keys())
        col_site1, col_site2 = st.columns(2)
        selected_main_site = None
        selected_sub_site = None
        current_site_address = ""
        with col_site1:
            if main_sites:
                selected_main_site = st.selectbox("Select Area:", main_sites)
        with col_site2:
            if selected_main_site:
                sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
                if sub_sites:
                    selected_sub_site = st.selectbox("Select Site:", sub_sites)
                    current_site_address = st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", "")
        if not main_sites or not selected_main_site or not selected_sub_site:
            st.warning("Please add and select a site")
            st.stop()
        st.divider()
        gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())
        if not gen_list:
            st.info("No generators in this site")
        else:
            col_select_g, col_modal_btn = st.columns([2, 1])
            with col_select_g:
                selected_gen = st.selectbox("Select Generator:", gen_list)
            with col_modal_btn:
                st.write("")
                if st.button("Open Calibration Modal"):
                    edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)
            gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            calib_e = gen_info.get("calib_elec", {})
            calib_m = gen_info.get("calib_engine", {})
            st.subheader(f"Calibration Dashboard ({selected_gen})")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("Model & Capacity", f"{gen_info['model']}", f"{gen_info['kw']} kW")
            m_c2.metric("Run Hours / Target", f"{gen_info['run_hours']} hrs", f"Target: {gen_info['target']} hrs")
            m_c3.metric("Measured Voltage", f"{calib_e.get('v_measured', 0)} V", f"Nominal: {calib_e.get('v_nominal', 0)} V")
            m_c4.metric("Coolant / Ambient", f"{calib_m.get('coolant_temp_c', 0)} C", f"Ambient: {calib_m.get('ambient_temp', 0)} C")
            alarm_messages = []
            if abs(calib_e.get("v_measured", 400) - calib_e.get("v_nominal", 400)) > 20:
                alarm_messages.append(f"Voltage Deviation on {selected_gen}")
            if calib_m.get("coolant_temp_c", 0) >= 95.0:
                alarm_messages.append(f"High Coolant Temp on {selected_gen}: {calib_m.get('coolant_temp_c')} C")
            if calib_m.get("oil_press_bar", 5) <= 1.8:
                alarm_messages.append(f"Low Oil Pressure on {selected_gen}")
            if alarm_messages:
                for msg in alarm_messages:
                    st.error(f"{msg}")
                play_audio(". ".join(alarm_messages), loop=True)
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
            st.subheader(f"Maintenance Table - {selected_gen}")
            df_parts_input = pd.DataFrame(st.session_state[parts_key])
            edited_df = st.data_editor(df_parts_input, num_rows="dynamic", width="stretch")
            if st.button("Update / Reset Checked Parts", type="primary"):
                new_data = []
                for _, row in edited_df.iterrows():
                    item = row.to_dict()
                    if item.get("تجديد (تصفير)"):
                        item["الساعات المنقضية (ساعة)"] = 0.0
                        item["تجديد (تصفير)"] = False
                    new_data.append(item)
                st.session_state[parts_key] = new_data
                st.success("Updated!")
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
                processed_rows.append({"الوحدة": row.get("الوحدة", idx + 1), "تصنيف القطعة": cat, "قطع الغيار / الفلاتر": part, "العمر الافتراضي (ساعة)": life, "الساعات المنقضية (ساعة)": used, "المدة المتبقية (ساعة)": max(0.0, rem), "نسبة الاستهلاك (%)": round(pct, 1), "حالة التنبيه": status_str, "الكود الملون": color_code})
            df_result = pd.DataFrame(processed_rows)
            st.divider()
            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.markdown("##### Parts Usage Chart")
                fig_bar = go.Figure(go.Bar(x=df_result["قطع الغيار / الفلاتر"], y=df_result["نسبة الاستهلاك (%)"], marker_color=bar_colors, text=df_result["نسبة الاستهلاك (%)"].astype(str) + "%", textposition='auto'))
                st.plotly_chart(fig_bar, use_container_width=True)
            with chart_col2:
                st.markdown("##### Genset Run Hours Ratio")
                fig_pie = px.pie(names=['Elapsed Hours', 'Remaining Target'], values=[float(gen_info["run_hours"]), max(0.0, float(gen_info["target"]) - float(gen_info["run_hours"]))], hole=0.5, color_discrete_sequence=["#182b49", "#28a745"])
                st.plotly_chart(fig_pie, use_container_width=True)
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
                pdf.cell(0, 5, f"Site Address: {sanitize_latin_only(current_site_address)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Main Site: {sanitize_latin_only(selected_main_site)} | Sub: {sanitize_latin_only(selected_sub_site)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Gen ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | {gen_info['kw']} kW", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Run Hours: {gen_info['run_hours']} | Target: {gen_info['target']}", ln=True)
                amb_temp_val = calib_m.get('ambient_temp', 43.0)
                pdf.ln(2)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(200, 30, 30)
                pdf.cell(0, 5, "Engine Oil Recommendation:", ln=True)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(24, 43, 73)
                if amb_temp_val >= 45:
                    pdf.cell(0, 5, f"[Ambient: {amb_temp_val} C] -> USE 20W50", ln=True)
                elif amb_temp_val >= 43:
                    pdf.cell(0, 5, f"[Ambient: {amb_temp_val} C] -> USE 15W40", ln=True)
                else:
                    pdf.cell(0, 5, f"[Ambient: {amb_temp_val} C] -> USE 15W40", ln=True)
                pdf.ln(8)
                headers_pdf = ["#", "Part", "Life", "Used", "Remain", "Status"]
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
            st.download_button(label=f"Download Report {selected_gen}", data=generate_full_pdf_bytes(), file_name=f"Report_{selected_gen}.pdf", mime="application/pdf", use_container_width=True)

    elif "2." in selected_app:
        st.title("Remote Control Center")
        df_iot = fetch_live_iot_data()
        if not df_iot.empty:
            latest = df_iot.iloc[-1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Temp C", f"{latest['temperature']:.1f}")
            c2.metric("Vibration", f"{latest['vibration']:.2f}")
            c3.metric("Oil Press", f"{latest['pressure']:.1f}")
            st.plotly_chart(px.line(df_iot, x='_time', y='temperature', title="Live Trend"), use_container_width=True)
        st.divider()
        rc1, rc2, rc3 = st.columns(3)
        if rc1.button("Start Generator", use_container_width=True):
            st.success("Start signal dispatched!")
        if rc2.button("Emergency Stop", use_container_width=True):
            st.error("Emergency Stop!")
        if rc3.button("Reset Alarms", use_container_width=True):
            st.info("Reset!")

    elif "3." in selected_app:
        st.title("Daily Monitoring")
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_logs = [log for log in st.session_state.daily_logs if log.get("date") == today_str]
        st.write(f"Date: {today_str}")
        if today_logs:
            st.dataframe(pd.DataFrame(today_logs), use_container_width=True)
        else:
            st.warning("No logs today")
        tech_phone = st.text_input("Technician Phone:", value="249912345678")
        reminder_msg = f"Reminder: Please register daily genset logs for {today_str}"
        encoded_msg = urllib.parse.quote(reminder_msg)
        whatsapp_url = f"https://wa.me/{tech_phone}?text={encoded_msg}"
        st.markdown(f'<a href="{whatsapp_url}" target="_blank"><button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px;">Send WhatsApp Reminder</button></a>', unsafe_allow_html=True)

    elif "4." in selected_app:
        st.title("AI Diagnostics & Catalog Reader")
        fault_input = st.text_input("Enter Fault Code:", value="Over Current")
        if st.button("Analyze Fault", use_container_width=True):
            st.markdown(analyze_fault_with_gemini(fault_input, language=L))

    elif "5." in selected_app:
        st.title("Equipment Inspection - WIC & Gensets")
        eq_type = st.selectbox("Equipment Type:", ["Industrial Diesel Generator", "WIC 10 & WIC 40 Cold Rooms", "3-Phase Electric Motor"])
        if "WIC" in eq_type:
            st.warning("Check expansion valves, defrost heaters, refrigerant flow for WIC 10 and WIC 40")
            c1, c2, c3 = st.columns(3)
            c1.metric("Room Temp", "-19.5 C", "-1.5 C")
            c2.metric("LP", "35 PSI", "Normal")
            c3.metric("HP", "210 PSI", "Normal")
            st.subheader("WIC Checklist - 16 Point")
            for item in ["Compressor Oil", "R404a Gas", "Expansion Valve", "Defrost Heater", "Evaporator Fans", "Condenser Fans", "Door Gasket", "Drain Heater", "Controller Eliwell", "HP Cutout", "LP Cutout"]:
                st.checkbox(item)
            room_vol = st.number_input("Room Volume m3", value=120.0)
            cooling_load = (room_vol * 65 * 0.022) / 0.8
            st.metric("Required Cooling Load", f"{cooling_load:.2f} kW")
        elif "Generator" in eq_type:
            st.subheader("Generator 22 Point Inspection")
            for item in ["Oil Level", "Coolant", "Fuel", "Battery", "Air Filter", "Belt", "Exhaust", "Vibration", "Alternator Output", "DSE Alarms", "ATS Test", "Load Test"]:
                st.checkbox(item)
        else:
            motor_kw = st.number_input("Motor kW", value=15.0)
            motor_flc = (motor_kw * 1000) / (1.732 * 400 * 0.85 * 0.92)
            st.metric("FLC", f"{motor_flc:.1f} A")
            for item in ["Insulation >1Mohm", "Bearing Noise", "Vibration <2.8mm/s"]:
                st.checkbox(item)

    elif "6." in selected_app:
        st.title("Smart Calculator")
        tab1, tab2 = st.tabs(["Cable Voltage Drop", "Fuel & Carbon"])
        with tab1:
            i_amp = st.number_input("Current A:", value=250.0)
            dist_m = st.number_input("Length m:", value=120.0)
            c_size = st.selectbox("Cable mm2:", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4)
            v_drop, v_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size)
            st.metric("Voltage Drop", f"{v_drop} V", f"{v_pct}%")
            if v_pct > 4.0:
                st.error("Exceeds 4% limit!")
            else:
                st.success("Acceptable")
        with tab2:
            load_kw = st.number_input("Load kW:", value=200.0)
            hours_run = st.number_input("Hours:", value=24.0)
            liters, co2 = calculate_fuel_consumption_and_emissions(load_kw, hours_run)
            st.metric("Diesel Used", f"{liters} Liters")
            st.metric("CO2 Output", f"{co2} kg")
