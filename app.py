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

try:
    from supabase import create_client
except ImportError:
    create_client = None

st.set_page_config(page_title="V4.9 FULL FIXED - 940 lines", page_icon="🔐", layout="wide")

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
        },
        "السعودية - الرياض": {
            "الصناعية الثانية": {"address": "الرياض الصناعية الثانية", "generators": {
                "R1-250": {"model": "Perkins 250 kVA", "run_hours": 100.0, "target": 250.0, "kw": 250.0, "load": 150.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 360.0, "current_measured": 220.0, "pf": 0.8, "ct_ratio": "400/5"},
                       "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 26.0, "ambient_temp": 45.0}}
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
        try: supabase = create_client(supabase_url, supabase_key)
        except Exception as e: st.error(f"Supabase {e}")

PARTS_PRICES = {"Oil Filter": 150, "Primary Fuel Filter": 120, "Secondary Fuel Filter": 130, "Air Filter": 200, "Fan Belt": 80, "ELC Coolant": 300, "Injectors Check": 600, "Batteries": 1200, "Charging Alternator": 950, "Top Overhaul": 15000, "Major Overhaul": 28000, "Oil Cooler Clean": 400, "Water Pump": 850, "Turbocharger Check": 2500, "Fuel Pump": 1800, "AVR": 2200, "Starter Motor": 1600}

def sanitize_pdf_text(t):
    if t is None: return "N/A"
    return "".join(c for c in str(t) if ord(c) < 128)[:80] or "N/A"

def load_clients_from_supabase():
    default_db = {"ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة - Admin PERMANENT", "plan": "Admin Permanent", "start_date": "2026-01-01", "duration_days": 36500}}
    if not supabase: return default_db
    try:
        res = supabase.table("subscriptions").select("*").execute()
        if res.data:
            for row in res.data:
                code = row.get("code")
                if code:
                    default_db[code] = {"name": row.get("client_name") or row.get("name") or "Client", "plan": row.get("plan") or "شهري", "start_date": row.get("start_date") or (row.get("created_at","")[:10] if row.get("created_at") else datetime.now().strftime("%Y-%m-%d")), "duration_days": row.get("duration_days") or 30}
    except Exception as e: print(f"Load err {e}")
    return default_db

def save_client_to_supabase(code, client_name, plan, duration_days):
    if not supabase: return False
    try:
        payload = {"code": code, "client_name": client_name, "plan": plan, "duration_days": int(duration_days), "start_date": datetime.now().strftime("%Y-%m-%d")}
        supabase.table("subscriptions").upsert(payload, on_conflict="code").execute()
        return True
    except Exception as e:
        try:
            payload2 = {"code": code, "client_name": client_name, "duration_days": int(duration_days)}
            supabase.table("subscriptions").upsert(payload2, on_conflict="code").execute()
            return True
        except: return False

def save_to_supabase_auto():
    if supabase:
        try: supabase.table("sites_data").upsert({"id": 1, "data": json.dumps(st.session_state.sites_data, ensure_ascii=False), "updated_at": datetime.now().isoformat()}).execute()
        except: pass

def load_sites_from_supabase():
    if supabase:
        try:
            r = supabase.table("sites_data").select("data").eq("id",1).execute()
            if r.data and r.data[0].get("data"):
                loaded = json.loads(r.data[0]["data"])
                if loaded and len(loaded)>0: st.session_state.sites_data = loaded
        except: pass

load_sites_from_supabase()

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client: return "Add GEMINI_API_KEY in secrets"
    lang_instr = "Respond in English." if language=="en" else "بالعربية"
    prompt = f"Expert generator engineer Fault:{fault_code} Context:{context_text[:2000]} {lang_instr}"
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
        self.cell(0,4,"ADDOMA V4.9 FIXED",ln=True)
        self.line(10,30,200,30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","I",8)
        self.cell(0,4,f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d')}",align="C")

def fetch_live_iot_data():
    data=[]
    for i in range(60):
        t = datetime.now() - timedelta(minutes=(60-i)*2)
        data.append({"_time": t, "temperature": 80+random.uniform(-3,6), "vibration": 3.2+random.uniform(-0.5,1.2), "pressure": 4.1+random.uniform(-0.4,0.4), "voltage": 400+random.uniform(-5,5), "current": 300+random.uniform(-20,30), "fuel_level": max(10, 90 - i*0.5), "rpm": 1500+random.uniform(-10,10)})
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    v_drop = (math.sqrt(3) * current_a * distance_m * 0.0178 * cos_phi) / cable_mm2
    return round(v_drop,2), round((v_drop/400)*100,2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    co2 = liters * 2.68
    cost = liters * 1.2
    return round(liters,1), round(co2,1), round(cost,1)

@st.dialog("🔔 واتساب للجميع")
def whatsapp_alert_modal(alert_data):
    st.error(f"{alert_data['gen']} - {alert_data['part']}")
    site_key = alert_data['site']
    techs = st.session_state.technicians_db.get(site_key, []) or st.session_state.technicians_db.get("DEFAULT", [])
    options = [f"{t['name']} - {t['phone']}" for t in techs] + ["رقم جديد"]
    sel = st.selectbox("اختر الفني:", options)
    phone = st.text_input("رقم:", value="09") if "جديد" in sel else techs[options.index(sel)]['phone'] if techs else "09"
    msg = st.text_area("رسالة:", value=f"ADDOMA ALERT: {alert_data['gen']} {alert_data['part']} Remain {alert_data['remain']:.0f}h")
    if st.button("ارسال واتساب", type="primary", use_container_width=True):
        clean = "249" + phone[1:] if phone.startswith("0") else phone
        wa_url = f"https://wa.me/{clean}?text={urllib.parse.quote(msg)}"
        st.markdown(f'<a href="{wa_url}" target="_blank"><div style="background:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;">افتح واتساب</div></a>', unsafe_allow_html=True)

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

@st.dialog("➕ إضافة دولة")
def add_main_area_modal():
    name = st.text_input("اسم الدولة:", placeholder="السودان - الخرطوم")
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
    if st.button("حفظ الموقع", type="primary", use_container_width=True):
        if sub_name.strip():
            st.session_state.sites_data[sel_main][sub_name.strip()] = {"address": address.strip(), "generators": {}}
            save_to_supabase_auto()
            st.success(f"✅ {sub_name}"); time.sleep(1); st.rerun()

@st.dialog("➕ إضافة مولد")
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
    kw = c3.number_input("القدرة kW:", value=410.0, min_value=5.0, max_value=5000.0)
    run_hours = c4.number_input("ساعات حالية:", value=0.0)
    target = c5.number_input("هدف صيانة:", value=250.0)
    load = st.number_input("الحمل الحالي kW:", value=kw*0.6)
    if st.button("💾 حفظ المولد", type="primary", use_container_width=True):
        if gen_id.strip():
            st.session_state.sites_data[sel_main][sel_sub]["generators"][gen_id.strip()] = {
                "model": model.strip(), "run_hours": run_hours, "target": target, "kw": kw, "load": load,
                "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": kw*1.8, "current_measured": load*1.8, "pf": 0.8, "ct_ratio": f"{int(kw*1.8)}/5"},
                "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 26.0, "ambient_temp": 43.0}
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
        if st.button("🗑️ حذف الدولة", type="primary"):
            del st.session_state.sites_data[sel_main]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()

if "clients_db" not in st.session_state:
    st.session_state.clients_db = load_clients_from_supabase()

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_v49")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
saved_code = None
if not st.session_state.get("authenticated", False):
    try:
        saved_code = cookie_manager.get(cookie="activation_code_v47")
        if saved_code is None: saved_code = cookie_manager.get(cookie="activation_code")
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

@st.dialog("➕ إصدار كود اشتراك - حفظ دائم")
def generate_subscription_modal():
    st.markdown("### إصدار كود جديد - حفظ دائم")
    client_name = st.text_input("اسم العميل/الشركة:", placeholder="شركة النيل")
    plan_type = st.selectbox("الباقة:", ["شهري (30 يوم)", "سنوي (365 يوم)", "تجريبي (7 أيام)", "دائم (36500 يوم)"])
    plan_clean = plan_type.split("(")[0].strip()
    default_duration = 36500 if "دائم" in plan_type else 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1, max_value=36500)
    if st.button("🚀 إصدار وحفظ دائم", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_clean, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            saved = save_client_to_supabase(new_code, client_name.strip(), plan_clean, custom_duration)
            if saved: st.success(f"✅ تم الحفظ الدائم - الكود سيعمل للأبد: {new_code}")
            else: st.error("⚠️ فشل الحفظ - تحقق من RLS")
            st.code(new_code, language="text")
            st.info(f"الكود: {new_code} العميل: {client_name} المدة: {custom_duration} يوم")

@st.dialog("👷 إضافة فني")
def add_technician_modal():
    all_sites = [f"{ms} / {ss}" for ms in st.session_state.sites_data for ss in st.session_state.sites_data[ms]]
    site_sel = st.selectbox("اختر الموقع:", all_sites) if all_sites else "DEFAULT"
    t_name = st.text_input("اسم الفني:")
    t_phone = st.text_input("رقم الهاتف (09):")
    t_role = st.selectbox("الدور:", ["مهندس", "فني", "مسؤول", "طوارئ"])
    if st.button("حفظ", type="primary", use_container_width=True):
        if t_name and t_phone:
            if site_sel not in st.session_state.technicians_db: st.session_state.technicians_db[site_sel] = []
            st.session_state.technicians_db[site_sel].append({"name": t_name.strip(), "phone": t_phone.strip(), "role": t_role})
            st.success("تم"); time.sleep(1); st.rerun()

st.sidebar.subheader("Language")
selected_lang = st.sidebar.radio("Select", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1, label_visibility="collapsed")
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang

if not st.session_state.authenticated:
    st.title("🔐 بوابة التفعيل V4.9 FIXED")
    fresh_for_display = load_clients_from_supabase()
    st.info(f"دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())} | أكواد: {len(fresh_for_display)}")
    user_code = st.sidebar.text_input("كود التفعيل:", type="password", key="login_code_input")
    if st.sidebar.button("🔓 تفعيل", type="primary"):
        fresh_db = load_clients_from_supabase()
        st.session_state.clients_db = fresh_db
        if user_code.strip() in fresh_db:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code.strip()
            try:
                cookie_manager.set("activation_code_v47", user_code.strip(), expires_at=datetime.now()+timedelta(days=3650))
                st.query_params["code"] = user_code.strip()
            except: pass
            st.success(f"✅ تم التفعيل: {fresh_db[user_code.strip()]['name']}")
            time.sleep(1); st.rerun()
        else: st.sidebar.error(f"❌ كود غير صحيح: {user_code}")
    st.stop()
else:
    active_code = st.session_state.get("active_code","")
    IS_ADMIN = active_code == "ADDOMA-2026-PRO"
    with st.sidebar:
        st.header("⚙️ نظام الدومة V4.9 FIXED")
        if IS_ADMIN: st.warning("👑 Admin Permanent ♾️")
        else: st.success(f"🟢 مفعل - {active_code[:12]}...")
        st.write("---")
        if st.button("💬 المساعد الذكي", use_container_width=True): st.session_state.current_page = "chat"
        if st.button("📊 لوحة التحكم CEO", use_container_width=True): st.session_state.current_page = "dashboard"
        if st.button("🛠️ التطبيقات", use_container_width=True): st.session_state.current_page = "main_apps"
        st.write("---")
        st.markdown("### 🗺️ إدارة المواقع")
        st.caption(f"دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())}")
        if st.button("➕ إضافة دولة", use_container_width=True): add_main_area_modal()
        if st.button("➕ إضافة موقع فرعي", use_container_width=True, type="primary"): add_sub_site_modal()
        if st.button("➕ إضافة مولد", use_container_width=True): add_generator_modal()
        if st.button("🗑️ حذف موقع/مولد", use_container_width=True): delete_modal()
        st.divider()
        if st.button("➕ إضافة فني", use_container_width=True): add_technician_modal()
        if IS_ADMIN:
            st.divider()
            if st.button("➕ إصدار اشتراك جديد", use_container_width=True, type="primary"): generate_subscription_modal()
            if st.button("📋 عرض كل الأكواد", use_container_width=True):
                fresh = load_clients_from_supabase()
                st.dataframe(pd.DataFrame.from_dict(fresh, orient='index'), use_container_width=True)
        st.write("---")
        if st.button("🚪 خروج نهائي", use_container_width=True, type="primary"):
            st.session_state.authenticated = False
            st.session_state.active_code = ""
            try: cookie_manager.delete("activation_code_v47")
            except: pass
            try: st.query_params.clear()
            except: pass
            st.rerun()

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة + PDF (كامل)", "2. التحكم IoT Live", "3. المتابعة + واتساب", "4. المساعد الذكي", "5. فحص WIC & Motor", "6. الحاسبة + وقود + CEO"]
selected_app = st.sidebar.radio("اختر النظام:", apps_ar)

@st.dialog("تحرير مولد")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    st.markdown(f"### {gen_key} - {sub_site}")
    new_model = st.text_input("الموديل", value=gen_data.get("model",""))
    new_kw = st.number_input("kW", value=float(gen_data.get("kw",0)))
    new_run = st.number_input("ساعات", value=float(gen_data.get("run_hours",0)))
    new_target = st.number_input("هدف", value=float(gen_data.get("target",250)))
    new_load = st.number_input("حمل", value=float(gen_data.get("load",0)))
    if st.button("حفظ", type="primary", use_container_width=True):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key].update({"model": new_model, "kw": new_kw, "run_hours": new_run, "target": new_target, "load": new_load})
        save_to_supabase_auto()
        st.success("تم"); st.rerun()

if st.session_state.current_page == "chat":
    st.title("المساعد الذكي")
    if "messages" not in st.session_state: st.session_state.messages = [{"role":"assistant","content":"مرحبا! اسأل عن أي عطل"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    q = st.chat_input("سؤالك...")
    if q:
        st.session_state.messages.append({"role":"user","content":q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            ans = analyze_fault_with_gemini(q, language=L) if client else "Add GEMINI_API_KEY"
            st.markdown(ans)
        st.session_state.messages.append({"role":"assistant","content":ans})

elif st.session_state.current_page == "dashboard":
    st.title("CEO Dashboard V4.9 FIXED")
    alerts = check_critical_parts()
    if alerts:
        st.error(f"🚨 {len(alerts)} تنبيه")
        for al in alerts:
            c1,c2 = st.columns([4,1])
            with c1: st.warning(f"{al['level']} | {al['gen']} - {al['part']} | باقي {al['remain']:.0f}h | {al['site']}")
            with c2:
                if st.button("واتساب", key=f"dash_{al['gen']}_{al['part']}"): whatsapp_alert_modal(al)
    col1,col2,col3,col4 = st.columns(4)
    col1.metric("الدول", len(st.session_state.sites_data))
    col2.metric("المواقع", sum(len(v) for v in st.session_state.sites_data.values()))
    col3.metric("المولدات", sum(len(s["generators"]) for m in st.session_state.sites_data.values() for s in m.values()))
    col4.metric("تنبيهات", len(alerts))
    all_data=[]
    for main, subs in st.session_state.sites_data.items():
        for sub, d in subs.items():
            for gen_id, gen in d["generators"].items():
                all_data.append({"الدولة": main, "الموقع": sub, "المولد": gen_id, "الموديل": gen["model"], "kW": gen["kw"], "ساعات": gen["run_hours"]})
    st.dataframe(pd.DataFrame(all_data), use_container_width=True)

else:
    if "1." in selected_app:
        st.title("🔧 الصيانة التنبؤية V4.9 FIXED - جدول + QR + معايرة")
        search = st.text_input("🔍 بحث سريع:", placeholder="الخرطوم أو G1", key="fix_search")
        main_sites = list(st.session_state.sites_data.keys())
        if search:
            main_sites = [m for m in main_sites if search.lower() in m.lower() or any(search.lower() in s.lower() for s in st.session_state.sites_data[m])]
        sel_main = st.selectbox(f"الدولة ({len(main_sites)}):", main_sites, key="fix_main") if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            sel_sub = st.selectbox(f"الموقع الفرعي ({len(subs)}):", subs, key="fix_sub") if subs else None
        if not sel_main or not sel_sub:
            st.info("➕ أضف دولة وموقع"); st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox(f"المولد ({len(gen_list)}):", gen_list, key="fix_gen") if gen_list else None
        if sel_gen and st.button("✏️ تحرير بيانات المولد", key="edit_btn_fix"):
            edit_generator_modal(sel_main, sel_sub, sel_gen)
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            st.success(f"📍 {sel_main} / {sel_sub} | ⚙️ {sel_gen} | {gen_info['model']} | {gen_info['kw']}kW | حمل {gen_info['load']}kW")
            # QR FIXED
            qr_data = f"{sel_gen} {sel_sub} {gen_info['kw']}kW"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={qr_data}"
            c_qr, c_info, c_calib = st.columns([1,2,2])
            with c_qr:
                st.image(qr_url, caption=f"QR {sel_gen}", width=150)
                st.caption(qr_data)
            with c_info:
                st.metric("ساعات التشغيل", f"{gen_info['run_hours']}h", f"هدف {gen_info['target']}h")
                st.metric("القدرة", f"{gen_info['kw']} kW", f"حمل {gen_info['load']} kW")
                load_pct = gen_info['load']/gen_info['kw']*100 if gen_info['kw']>0 else 0
                st.metric("نسبة التحميل", f"{load_pct:.1f}%")
                liters = gen_info['load']*0.24*24
                st.metric("ديزل يومي", f"{liters:.0f} L")
            with c_calib:
                st.markdown("### ⚡ المعايرة الكهربائية")
                elec = gen_info.get('calib_elec', {})
                eng = gen_info.get('calib_engine', {})
                v_nom = elec.get('v_nominal', 400.0); v_meas = elec.get('v_measured', 398.0)
                v_diff = abs(v_nom - v_meas); v_status = "✅" if v_diff < 10 else "⚠️" if v_diff < 20 else "🔴"
                f_nom = elec.get('freq_nominal', 50.0); f_meas = elec.get('freq_measured', 50.0)
                f_diff = abs(f_nom - f_meas); f_status = "✅" if f_diff < 0.5 else "⚠️" if f_diff < 1 else "🔴"
                st.write(f"{v_status} جهد: {v_meas}V / {v_nom}V فرق {v_diff:.1f}V")
                st.write(f"{f_status} تردد: {f_meas}Hz / {f_nom}Hz فرق {f_diff:.2f}Hz")
                st.write(f"تيار: {elec.get('current_measured',0)}A / {elec.get('current_max',0)}A PF:{elec.get('pf',0.8)} CT:{elec.get('ct_ratio','-')}")
                st.progress(min(1.0, (v_meas / v_nom) if v_nom>0 else 0), text=f"V {v_meas/v_nom*100:.1f}%" if v_nom>0 else "V")
                if st.button("✏️ تعديل كهرباء", key=f"edit_elec_{sel_gen}", use_container_width=True):
                    st.session_state[f"show_elec_edit_{sel_gen}"] = True
                if st.session_state.get(f"show_elec_edit_{sel_gen}", False):
                    with st.form(f"elec_form_{sel_gen}"):
                        c1,c2 = st.columns(2)
                        new_v_nom = c1.number_input("V Nominal", value=float(v_nom))
                        new_v_meas = c2.number_input("V Measured", value=float(v_meas))
                        c3,c4 = st.columns(2)
                        new_f_nom = c3.number_input("Freq Nom", value=float(f_nom))
                        new_f_meas = c4.number_input("Freq Meas", value=float(f_meas))
                        c5,c6,c7 = st.columns(3)
                        new_c_max = c5.number_input("Current Max", value=float(elec.get('current_max',600)))
                        new_c_meas = c6.number_input("Current Meas", value=float(elec.get('current_measured',360)))
                        new_pf = c7.number_input("PF", value=float(elec.get('pf',0.85)), min_value=0.1, max_value=1.0)
                        new_ct = st.text_input("CT Ratio", value=str(elec.get('ct_ratio','600/5')))
                        if st.form_submit_button("💾 حفظ كهرباء", type="primary"):
                            st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]["calib_elec"] = {"v_nominal": new_v_nom, "v_measured": new_v_meas, "freq_nominal": new_f_nom, "freq_measured": new_f_meas, "current_max": new_c_max, "current_measured": new_c_meas, "pf": new_pf, "ct_ratio": new_ct}
                            save_to_supabase_auto()
                            st.session_state[f"show_elec_edit_{sel_gen}"] = False
                            st.success("✅ تم حفظ كهرباء"); time.sleep(0.5); st.rerun()
                st.divider()
                st.markdown("### 🔧 المعايرة الميكانيكية")
                oil_p = eng.get('oil_press_bar', 4.5); coolant = eng.get('coolant_temp_c', 85.0); batt = eng.get('battery_v', 26.5)
                oil_status = "✅" if 3.5 <= oil_p <= 5.5 else "⚠️" if 2.5 <= oil_p <= 6 else "🔴"
                cool_status = "✅" if coolant < 90 else "⚠️" if coolant < 95 else "🔴"
                batt_status = "✅" if batt >= 24 else "⚠️" if batt >= 22 else "🔴"
                st.write(f"{oil_status} زيت: {oil_p} bar طبيعي 3.5-5.5")
                st.write(f"{cool_status} تبريد: {coolant}°C طبيعي <90")
                st.write(f"{batt_status} بطارية: {batt}V طبيعي >24")
                st.write(f"RPM: {eng.get('rpm',1500)} جو: {eng.get('ambient_temp',43)}°C")
                st.progress(min(1.0, coolant/100), text=f"Coolant {coolant}°C")
                if st.button("✏️ تعديل ميكانيكا", key=f"edit_mech_{sel_gen}", use_container_width=True):
                    st.session_state[f"show_mech_edit_{sel_gen}"] = True
                if st.session_state.get(f"show_mech_edit_{sel_gen}", False):
                    with st.form(f"mech_form_{sel_gen}"):
                        c1,c2,c3 = st.columns(3)
                        new_oil = c1.number_input("Oil bar", value=float(oil_p))
                        new_cool = c2.number_input("Coolant C", value=float(coolant))
                        new_rpm = c3.number_input("RPM", value=float(eng.get('rpm',1500)))
                        c4,c5 = st.columns(2)
                        new_batt = c4.number_input("Battery V", value=float(batt))
                        new_amb = c5.number_input("Ambient C", value=float(eng.get('ambient_temp',43)))
                        if st.form_submit_button("💾 حفظ ميكانيكا", type="primary"):
                            st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]["calib_engine"] = {"oil_press_bar": new_oil, "coolant_temp_c": new_cool, "rpm": new_rpm, "battery_v": new_batt, "ambient_temp": new_amb}
                            save_to_supabase_auto()
                            st.session_state[f"show_mech_edit_{sel_gen}"] = False
                            st.success("✅ تم حفظ ميكانيكا"); time.sleep(0.5); st.rerun()

            key = f"parts_{sel_main}_{sel_sub}_{sel_gen}"
            if key not in st.session_state or not st.session_state[key]:
                st.session_state[key] = []
                for i in range(16):
                    pname = list(PARTS_PRICES.keys())[i % len(PARTS_PRICES)]
                    st.session_state[key].append({"الوحدة": i+1, "قطع الغيار / الفلاتر": pname, "العمر الافتراضي (ساعة)": 250.0*(i+1), "الساعات المنقضية (ساعة)": 100.0*i + random.randint(0,50), "تجديد (تصفير)": False})
            st.markdown("### 📝 جدول الصيانة - FIXED")
            df_edit = pd.DataFrame(st.session_state[key])
            edited_df = st.data_editor(df_edit, use_container_width=True, num_rows="dynamic", key=f"editor_{sel_main}_{sel_sub}_{sel_gen}_fixed", column_config={"تجديد (تصفير)": st.column_config.CheckboxColumn("تصفير؟", default=False)})
            if st.button("🔄 تحديث/تصفير", type="primary", use_container_width=True, key="update_parts_btn"):
                new_data = []
                for idx, row in edited_df.iterrows():
                    it = row.to_dict()
                    if it.get("تجديد (تصفير)") == True:
                        it["الساعات المنقضية (ساعة)"] = 0.0
                        it["تجديد (تصفير)"] = False
                        st.toast(f"✅ تم تصفير {it['قطع الغيار / الفلاتر']}")
                    new_data.append(it)
                st.session_state[key] = new_data
                st.success("✅ تم التحديث"); time.sleep(0.5); st.rerun()
            processed = []
            for row in st.session_state[key]:
                try:
                    life = float(row.get("العمر الافتراضي (ساعة)", 250)); used = float(row.get("الساعات المنقضية (ساعة)", 0))
                    remain = max(0, life-used); pct = round((used/life*100) if life>0 else 0, 1)
                    status = "حرج" if pct>=90 else "تحذير" if pct>=70 else "جيد"
                    processed.append({"قطع الغيار / الفلاتر": row.get("قطع الغيار / الفلاتر",""), "العمر الافتراضي": life, "المنقضية": used, "المتبقية": remain, "نسبة الاستهلاك %": pct, "حالة": status})
                except: continue
            df_res = pd.DataFrame(processed)
            if not df_res.empty:
                st.dataframe(df_res, use_container_width=True)
                fig = px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك %", color="حالة", color_discrete_map={"حرج":"red","تحذير":"orange","جيد":"green"}, title=f"استهلاك {sel_gen}")
                st.plotly_chart(fig, use_container_width=True)
                st.divider()
                st.markdown("### 🧾 فاتورة (<50h)")
                invoice=[]; total=0
                for r in processed:
                    if r["المتبقية"] < 50:
                        price = PARTS_PRICES.get(r["قطع الغيار / الفلاتر"], 500)
                        invoice.append({"القطعة": r["قطع الغيار / الفلاتر"], "السعر $": price, "الحالة": r["حالة"], "المتبقي h": r["المتبقية"]})
                        total+=price
                if invoice:
                    st.dataframe(pd.DataFrame(invoice), use_container_width=True)
                    st.metric("إجمالي", f"${total}", f"{len(invoice)} قطعة")
                else: st.success("✅ لا قطع تحتاج تغيير خلال 50h")
                if st.button("📄 PDF", type="primary", use_container_width=True, key="pdf_btn_fix"):
                    try:
                        pdf = ComprehensivePDF(f"REPORT - {sel_gen}")
                        pdf.add_page()
                        pdf.set_font("Helvetica","B",11)
                        pdf.cell(0,8,f"Gen: {sanitize_pdf_text(sel_gen)} Model: {sanitize_pdf_text(gen_info['model'])} kW:{gen_info['kw']}", ln=True)
                        pdf.set_font("Helvetica","",9)
                        pdf.cell(0,6,f"Site: {sanitize_pdf_text(sel_main)}/{sanitize_pdf_text(sel_sub)} Run:{gen_info['run_hours']}h", ln=True)
                        pdf.ln(4)
                        pdf.set_font("Helvetica","B",9); pdf.set_fill_color(200,200,200)
                        pdf.cell(50,7,"Part", border=1, fill=True); pdf.cell(20,7,"Life", border=1, fill=True); pdf.cell(20,7,"Used", border=1, fill=True); pdf.cell(20,7,"Remain", border=1, fill=True); pdf.cell(25,7,"Status", border=1, fill=True); pdf.ln()
                        pdf.set_font("Helvetica","",8)
                        for r in processed:
                            pdf.cell(50,6, sanitize_pdf_text(r["قطع الغيار / الفلاتر"]), border=1)
                            pdf.cell(20,6, str(r["العمر الافتراضي"]), border=1)
                            pdf.cell(20,6, str(r["المنقضية"]), border=1)
                            pdf.cell(20,6, str(r["المتبقية"]), border=1)
                            pdf.cell(25,6, sanitize_pdf_text(r["حالة"]), border=1); pdf.ln()
                        out = pdf.output(dest="S")
                        pdata = out.encode("latin-1", errors="ignore") if isinstance(out,str) else bytes(out)
                        st.download_button("⬇️ تحميل PDF", data=pdata, file_name=f"Report_{sel_gen}.pdf", mime="application/pdf", use_container_width=True)
                    except Exception as e: st.error(f"PDF Error {e}")

    elif "2." in selected_app:
        st.title("📡 IoT Live")
        main_sites = list(st.session_state.sites_data.keys())
        sel_main = st.selectbox("الدولة:", main_sites, key="iot_main") if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            sel_sub = st.selectbox("الموقع:", subs, key="iot_sub") if subs else None
        if not sel_main or not sel_sub: st.info("اختر موقع"); st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox("المولد:", gen_list, key="iot_gen") if gen_list else None
        if sel_gen:
            df_iot = fetch_live_iot_data()
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("حرارة", f"{df_iot['temperature'].iloc[-1]:.1f}°C")
            c2.metric("اهتزاز", f"{df_iot['vibration'].iloc[-1]:.2f}")
            c3.metric("ضغط", f"{df_iot['pressure'].iloc[-1]:.1f} bar")
            c4.metric("وقود", f"{df_iot['fuel_level'].iloc[-1]:.0f}%")
            st.plotly_chart(px.line(df_iot, x="_time", y=["temperature","vibration"], title="حرارة واهتزاز"), use_container_width=True)
            st.dataframe(df_iot.tail(10), use_container_width=True)

    elif "3." in selected_app:
        st.title("📱 المتابعة + واتساب")
        alerts=check_critical_parts()
        if alerts:
            st.error(f"يوجد {len(alerts)} تنبيه")
            for al in alerts:
                c1,c2,c3 = st.columns([3,2,1])
                with c1: st.write(f"{al['level']} | {al['gen']} - {al['part']}")
                with c2: st.write(f"{al['site']} | باقي {al['remain']:.0f}h")
                with c3:
                    if st.button("واتساب", key=f"wa_{al['gen']}_{al['part']}_{al['remain']}_{random.randint(1,9999)}"): whatsapp_alert_modal(al)
        else: st.success("لا تنبيهات")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs) if st.session_state.daily_logs else pd.DataFrame([{"msg":"لا سجلات"}]), use_container_width=True)

    elif "4." in selected_app:
        st.title("AI Diagnostics")
        fault=st.text_input("Fault:", value="Over Current")
        if st.button("Analyze"): st.markdown(analyze_fault_with_gemini(fault, language=L))

    elif "5." in selected_app:
        st.title("WIC & Motor")
        st.checkbox("Oil Level"); st.checkbox("Compressor")
        kw = st.number_input("Motor kW", value=15.0)
        flc = (kw*1000)/(1.732*400*0.85*0.92)
        st.metric("FLC", f"{flc:.1f} A")

    elif "6." in selected_app:
        st.title("الحاسبة + وقود")
        i_amp=st.number_input("Current A", value=250.0)
        dist=st.number_input("Length m", value=120.0)
        size=st.selectbox("mm2", [35,50,70,95,120,150], index=4)
        vd,vp=calculate_cable_voltage_drop(i_amp,dist,size)
        st.metric("Voltage Drop", f"{vd} V {vp}%")
        load=st.number_input("Load kW", value=200.0)
        hrs=st.number_input("Hours", value=24.0)
        liters,co2,cost=calculate_fuel_consumption_and_emissions(load,hrs)
        st.metric("Diesel", f"{liters} L | CO2 {co2} kg | ${cost}")
