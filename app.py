import os, json, uuid, time, urllib.parse, io, math
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import extra_streamlit_components as stx
from fpdf import FPDF
from google import genai
from gtts import gTTS

try:
    from supabase import create_client
except ImportError:
    create_client = None

st.set_page_config(page_title="V4.7 FIXED AUTH - 860 lines", page_icon="🔐", layout="wide")

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
                       "calib_engine": {"oil_press_bar": 4.2, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 25.8, "ambient_temp": 45.0}}
            }}
        },
        "السعودية - الرياض": {
            "الصناعية الثانية": {"address": "الرياض الصناعية الثانية شارع 50", "generators": {
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

PARTS_PRICES = {"Oil Filter": 150, "Primary Fuel Filter": 120, "Secondary Fuel Filter": 130, "Air Filter": 200, "Fan Belt": 80, "ELC Coolant": 300, "Injectors Check": 600, "Batteries": 1200, "Charging Alternator": 950, "Top Overhaul": 15000, "Major Overhaul": 28000, "Oil Cooler Clean": 400, "Water Pump": 850, "Turbocharger Check": 2500}

def sanitize_pdf_text(t):
    if t is None: return "N/A"
    return "".join(c for c in str(t) if ord(c) < 128)[:80] or "N/A"

def load_clients_from_supabase():
    default_db = {
        "ADDOMA-2026-PRO": {"name": "عثمان آدم أدومة - Admin PERMANENT ♾️", "plan": "Admin Permanent", "start_date": "2026-01-01", "duration_days": 36500},
    }
    if supabase:
        try:
            res = supabase.table("subscriptions").select("*").execute()
            if res.data:
                for row in res.data:
                    code = row.get("code")
                    if code:
                        default_db[code] = {"name": row.get("client_name","Client"), "plan": row.get("plan","شهري"), "start_date": row.get("start_date") or (row.get("created_at","")[:10] if row.get("created_at") else datetime.now().strftime("%Y-%m-%d")), "duration_days": row.get("duration_days",30)}
        except Exception as e: print(f"Load err {e}")
    return default_db

def save_client_to_supabase(code, client_name, plan, duration_days):
    if supabase:
        try:
            supabase.table("subscriptions").upsert({"code": code, "client_name": client_name, "plan": plan, "duration_days": duration_days, "start_date": datetime.now().strftime("%Y-%m-%d"), "created_at": datetime.now().isoformat()}).execute()
            return True
        except Exception as e:
            print(f"Save err {e}")
            return False
    return False

def save_to_supabase_auto():
    if supabase:
        try: supabase.table("sites_data").upsert({"id": 1, "data": json.dumps(st.session_state.sites_data, ensure_ascii=False), "updated_at": datetime.now().isoformat()}).execute()
        except Exception as e: print(e)

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
        self.cell(0,4,"ADDOMA V4.7 FIXED AUTH",ln=True)
        self.line(10,30,200,30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","I",8)
        self.cell(0,4,f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d')}",align="C")

def create_performance_chart_image(df_res, gen_id):
    try:
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10,6))
        colors = ['red' if p>=90 else 'orange' if p>=70 else 'green' for p in df_res['نسبة الاستهلاك (%)']]
        labels = [sanitize_pdf_text(x)[:15] for x in df_res['قطع الغيار / الفلاتر']]
        ax1.barh(labels, df_res['نسبة الاستهلاك (%)'], color=colors)
        ax1.set_title(f'Gen {sanitize_pdf_text(gen_id)}', fontsize=10)
        ax2.barh(labels, df_res['المدة المتبقية (ساعة)'], color='skyblue')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        return buf
    except: return None

def fetch_live_iot_data():
    import random
    data=[]
    for i in range(30):
        t = datetime.now() - timedelta(minutes=(30-i)*2)
        data.append({"_time": t, "temperature": 80+random.uniform(-3,6), "vibration": 3.2+random.uniform(-0.5,1.2), "pressure": 4.1+random.uniform(-0.4,0.4)})
    return pd.DataFrame(data).sort_values("_time")

def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    v_drop = (math.sqrt(3) * current_a * distance_m * 0.0178 * cos_phi) / cable_mm2
    return round(v_drop,2), round((v_drop/400)*100,2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    liters = kw_load * 0.24 * run_hours
    co2 = liters * 2.68
    cost = liters * 1.2
    return round(liters,1), round(co2,1), round(cost,1)

def detect_carrier(phone):
    p = phone.replace("+249","0").replace(" ","").strip()
    if p.startswith(("090","091","096")): return "ZAIN"
    elif p.startswith(("092","093","099")): return "MTN"
    elif p.startswith(("011","012","010","015")): return "SUDANI"
    else: return "SUDAN"

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
    if st.button("حفظ الموقع", type="primary", use_container_width=True):
        if sub_name.strip():
            st.session_state.sites_data[sel_main][sub_name.strip()] = {"address": address.strip(), "generators": {}}
            save_to_supabase_auto()
            st.success(f"✅ {sub_name}"); time.sleep(1); st.rerun()

@st.dialog("➕ إضافة مولد - أي حجم")
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

# ===== AUTH FIXED V4.7 - يحل مشكلة 9999 والخروج =====
if "clients_db" not in st.session_state:
    st.session_state.clients_db = load_clients_from_supabase()

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_v47")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()

# قراءة الكوكيز فقط إذا لم يكن مسجل دخول
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

@st.dialog("➕ إصدار كود اشتراك - حفظ دائم - مصلح")
def generate_subscription_modal():
    st.markdown("### إصدار كود جديد - حفظ دائم")
    client_name = st.text_input("اسم العميل/الشركة:", placeholder="شركة النيل")
    plan_type = st.selectbox("الباقة:", ["شهري (30 يوم)", "سنوي (365 يوم)", "تجريبي (7 أيام)", "دائم (36500 يوم)"])
    plan_clean = plan_type.split("(")[0].strip()
    default_duration = 36500 if "دائم" in plan_type else 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1, max_value=36500)
    if st.button("🚀 إصدار وحفظ دائم في Supabase", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            # حفظ محلي فوري
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_clean, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            # حفظ في Supabase
            saved = save_client_to_supabase(new_code, client_name.strip(), plan_clean, custom_duration)
            if saved:
                st.success(f"✅ تم الحفظ الدائم في Supabase - الكود سيعمل للأبد")
            else:
                st.error(f"⚠️ فشل الحفظ في Supabase - تأكد من جدول subscriptions و RLS")
                st.info("نفذ هذا في Supabase SQL Editor: create policy \"Allow all\" on subscriptions for all using (true) with check (true);")
            st.code(new_code, language="text")
            st.info(f"📋 الكود: {new_code}\n👤 العميل: {client_name}\n📅 المدة: {custom_duration} يوم\n🔗 أعط هذا الكود للعميل - سيعمل مباشرة في أي متصفح")
            # اختبار فوري
            st.write(f"✅ عدد الأكواد الآن: {len(st.session_state.clients_db)}")
            st.write(f"✅ الكود موجود في الذاكرة؟ {new_code in st.session_state.clients_db}")
        else: st.error("ادخل اسم العميل")

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
    st.title("🔐 بوابة التفعيل V4.7 FIXED")
    fresh_for_display = load_clients_from_supabase()
    st.info(f"💡 دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())} | أكواد محفوظة: {len(fresh_for_display)} | Admin: ADDOMA-2026-PRO ♾️")
    st.write("الأكواد المتاحة للاختبار:")
    st.json({k: v["name"] for k,v in list(fresh_for_display.items())[:10]})
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
            st.success(f"✅ تم التفعيل: {fresh_db[user_code.strip()]['name']} - {fresh_db[user_code.strip()]['duration_days']} يوم")
            time.sleep(1)
            st.rerun()
        else:
            st.sidebar.error(f"❌ كود غير صحيح: {user_code}")
            st.sidebar.write(f"الأكواد الموجودة: {list(fresh_db.keys())}")
    st.warning("ادخل كود صالح - الأكواد محفوظة للأبد في Supabase")
    st.stop()
else:
    active_code = st.session_state.get("active_code","")
    IS_ADMIN = active_code == "ADDOMA-2026-PRO"
    with st.sidebar:
        st.header("⚙️ نظام الدومة V4.7 FIXED")
        if IS_ADMIN: st.warning("👑 Admin Permanent ♾️ 9999 يوم - أنت الأدمن")
        else: st.success(f"🟢 مفعل - كود: {active_code[:12]}...")
        st.write("---")
        if st.button("💬 المساعد الذكي", use_container_width=True): st.session_state.current_page = "chat"
        if st.button("📊 لوحة التحكم CEO", use_container_width=True): st.session_state.current_page = "dashboard"
        if st.button("🛠️ التطبيقات", use_container_width=True): st.session_state.current_page = "main_apps"
        st.write("---")
        st.markdown("### 🗺️ إدارة المواقع الهرمية")
        st.caption(f"دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())}")
        if st.button("➕ إضافة دولة", use_container_width=True): add_main_area_modal()
        if st.button("➕ إضافة موقع فرعي", use_container_width=True, type="primary"): add_sub_site_modal()
        if st.button("➕ إضافة مولد (أي حجم)", use_container_width=True): add_generator_modal()
        if st.button("🗑️ حذف موقع/مولد", use_container_width=True): delete_modal()
        st.divider()
        st.markdown("### 👷 دفتر الفنيين")
        if st.button("➕ إضافة فني", use_container_width=True): add_technician_modal()
        if IS_ADMIN:
            st.divider()
            st.markdown("### 🔐 Admin - إصدار أكواد")
            if st.button("➕ إصدار اشتراك جديد - مصلح", use_container_width=True, type="primary"): generate_subscription_modal()
            if st.button("📋 عرض كل الأكواد + اختبار", use_container_width=True):
                fresh = load_clients_from_supabase()
                st.dataframe(pd.DataFrame.from_dict(fresh, orient='index'), use_container_width=True)
                st.write(f"إجمالي: {len(fresh)} كود")
        st.write("---")
        # ===== زر خروج مصلح نهائيا - يحل مشكلة 9999 =====
        if st.button("🚪 خروج نهائي - مسح كامل", use_container_width=True, type="primary"):
            st.session_state.authenticated = False
            st.session_state.active_code = ""
            # مسح الكوكيز بكل الطرق
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
            st.warning("✅ تم تسجيل الخروج النهائي - أعد تحميل الصفحة وادخل بكود العميل الجديد")
            time.sleep(2)
            st.rerun()

    data = load_clients_from_supabase().get(active_code, {})
    if IS_ADMIN:
        days_left = 9999
        st.sidebar.info(f"👤 {data.get('name','Admin')} | ♾️ دائم")
    else:
        start_dt = datetime.strptime(data.get("start_date","2026-01-01"), "%Y-%m-%d").date()
        duration = data.get("duration_days",30)
        expiry_dt = start_dt + timedelta(days=duration)
        if datetime.now().date() > expiry_dt:
            st.error(f"⛔ انتهى الاشتراك في {expiry_dt} - اتصل بالأدمن")
            st.session_state.authenticated = False
            st.stop()
        days_left = (expiry_dt - datetime.now().date()).days
        st.sidebar.info(f"👤 {data.get('name','')} | ⏳ {days_left} يوم | ينتهي {expiry_dt}")

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة + PDF", "2. التحكم IoT Live", "3. المتابعة + واتساب", "4. المساعد الذكي", "5. فحص WIC & Motor", "6. الحاسبة + وقود + CEO"]
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
    st.title("CEO Dashboard V4.7")
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
                all_data.append({"الدولة": main, "الموقع": sub, "العنوان": d.get("address",""), "المولد": gen_id, "الموديل": gen["model"], "kW": gen["kw"], "ساعات": gen["run_hours"]})
    st.dataframe(pd.DataFrame(all_data), use_container_width=True)
    with st.expander("🌳 عرض الشجرة الهرمية"):
        for main, subs in st.session_state.sites_data.items():
            st.markdown(f"### 📁 {main} ({len(subs)} موقع)")
            for sub, d in subs.items():
                st.markdown(f"**📍 {sub}** - {d.get('address','')} - {len(d['generators'])} مولد")
                for gen_id, gen in d["generators"].items():
                    st.caption(f" ⚙️ {gen_id}: {gen['model']} - {gen['kw']}kW")

else:
    if "1." in selected_app:
        st.title("الصيانة التنبؤية V4.7 - مئات المواقع")
        search = st.text_input("🔍 بحث:", placeholder="الخرطوم أو G1 أو CAT")
        main_sites = list(st.session_state.sites_data.keys())
        if search:
            main_sites = [m for m in main_sites if search.lower() in m.lower() or any(search.lower() in s.lower() for s in st.session_state.sites_data[m])]
        sel_main = st.selectbox(f"الدولة ({len(main_sites)}):", main_sites) if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            sel_sub = st.selectbox(f"الموقع ({len(subs)}):", subs) if subs else None
        if not sel_main or not sel_sub:
            st.info("أضف دولة وموقع من الجانب")
            st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox(f"المولد ({len(gen_list)}):", gen_list) if gen_list else None
        if sel_gen and st.button("تحرير بيانات المولد"):
            edit_generator_modal(sel_main, sel_sub, sel_gen)
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            st.info(f"📍 {sel_main} / {sel_sub} | {sel_gen} | {gen_info['model']} | {gen_info['kw']}kW")
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={urllib.parse.quote(f'Gen:{sel_gen}|Site:{sel_sub}|kW:{gen_info['kw']}')}"
            c_qr, c_info = st.columns([1,3])
            c_qr.image(qr_url, caption=f"QR {sel_gen}")
            c_info.metric("ساعات", f"{gen_info['run_hours']}h", f"هدف {gen_info['target']}")
            key = f"parts_{sel_main}_{sel_sub}_{sel_gen}"
            if key not in st.session_state:
                st.session_state[key] = [{"الوحدة": i+1, "قطع الغيار / الفلاتر": list(PARTS_PRICES.keys())[i % len(PARTS_PRICES)], "العمر الافتراضي (ساعة)": 250.0*(i+1), "الساعات المنقضية (ساعة)": 180.0*i, "تجديد (تصفير)": False} for i in range(14)]
            df = pd.DataFrame(st.session_state[key])
            edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
            if st.button("تحديث/تصفير", type="primary"):
                new_data=[]
                for _, row in edited.iterrows():
                    it=row.to_dict()
                    if it.get("تجديد (تصفير)"):
                        it["الساعات المنقضية (ساعة)"]=0.0
                        it["تجديد (تصفير)"]=False
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
            st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك (%)", color="حالة"), use_container_width=True)
            st.divider()
            invoice=[]
            total=0
            for r in processed:
                if r["المدة المتبقية (ساعة)"]<50:
                    price=PARTS_PRICES.get(r["قطع الغيار / الفلاتر"],500)
                    invoice.append({"Part": r["قطع الغيار / الفلاتر"], "Price": price})
                    total+=price
            if invoice:
                st.dataframe(pd.DataFrame(invoice), use_container_width=True)
                st.metric("إجمالي", f"${total}")
            if st.button("إنشاء PDF شامل", type="primary", use_container_width=True):
                try:
                    pdf = ComprehensivePDF(f"REPORT - {sanitize_pdf_text(sel_gen)}")
                    pdf.add_page()
                    pdf.set_font("Helvetica","B",11)
                    pdf.cell(0,8,f"Gen: {sanitize_pdf_text(sel_gen)} | Model: {sanitize_pdf_text(gen_info['model'])} | kW: {gen_info['kw']}", ln=True)
                    pdf.set_font("Helvetica","",9)
                    pdf.cell(0,6,f"Site: {sanitize_pdf_text(sel_main)}/{sanitize_pdf_text(sel_sub)} | Run: {gen_info['run_hours']}", ln=True)
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
                    out = pdf.output(dest="S")
                    pdata = out.encode("latin-1", errors="ignore") if isinstance(out,str) else bytes(out)
                    st.download_button("تحميل PDF", data=pdata, file_name=f"Report_{sanitize_pdf_text(sel_gen)}.pdf", mime="application/pdf", use_container_width=True)
                except Exception as e: st.error(f"PDF Error {e}")

    elif "3." in selected_app:
        st.title("المتابعة + واتساب")
        alerts=check_critical_parts()
        if alerts:
            st.error(f"يوجد {len(alerts)} تنبيه")
            for al in alerts:
                c1,c2,c3 = st.columns([3,2,1])
                with c1: st.write(f"{al['level']} | {al['gen']} - {al['part']}")
                with c2: st.write(f"{al['site']} | باقي {al['remain']:.0f}h")
                with c3:
                    if st.button("واتساب", key=f"wa_{al['gen']}_{al['part']}_{al['remain']}"): whatsapp_alert_modal(al)
        else: st.success("لا تنبيهات")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs) if st.session_state.daily_logs else pd.DataFrame([{"msg":"لا سجلات"}]), use_container_width=True)
    elif "4." in selected_app:
        st.title("AI Diagnostics")
        fault=st.text_input("Fault:", value="Over Current")
        if st.button("Analyze"): st.markdown(analyze_fault_with_gemini(fault, language=L))
    elif "5." in selected_app:
        st.title("WIC & Motor")
        st.checkbox("Oil Level")
        st.checkbox("Compressor")
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
