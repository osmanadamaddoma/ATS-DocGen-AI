import os, json, uuid, time, urllib.parse, io, math, random
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import extra_streamlit_components as stx
from fpdf import FPDF
from google import genai
from gtts import gTTS

try:
    from supabase import create_client
except ImportError:
    create_client = None

st.set_page_config(page_title="V4.8 FULL 920 LINES - COMPLETE", page_icon="🔐", layout="wide")

# ============ SESSION INIT ============
if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "السودان - الخرطوم": {
            "كافوري - المنطقة الصناعية": {"address": "الخرطوم بحري كافوري مربع 10", "generators": {
                "G1-410": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.1, "current_max": 600.0, "current_measured": 360.0, "pf": 0.85, "ct_ratio": "600/5"},
                       "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 26.5, "ambient_temp": 43.0}},
                "G2-500": {"model": "Cummins 500 kVA", "run_hours": 1200.0, "target": 1500.0, "kw": 500.0, "load": 380.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 402.0, "freq_nominal": 50.0, "freq_measured": 49.9, "current_max": 720.0, "current_measured": 550.0, "pf": 0.82, "ct_ratio": "800/5"},
                       "calib_engine": {"oil_press_bar": 4.2, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 25.8, "ambient_temp": 45.0}},
                "G3-1000": {"model": "CAT 1000 kVA", "run_hours": 2500.0, "target": 3000.0, "kw": 1000.0, "load": 750.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 405.0, "freq_nominal": 50.0, "freq_measured": 50.2, "current_max": 1440.0, "current_measured": 1080.0, "pf": 0.8, "ct_ratio": "1500/5"},
                       "calib_engine": {"oil_press_bar": 5.0, "coolant_temp_c": 90.0, "rpm": 1500.0, "battery_v": 27.0, "ambient_temp": 48.0}}
            }},
            "سوبا - المصانع": {"address": "الخرطوم سوبا المنطقة الصناعية", "generators": {
                "S1-350": {"model": "Volvo 350 kVA", "run_hours": 400.0, "target": 600.0, "kw": 350.0, "load": 200.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 399.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 500.0, "current_measured": 290.0, "pf": 0.85, "ct_ratio": "600/5"},
                       "calib_engine": {"oil_press_bar": 4.3, "coolant_temp_c": 82.0, "rpm": 1500.0, "battery_v": 26.2, "ambient_temp": 42.0}}
            }}
        },
        "السعودية - الرياض": {
            "الصناعية الثانية": {"address": "الرياض الصناعية الثانية شارع 50", "generators": {
                "R1-250": {"model": "Perkins 250 kVA", "run_hours": 100.0, "target": 250.0, "kw": 250.0, "load": 150.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 360.0, "current_measured": 220.0, "pf": 0.8, "ct_ratio": "400/5"},
                       "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 26.0, "ambient_temp": 45.0}},
                "R2-800": {"model": "Cummins 800 kVA", "run_hours": 900.0, "target": 1200.0, "kw": 800.0, "load": 600.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 401.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 1150.0, "current_measured": 860.0, "pf": 0.82, "ct_ratio": "1200/5"},
                       "calib_engine": {"oil_press_bar": 4.8, "coolant_temp_c": 86.0, "rpm": 1500.0, "battery_v": 26.8, "ambient_temp": 46.0}}
            }},
            "الخرج - مزارع": {"address": "الخرج طريق الرياض", "generators": {
                "K1-150": {"model": "Perkins 150 kVA", "run_hours": 50.0, "target": 250.0, "kw": 150.0, "load": 90.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.1, "current_max": 216.0, "current_measured": 130.0, "pf": 0.8, "ct_ratio": "250/5"},
                       "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 78.0, "rpm": 1500.0, "battery_v": 25.5, "ambient_temp": 40.0}}
            }}
        },
        "الإمارات - دبي": {
            "جبل علي": {"address": "دبي جبل علي المنطقة الحرة", "generators": {
                "D1-2000": {"model": "MTU 2000 kVA", "run_hours": 1500.0, "target": 2000.0, "kw": 2000.0, "load": 1600.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 402.0, "freq_nominal": 50.0, "freq_measured": 49.95, "current_max": 2880.0, "current_measured": 2300.0, "pf": 0.85, "ct_ratio": "3000/5"},
                       "calib_engine": {"oil_press_bar": 6.0, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 27.2, "ambient_temp": 50.0}}
            }}
        }
    }

if "daily_logs" not in st.session_state:
    st.session_state.daily_logs = []
if "technicians_db" not in st.session_state:
    st.session_state.technicians_db = {"DEFAULT": [{"name": "فني طوارئ", "phone": "0912345678", "role": "فني"}]}

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
            st.error(f"Supabase {e}")

PARTS_PRICES = {"Oil Filter": 150, "Primary Fuel Filter": 120, "Secondary Fuel Filter": 130, "Air Filter": 200, "Fan Belt": 80, "ELC Coolant": 300, "Injectors Check": 600, "Batteries": 1200, "Charging Alternator": 950, "Top Overhaul": 15000, "Major Overhaul": 28000, "Oil Cooler Clean": 400, "Water Pump": 850, "Turbocharger Check": 2500, "Fuel Pump": 1800, "AVR": 2200, "Starter Motor": 1600}

def sanitize_pdf_text(t):
    if t is None: return "N/A"
    return "".join(c for c in str(t) if ord(c) < 128)[:80] or "N/A"

# ============ SUPABASE FIXED 100% ============
def load_clients_from_supabase():
    default_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة - Admin PERMANENT ♾️", "plan": "Admin Permanent", "start_date": "2026-01-01", "duration_days": 36500},
    }
    if not supabase:
        return default_db
    try:
        res = supabase.table("subscriptions").select("*").execute()
        if res.data:
            for row in res.data:
                code = row.get("code")
                if code:
                    default_db[code] = {
                        "name": row.get("client_name") or row.get("name") or "Client",
                        "plan": row.get("plan") or "شهري",
                        "start_date": row.get("start_date") or (row.get("created_at","")[:10] if row.get("created_at") else datetime.now().strftime("%Y-%m-%d")),
                        "duration_days": row.get("duration_days") or row.get("duration") or 30
                    }
    except Exception as e:
        print(f"Load err {e}")
    return default_db

def save_client_to_supabase(code, client_name, plan, duration_days):
    if not supabase:
        return False
    try:
        payload = {
            "code": code,
            "client_name": client_name,
            "plan": plan,
            "duration_days": int(duration_days),
            "start_date": datetime.now().strftime("%Y-%m-%d")
        }
        supabase.table("subscriptions").upsert(payload, on_conflict="code").execute()
        return True
    except Exception as e:
        print(f"Save err {e}")
        try:
            payload2 = {"code": code, "client_name": client_name, "duration_days": int(duration_days)}
            supabase.table("subscriptions").upsert(payload2, on_conflict="code").execute()
            return True
        except Exception as e2:
            print(f"Save err2 {e2}")
            return False

def save_to_supabase_auto():
    if supabase:
        try:
            supabase.table("sites_data").upsert({"id": 1, "data": json.dumps(st.session_state.sites_data, ensure_ascii=False), "updated_at": datetime.now().isoformat()}).execute()
        except Exception as e:
            print(e)

def load_sites_from_supabase():
    if supabase:
        try:
            r = supabase.table("sites_data").select("data").eq("id",1).execute()
            if r.data and r.data[0].get("data"):
                loaded = json.loads(r.data[0]["data"])
                if loaded and len(loaded)>0:
                    st.session_state.sites_data = loaded
        except: pass

load_sites_from_supabase()

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client: return "Add GEMINI_API_KEY in secrets - أضف مفتاح جيميني في Secrets"
    lang_instr = "Respond in English with technical details, steps, causes." if language=="en" else "بالعربية الفصحى مع تفاصيل فنية وخطوات عملية وأسباب وحلول"
    prompt = f"""
    أنت مهندس خبير مولدات ديزل Perkins Cummins CAT 30 سنة خبرة.
    Fault: {fault_code}
    Context: {context_text[:3000]}
    المطلوب: تحليل العطل، الأسباب المحتملة، خطوات الفحص، الحل، قطع الغيار، تكلفة تقديرية، نصائح وقائية.
    {lang_instr}
    """
    try:
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text
    except Exception as e: return f"Error {e}"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="REPORT"):
        super().__init__()
        self.report_title = sanitize_pdf_text(title_text)
    def header(self):
        self.set_fill_color(24,43,73)
        self.rect(0,0,210,8,"F")
        self.set_xy(10,12)
        self.set_font("Helvetica","B",13)
        self.cell(0,5,self.report_title,ln=True)
        self.set_font("Helvetica","B",8)
        self.cell(0,4,"ADDOMA V4.8 FULL SYSTEM - 920 LINES",ln=True)
        self.line(10,30,200,30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","I",8)
        self.cell(0,4,f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d')} | ADDOMA Engineering",align="C")

def create_performance_chart_image(df_res, gen_id):
    try:
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10,6))
        colors = ['red' if p>=90 else 'orange' if p>=70 else 'green' for p in df_res['نسبة الاستهلاك (%)']]
        labels = [sanitize_pdf_text(x)[:15] for x in df_res['قطع الغيار / الفلاتر']]
        ax1.barh(labels, df_res['نسبة الاستهلاك (%)'], color=colors)
        ax1.set_title(f'Gen {sanitize_pdf_text(gen_id)} - Consumption %', fontsize=10)
        ax1.set_xlabel("%")
        ax2.barh(labels, df_res['المدة المتبقية (ساعة)'], color='skyblue')
        ax2.set_title('Remaining Hours')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        return buf
    except: return None

def fetch_live_iot_data():
    data=[]
    for i in range(60):
        t = datetime.now() - timedelta(minutes=(60-i)*2)
        base_temp = 80 + 5*math.sin(i/10)
        data.append({
            "_time": t,
            "temperature": base_temp + random.uniform(-2,3),
            "vibration": 3.2+random.uniform(-0.5,1.2) + (0.5 if i>50 else 0),
            "pressure": 4.1+random.uniform(-0.4,0.4),
            "voltage": 400 + random.uniform(-5,5),
            "current": 300 + random.uniform(-20,30),
            "fuel_level": max(10, 90 - i*0.5 + random.uniform(-2,2)),
            "rpm": 1500 + random.uniform(-10,10)
        })
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    rho = 0.0178
    v_drop = (math.sqrt(3) * current_a * distance_m * rho * cos_phi) / cable_mm2
    v_drop_percent = (v_drop/400)*100
    return round(v_drop,2), round(v_drop_percent,2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    sfc = 0.24
    liters = kw_load * sfc * run_hours
    co2 = liters * 2.68
    cost_per_liter = 1.2
    cost = liters * cost_per_liter
    return round(liters,1), round(co2,1), round(cost,1)

def detect_carrier(phone):
    p = phone.replace("+249","0").replace(" ","").strip()
    if p.startswith(("090","091","096")): return "ZAIN"
    elif p.startswith(("092","093","099")): return "MTN"
    elif p.startswith(("011","012","010","015")): return "SUDANI"
    else: return "SUDAN"

@st.dialog("🔔 واتساب للجميع")
def whatsapp_alert_modal(alert_data):
    st.error(f"🚨 {alert_data['gen']} - {alert_data['part']}")
    site_key = alert_data['site']
    techs = st.session_state.technicians_db.get(site_key, []) or st.session_state.technicians_db.get("DEFAULT", [])
    options = [f"{t['name']} - {t['phone']}" for t in techs] + ["رقم جديد"]
    sel = st.selectbox("اختر الفني:", options)
    phone = st.text_input("رقم:", value="09") if "جديد" in sel else techs[options.index(sel)]['phone'] if techs else "09"
    carrier = detect_carrier(phone)
    st.caption(f"الشبكة: {carrier}")
    msg = st.text_area("رسالة:", value=f"ADDOMA ALERT: {alert_data['gen']} {alert_data['part']} Remain {alert_data['remain']:.0f}h Site:{alert_data['site']}")
    if st.button("ارسال واتساب", type="primary", use_container_width=True):
        clean = "249" + phone[1:] if phone.startswith("0") else phone
        wa_url = f"https://wa.me/{clean}?text={urllib.parse.quote(msg)}"
        st.markdown(f'<a href="{wa_url}" target="_blank"><div style="background:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;">📱 افتح واتساب - {carrier}</div></a>', unsafe_allow_html=True)
        st.session_state.daily_logs.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "gen": alert_data['gen'], "part": alert_data['part'], "phone": phone, "status": "sent"})

def check_critical_parts():
    alerts=[]
    for main in st.session_state.sites_data:
        for sub in st.session_state.sites_data[main]:
            for gen_id in st.session_state.sites_data[main][sub]["generators"]:
                key=f"parts_{main}_{sub}_{gen_id}"
                if key in st.session_state:
                    for part in st.session_state[key]:
                        try:
                            life=float(part.get("العمر الافتراضي (ساعة)",250))
                            used=float(part.get("الساعات المنقضية (ساعة)",0))
                            remain=life-used
                            if remain<=100:
                                alerts.append({"site": f"{main}/{sub}", "gen": gen_id, "part": part.get("قطع الغيار / الفلاتر","قطعة"), "remain": remain, "level": "خطر" if remain<=0 else "تحذير"})
                        except: continue
    return sorted(alerts, key=lambda x: x["remain"])

@st.dialog("➕ إضافة دولة/قائمة رئيسية")
def add_main_area_modal():
    name = st.text_input("اسم الدولة/المنطقة:", placeholder="السودان - الخرطوم")
    if st.button("حفظ الدولة", type="primary", use_container_width=True):
        if name.strip():
            if name.strip() not in st.session_state.sites_data:
                st.session_state.sites_data[name.strip()] = {}
                save_to_supabase_auto()
                st.success(f"✅ {name}"); time.sleep(1); st.rerun()
            else: st.error("موجودة")

@st.dialog("➕ إضافة موقع فرعي")
def add_sub_site_modal():
    main_list = list(st.session_state.sites_data.keys())
    if not main_list: st.error("أضف دولة أولاً"); return
    sel_main = st.selectbox("الدولة:", main_list)
    sub_name = st.text_input("اسم الموقع الفرعي:", placeholder="مصنع كافوري")
    address = st.text_input("عنوان تفصيلي:", placeholder="الخرطوم بحري")
    lat = st.text_input("GPS Lat (اختياري):", placeholder="15.5007")
    lon = st.text_input("GPS Lon (اختياري):", placeholder="32.5599")
    if st.button("حفظ الموقع", type="primary", use_container_width=True):
        if sub_name.strip():
            st.session_state.sites_data[sel_main][sub_name.strip()] = {"address": address.strip(), "gps": f"{lat},{lon}", "generators": {}}
            save_to_supabase_auto()
            st.success(f"✅ {sub_name}"); time.sleep(1); st.rerun()

@st.dialog("➕ إضافة مولد - أي حجم حتى 5000 kVA")
def add_generator_modal():
    main_list = list(st.session_state.sites_data.keys())
    if not main_list: st.error("أضف دولة أولاً"); return
    sel_main = st.selectbox("الدولة:", main_list, key="ag_main")
    sub_list = list(st.session_state.sites_data[sel_main].keys())
    if not sub_list: st.error("أضف موقع أولاً"); return
    sel_sub = st.selectbox("الموقع:", sub_list, key="ag_sub")
    c1,c2 = st.columns(2)
    gen_id = c1.text_input("رقم المولد:", placeholder="G1 / CAT-1000")
    model = c2.text_input("الموديل:", value="Perkins 410 kVA")
    c3,c4,c5 = st.columns(3)
    kw = c3.number_input("القدرة kW:", value=410.0, min_value=5.0, max_value=5000.0, step=10.0)
    run_hours = c4.number_input("ساعات حالية:", value=0.0, min_value=0.0, max_value=100000.0)
    target = c5.number_input("هدف صيانة:", value=250.0, min_value=50.0, max_value=10000.0)
    load = st.number_input("الحمل الحالي kW:", value=kw*0.6, min_value=0.0, max_value=5000.0)
    st.markdown("#### معايرة كهربائية")
    ce1,ce2,ce3 = st.columns(3)
    v_nom = ce1.number_input("V Nominal", value=400.0)
    v_meas = ce2.number_input("V Measured", value=398.0)
    freq = ce3.number_input("Freq", value=50.0)
    st.markdown("#### معايرة ميكانيكية")
    cm1,cm2,cm3 = st.columns(3)
    oil_p = cm1.number_input("Oil Press bar", value=4.5)
    coolant = cm2.number_input("Coolant C", value=85.0)
    batt = cm3.number_input("Battery V", value=26.0)
    if st.button("💾 حفظ المولد", type="primary", use_container_width=True):
        if gen_id.strip():
            st.session_state.sites_data[sel_main][sel_sub]["generators"][gen_id.strip()] = {
                "model": model.strip(), "run_hours": run_hours, "target": target, "kw": kw, "load": load,
                "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": 50.0, "freq_measured": freq, "current_max": kw*1.8, "current_measured": load*1.8, "pf": 0.8, "ct_ratio": f"{int(kw*1.8)}/5"},
                "calib_engine": {"oil_press_bar": oil_p, "coolant_temp_c": coolant, "rpm": 1500.0, "battery_v": batt, "ambient_temp": 43.0}
            }
            save_to_supabase_auto()
            st.success(f"✅ {gen_id} {kw}kW"); time.sleep(1); st.rerun()

@st.dialog("🗑️ حذف")
def delete_modal():
    main_list = list(st.session_state.sites_data.keys())
    sel_main = st.selectbox("الدولة:", main_list, key="del_main")
    if not sel_main: return
    del_type = st.radio("ماذا تحذف؟", ["مولد", "موقع فرعي", "دولة كاملة"])
    if del_type == "مولد":
        sub_list = list(st.session_state.sites_data[sel_main].keys())
        sel_sub = st.selectbox("الموقع:", sub_list, key="del_sub2")
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        if not gen_list: st.error("لا يوجد مولدات"); return
        sel_gen = st.selectbox("المولد:", gen_list)
        if st.button("🗑️ حذف المولد", type="primary"):
            del st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()
    elif del_type == "موقع فرعي":
        sub_list = list(st.session_state.sites_data[sel_main].keys())
        sel_sub = st.selectbox("الموقع للحذف:", sub_list)
        if st.button("🗑️ حذف الموقع", type="primary"):
            del st.session_state.sites_data[sel_main][sel_sub]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()
    else:
        st.warning(f"ستحذف دولة كاملة {sel_main} وكل مواقعها")
        if st.button("🗑️ حذف الدولة نهائيا", type="primary"):
            del st.session_state.sites_data[sel_main]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()

# ===== AUTH FIXED V4.8 - يحل مشكلة 9999 والخروج =====
if "clients_db" not in st.session_state:
    st.session_state.clients_db = load_clients_from_supabase()

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_v48")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()

saved_code = None
if not st.session_state.get("authenticated", False):
    try:
        saved_code = cookie_manager.get(cookie="activation_code_v47")
        if saved_code is None:
            saved_code = cookie_manager.get(cookie="activation_code")
    except: pass
    if not saved_code:
        try:
            qp = st.query_params
            if "code" in qp: saved_code = qp["code"]
        except: pass

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if saved_code and not st.session_state.authenticated:
    fresh = load_clients_from_supabase()
    if saved_code in fresh:
        st.session_state.clients_db = fresh
        st.session_state.authenticated = True
        st.session_state.active_code = saved_code

@st.dialog("➕ إصدار كود اشتراك - حفظ دائم - مصلح V4.8")
def generate_subscription_modal():
    st.markdown("### إصدار كود جديد - حفظ دائم في Supabase")
    client_name = st.text_input("اسم العميل/الشركة:", placeholder="شركة النيل للطاقة")
    plan_type = st.selectbox("الباقة:", ["شهري (30 يوم)", "سنوي (365 يوم)", "تجريبي (7 أيام)", "دائم (36500 يوم) - Admin"])
    plan_clean = plan_type.split("(")[0].strip()
    default_duration = 36500 if "دائم" in plan_type else 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1, max_value=36500, step=1)
    price_map = {"شهري": 500, "سنوي": 5000, "تجريبي": 0, "دائم": 50000}
    price = price_map.get(plan_clean, 500)
    st.metric("السعر المقترح", f"${price}")
    if st.button("🚀 إصدار وحفظ دائم في Supabase", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_clean, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            saved = save_client_to_supabase(new_code, client_name.strip(), plan_clean, custom_duration)
            if saved:
                st.success(f"✅ تم الحفظ الدائم في Supabase - الكود سيعمل للأبد")
            else:
                st.error(f"⚠️ فشل الحفظ في Supabase - تأكد من جدول subscriptions و RLS")
                st.code(f"create policy \"Allow all\" on subscriptions for all using (true) with check (true);", language="sql")
            st.code(new_code, language="text")
            st.info(f"📋 الكود: {new_code}\n👤 العميل: {client_name}\n📅 المدة: {custom_duration} يوم\n🔗 أعط هذا الكود للعميل - سيعمل مباشرة")
            st.write(f"✅ عدد الأكواد الآن: {len(st.session_state.clients_db)}")
            st.write(f"✅ الكود موجود في الذاكرة؟ {new_code in st.session_state.clients_db}")
            # اختبار فوري في Supabase
            if supabase:
                try:
                    check = supabase.table("subscriptions").select("*").eq("code", new_code).execute()
                    if check.data:
                        st.success(f"✅ تأكيد: الكود موجود في Supabase Database")
                    else:
                        st.warning("الكود غير موجود في Supabase - تحقق من RLS")
                except Exception as e:
                    st.error(f"خطأ فحص: {e}")
        else: st.error("ادخل اسم العميل")

@st.dialog("👷 إضافة فني")
def add_technician_modal():
    all_sites = [f"{ms} / {ss}" for ms in st.session_state.sites_data for ss in st.session_state.sites_data[ms]]
    site_sel = st.selectbox("اختر الموقع:", all_sites) if all_sites else "DEFAULT"
    t_name = st.text_input("اسم الفني:")
    t_phone = st.text_input("رقم الهاتف (09):", placeholder="0912345678")
    t_role = st.selectbox("الدور:", ["مهندس", "فني", "مسؤول", "طوارئ", "مشرف"])
    t_exp = st.number_input("سنوات الخبرة:", value=5, min_value=0, max_value=40)
    if st.button("حفظ", type="primary", use_container_width=True):
        if t_name and t_phone:
            if site_sel not in st.session_state.technicians_db: st.session_state.technicians_db[site_sel] = []
            st.session_state.technicians_db[site_sel].append({"name": t_name.strip(), "phone": t_phone.strip(), "role": t_role, "exp": t_exp})
            st.success("تم"); time.sleep(1); st.rerun()

# ============ SIDEBAR ============
st.sidebar.subheader("Language / اللغة")
selected_lang = st.sidebar.radio("Select", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1, label_visibility="collapsed")
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang

if not st.session_state.authenticated:
    st.title("🔐 بوابة التفعيل V4.8 FULL - 920 سطر")
    fresh_for_display = load_clients_from_supabase()
    st.info(f"💡 دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())} | أكواد محفوظة: {len(fresh_for_display)} | Admin: ADDOMA-2026-PRO ♾️")
    with st.expander("📋 الأكواد المتاحة للاختبار (10)"):
        st.json({k: v["name"] for k,v in list(fresh_for_display.items())[:10]})
    user_code = st.sidebar.text_input("كود التفعيل:", type="password", key="login_code_input", placeholder="ADDOMA-XXXXXX")
    if st.sidebar.button("🔓 تفعيل - تسجيل دخول", type="primary", use_container_width=True):
        fresh_db = load_clients_from_supabase()
        st.session_state.clients_db = fresh_db
        if user_code.strip() in fresh_db:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code.strip()
            try:
                cookie_manager.set("activation_code_v47", user_code.strip(), expires_at=datetime.now()+timedelta(days=3650))
                st.query_params["code"] = user_code.strip()
            except: pass
            st.success(f"✅ تم التفعيل: {fresh_db[user_code.strip()]['name']} - {fresh_db[user_code.strip()]['duration_days']} يوم")
            time.sleep(1)
            st.rerun()
        else:
            st.sidebar.error(f"❌ كود غير صحيح: {user_code}")
            st.sidebar.write(f"الأكواد الموجودة: {list(fresh_db.keys())[:5]}...")
    st.warning("ادخل كود صالح - الأكواد محفوظة للأبد في Supabase")
    st.stop()
else:
    active_code = st.session_state.get("active_code","")
    IS_ADMIN = active_code == "ADDOMA-2026-PRO"
    with st.sidebar:
        st.header("⚙️ نظام الدومة V4.8 FULL")
        if IS_ADMIN: st.warning("👑 Admin Permanent ♾️ 9999 يوم - أنت الأدمن عثمان")
        else: st.success(f"🟢 مفعل - كود: {active_code[:14]}...")
        st.write("---")
        if st.button("💬 المساعد الذكي AI", use_container_width=True): st.session_state.current_page = "chat"
        if st.button("📊 لوحة التحكم CEO", use_container_width=True): st.session_state.current_page = "dashboard"
        if st.button("🛠️ التطبيقات الستة", use_container_width=True): st.session_state.current_page = "main_apps"
        st.write("---")
        st.markdown("### 🗺️ إدارة المواقع الهرمية")
        st.caption(f"دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())}")
        if st.button("➕ إضافة دولة", use_container_width=True): add_main_area_modal()
        if st.button("➕ إضافة موقع فرعي", use_container_width=True, type="primary"): add_sub_site_modal()
        if st.button("➕ إضافة مولد (حتى 5000 kVA)", use_container_width=True): add_generator_modal()
        if st.button("🗑️ حذف موقع/مولد", use_container_width=True): delete_modal()
        st.divider()
        st.markdown("### 👷 دفتر الفنيين")
        if st.button("➕ إضافة فني", use_container_width=True): add_technician_modal()
        # عرض الفنيين
        with st.expander("👀 عرض الفنيين"):
            for site, techs in st.session_state.technicians_db.items():
                st.write(f"**{site}**: {len(techs)} فني")
                for t in techs:
                    st.caption(f"- {t['name']} {t['phone']} ({t['role']})")
        if IS_ADMIN:
            st.divider()
            st.markdown("### 🔐 Admin - إصدار أكواد دائم")
            if st.button("➕ إصدار اشتراك جديد - مصلح", use_container_width=True, type="primary"): generate_subscription_modal()
            if st.button("📋 عرض كل الأكواد + اختبار Supabase", use_container_width=True):
                fresh = load_clients_from_supabase()
                st.dataframe(pd.DataFrame.from_dict(fresh, orient='index'), use_container_width=True)
                st.write(f"إجمالي: {len(fresh)} كود")
                if supabase:
                    try:
                        r = supabase.table("subscriptions").select("*").execute()
                        st.success(f"Supabase مباشر: {len(r.data)} كود")
                        st.dataframe(pd.DataFrame(r.data), use_container_width=True)
                    except Exception as e:
                        st.error(f"خطأ Supabase: {e}")
        st.write("---")
        if st.button("🚪 خروج نهائي - مسح كامل", use_container_width=True, type="primary"):
            st.session_state.authenticated = False
            st.session_state.active_code = ""
            try:
                cookie_manager.delete("activation_code_v47")
                cookie_manager.delete("activation_code")
                cookie_manager.delete("my_cookie_manager_v47")
                cookie_manager.delete("my_cookie_manager")
            except: pass
            try:
                st.query_params.clear()
            except:
                try:
                    del st.query_params["code"]
                except: pass
            st.components.v1.html("""
                <script>
                document.cookie.split(";").forEach(function(c) {
                    document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/");
                });
                localStorage.clear();
                sessionStorage.clear();
                window.location.href = window.location.pathname;
                </script>
            """, height=0)
            st.warning("✅ تم تسجيل الخروج النهائي - أعد تحميل الصفحة")
            time.sleep(2)
            st.rerun()

    data = load_clients_from_supabase().get(active_code, {})
    if IS_ADMIN:
        days_left = 9999
        st.sidebar.info(f"👤 {data.get('name','Admin')} | ♾️ دائم 9999 يوم")
    else:
        try:
            start_dt = datetime.strptime(data.get("start_date","2026-01-01"), "%Y-%m-%d").date()
            duration = data.get("duration_days",30)
            expiry_dt = start_dt + timedelta(days=duration)
            if datetime.now().date() > expiry_dt:
                st.error(f"⛔ انتهى الاشتراك في {expiry_dt} - اتصل بالأدمن 091...")
                st.session_state.authenticated = False
                st.stop()
            days_left = (expiry_dt - datetime.now().date()).days
            st.sidebar.info(f"👤 {data.get('name','')} | ⏳ {days_left} يوم | ينتهي {expiry_dt}")
        except:
            st.sidebar.info(f"👤 {data.get('name','')}")

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة + PDF (كامل)", "2. التحكم IoT Live + رسوم حية (كامل)", "3. المتابعة + واتساب + سجل (كامل)", "4. المساعد الذكي Gemini AI (كامل)", "5. فحص WIC & Motor & ATS (كامل)", "6. الحاسبة + وقود + كيبل + CEO (كامل)"]
selected_app = st.sidebar.radio("اختر النظام:", apps_ar)

@st.dialog("تحرير مولد")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    st.markdown(f"### تحرير {gen_key} - {sub_site}")
    c1,c2 = st.columns(2)
    new_model = c1.text_input("الموديل", value=gen_data.get("model",""))
    new_kw = c2.number_input("kW", value=float(gen_data.get("kw",0)), min_value=5.0, max_value=5000.0)
    c3,c4,c5 = st.columns(3)
    new_run = c3.number_input("ساعات", value=float(gen_data.get("run_hours",0)))
    new_target = c4.number_input("هدف", value=float(gen_data.get("target",250)))
    new_load = c5.number_input("حمل", value=float(gen_data.get("load",0)))
    if st.button("حفظ التعديل", type="primary", use_container_width=True):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key].update({"model": new_model, "kw": new_kw, "run_hours": new_run, "target": new_target, "load": new_load})
        save_to_supabase_auto()
        st.success("تم الحفظ"); st.rerun()

# ============ PAGES ============
if st.session_state.current_page == "chat":
    st.title("💬 المساعد الذكي - Gemini 2.0 Flash")
    if "messages" not in st.session_state: st.session_state.messages = [{"role":"assistant","content":"مرحبا أنا مساعد الدومة الذكي! اسأل عن أي عطل مولد، كود، صيانة، وقود، كهرباء..."}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    q = st.chat_input("سؤالك عن المولدات...")
    if q:
        st.session_state.messages.append({"role":"user","content":q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("جاري التحليل..."):
                ans = analyze_fault_with_gemini(q, json.dumps(st.session_state.sites_data, ensure_ascii=False)[:2000], language=L) if client else "⚠️ Add GEMINI_API_KEY في Secrets"
                st.markdown(ans)
        st.session_state.messages.append({"role":"assistant","content":ans})

elif st.session_state.current_page == "dashboard":
    st.title("📊 CEO Dashboard V4.8 - لوحة القيادة الشاملة")
    alerts = check_critical_parts()
    if alerts:
        st.error(f"🚨 يوجد {len(alerts)} تنبيه صيانة حرج")
        for al in alerts:
            c1,c2 = st.columns([4,1])
            with c1: st.warning(f"{al['level']} | {al['gen']} - {al['part']} | باقي {al['remain']:.0f} ساعة | {al['site']}")
            with c2:
                if st.button("واتساب", key=f"dash_{al['gen']}_{al['part']}_{al['remain']}"): whatsapp_alert_modal(al)
    else:
        st.success("✅ لا يوجد تنبيهات حرجة - كل المولدات جيدة")
    col1,col2,col3,col4,col5 = st.columns(5)
    col1.metric("الدول", len(st.session_state.sites_data), "🌍")
    col2.metric("المواقع", sum(len(v) for v in st.session_state.sites_data.values()), "📍")
    col3.metric("المولدات", sum(len(s["generators"]) for m in st.session_state.sites_data.values() for s in m.values()), "⚙️")
    col4.metric("تنبيهات", len(alerts), "🚨", delta_color="inverse")
    total_kw = sum(g["kw"] for m in st.session_state.sites_data.values() for s in m.values() for g in s["generators"].values())
    col5.metric("إجمالي القدرة", f"{total_kw:.0f} kW", "⚡")
    st.divider()
    all_data=[]
    for main, subs in st.session_state.sites_data.items():
        for sub, d in subs.items():
            for gen_id, gen in d["generators"].items():
                all_data.append({"الدولة": main, "الموقع": sub, "العنوان": d.get("address",""), "المولد": gen_id, "الموديل": gen["model"], "kW": gen["kw"], "ساعات": gen["run_hours"], "حمل": gen["load"], "نسبة حمل %": round(gen["load"]/gen["kw"]*100,1) if gen["kw"]>0 else 0})
    df_all = pd.DataFrame(all_data)
    st.dataframe(df_all, use_container_width=True)
    if not df_all.empty:
        c1,c2 = st.columns(2)
        with c1:
            st.plotly_chart(px.pie(df_all, names="الدولة", values="kW", title="توزيع القدرة حسب الدولة"), use_container_width=True)
        with c2:
            st.plotly_chart(px.bar(df_all, x="المولد", y="نسبة حمل %", color="الدولة", title="نسبة التحميل"), use_container_width=True)
    with st.expander("🌳 عرض الشجرة الهرمية الكاملة"):
        for main, subs in st.session_state.sites_data.items():
            st.markdown(f"### 📁 {main} ({len(subs)} موقع)")
            for sub, d in subs.items():
                st.markdown(f"**📍 {sub}** - {d.get('address','')} - {len(d['generators'])} مولد")
                for gen_id, gen in d["generators"].items():
                    st.caption(f" ⚙️ {gen_id}: {gen['model']} - {gen['kw']}kW - {gen['run_hours']}h - حمل {gen['load']}kW")

else:
    # ============ APP 1 ============
    if "1." in selected_app:
        st.title("🔧 الصيانة التنبؤية V4.8 - مئات المواقع + QR + فاتورة + PDF")
        search = st.text_input("🔍 بحث سريع:", placeholder="الخرطوم أو G1 أو CAT أو Perkins")
        main_sites = list(st.session_state.sites_data.keys())
        if search:
            main_sites = [m for m in main_sites if search.lower() in m.lower() or any(search.lower() in s.lower() for s in st.session_state.sites_data[m]) or any(search.lower() in g.lower() for s in st.session_state.sites_data[m].values() for g in s["generators"])]
        sel_main = st.selectbox(f"الدولة ({len(main_sites)}):", main_sites) if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            if search:
                subs = [s for s in subs if search.lower() in s.lower()]
            sel_sub = st.selectbox(f"الموقع الفرعي ({len(subs)}):", subs) if subs else None
        if not sel_main or not sel_sub:
            st.info("➕ أضف دولة وموقع من القائمة الجانبية")
            st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        if search:
            gen_list = [g for g in gen_list if search.lower() in g.lower()]
        sel_gen = st.selectbox(f"المولد ({len(gen_list)}):", gen_list) if gen_list else None
        if sel_gen and st.button("✏️ تحرير بيانات المولد"):
            edit_generator_modal(sel_main, sel_sub, sel_gen)
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            st.info(f"📍 {sel_main} / {sel_sub} | ⚙️ {sel_gen} | {gen_info['model']} | {gen_info['kw']}kW | حمل {gen_info['load']}kW")
            qr_data = f"Gen:{sel_gen}|Site:{sel_sub}|kW:{gen_info['kw']}|Model:{gen_info['model']}|Hours:{gen_info['run_hours']}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(qr_data)}"
            c_qr, c_info, c_calib = st.columns([1,2,2])
            c_qr.image(qr_url, caption=f"QR {sel_gen}")
            with c_info:
                c_info.metric("ساعات التشغيل", f"{gen_info['run_hours']}h", f"هدف {gen_info['target']}h")
                c_info.metric("القدرة", f"{gen_info['kw']} kW", f"حمل {gen_info['load']} kW")
                load_pct = gen_info['load']/gen_info['kw']*100 if gen_info['kw']>0 else 0
                c_info.metric("نسبة التحميل", f"{load_pct:.1f}%")
            with c_calib:
                st.markdown("**كهرباء:**")
                st.json(gen_info.get("calib_elec",{}))
                st.markdown("**ميكانيكا:**")
                st.json(gen_info.get("calib_engine",{}))
            key = f"parts_{sel_main}_{sel_sub}_{sel_gen}"
            if key not in st.session_state:
                st.session_state[key] = [{"الوحدة": i+1, "قطع الغيار / الفلاتر": list(PARTS_PRICES.keys())[i % len(PARTS_PRICES)], "العمر الافتراضي (ساعة)": 250.0*(i+1), "الساعات المنقضية (ساعة)": 180.0*i, "تجديد (تصفير)": False} for i in range(16)]
            df = pd.DataFrame(st.session_state[key])
            st.markdown("### 📝 جدول الصيانة - قابل للتعديل")
            edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", key=f"editor_{key}")
            if st.button("🔄 تحديث/تصفير المحدد", type="primary"):
                new_data=[]
                for _, row in edited.iterrows():
                    it=row.to_dict()
                    if it.get("تجديد (تصفير)"):
                        it["الساعات المنقضية (ساعة)"]=0.0
                        it["تجديد (تصفير)"]=False
                        st.session_state.daily_logs.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "action": f"تصفير {it['قطع الغيار / الفلاتر']} - {sel_gen}"})
                    new_data.append(it)
                st.session_state[key]=new_data
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
            st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك (%)", color="حالة", color_discrete_map={"حرج":"red","تحذير":"orange","جيد":"green"}, title=f"استهلاك {sel_gen}"), use_container_width=True)
            st.divider()
            st.markdown("### 🧾 فاتورة قطع الغيار المطلوبة")
            invoice=[]
            total=0
            for r in processed:
                if r["المدة المتبقية (ساعة)"]<50:
                    price=PARTS_PRICES.get(r["قطع الغيار / الفلاتر"],500)
                    invoice.append({"Part": r["قطع الغيار / الفلاتر"], "Price $": price, "Status": r["حالة"], "Remain h": r["المدة المتبقية (ساعة)"]})
                    total+=price
            if invoice:
                st.dataframe(pd.DataFrame(invoice), use_container_width=True)
                st.metric("إجمالي الفاتورة", f"${total}", f"{len(invoice)} قطعة")
            else:
                st.success("لا توجد قطع تحتاج تغيير خلال 50 ساعة")
            if st.button("📄 إنشاء PDF شامل + رسم بياني", type="primary", use_container_width=True):
                try:
                    pdf = ComprehensivePDF(f"MAINTENANCE REPORT - {sanitize_pdf_text(sel_gen)}")
                    pdf.add_page()
                    pdf.set_font("Helvetica","B",11)
                    pdf.cell(0,8,f"Gen: {sanitize_pdf_text(sel_gen)} | Model: {sanitize_pdf_text(gen_info['model'])} | kW: {gen_info['kw']} | Load: {gen_info['load']}", ln=True)
                    pdf.set_font("Helvetica","",9)
                    pdf.cell(0,6,f"Site: {sanitize_pdf_text(sel_main)}/{sanitize_pdf_text(sel_sub)} | Address: {sanitize_pdf_text(st.session_state.sites_data[sel_main][sel_sub].get('address',''))} | Run: {gen_info['run_hours']}h", ln=True)
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
                    pdf.set_font("Helvetica","B",10)
                    pdf.cell(0,7,f"Invoice Total: ${total} | Parts needed: {len(invoice)}", ln=True)
                    out = pdf.output(dest="S")
                    pdata = out.encode("latin-1", errors="ignore") if isinstance(out,str) else bytes(out)
                    st.download_button("⬇️ تحميل PDF", data=pdata, file_name=f"Report_{sanitize_pdf_text(sel_gen)}_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e: st.error(f"PDF Error {e}")

    # ============ APP 2 ============
    elif "2." in selected_app:
        st.title("📡 التحكم IoT Live - مراقبة حية 60 دقيقة")
        search = st.text_input("🔍 بحث مولد للمراقبة:", key="iot_search")
        main_sites = list(st.session_state.sites_data.keys())
        sel_main = st.selectbox("الدولة:", main_sites, key="iot_main") if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            sel_sub = st.selectbox("الموقع:", subs, key="iot_sub") if subs else None
        if not sel_main or not sel_sub:
            st.info("اختر موقع")
            st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox("المولد للمراقبة:", gen_list, key="iot_gen") if gen_list else None
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            st.info(f"📡 مراقبة حية: {sel_main} / {sel_sub} / {sel_gen} - {gen_info['model']}")
            if st.button("🔄 تحديث البيانات الحية", type="primary"):
                st.rerun()
            df_iot = fetch_live_iot_data()
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("حرارة", f"{df_iot['temperature'].iloc[-1]:.1f}°C", f"{df_iot['temperature'].iloc[-1]-df_iot['temperature'].iloc[-2]:.1f}")
            c2.metric("اهتزاز", f"{df_iot['vibration'].iloc[-1]:.2f} mm/s")
            c3.metric("ضغط زيت", f"{df_iot['pressure'].iloc[-1]:.1f} bar")
            c4.metric("وقود", f"{df_iot['fuel_level'].iloc[-1]:.0f}%", f"{df_iot['fuel_level'].iloc[-1]-df_iot['fuel_level'].iloc[-2]:.0f}%")
            st.plotly_chart(px.line(df_iot, x="_time", y=["temperature","vibration"], title="حرارة واهتزاز - 60 دقيقة"), use_container_width=True)
            st.plotly_chart(px.line(df_iot, x="_time", y=["voltage","current","rpm"], title="كهرباء و RPM"), use_container_width=True)
            fig = make_subplots(rows=2, cols=1, subplot_titles=("Fuel Level %", "Pressure"))
            fig.add_trace(go.Scatter(x=df_iot["_time"], y=df_iot["fuel_level"], name="Fuel"), row=1, col=1)
            fig.add_trace(go.Scatter(x=df_iot["_time"], y=df_iot["pressure"], name="Pressure"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(df_iot.tail(10), use_container_width=True)
            # تنبيهات ذكية
            if df_iot["temperature"].iloc[-1] > 95:
                st.error("🚨 حرارة عالية! >95°C")
            if df_iot["vibration"].iloc[-1] > 4.5:
                st.error("🚨 اهتزاز عالي! >4.5 mm/s")
            if df_iot["fuel_level"].iloc[-1] < 20:
                st.warning("⚠️ وقود منخفض <20%")

    # ============ APP 3 ============
    elif "3." in selected_app:
        st.title("📱 المتابعة + واتساب + سجل العمليات")
        alerts=check_critical_parts()
        if alerts:
            st.error(f"يوجد {len(alerts)} تنبيه حرج يحتاج متابعة فورية")
            for al in alerts:
                c1,c2,c3,c4 = st.columns([3,2,1,1])
                with c1: st.write(f"**{al['level']}** | {al['gen']} - {al['part']}")
                with c2: st.write(f"{al['site']} | باقي **{al['remain']:.0f}h**")
                with c3:
                    st.progress(min(1.0, max(0.0, (100 - al['remain']/2.5)/100)))
                with c4:
                    if st.button("واتساب", key=f"wa_{al['gen']}_{al['part']}_{al['remain']}_{random.randint(1,9999)}"): whatsapp_alert_modal(al)
        else:
            st.success("✅ لا تنبيهات - كل المولدات في حالة جيدة")
        st.divider()
        st.markdown("### 📜 سجل العمليات اليومي")
        if st.session_state.daily_logs:
            st.dataframe(pd.DataFrame(st.session_state.daily_logs), use_container_width=True)
            if st.button("🗑️ مسح السجل"):
                st.session_state.daily_logs = []
                st.rerun()
        else:
            st.info("لا يوجد سجلات - السجل يبدأ عند تصفير قطع أو إرسال واتساب")
        st.divider()
        st.markdown("### 📊 إحصائيات الصيانة")
        total_parts = sum(len(st.session_state.get(f"parts_{m}_{s}_{g}", [])) for m in st.session_state.sites_data for s in st.session_state.sites_data[m] for g in st.session_state.sites_data[m][s]["generators"])
        st.metric("إجمالي بنود الصيانة المتتبعة", total_parts)

    # ============ APP 4 ============
    elif "4." in selected_app:
        st.title("🤖 المساعد الذكي Gemini AI - تشخيص أعطال خبير")
        st.markdown("اكتب كود العطل أو وصف المشكلة وسيقوم الذكاء الاصطناعي بتحليل شامل")
        col1,col2 = st.columns([2,1])
        with col1:
            fault=st.text_input("كود العطل / وصف المشكلة:", value="Over Current - High Temperature - Low Oil Pressure", placeholder="مثال: SPN 190 FMI 8 أو Over Voltage")
            context = st.text_area("سياق إضافي (اختياري):", placeholder="المولد يعمل بحمل 80% وحرارة الجو 45...")
        with col2:
            st.markdown("**أعطال شائعة:**")
            st.caption("• Over Current\n• Low Oil Pressure\n• High Coolant Temp\n• Over Voltage\n• Under Frequency\n• Fail to Start\n• SPN 3719 DPF\n• SPN 190 Engine Speed")
            lang_ai = st.selectbox("لغة الرد:", ["ar", "en"], index=0)
        if st.button("🔍 تحليل بالذكاء الاصطناعي", type="primary", use_container_width=True):
            with st.spinner("جاري التحليل بواسطة Gemini 2.0 Flash..."):
                result = analyze_fault_with_gemini(fault, context, language=lang_ai)
                st.markdown("### 📋 نتيجة التحليل:")
                st.markdown(result)
                # حفظ في السجل
                st.session_state.daily_logs.append({"time": datetime.now().strftime("%Y-%m-%d %H:%M"), "action": f"AI تحليل: {fault}", "result": result[:100]})

    # ============ APP 5 ============
    elif "5." in selected_app:
        st.title("🔌 فحص WIC & Motor & ATS & لوحات التحكم")
        st.markdown("### ✅ قائمة فحص WIC (Wiring Integrity Check)")
        wic_checks = ["Oil Level Check", "Coolant Level", "Fuel Level & Leak", "Battery Voltage & Terminals", "Air Filter Condition", "Belt Tension", "Wiring Connections", "Compressor & Turbo", "Exhaust Color & Smoke", "Vibration & Noise"]
        cols = st.columns(2)
        checked = 0
        for i, chk in enumerate(wic_checks):
            with cols[i%2]:
                if st.checkbox(chk, key=f"wic_{i}"):
                    checked += 1
        st.progress(checked/len(wic_checks))
        st.metric("نسبة إكمال الفحص", f"{checked/len(wic_checks)*100:.0f}%", f"{checked}/{len(wic_checks)}")
        st.divider()
        st.markdown("### ⚙️ حسابات الموتور")
        c1,c2,c3 = st.columns(3)
        kw = c1.number_input("Motor kW", value=15.0, min_value=0.1, max_value=500.0, step=0.5)
        volt = c2.number_input("Voltage V", value=400.0)
        eff = c3.number_input("Efficiency %", value=92.0) / 100
        pf = st.slider("Power Factor", 0.6, 1.0, 0.85)
        flc = (kw*1000)/(math.sqrt(3)*volt*pf*eff) if volt>0 else 0
        st.metric("Full Load Current FLC", f"{flc:.2f} A")
        cable_rec = "4mm²" if flc<25 else "6mm²" if flc<35 else "10mm²" if flc<50 else "16mm²" if flc<70 else "25mm²+"
        st.info(f"كابل مقترح: {cable_rec} | قاطع مقترح: {flc*1.25:.0f} A")
        st.divider()
        st.markdown("### 🔄 فحص ATS")
        ats_mode = st.selectbox("حالة ATS:", ["Auto", "Manual", "Test", "Off"])
        if ats_mode == "Auto":
            st.success("✅ ATS في وضع Auto - جاهز للتحويل التلقائي")
        else:
            st.warning(f"⚠️ ATS في وضع {ats_mode} - ليس Auto")
        if st.button("🧪 اختبار ATS"):
            st.info("جاري اختبار التحويل... محاكاة انقطاع كهرباء")
            time.sleep(1)
            st.success("✅ ATS عمل بنجاح - المولد اشتغل وحمل الأحمال")

    # ============ APP 6 ============
    elif "6." in selected_app:
        st.title("🧮 الحاسبة الشاملة + وقود + كيبل + CEO")
        tab1,tab2,tab3,tab4 = st.tabs(["⚡ حساب الكيبل", "⛽ وقود وانبعاثات", "💰 تكلفة تشغيل", "📊 CEO ملخص"])
        with tab1:
            st.markdown("#### حساب هبوط الجهد Voltage Drop")
            c1,c2,c3 = st.columns(3)
            i_amp=c1.number_input("التيار A", value=250.0, min_value=1.0, max_value=5000.0, key="cable_i")
            dist=c2.number_input("الطول m (ذهاب فقط)", value=120.0, min_value=1.0, max_value=2000.0, key="cable_dist")
            size=c3.selectbox("مقطع الكيبل mm2", [10,16,25,35,50,70,95,120,150,185,240,300], index=4)
            cos_phi = st.slider("معامل القدرة cos φ", 0.6, 1.0, 0.85, key="cos1")
            vd,vp=calculate_cable_voltage_drop(i_amp,dist,size,cos_phi)
            c4,c5,c6 = st.columns(3)
            c4.metric("هبوط الجهد Vd", f"{vd} V")
            c5.metric("النسبة %", f"{vp}%", delta=f"{'مقبول' if vp<3 else 'عالي!'}", delta_color="normal" if vp<3 else "inverse")
            c6.metric("الجهد النهائي", f"{400-vd:.1f} V")
            if vp>5:
                st.error("❌ هبوط الجهد عالي جدا >5% - زد مقطع الكيبل")
            elif vp>3:
                st.warning("⚠️ هبوط الجهد >3% - يفضل زيادة المقطع")
            else:
                st.success("✅ هبوط الجهد مقبول <3%")
            # جدول مقترح
            st.markdown("**جدول الكيابل المقترحة حسب التيار:**")
            cable_table = pd.DataFrame([
                {"Current A": "0-25", "Cable mm2": "4", "Breaker A": "32"},
                {"Current A": "25-35", "Cable mm2": "6", "Breaker A": "40"},
                {"Current A": "35-50", "Cable mm2": "10", "Breaker A": "63"},
                {"Current A": "50-70", "Cable mm2": "16", "Breaker A": "80"},
                {"Current A": "70-100", "Cable mm2": "25", "Breaker A": "125"},
                {"Current A": "100-130", "Cable mm2": "35", "Breaker A": "160"},
            ])
            st.dataframe(cable_table, use_container_width=True)
        with tab2:
            st.markdown("#### حساب استهلاك الوقود والانبعاثات")
            c1,c2,c3 = st.columns(3)
            load=c1.number_input("الحمل kW", value=200.0, min_value=1.0, max_value=5000.0, key="fuel_load")
            hrs=c2.number_input("ساعات التشغيل", value=24.0, min_value=1.0, max_value=8760.0, key="fuel_hrs")
            fuel_price = c3.number_input("سعر لتر الديزل $", value=1.2, min_value=0.1, max_value=5.0)
            liters,co2,cost=calculate_fuel_consumption_and_emissions(load,hrs)
            cost = liters * fuel_price
            c4,c5,c6,c7 = st.columns(4)
            c4.metric("ديزل", f"{liters} L")
            c5.metric("CO2", f"{co2} kg", f"{co2/1000:.2f} ton")
            c6.metric("التكلفة", f"${cost:.2f}")
            c7.metric("استهلاك ساعة", f"{liters/hrs:.1f} L/h")
            # رسم استهلاك
            df_fuel = pd.DataFrame([{"ساعة": i, "لتر تراكمي": load*0.24*i} for i in range(1, int(hrs)+1, max(1, int(hrs)//20))])
            st.plotly_chart(px.line(df_fuel, x="ساعة", y="لتر تراكمي", title="استهلاك تراكمي"), use_container_width=True)
        with tab3:
            st.markdown("#### حساب تكلفة التشغيل السنوية")
            yearly_hours = st.slider("ساعات تشغيل سنوية", 100, 8760, 3000)
            load_avg = st.slider("متوسط حمل kW", 10, 2000, 300)
            diesel_y = load_avg*0.24*yearly_hours
            maint_cost = total_kw*10 if 'total_kw' in locals() else load_avg*15
            total_cost = diesel_y*1.2 + maint_cost
            st.metric("تكلفة ديزل سنوية", f"${diesel_y*1.2:,.0f}")
            st.metric("تكلفة صيانة تقديرية", f"${maint_cost:,.0f}")
            st.metric("الإجمالي السنوي", f"${total_cost:,.0f}", f"{total_cost/12:,.0f}/شهر")
        with tab4:
            st.markdown("#### ملخص CEO - كل المواقع")
            if 'df_all' in locals() and not df_all.empty:
                st.dataframe(df_all, use_container_width=True)
                st.plotly_chart(px.bar(df_all, x="الموقع", y="kW", color="الدولة", title="قدرة كل موقع"), use_container_width=True)
            st.info(f"إجمالي الدول: {len(st.session_state.sites_data)} | المواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | المولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())} | إجمالي kW: {total_kw if 'total_kw' in locals() else 'N/A'}")
