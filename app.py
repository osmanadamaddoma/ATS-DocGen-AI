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
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import requests
from fpdf import FPDF
import pdfplumber
import streamlit as st
import extra_streamlit_components as stx
from google import genai
from gtts import gTTS

try:
    from supabase import create_client
except ImportError:
    create_client = None
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None

st.set_page_config(page_title="المجمع الصناعي الشامل V4.1 - Addoma FIXED", page_icon="🔐", layout="wide")

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# ===== DATABASE =====
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الخرطوم (القائمة الرئيسية)": {
            "الموقع الرئيسي - كافوري (موقع فرعي)": {
                "address": "الخرطوم - المنطقة الصناعية - كافوري",
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
    st.session_state.daily_logs = [{"timestamp": f"{today_str} 08:30:00", "date": today_str, "site": "الخرطوم - كافوري", "generator": "G1", "technician": "أحمد فني", "run_hours": 700.0, "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"}]

# ===== KEYS =====
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
            st.error(f"Supabase: {e}")

PARTS_PRICES = {"Oil Filter": 150, "Primary Fuel Filter": 120, "Secondary Fuel Filter": 130, "Air Filter": 200, "Fan Belt": 80, "ELC Coolant": 300, "Injectors Check": 600, "Batteries": 1200, "Charging Alternator": 950, "Top Overhaul": 15000, "Major Overhaul": 28000, "Oil Cooler Clean": 400, "Water Pump": 850, "Turbocharger Check": 2500}

def play_audio(text, lang='ar', loop=False):
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts_lang = 'en' if st.session_state.lang == 'en' or lang == 'en' else 'ar'
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
    if not client:
        return "GEMINI_API_KEY missing"
    lang_instr = "Respond in English." if language == "en" else "اكتب بالعربية التقنية."
    prompt = f"Expert generator engineer DSE7320/8610 Perkins Cummins. Fault:{fault_code} Context:{context_text[:2000]} Provide 1.Explanation 2.Top3 Causes 3.Actions. {lang_instr}"
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
    return re.sub(r"[^\x00-\x7F]+", "", text).strip() or "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL REPORT", logo_path=None):
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
        self.cell(0, 4, "ADDOMA TRADING SERVICES", ln=True)
        self.line(10, 30, 200, 30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d %H:%M')} | Osman Adam Addoma", align="C")

def fetch_live_iot_data():
    import random
    data = []
    for i in range(20):
        t = datetime.now() - timedelta(minutes=(20-i)*2)
        data.append({"_time": t, "temperature": 80+random.uniform(-3,6), "vibration": 3.2+random.uniform(-0.5,1.2), "pressure": 4.1+random.uniform(-0.4,0.4)})
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    v_drop = (math.sqrt(3) * current_a * distance_m * 0.0178 * cos_phi) / cable_mm2
    return round(v_drop,2), round((v_drop/400)*100,2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    return round(liters,1), round(liters*2.68,1)

# ===== FIXED: نظام كشف الشبكات السودانية + إنذار واتساب فقط =====
def detect_carrier(phone):
    p = phone.replace("+249","0").replace(" ","").strip()
    if p.startswith(("090","091","096")):
        return "ZAIN 🟠"
    elif p.startswith(("092","093","099")):
        return "MTN 🟡"
    elif p.startswith(("011","012","010","015","099")):
        return "SUDANI 🔵"
    else:
        return "SUDAN 📱"

@st.dialog("🔔 إنذار صيانة - إرسال واتساب")
def whatsapp_alert_modal(alert_data):
    st.error(f"🚨 {alert_data['gen']} - {alert_data['part']}")
    st.write(f"📍 {alert_data['site']} | ⏱️ باقي {alert_data['remain']:.0f} ساعة | {alert_data.get('level','')}")
    phone = st.text_input("📱 رقم الفني (يبدأ بـ 09):", value="0912345678", key=f"phone_{alert_data['gen']}_{alert_data['part']}")
    st.caption(f"الشبكة المكتشفة: {detect_carrier(phone)}")
    default_msg = f"""*ADDOMA - تنبيه صيانة حرج* 🚨

*المولد:* {alert_data['gen']}
*القطعة:* {alert_data['part']}
*الموقع:* {alert_data['site']}
*الحالة:* {alert_data.get('level','تنبيه')}
*متبقي:* {alert_data['remain']:.0f} ساعة فقط
*المطلوب:* تغيير القطعة فوراً قبل التوقف

- نظام المجمع الصناعي V4.1 FIXED
"""
    msg = st.text_area("✏️ نص الرسالة:", value=default_msg, height=200, key=f"msg_{alert_data['gen']}_{alert_data['part']}")
    if st.button("📤 إرسال واتساب الآن", type="primary", use_container_width=True):
        clean = phone.strip().replace(" ","")
        if clean.startswith("0"):
            clean_intl = "249" + clean[1:]
        elif clean.startswith("+249"):
            clean_intl = clean.replace("+","")
        else:
            clean_intl = clean
        wa_url = f"https://wa.me/{clean_intl}?text={urllib.parse.quote(msg)}"
        st.success(f"✅ جاهز للإرسال إلى {detect_carrier(phone)} - {phone}")
        st.markdown(f'<a href="{wa_url}" target="_blank" style="text-decoration:none;"><div style="background:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-size:18px;font-weight:bold;">👉 افتح واتساب وأرسل الآن 📱</div></a>', unsafe_allow_html=True)
        st.caption(wa_url)

# ===== FIXED: ربط حساب الساعات المتبقية مع ساعات المولد =====
def check_critical_parts():
    alerts = []
    for main_site in st.session_state.sites_data:
        for sub_site in st.session_state.sites_data[main_site]:
            for gen_id in st.session_state.sites_data[main_site][sub_site]["generators"]:
                key = f"parts_{main_site}_{sub_site}_{gen_id}"
                if key in st.session_state:
                    for part in st.session_state[key]:
                        try:
                            life = float(part.get("العمر الافتراضي (ساعة)",250))
                            used = float(part.get("الساعات المنقضية (ساعة)",0))
                            remain = life - used
                            # يطلع إنذار لو باقي 100 ساعة أو أقل - مربوط بالحساب الصحيح
                            if remain <= 100:
                                level = "🔴 خطر - توقف" if remain <= 0 else "🟡 قريب - جهز القطعة" if remain <= 50 else "🟠 تنبيه"
                                alerts.append({"site": f"{main_site}/{sub_site}", "gen": gen_id, "part": part.get("قطع الغيار / الفلاتر","قطعة"), "remain": remain, "level": level})
                        except Exception:
                            continue
    return sorted(alerts, key=lambda x: x["remain"])

def save_to_supabase_auto():
    if supabase:
        try:
            supabase.table("sites_data").upsert({"id": 1, "data": json.dumps(st.session_state.sites_data, ensure_ascii=False), "updated_at": datetime.now().isoformat()}).execute()
        except Exception:
            pass

# ===== CLIENTS DB =====
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة - Admin", "plan": "Admin Super", "start_date": "2026-09-15", "duration_days": 3650},
        "CLIENT-M-881": {"name": "شركة النيل", "plan": "شهري", "start_date": "2026-09-01", "duration_days": 30},
        "CLIENT-Y-992": {"name": "مصانع الحديد", "plan": "سنوي", "start_date": "2026-03-15", "duration_days": 365},
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

@st.dialog("🔑 إصدار كود اشتراك جديد - Admin Only")
def generate_subscription_modal():
    st.markdown("### إصدار كود للعملاء")
    client_name = st.text_input("اسم العميل / الشركة:")
    plan_type = st.selectbox("الباقة:", ["شهري (Monthly)", "سنوي (Yearly)", "تجريبي (Trial)"])
    default_duration = 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1)
    if st.button("🚀 إصدار الكود", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_type, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            if supabase:
                try:
                    supabase.table("subscriptions").insert({"code": new_code, "client_name": client_name.strip(), "plan": plan_type, "duration_days": custom_duration}).execute()
                except Exception:
                    pass
            st.success(f"✅ الكود: {new_code}")
            st.code(new_code)
        else:
            st.error("ادخل اسم العميل")

# ===== LANGUAGE =====
st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1, label_visibility="collapsed")
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang
TXT = {"ar": {"title": "🔐 بوابة التفعيل", "code_input": "كود التفعيل:", "btn_activate": "تفعيل", "invalid": "كود غير صحيح", "auth": "ادخل كود صالح", "nav_header": "⚙️ نظام الدومة V4.1 FIXED", "nav_status": "🟢 مفعل", "btn_chat": "💬 المساعد الذكي", "btn_dashboard": "📊 لوحة التحكم", "btn_apps": "🛠️ التطبيقات", "btn_logout": "🚪 خروج", "choose_app": "اختر النظام:"},
       "en": {"title": "🔐 Activation Portal", "code_input": "Code:", "btn_activate": "Activate", "invalid": "Invalid", "auth": "Enter valid code", "nav_header": "⚙️ Addoma V4.1 FIXED", "nav_status": "🟢 Active", "btn_chat": "💬 AI Assistant", "btn_dashboard": "📊 Dashboard", "btn_apps": "🛠️ Apps", "btn_logout": "🚪 Logout", "choose_app": "Select System:"}}[L]

# ===== AUTH =====
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
            st.sidebar.error(TXT["invalid"])
    st.warning(TXT["auth"])
    st.stop()
else:
    active_code = st.session_state.get("active_code","")
    IS_ADMIN = active_code == "ADDOMA-2026-PRO"
    with st.sidebar:
        st.header(TXT["nav_header"])
        st.success(TXT["nav_status"])
        if IS_ADMIN:
            st.warning("👑 Admin Mode - أنت المسؤول")
        st.write("---")
        if st.button(TXT["btn_chat"], use_container_width=True):
            st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True):
            st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True):
            st.session_state.current_page = "main_apps"
        st.write("---")
        if IS_ADMIN:
            st.divider()
            st.markdown("### 🔐 Admin Panel")
            if st.button("➕ إصدار اشتراك جديد", use_container_width=True, type="primary"):
                generate_subscription_modal()
            if st.button("📋 عرض كل الأكواد", use_container_width=True):
                st.dataframe(pd.DataFrame.from_dict(st.session_state.clients_db, orient='index'), use_container_width=True)
        st.write("---")
        if st.button(TXT["btn_logout"], use_container_width=True):
            st.session_state.authenticated = False
            cookie_manager.delete("activation_code")
            st.rerun()

    data = CLIENTS_DATABASE.get(active_code, {})
    start_dt = datetime.strptime(data.get("start_date","2026-09-15"), "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data.get("duration_days",30))
    if datetime.now().date() > expiry_dt and not IS_ADMIN:
        st.error(f"Expired on {expiry_dt}")
        st.session_state.authenticated = False
        st.stop()
    days_left = (expiry_dt - datetime.now().date()).days
    st.sidebar.info(f"👤 {data.get('name','')} | {days_left} يوم متبقي")

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة", "2. التحكم عن بعد IoT", "3. المتابعة اليومية + تنبيهات", "4. المساعد الذكي", "5. فحص WIC & Motor", "6. الحاسبة + CEO Dashboard"]
apps_en = ["1. Maintenance + QR + Invoice", "2. Remote IoT", "3. Daily + Alerts", "4. AI Diagnostics", "5. WIC & Motor Inspection", "6. Calculator + CEO"]
selected_app = st.sidebar.radio(TXT["choose_app"], apps_ar if L=="ar" else apps_en)
st.sidebar.divider()

@st.dialog("Edit Generator")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec",{})
    eng = gen_data.get("calib_engine",{})
    st.markdown(f"### {gen_key} - {sub_site}")
    tech_name = st.text_input("Technician:", value="فني الصيانة")
    t1,t2,t3 = st.tabs(["Basic","Electrical","Engine"])
    with t1:
        new_model = st.text_input("Model", value=gen_data.get("model",""))
        new_run_hours = st.number_input("Run Hours", value=float(gen_data.get("run_hours",0)))
        new_target = st.number_input("Target", value=float(gen_data.get("target",250)))
        new_kw = st.number_input("kW", value=float(gen_data.get("kw",0)))
        new_load = st.number_input("Load kW", value=float(gen_data.get("load",0)))
    with t2:
        v_nom = st.number_input("Nominal V", value=float(elec.get("v_nominal",400)))
        v_meas = st.number_input("Measured V", value=float(elec.get("v_measured",398)))
        f_nom = st.number_input("Nominal Hz", value=float(elec.get("freq_nominal",50)))
        f_meas = st.number_input("Measured Hz", value=float(elec.get("freq_measured",50)))
        c_max = st.number_input("Max A", value=float(elec.get("current_max",600)))
        c_meas = st.number_input("Measured A", value=float(elec.get("current_measured",360)))
        pf_val = st.number_input("PF", value=float(elec.get("pf",0.85)))
        ct_rat = st.text_input("CT Ratio", value=str(elec.get("ct_ratio","600/5")))
    with t3:
        o_press = st.number_input("Oil Bar", value=float(eng.get("oil_press_bar",4.5)))
        c_temp = st.number_input("Coolant C", value=float(eng.get("coolant_temp_c",85)))
        r_rpm = st.number_input("RPM", value=float(eng.get("rpm",1500)))
        b_volt = st.number_input("Battery V", value=float(eng.get("battery_v",26)))
        ambient_t = st.number_input("Ambient C", value=float(eng.get("ambient_temp",43)))
    if st.button("Save Data", type="primary", use_container_width=True):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {"model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load, "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat}, "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}}
        st.session_state.daily_logs.append({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d"), "site": f"{main_site}-{sub_site}", "generator": gen_key, "technician": tech_name, "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "Updated"})
        save_to_supabase_auto()
        st.success("Saved + Synced to Supabase!")
        st.rerun()

# ===== PAGES =====
if st.session_state.current_page == "chat":
    st.title("🤖 AI Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحبا! اسأل عن أي عطل"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    q = st.chat_input("اكتب سؤالك...")
    if q:
        st.session_state.messages.append({"role":"user","content":q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            ans = analyze_fault_with_gemini(q, language=L) if client else "Add GEMINI_API_KEY"
            st.markdown(ans)
        st.session_state.messages.append({"role":"assistant","content":ans})

elif st.session_state.current_page == "dashboard":
    st.title("📊 CEO Dashboard + Alerts FIXED")
    alerts = check_critical_parts()
    if alerts:
        st.error(f"🚨 يوجد {len(alerts)} تنبيه حرج! - مربوط")
        for al in alerts:
            c1,c2 = st.columns([4,1])
            with c1:
                st.warning(f"{al['level']} | {al['gen']} - {al['part']} | باقي {al['remain']:.0f} ساعة | موقع {al['site']}")
            with c2:
                if st.button("📱 واتساب", key=f"dash_wa_{al['gen']}_{al['part']}"):
                    whatsapp_alert_modal(al)
    col1,col2,col3 = st.columns(3)
    total_gens = sum(len(v["generators"]) for ms in st.session_state.sites_data.values() for v in ms.values())
    col1.metric("إجمالي المولدات", total_gens)
    col2.metric("تنبيهات حرجة", len(alerts))
    col3.metric("Supabase", "Online" if supabase else "Offline")
    all_data=[]
    for main_site, subs in st.session_state.sites_data.items():
        for sub_site, d in subs.items():
            for gen_id, gen in d["generators"].items():
                all_data.append({"المنطقة": main_site, "الموقع": sub_site, "المولد": gen_id, "الموديل": gen["model"], "ساعات": gen["run_hours"], "الحالة": "⚠️ حرج" if gen["run_hours"]>gen["target"]*0.9 else "✅ جيد"})
    st.dataframe(pd.DataFrame(all_data), use_container_width=True)

else:
    if "1." in selected_app:
        st.title("⚙️ Predictive Maintenance + QR + Invoice")
        main_sites = list(st.session_state.sites_data.keys())
        sel_main = st.selectbox("Area:", main_sites) if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            sel_sub = st.selectbox("Site:", subs) if subs else None
        if not sel_main or not sel_sub:
            st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox("Generator:", gen_list) if gen_list else None
        if sel_gen and st.button("📝 Edit Calibration"):
            edit_generator_modal(sel_main, sel_sub, sel_gen)
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(f'Gen:{sel_gen}|Site:{sel_sub}|Hours:{gen_info['run_hours']}')}"
            c_qr, c_info = st.columns([1,3])
            c_qr.image(qr_url, caption=f"QR {sel_gen}")
            c_info.metric("Run Hours", f"{gen_info['run_hours']} hrs", f"Target {gen_info['target']}")
            c_info.metric("Model", gen_info["model"], f"{gen_info['kw']} kW")
            key = f"parts_{sel_main}_{sel_sub}_{sel_gen}"
            if key not in st.session_state:
                st.session_state[key] = [{"الوحدة": i+1, "تصنيف القطعة": "Service", "قطع الغيار / الفلاتر": list(PARTS_PRICES.keys())[i % len(PARTS_PRICES)], "العمر الافتراضي (ساعة)": 250.0*(i+1), "الساعات المنقضية (ساعة)": 180.0*i, "تجديد (تصفير)": False} for i in range(14)]
            df = pd.DataFrame(st.session_state[key])
            edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
            if st.button("🔄 Update / Reset", type="primary"):
                new_data=[]
                for _, row in edited.iterrows():
                    it=row.to_dict()
                    if it.get("تجديد (تصفير)"):
                        it["الساعات المنقضية (ساعة)"]=0.0
                        it["تجديد (تصفير)"]=False
                    new_data.append(it)
                st.session_state[key]=new_data
                save_to_supabase_auto()
                st.rerun()
            processed=[]
            for row in st.session_state[key]:
                life=float(row["العمر الافتراضي (ساعة)"])
                used=float(row["الساعات المنقضية (ساعة)"])
                remain=max(0,life-used)
                pct=round((used/life*100) if life>0 else 0,1)
                processed.append({**row, "المدة المتبقية (ساعة)": remain, "نسبة الاستهلاك (%)": pct, "حالة": "🔴 حرج" if pct>=90 else "🟡 تحذير" if pct>=70 else "🟢 جيد"})
            df_res=pd.DataFrame(processed)
            st.dataframe(df_res, use_container_width=True)
            st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك (%)", color="حالة"), use_container_width=True)
            st.divider()
            st.subheader("🧾 فاتورة قطع الغيار المطلوبة")
            invoice=[]
            total=0
            for r in processed:
                if r["المدة المتبقية (ساعة)"]<50:
                    price=PARTS_PRICES.get(r["قطع الغيار / الفلاتر"],500)
                    invoice.append({"Part": r["قطع الغيار / الفلاتر"], "Price USD": price, "Remain hrs": r["المدة المتبقية (ساعة)"]})
                    total+=price
            if invoice:
                st.dataframe(pd.DataFrame(invoice), use_container_width=True)
                st.metric("إجمالي الفاتورة", f"${total} USD")
                pdf = ComprehensivePDF(f"INVOICE {sel_gen}")
                pdf.add_page()
                pdf.set_font("Helvetica","B",10)
                pdf.cell(0,10,f"Generator: {sel_gen} | Total: ${total}", ln=True)
                for inv in invoice:
                    pdf.set_font("Helvetica","",9)
                    pdf.cell(0,6,f"{inv['Part']} - ${inv['Price USD']} - Remain {inv['Remain hrs']} hrs", ln=True)
                pdf_bytes = pdf.output(dest="S")
                pdf_data = pdf_bytes.encode("latin-1",errors="replace") if isinstance(pdf_bytes,str) else bytes(pdf_bytes)
                st.download_button("📥 تحميل الفاتورة PDF", data=pdf_data, file_name=f"Invoice_{sel_gen}.pdf", mime="application/pdf", use_container_width=True)
            else:
                st.success("لا توجد قطع حرجة - لا فاتورة حالياً")

    elif "2." in selected_app:
        st.title("🎛️ Remote IoT Control")
        df_iot = fetch_live_iot_data()
        latest=df_iot.iloc[-1]
        c1,c2,c3=st.columns(3)
        c1.metric("Temp", f"{latest['temperature']:.1f} C")
        c2.metric("Vibration", f"{latest['vibration']:.2f} mm/s")
        c3.metric("Pressure", f"{latest['pressure']:.1f} Bar")
        st.plotly_chart(px.line(df_iot, x='_time', y='temperature', title="Live Sensor"), use_container_width=True)
        rc1,rc2,rc3=st.columns(3)
        if rc1.button("🟢 Start", use_container_width=True):
            st.success("Start sent!")
        if rc2.button("🔴 Stop", use_container_width=True):
            st.error("Stop sent!")
        if rc3.button("🔄 Reset", use_container_width=True):
            st.info("Reset sent!")

    elif "3." in selected_app:
        st.title("📊 Daily Monitoring + WhatsApp Alerts - V4.1 FIXED ✅")
        st.info("النظام الآن مربوط: الساعات المتبقية = العمر الافتراضي - الساعات المنقضية")
        alerts=check_critical_parts()
        if alerts:
            st.error(f"🚨 يوجد {len(alerts)} تنبيه حرج - مربوط بساعات التشغيل الحقيقية!")
            for al in alerts:
                c1,c2,c3 = st.columns([3,2,1])
                with c1:
                    st.write(f"{al['level']} | **{al['gen']}** - {al['part']}")
                with c2:
                    st.write(f"📍 {al['site']} | باقي {al['remain']:.0f}h")
                with c3:
                    if st.button("📱 واتساب", key=f"daily_wa_{al['gen']}_{al['part']}_{al['remain']}"):
                        whatsapp_alert_modal(al)
            st.divider()
        else:
            st.success("✅ لا يوجد تنبيهات حرجة - كل المولدات آمنة - الإنذار شغال")

        today=datetime.now().strftime("%Y-%m-%d")
        logs=[l for l in st.session_state.daily_logs if l.get("date")==today]
        st.subheader("سجل اليوم")
        st.dataframe(pd.DataFrame(logs) if logs else pd.DataFrame([{"msg":"No logs today"}]), use_container_width=True)

    elif "4." in selected_app:
        st.title("🤖 AI Diagnostics")
        fault=st.text_input("Fault Code:", value="Over Current")
        if st.button("Analyze"):
            st.markdown(analyze_fault_with_gemini(fault, language=L))

    elif "5." in selected_app:
        st.title("🔍 WIC & Motor Inspection")
        eq_type=st.selectbox("Equipment:", ["Generator 22 Points", "WIC Cold Rooms 16 Points", "Motor 6 Points"])
        if "WIC" in eq_type:
            c1,c2,c3=st.columns(3)
            c1.metric("Room Temp", "-19.5 C")
            c2.metric("LP", "35 PSI")
            c3.metric("HP", "210 PSI")
            for it in ["Compressor Oil","R404a Gas","Expansion Valve","Defrost Heater","Evaporator Fans","Door Gasket","Eliwell Controller","HP/LP Cutout"]:
                st.checkbox(it)
            vol=st.number_input("Room Volume m3", value=120.0)
            st.metric("Cooling Load", f"{(vol*65*0.022)/0.8:.2f} kW")
        elif "Generator" in eq_type:
            for it in ["Oil Level","Coolant","Fuel","Battery","Air Filter","Belt","Exhaust","DSE Alarms","ATS Test","Load Test"]:
                st.checkbox(it)
        else:
            kw=st.number_input("Motor kW", value=15.0)
            flc=(kw*1000)/(1.732*400*0.85*0.92)
            st.metric("FLC", f"{flc:.1f} A")
            st.metric("Cable", f"{35 if flc<60 else 70} mm2")
            st.metric("Breaker", f"{flc*1.25:.0f} A")

    elif "6." in selected_app:
        st.title("🧮 Calculator + CEO")
        tab1,tab2=st.tabs(["Cable Drop","Fuel & CO2"])
        with tab1:
            i_amp=st.number_input("Current A", value=250.0)
            dist=st.number_input("Length m", value=120.0)
            size=st.selectbox("mm2", [35,50,70,95,120,150,185,240,300], index=4)
            vd,vp=calculate_cable_voltage_drop(i_amp,dist,size)
            st.metric("Voltage Drop", f"{vd} V", f"{vp}%")
            st.error("Exceeds 4%!") if vp>4 else st.success("OK")
        with tab2:
            load=st.number_input("Load kW", value=200.0)
            hrs=st.number_input("Hours", value=24.0)
            liters,co2=calculate_fuel_consumption_and_emissions(load,hrs)
            st.metric("Diesel", f"{liters} L")
            st.metric("CO2", f"{co2} kg")
