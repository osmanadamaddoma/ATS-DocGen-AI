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

st.set_page_config(page_title="المجمع الصناعي V4.4 - Persistent", page_icon="🔐", layout="wide")

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
    st.session_state.daily_logs = [{"timestamp": f"{today_str} 08:30:00", "date": today_str, "site": "الخرطوم - كافوري", "generator": "G1", "technician": "أحمد فني", "run_hours": 700.0, "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"}]

if "technicians_db" not in st.session_state:
    st.session_state.technicians_db = {
        "الخرطوم (القائمة الرئيسية) / الموقع الرئيسي - كافوري (موقع فرعي)": [
            {"name": "م. عثمان - مسؤول", "phone": "0912345678", "role": "مهندس"},
            {"name": "أحمد فني", "phone": "0923456789", "role": "فني"},
        ],
        "DEFAULT": [{"name": "فني طوارئ", "phone": "0912345678", "role": "فني"}]
    }

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

def sanitize_pdf_text(t):
    if t is None: return "N/A"
    t = str(t)
    return "".join(c for c in t if ord(c) < 128)[:80] or "N/A"

# ===== PERSISTENT CODES FIX =====
def load_clients_from_supabase():
    default_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة - Admin PERMANENT", "plan": "Admin Permanent", "start_date": "2026-01-01", "duration_days": 36500},
        "CLIENT-M-881": {"name": "شركة النيل", "plan": "شهري", "start_date": "2026-09-01", "duration_days": 30},
        "CLIENT-Y-992": {"name": "مصانع الحديد", "plan": "سنوي", "start_date": "2026-03-15", "duration_days": 365},
    }
    if supabase:
        try:
            res = supabase.table("subscriptions").select("*").execute()
            if res.data:
                for row in res.data:
                    code = row.get("code")
                    if code:
                        c_date = row.get("start_date") or (row.get("created_at","")[:10] if row.get("created_at") else datetime.now().strftime("%Y-%m-%d"))
                        default_db[code] = {
                            "name": row.get("client_name", "Client"),
                            "plan": row.get("plan", "شهري"),
                            "start_date": c_date,
                            "duration_days": row.get("duration_days", 30)
                        }
        except Exception as e:
            print(f"Load error {e}")
    return default_db

def save_client_to_supabase(code, client_name, plan, duration_days):
    if supabase:
        try:
            supabase.table("subscriptions").upsert({
                "code": code,
                "client_name": client_name,
                "plan": plan,
                "duration_days": duration_days,
                "start_date": datetime.now().strftime("%Y-%m-%d"),
                "created_at": datetime.now().isoformat()
            }).execute()
            return True
        except Exception as e:
            print(f"Save error {e}")
            return False
    return False

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client:
        return "Add GEMINI_API_KEY in secrets"
    lang_instr = "Respond in English." if language == "en" else "اكتب بالعربية التقنية."
    prompt = f"Expert generator engineer DSE7320/8610. Fault:{fault_code} Context:{context_text[:2000]} Provide explanation, causes, actions. {lang_instr}"
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(2)
                continue
            return f"Error: {e}"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL REPORT", logo_path=None):
        super().__init__()
        self.report_title = sanitize_pdf_text(title_text)
    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        self.set_xy(10, 12)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(24, 43, 73)
        self.cell(0, 5, self.report_title, ln=True)
        self.set_x(10)
        self.set_font("Helvetica", "B", 8)
        self.cell(0, 4, "ADDOMA TRADING - V4.4 PERSISTENT", ln=True)
        self.line(10, 30, 200, 30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 4, f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d')} | V4.4", align="C")

def create_performance_chart_image(df_res, gen_id):
    try:
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
        colors = ['red' if p>=90 else 'orange' if p>=70 else 'green' for p in df_res['نسبة الاستهلاك (%)']]
        ax1.barh([sanitize_pdf_text(x) for x in df_res['قطع الغيار / الفلاتر']], df_res['نسبة الاستهلاك (%)'], color=colors)
        ax1.set_title(f'Gen {sanitize_pdf_text(gen_id)} - Consumption %', fontsize=10)
        ax2.barh([sanitize_pdf_text(x) for x in df_res['قطع الغيار / الفلاتر']], df_res['المدة المتبقية (ساعة)'], color='skyblue')
        ax2.set_title('Remaining Hours', fontsize=10)
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        return buf
    except Exception:
        return None

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

def detect_carrier(phone):
    p = phone.replace("+249","0").replace(" ","").strip()
    if p.startswith(("090","091","096")): return "ZAIN"
    elif p.startswith(("092","093","099")): return "MTN"
    elif p.startswith(("011","012","010","015")): return "SUDANI"
    else: return "SUDAN"

@st.dialog("🔔 واتساب - للجميع")
def whatsapp_alert_modal(alert_data):
    st.error(f"{alert_data['gen']} - {alert_data['part']}")
    st.write(f"{alert_data['site']} | باقي {alert_data['remain']:.0f} ساعة | {alert_data.get('level','')}")
    site_key = alert_data['site']
    techs = st.session_state.technicians_db.get(site_key, [])
    if not techs:
        for k in st.session_state.technicians_db.keys():
            if k!= "DEFAULT" and (k in site_key or site_key in k):
                techs = st.session_state.technicians_db[k]
                break
    if not techs:
        techs = st.session_state.technicians_db.get("DEFAULT", [])
    options = [f"{t['name']} - {t['phone']} ({t['role']}) | {detect_carrier(t['phone'])}" for t in techs]
    options.append("رقم جديد غير محفوظ")
    sel = st.selectbox("اختر الفني:", options, key=f"sel_{alert_data['gen']}_{alert_data['part']}")
    if "رقم جديد" in sel:
        phone = st.text_input("رقم جديد (09):", value="09", key=f"new_phone_{alert_data['gen']}_{alert_data['part']}")
        tech_name = "فني"
    else:
        idx = options.index(sel)
        phone = techs[idx]['phone']
        tech_name = techs[idx]['name']
    st.caption(f"الشبكة: {detect_carrier(phone)} | الى: {tech_name}")
    default_msg = f"ADDOMA ALERT: Gen {alert_data['gen']} Part {alert_data['part']} Site {alert_data['site']} Remain {alert_data['remain']:.0f}h Tech {tech_name} - V4.4"
    msg = st.text_area("نص الرسالة:", value=default_msg, height=150, key=f"msg_{alert_data['gen']}_{alert_data['part']}")
    if st.button("ارسال واتساب الآن", type="primary", use_container_width=True):
        clean = phone.strip().replace(" ","")
        clean_intl = "249" + clean[1:] if clean.startswith("0") else clean.replace("+","")
        wa_url = f"https://wa.me/{clean_intl}?text={urllib.parse.quote(msg)}"
        st.success(f"جاهز للارسال الى {tech_name}")
        st.markdown(f'<a href="{wa_url}" target="_blank"><div style="background:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">افتح واتساب وارسل الآن</div></a>', unsafe_allow_html=True)

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
                            if remain <= 100:
                                level = "خطر" if remain <= 0 else "قريب" if remain <= 50 else "تنبيه"
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

# ===== LOAD PERSISTENT CODES =====
if "clients_db" not in st.session_state:
    st.session_state.clients_db = load_clients_from_supabase()
else:
    try:
        fresh = load_clients_from_supabase()
        for k,v in fresh.items():
            if k not in st.session_state.clients_db:
                st.session_state.clients_db[k] = v
    except:
        pass
CLIENTS_DATABASE = st.session_state.clients_db

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager")
    return st.session_state["cookie_manager"]
cookie_manager = get_cookie_manager()
saved_code = None
try:
    saved_code = cookie_manager.get(cookie="activation_code")
except:
    saved_code = None
if not saved_code:
    try:
        qp = st.query_params
        if "code" in qp:
            saved_code = qp["code"]
    except:
        pass

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if saved_code and not st.session_state.authenticated:
    fresh_db = load_clients_from_supabase()
    if saved_code in fresh_db:
        st.session_state.clients_db[saved_code] = fresh_db[saved_code]
        st.session_state.authenticated = True
        st.session_state.active_code = saved_code
        CLIENTS_DATABASE = st.session_state.clients_db

@st.dialog("إصدار كود اشتراك جديد - حفظ دائم")
def generate_subscription_modal():
    st.markdown("### إصدار كود - حفظ دائم في Supabase")
    client_name = st.text_input("اسم العميل:")
    plan_type = st.selectbox("الباقة:", ["شهري", "سنوي", "تجريبي"])
    default_duration = 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1)
    if st.button("إصدار وحفظ دائم", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_type, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            saved = save_client_to_supabase(new_code, client_name.strip(), plan_type, custom_duration)
            if saved:
                st.success("✅ تم الحفظ الدائم في Supabase - سيعمل حتى بعد إغلاق التطبيق")
            else:
                st.warning("⚠️ حفظ محلي فقط - أنشئ جدول subscriptions")
            st.code(new_code)
            st.info(f"الكود: {new_code} | العميل: {client_name} | {custom_duration} يوم")
        else:
            st.error("ادخل اسم العميل")

@st.dialog("إضافة فني")
def add_technician_modal():
    all_sites = []
    for ms in st.session_state.sites_data:
        for ss in st.session_state.sites_data[ms]:
            all_sites.append(f"{ms} / {ss}")
    site_sel = st.selectbox("اختر الموقع:", all_sites)
    t_name = st.text_input("اسم الفني:", placeholder="م. أحمد")
    t_phone = st.text_input("رقم الهاتف (09):", placeholder="0912345678")
    t_role = st.selectbox("الدور:", ["مهندس", "فني", "مسؤول صيانة", "طوارئ"])
    if st.button("حفظ", type="primary", use_container_width=True):
        if t_name and t_phone:
            if site_sel not in st.session_state.technicians_db:
                st.session_state.technicians_db[site_sel] = []
            st.session_state.technicians_db[site_sel].append({"name": t_name.strip(), "phone": t_phone.strip(), "role": t_role})
            st.success(f"تم حفظ {t_name}")
            time.sleep(1)
            st.rerun()
        else:
            st.error("أكمل البيانات")

st.sidebar.subheader("Language")
selected_lang = st.sidebar.radio("Select", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1, label_visibility="collapsed")
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang
TXT = {"ar": {"title": "بوابة التفعيل - V4.4", "code_input": "كود التفعيل:", "btn_activate": "تفعيل", "invalid": "كود غير صحيح", "auth": "ادخل كود صالح - الكود محفوظ للأبد", "nav_header": "نظام الدومة V4.4", "nav_status": "مفعل", "btn_chat": "المساعد الذكي", "btn_dashboard": "لوحة التحكم", "btn_apps": "التطبيقات", "btn_logout": "خروج", "choose_app": "اختر النظام:"},
       "en": {"title": "Activation V4.4", "code_input": "Code:", "btn_activate": "Activate", "invalid": "Invalid", "auth": "Enter code - Persistent", "nav_header": "Addoma V4.4", "nav_status": "Active", "btn_chat": "AI", "btn_dashboard": "Dashboard", "btn_apps": "Apps", "btn_logout": "Logout", "choose_app": "Select:"}}[L]

if not st.session_state.authenticated:
    st.title(TXT["title"])
    st.info(f"💡 الأكواد محفوظة في Supabase - عدد الأكواد: {len(CLIENTS_DATABASE)} | Admin دائم: ADDOMA-2026-PRO")
    user_code = st.sidebar.text_input(TXT["code_input"], type="password", key="activation_input")
    if st.sidebar.button(TXT["btn_activate"]):
        st.session_state.clients_db = load_clients_from_supabase()
        CLIENTS_DATABASE = st.session_state.clients_db
        if user_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            try:
                cookie_manager.set("activation_code", user_code, expires_at=datetime.now()+timedelta(days=3650))
                st.query_params["code"] = user_code
            except:
                pass
            st.success(f"✅ تم التفعيل: {CLIENTS_DATABASE[user_code]['name']}")
            time.sleep(1)
            st.rerun()
        else:
            st.sidebar.error(f"{TXT['invalid']} - {user_code}")
            fresh = load_clients_from_supabase()
            if user_code in fresh:
                st.sidebar.success("الكود موجود في Supabase!")
                st.session_state.clients_db = fresh
                st.session_state.authenticated = True
                st.session_state.active_code = user_code
                st.rerun()
            else:
                st.sidebar.write(f"الأكواد المتاحة: {list(CLIENTS_DATABASE.keys())[:5]}")
    st.warning(TXT["auth"])
    st.stop()
else:
    active_code = st.session_state.get("active_code","")
    IS_ADMIN = active_code == "ADDOMA-2026-PRO"
    with st.sidebar:
        st.header(TXT["nav_header"])
        st.success(TXT["nav_status"])
        if IS_ADMIN:
            st.warning("Admin Permanent - دائم ♾️")
        st.write("---")
        if st.button(TXT["btn_chat"], use_container_width=True):
            st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True):
            st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True):
            st.session_state.current_page = "main_apps"
        st.write("---")
        st.markdown("### دفتر الفنيين (للجميع)")
        if st.button("إضافة فني/مهندس", use_container_width=True, type="primary"):
            add_technician_modal()
        if st.button("عرض الدفتر", use_container_width=True):
            for site_k, tech_list in st.session_state.technicians_db.items():
                if site_k!= "DEFAULT":
                    with st.expander(f"{site_k[:25]} ({len(tech_list)})"):
                        for t in tech_list:
                            st.write(f"{t['name']} | {t['phone']}")
        st.divider()
        if IS_ADMIN:
            st.markdown("### Admin Panel - حفظ دائم")
            if st.button("إصدار اشتراك جديد", use_container_width=True):
                generate_subscription_modal()
            if st.button("عرض كل الأكواد", use_container_width=True):
                st.dataframe(pd.DataFrame.from_dict(st.session_state.clients_db, orient='index'), use_container_width=True)
                st.write(f"إجمالي: {len(st.session_state.clients_db)} كود")
        st.write("---")
        if st.button(TXT["btn_logout"], use_container_width=True):
            st.session_state.authenticated = False
            try:
                cookie_manager.delete("activation_code")
                if "code" in st.query_params:
                    del st.query_params["code"]
            except:
                pass
            st.rerun()
    data = CLIENTS_DATABASE.get(active_code, {})
    start_dt = datetime.strptime(data.get("start_date","2026-01-01"), "%Y-%m-%d").date()
    if IS_ADMIN:
        expiry_dt = datetime.strptime("2099-12-31", "%Y-%m-%d").date()
        days_left = 9999
        st.sidebar.info(f"👤 {data.get('name','')} | Admin دائم ♾️")
    else:
        duration = data.get("duration_days",30)
        expiry_dt = start_dt + timedelta(days=duration)
        if datetime.now().date() > expiry_dt:
            st.error(f"Expired on {expiry_dt}")
            st.session_state.authenticated = False
            st.stop()
        days_left = (expiry_dt - datetime.now().date()).days
        st.sidebar.info(f"👤 {data.get('name','')} | {days_left} يوم متبقي")

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة", "2. التحكم عن بعد IoT", "3. المتابعة اليومية + تنبيهات", "4. المساعد الذكي", "5. فحص WIC & Motor", "6. الحاسبة + CEO Dashboard"]
apps_en = ["1. Maintenance + QR + Invoice", "2. Remote IoT", "3. Daily + Alerts", "4. AI Diagnostics", "5. WIC & Motor Inspection", "6. Calculator + CEO"]
selected_app = st.sidebar.radio(TXT["choose_app"], apps_ar if L=="ar" else apps_en)

@st.dialog("Edit Generator")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec",{})
    eng = gen_data.get("calib_engine",{})
    st.markdown(f"### {gen_key}")
    tech_name = st.text_input("Technician:", value="فني")
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
    if st.button("Save", type="primary", use_container_width=True):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {"model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load, "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat}, "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}}
        st.session_state.daily_logs.append({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d"), "site": f"{main_site}-{sub_site}", "generator": gen_key, "technician": tech_name, "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "Updated"})
        save_to_supabase_auto()
        st.success("Saved!")
        st.rerun()

if st.session_state.current_page == "chat":
    st.title("AI Assistant")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحبا! اسأل عن أي عطل"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    q = st.chat_input("سؤالك...")
    if q:
        st.session_state.messages.append({"role":"user","content":q})
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            ans = analyze_fault_with_gemini(q, language=L) if client else "Add GEMINI_API_KEY"
            st.markdown(ans)
        st.session_state.messages.append({"role":"assistant","content":ans})

elif st.session_state.current_page == "dashboard":
    st.title("CEO Dashboard")
    alerts = check_critical_parts()
    if alerts:
        st.error(f"يوجد {len(alerts)} تنبيه حرج - يظهر للجميع")
        for al in alerts:
            c1,c2 = st.columns([4,1])
            with c1:
                st.warning(f"{al['level']} | {al['gen']} - {al['part']} | باقي {al['remain']:.0f}h | {al['site']}")
            with c2:
                if st.button("واتساب", key=f"dash_wa_{al['gen']}_{al['part']}"):
                    whatsapp_alert_modal(al)
    col1,col2,col3 = st.columns(3)
    total_gens = sum(len(v["generators"]) for ms in st.session_state.sites_data.values() for v in ms.values())
    col1.metric("المولدات", total_gens)
    col2.metric("تنبيهات", len(alerts))
    col3.metric("الفنيين", sum(len(v) for v in st.session_state.technicians_db.values()))
    all_data=[]
    for main_site, subs in st.session_state.sites_data.items():
        for sub_site, d in subs.items():
            for gen_id, gen in d["generators"].items():
                all_data.append({"المنطقة": main_site, "الموقع": sub_site, "المولد": gen_id, "الموديل": gen["model"], "ساعات": gen["run_hours"]})
    st.dataframe(pd.DataFrame(all_data), use_container_width=True)

else:
    if "1." in selected_app:
        st.title("الصيانة التنبؤية + QR + فاتورة + PDF")
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
        if sel_gen and st.button("Edit Calibration"):
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
            if st.button("Update / Reset", type="primary"):
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
                processed.append({**row, "المدة المتبقية (ساعة)": remain, "نسبة الاستهلاك (%)": pct, "حالة": "حرج" if pct>=90 else "تحذير" if pct>=70 else "جيد"})
            df_res=pd.DataFrame(processed)
            st.dataframe(df_res, use_container_width=True)
            st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك (%)", color="حالة"), use_container_width=True)
            st.divider()
            st.subheader("فاتورة + تقرير شامل PDF - يظهر للجميع")
            invoice=[]
            total=0
            for r in processed:
                if r["المدة المتبقية (ساعة)"]<50:
                    price=PARTS_PRICES.get(r["قطع الغيار / الفلاتر"],500)
                    invoice.append({"Part": r["قطع الغيار / الفلاتر"], "Price USD": price, "Remain hrs": r["المدة المتبقية (ساعة)"]})
                    total+=price
            c_rep1, c_rep2 = st.columns(2)
            with c_rep1:
                if invoice:
                    st.dataframe(pd.DataFrame(invoice), use_container_width=True)
                    st.metric("إجمالي الفاتورة", f"${total} USD")
                else:
                    st.success("لا فاتورة")
            with c_rep2:
                st.metric("متوسط الاستهلاك", f"{df_res['نسبة الاستهلاك (%)'].mean():.1f}%")
                st.metric("أقل متبقي", f"{df_res['المدة المتبقية (ساعة)'].min():.0f}h")
            if st.button("إنشاء تقرير شامل PDF + رسوم", type="primary", use_container_width=True):
                try:
                    pdf = ComprehensivePDF(f"MAINTENANCE REPORT - {sanitize_pdf_text(sel_gen)}")
                    pdf.add_page()
                    pdf.set_font("Helvetica","B",11)
                    pdf.cell(0,8,f"Generator: {sanitize_pdf_text(sel_gen)} | Model: {sanitize_pdf_text(gen_info['model'])} | kW: {gen_info['kw']}", ln=True)
                    pdf.set_font("Helvetica","",9)
                    pdf.cell(0,6,f"Site: {sanitize_pdf_text(sel_main)} / {sanitize_pdf_text(sel_sub)} | Run: {gen_info['run_hours']} | Target: {gen_info['target']}", ln=True)
                    pdf.cell(0,6,f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Client: {sanitize_pdf_text(data.get('name',''))} | Days: {days_left}", ln=True)
                    pdf.ln(4)
                    pdf.set_font("Helvetica","B",10)
                    pdf.set_fill_color(200,200,200)
                    pdf.cell(60,7,"Part", border=1, fill=True)
                    pdf.cell(25,7,"Life", border=1, fill=True)
                    pdf.cell(25,7,"Used", border=1, fill=True)
                    pdf.cell(25,7,"Remain", border=1, fill=True)
                    pdf.cell(30,7,"Status", border=1, fill=True)
                    pdf.ln()
                    pdf.set_font("Helvetica","",8)
                    for r in processed:
                        pdf.cell(60,6, sanitize_pdf_text(r["قطع الغيار / الفلاتر"]), border=1)
                        pdf.cell(25,6, str(r["العمر الافتراضي (ساعة)"]), border=1)
                        pdf.cell(25,6, str(r["الساعات المنقضية (ساعة)"]), border=1)
                        pdf.cell(25,6, str(r["المدة المتبقية (ساعة)"]), border=1)
                        pdf.cell(30,6, sanitize_pdf_text(r["حالة"]), border=1)
                        pdf.ln()
                    pdf.ln(5)
                    if invoice:
                        pdf.set_font("Helvetica","B",10)
                        pdf.cell(0,7,f"INVOICE TOTAL: ${total} USD - Critical: {len(invoice)}", ln=True)
                        for inv in invoice:
                            pdf.set_font("Helvetica","",8)
                            pdf.cell(0,5,f"- {sanitize_pdf_text(inv['Part'])} : ${inv['Price USD']} | Remain {inv['Remain hrs']} hrs", ln=True)
                    chart_buf = create_performance_chart_image(df_res, sel_gen)
                    if chart_buf:
                        pdf.ln(5)
                        pdf.set_font("Helvetica","B",10)
                        pdf.cell(0,7,"Performance Charts:", ln=True)
                        chart_path = f"/tmp/chart_{sanitize_pdf_text(sel_gen)}.png"
                        with open(chart_path, "wb") as f:
                            f.write(chart_buf.getvalue())
                        try:
                            pdf.image(chart_path, x=10, w=190)
                        except Exception:
                            pass
                    pdf_output = pdf.output(dest="S")
                    if isinstance(pdf_output, str):
                        pdf_data = pdf_output.encode("latin-1", errors="ignore")
                    else:
                        pdf_data = bytes(pdf_output)
                    st.download_button("تحميل التقرير PDF", data=pdf_data, file_name=f"Full_Report_{sanitize_pdf_text(sel_gen)}_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True, key="full_pdf")
                    st.success("التقرير جاهز!")
                except Exception as e:
                    st.error(f"PDF Error: {e}")

    elif "2." in selected_app:
        st.title("Remote IoT")
        df_iot = fetch_live_iot_data()
        latest=df_iot.iloc[-1]
        c1,c2,c3=st.columns(3)
        c1.metric("Temp", f"{latest['temperature']:.1f} C")
        c2.metric("Vibration", f"{latest['vibration']:.2f} mm/s")
        c3.metric("Pressure", f"{latest['pressure']:.1f} Bar")
        st.plotly_chart(px.line(df_iot, x='_time', y='temperature', title="Live"), use_container_width=True)

    elif "3." in selected_app:
        st.title("Daily + Alerts + واتساب للجميع V4.4")
        st.info("زر واتساب الآن يظهر للعملاء + Admin - مربوط بالدفتر ومحفوظ للأبد")
        alerts=check_critical_parts()
        if alerts:
            st.error(f"يوجد {len(alerts)} تنبيه حرج!")
            for al in alerts:
                c1,c2,c3 = st.columns([3,2,1])
                with c1:
                    st.write(f"{al['level']} | {al['gen']} - {al['part']}")
                with c2:
                    st.write(f"{al['site']} | باقي {al['remain']:.0f}h")
                with c3:
                    if st.button("واتساب", key=f"daily_wa_{al['gen']}_{al['part']}_{al['remain']}"):
                        whatsapp_alert_modal(al)
        else:
            st.success("لا تنبيهات")
        today=datetime.now().strftime("%Y-%m-%d")
        logs=[l for l in st.session_state.daily_logs if l.get("date")==today]
        st.dataframe(pd.DataFrame(logs), use_container_width=True)

    elif "4." in selected_app:
        st.title("AI Diagnostics")
        fault=st.text_input("Fault Code:", value="Over Current")
        if st.button("Analyze"):
            st.markdown(analyze_fault_with_gemini(fault, language=L))
    elif "5." in selected_app:
        st.title("WIC & Motor")
        st.checkbox("Oil Level")
    elif "6." in selected_app:
        st.title("Calculator")
        i_amp=st.number_input("Current A", value=250.0)
        dist=st.number_input("Length m", value=120.0)
        size=st.selectbox("mm2", [35,50,70,95,120,150], index=4)
        vd,vp=calculate_cable_voltage_drop(i_amp,dist,size)
        st.metric("Voltage Drop", f"{vd} V {vp}%")
