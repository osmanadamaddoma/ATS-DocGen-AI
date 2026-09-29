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

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="Addoma - Industrial", page_icon="🔐", layout="wide")

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# DEFAULT 14 PARTS - الأصلية الكاملة
DEFAULT_PARTS_14 = [
    {"Unit": 1, "Category": "Engine", "Part": "Engine Oil Change", "Life": 250.0, "Used": 180.0, "Reset": False},
    {"Unit": 2, "Category": "Filter", "Part": "Oil Filter", "Life": 250.0, "Used": 180.0, "Reset": False},
    {"Unit": 3, "Category": "Filter", "Part": "Fuel Filter", "Life": 500.0, "Used": 430.0, "Reset": False},
    {"Unit": 4, "Category": "Filter", "Part": "Fuel Water Separator", "Life": 500.0, "Used": 320.0, "Reset": False},
    {"Unit": 5, "Category": "Air", "Part": "Air Filter Primary", "Life": 1000.0, "Used": 650.0, "Reset": False},
    {"Unit": 6, "Category": "Air", "Part": "Air Filter Secondary", "Life": 1000.0, "Used": 650.0, "Reset": False},
    {"Unit": 7, "Category": "Cooling", "Part": "Coolant Change", "Life": 2000.0, "Used": 1200.0, "Reset": False},
    {"Unit": 8, "Category": "Cooling", "Part": "Radiator Cleaning", "Life": 1000.0, "Used": 800.0, "Reset": False},
    {"Unit": 9, "Category": "Belt", "Part": "Fan Belt", "Life": 1000.0, "Used": 400.0, "Reset": False},
    {"Unit": 10, "Category": "Battery", "Part": "Battery Check", "Life": 500.0, "Used": 250.0, "Reset": False},
    {"Unit": 11, "Category": "Engine", "Part": "Valve Clearance", "Life": 2000.0, "Used": 1200.0, "Reset": False},
    {"Unit": 12, "Category": "Engine", "Part": "Injector Service", "Life": 2000.0, "Used": 1100.0, "Reset": False},
    {"Unit": 13, "Category": "General", "Part": "General Inspection", "Life": 250.0, "Used": 200.0, "Reset": False},
    {"Unit": 14, "Category": "General", "Part": "Load Bank Test", "Life": 1000.0, "Used": 300.0, "Reset": False},
]

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الخرطوم (القائمة الرئيسية)": {
            "الموقع الرئيسي - كافوري": {
                "address": "الخرطوم - كافوري",
                "generators": {
                    "G1": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0,
                           "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.1, "current_max": 600.0, "current_measured": 360.0, "pf": 0.85, "ct_ratio": "600/5"},
                           "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 26.5, "ambient_temp": 43.0}},
                    "G2": {"model": "Cummins 250 kVA", "run_hours": 1200.0, "target": 1500.0, "kw": 250.0, "load": 180.0,
                           "calib_elec": {"v_nominal": 400.0, "v_measured": 402.0, "freq_nominal": 50.0, "freq_measured": 49.9, "current_max": 360.0, "current_measured": 260.0, "pf": 0.82, "ct_ratio": "400/5"},
                           "calib_engine": {"oil_press_bar": 4.2, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 25.8, "ambient_temp": 45.0}}
                }
            }
        }
    }

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [{"timestamp": f"{today_str} 08:30:00", "date": today_str, "site": "الخرطوم - كافوري", "generator": "G1", "technician": "احمد", "run_hours": 700.0, "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"}]

# KEYS
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")
client_ai = genai.Client(api_key=gemini_key) if gemini_key else None

supabase = None
if create_client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url and "supabase" in st.secrets:
        url = st.secrets["supabase"].get("SUPABASE_URL")
        key = st.secrets["supabase"].get("SUPABASE_KEY")
    if url and key:
        try:
            supabase = create_client(url, key)
        except Exception:
            supabase = None

# SUPABASE HELPERS
def load_sites_from_supabase(user_code):
    if not supabase:
        return None
    try:
        res = supabase.table("sites").select("*").eq("user_code", user_code).execute()
        sites = {}
        for row in res.data:
            m = row["main_site"]
            s = row["sub_site"]
            if m not in sites:
                sites[m] = {}
            sites[m][s] = {"address": row["address"], "generators": row["generators"]}
        return sites if sites else None
    except Exception:
        return None

def save_site_to_supabase(user_code, main_site, sub_site, address, generators):
    if not supabase:
        return False
    try:
        supabase.table("sites").upsert({"user_code": user_code, "main_site": main_site, "sub_site": sub_site, "address": address, "generators": generators, "updated_at": datetime.now().isoformat()}, on_conflict="user_code,main_site,sub_site").execute()
        return True
    except Exception as e:
        st.error(f"Save error: {e}")
        return False

def save_log_to_supabase(log_entry, user_code):
    if not supabase:
        return
    try:
        supabase.table("daily_logs").insert({"user_code": user_code, "timestamp": log_entry["timestamp"], "date": log_entry["date"], "site": log_entry["site"], "generator": log_entry["generator"], "technician": log_entry["technician"], "run_hours": log_entry["run_hours"], "v_measured": log_entry["v_measured"], "oil_press": log_entry["oil_press"], "coolant_temp": log_entry["coolant_temp"], "status": log_entry["status"]}).execute()
    except Exception:
        pass

def play_audio(text, lang='ar', loop=False):
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts_lang = 'en' if st.session_state.lang == 'en' else 'ar'
        tts = gTTS(text=text, lang=tts_lang)
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        if loop:
            b64 = base64.b64encode(audio_data.getvalue()).decode("utf-8")
            st.components.v1.html(f'<audio autoplay loop controls style="width:100%;"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>', height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"Audio: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client_ai:
        return "Add GEMINI_API_KEY in Secrets"
    lang_instr = "Respond in English." if language == "en" else "اكتب بالعربية الفصحى التقنية"
    prompt = f"Expert DSE 7320/8610 Perkins Cummins. Fault: {fault_code}. Context: {context_text[:2000]}. Give explanation, 3 causes, actions. {lang_instr}"
    for _ in range(3):
        try:
            resp = client_ai.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return resp.text
        except Exception as e:
            if "503" in str(e):
                time.sleep(1)
                continue
            return f"Error: {e}"
    return "Busy"

def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean if clean else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path
    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        x = 40 if self.logo_path and os.path.exists(self.logo_path) else 10
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=12, w=25)
        self.set_xy(x, 12)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(24, 43, 73)
        self.cell(0, 5, self.report_title, ln=True)
        self.set_x(x)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "ADDOMA TRADING SERVICES", ln=True)
        self.line(10, 30, 200, 30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

def fetch_live_iot_data():
    data = []
    for i in range(20):
        t = datetime.now() - timedelta(minutes=(20-i)*2)
        data.append({"_time": t, "temperature": 80.0 + random.uniform(-3, 6), "vibration": 3.2 + random.uniform(-0.5, 1.2), "pressure": 4.1 + random.uniform(-0.4, 0.4)})
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    rho = 0.0178
    v_drop = (math.sqrt(3) * current_a * distance_m * rho * cos_phi) / cable_mm2
    return round(v_drop, 2), round((v_drop/400.0)*100, 2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    return round(liters, 1), round(liters*2.68, 1)

# AUTH
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {"ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة", "plan": "شهري", "start_date": "2026-09-15", "duration_days": 365}}
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

# LANGUAGE - FIXED NO SYNTAX ERROR
st.sidebar.subheader("Language / اللغة")
lang_choice = st.sidebar.radio("Select Language", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if lang_choice == "Arabic" else "en"
L = st.session_state.lang
TXT = {"ar": {"title": "بوابة التفعيل", "code_input": "كود التفعيل", "btn_activate": "تفعيل", "invalid_code": "كود غير صحيح", "warning_auth": "ادخل كود صالح", "nav_header": "نظام الدومة", "nav_status": "النظام مفعل", "btn_chat": "المساعد الذكي", "btn_dashboard": "لوحة التحكم", "btn_apps": "التطبيقات", "btn_logout": "خروج", "choose_app": "اختر النظام"}, "en": {"title": "Activation Portal", "code_input": "Activation Code", "btn_activate": "Activate", "invalid_code": "Invalid", "warning_auth": "Enter valid code", "nav_header": "Addoma System", "nav_status": "Active", "btn_chat": "AI Assistant", "btn_dashboard": "Dashboard", "btn_apps": "Apps", "btn_logout": "Logout", "choose_app": "Select System"}}[L]

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
        if st.button(TXT["btn_chat"], use_container_width=True):
            st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True):
            st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True):
            st.session_state.current_page = "main_apps"
        if st.button(TXT["btn_logout"], type="primary", use_container_width=True):
            st.session_state.authenticated = False
            cookie_manager.delete("activation_code")
            st.rerun()

if st.session_state.get("active_code", "") in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[st.session_state.active_code]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    if datetime.now().date() > expiry_dt:
        st.sidebar.error(f"Expired {expiry_dt}")
        st.session_state.authenticated = False
        st.stop()

st.sidebar.divider()
selected_app = st.sidebar.radio(TXT["choose_app"], ["1. Predictive Maintenance", "2. Remote Control", "3. Daily Monitoring", "4. AI Diagnostics", "5. Inspection", "6. Calculator"])

@st.dialog("Edit Generator")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})
    st.markdown(f"### {gen_key} - {sub_site}")
    tech_name = st.text_input("Technician:", value="Technician")
    tab1, tab2, tab3 = st.tabs(["Basic", "Electrical", "Engine"])
    with tab1:
        new_model = st.text_input("Model", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("Run Hours", value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours", value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("kW", value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("Load kW", value=float(gen_data.get("load", 0.0)))
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
        o_press = st.number_input("Oil Press", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("Coolant Temp", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = st.number_input("RPM", value=float(eng.get("rpm", 1500.0)))
        b_volt = st.number_input("Battery V", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("Ambient", value=float(eng.get("ambient_temp", 43.0)))
    if st.button("Save Data", use_container_width=True, type="primary"):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {"model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load, "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat}, "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}}
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_log = {"timestamp": now_str, "date": datetime.now().strftime("%Y-%m-%d"), "site": f"{main_site} - {sub_site}", "generator": gen_key, "technician": tech_name, "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "Updated"}
        st.session_state.daily_logs.append(new_log)
        save_log_to_supabase(new_log, st.session_state.active_code)
        save_site_to_supabase(st.session_state.active_code, main_site, sub_site, st.session_state.sites_data[main_site][sub_site]["address"], st.session_state.sites_data[main_site][sub_site]["generators"])
        st.success("Saved to cloud!")
        st.rerun()

# PAGES
if st.session_state.current_page == "chat":
    st.title("AI Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! How can I help?"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    q = st.chat_input("Ask...")
    if q:
        st.session_state.messages.append({"role": "user", "content": q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            ans = analyze_fault_with_gemini(q, language=L) if client_ai else "Add GEMINI_API_KEY"
            st.markdown(ans)
            st.session_state.messages.append({"role": "assistant", "content": ans})

elif st.session_state.current_page == "dashboard":
    st.title("Dashboard")
    c1, c2, c3 = st.columns(3)
    c1.metric("Generators", "Stable", "Sync Ready")
    c2.metric("WIC", "2 Units")
    c3.metric("Supabase", "Online" if supabase else "Offline")
    st.plotly_chart(px.line(fetch_live_iot_data(), x='_time', y='temperature', title="Live Temp"), use_container_width=True)

else:
    if "1." in selected_app:
        st.title("Predictive Maintenance")
        if "loaded_once" not in st.session_state:
            loaded = load_sites_from_supabase(st.session_state.active_code)
            if loaded:
                st.session_state.sites_data = loaded
            st.session_state.loaded_once = True

        with st.expander("Add Area / Site"):
            geo_region = st.text_input("Area Name:")
            site_name = st.text_input("Site Name:")
            site_address = st.text_input("Address:")
            num_gens = st.number_input("Number of Generators:", min_value=1, max_value=20, value=1)
            gen_inputs = []
            for i in range(int(num_gens)):
                st.markdown(f"**Generator {i+1}**")
                col_g1, col_g2, col_g3 = st.columns(3)
                g_id = col_g1.text_input(f"ID", value=f"G{i+1}", key=f"g_id_{i}")
                g_model = col_g2.text_input(f"Model", value="Perkins", key=f"g_mod_{i}")
                g_kw = col_g3.number_input(f"kW", value=100.0, key=f"g_kw_{i}")
                gen_inputs.append({"id": g_id, "model": g_model, "kw": g_kw})
            if st.button("Save Site", type="primary"):
                if geo_region and site_name:
                    if geo_region not in st.session_state.sites_data:
                        st.session_state.sites_data[geo_region] = {}
                    st.session_state.sites_data[geo_region][site_name] = {"address": site_address, "generators": {}}
                    for gen in gen_inputs:
                        if gen["id"]:
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {"model": gen["model"], "run_hours": 0.0, "target": 250.0, "kw": gen["kw"], "load": 0.0, "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"}, "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}}
                    save_site_to_supabase(st.session_state.active_code, geo_region, site_name, site_address, st.session_state.sites_data[geo_region][site_name]["generators"])
                    st.success(f"Saved {geo_region} - {site_name}")
                    st.rerun()

        main_sites = list(st.session_state.sites_data.keys())
        selected_main_site = st.selectbox("Area:", main_sites) if main_sites else None
        selected_sub_site = None
        if selected_main_site:
            subs = list(st.session_state.sites_data[selected_main_site].keys())
            selected_sub_site = st.selectbox("Site:", subs) if subs else None
        if not selected_main_site or not selected_sub_site:
            st.warning("Add site")
            st.stop()

        gens = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())
        sel_gen = st.selectbox("Generator:", gens) if gens else None
        if sel_gen:
            if st.button("Open Calibration Modal"):
                edit_generator_modal(selected_main_site, selected_sub_site, sel_gen)
            g = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][sel_gen]
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Model", g["model"], f"{g['kw']} kW")
            c2.metric("Hours", f"{g['run_hours']}", f"Target {g['target']}")
            c3.metric("Voltage", f"{g['calib_elec']['v_measured']} V")
            c4.metric("Temp", f"{g['calib_engine']['coolant_temp_c']} C")

            parts_key = f"parts_{selected_main_site}_{selected_sub_site}_{sel_gen}"
            if parts_key not in st.session_state:
                st.session_state[parts_key] = DEFAULT_PARTS_14.copy()

            st.subheader(f"Maintenance Table - 14 Items - {sel_gen}")
            df_input = pd.DataFrame(st.session_state[parts_key])
            edited_df = st.data_editor(df_input, num_rows="dynamic", width="stretch")

            if st.button("Update / Reset Checked", type="primary"):
                new_data = []
                for _, row in edited_df.iterrows():
                    item = row.to_dict()
                    if item.get("Reset"):
                        item["Used"] = 0.0
                        item["Reset"] = False
                    new_data.append(item)
                st.session_state[parts_key] = new_data
                st.success("Updated 14 items!")
                st.rerun()

            df_result = pd.DataFrame(st.session_state[parts_key])
            df_result["pct"] = (df_result["Used"] / df_result["Life"] * 100).round(1)
            colors = ["#28a745" if x < 70 else "#ffc107" if x < 90 else "#dc3545" for x in df_result["pct"]]
            col_chart1, col_chart2 = st.columns(2)
            with col_chart1:
                st.plotly_chart(go.Figure(go.Bar(x=df_result["Part"], y=df_result["pct"], marker_color=colors, text=df_result["pct"].astype(str)+"%", textposition='auto')), use_container_width=True)
            with col_chart2:
                st.plotly_chart(px.pie(names=['Elapsed', 'Remaining'], values=[float(g["run_hours"]), max(0.0, float(g["target"])-float(g["run_hours"]))], hole=0.5), use_container_width=True)

            def gen_pdf():
                pdf = ComprehensivePDF(f"REPORT {sanitize_latin_only(sel_gen)} - 14 ITEMS")
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 9)
                pdf.cell(0, 5, f"Site: {sanitize_latin_only(selected_main_site)} - {sanitize_latin_only(selected_sub_site)}", ln=True)
                pdf.cell(0, 5, f"Gen: {sanitize_latin_only(sel_gen)} Model: {sanitize_latin_only(g['model'])} Hours: {g['run_hours']}/{g['target']}", ln=True)
                pdf.ln(4)
                headers = ["#", "Part", "Life", "Used", "Rem", "Status"]
                widths = [8, 70, 20, 20, 20, 52]
                pdf.set_font("Helvetica", "B", 7)
                pdf.set_fill_color(24, 43, 73)
                pdf.set_text_color(255, 255, 255)
                for h, w in zip(headers, widths):
                    pdf.cell(w, 5, h, border=1, fill=True, align="C")
                pdf.ln()
                pdf.set_font("Helvetica", "", 6)
                pdf.set_text_color(0, 0, 0)
                for i, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
                    fill = i % 2 == 0
                    pdf.set_fill_color(240, 243, 246) if fill else pdf.set_fill_color(255, 255, 255)
                    life = row.get("Life", 250)
                    used = row.get("Used", 0)
                    pct = (used/life*100) if life else 0
                    status = "OK" if pct < 70 else "Due Soon" if pct < 90 else "OVERDUE"
                    pdf.cell(widths[0], 4, str(i+1), border=1, align="C", fill=fill)
                    pdf.cell(widths[1], 4, sanitize_latin_only(str(row.get("Part"))), border=1, fill=fill)
                    pdf.cell(widths[2], 4, str(life), border=1, align="C", fill=fill)
                    pdf.cell(widths[3], 4, str(used), border=1, align="C", fill=fill)
                    pdf.cell(widths[4], 4, str(max(0, life-used)), border=1, align="C", fill=fill)
                    pdf.cell(widths[5], 4, status, border=1, fill=fill)
                    pdf.ln()
                out = pdf.output(dest="S")
                return out.encode("latin-1") if isinstance(out, str) else bytes(out)

            st.download_button(f"Download PDF 14 Items {sel_gen}", data=gen_pdf(), file_name=f"Report_{sel_gen}_14items.pdf", mime="application/pdf", use_container_width=True)

    elif "4." in selected_app:
        st.title("AI Diagnostics")
        fault = st.text_input("Fault Code:", value="Over Current")
        if st.button("Analyze"):
            st.markdown(analyze_fault_with_gemini(fault, language=L))

    elif "6." in selected_app:
        st.title("Calculator")
        i_amp = st.number_input("Current A:", value=250.0)
        dist_m = st.number_input("Length m:", value=120.0)
        c_size = st.selectbox("Cable mm2:", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4)
        v_drop, v_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size)
        st.metric("Voltage Drop", f"{v_drop} V", f"{v_pct}%")
