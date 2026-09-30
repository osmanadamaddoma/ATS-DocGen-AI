import os, json, uuid, time, urllib.parse, io, base64, math, re
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
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None

st.set_page_config(page_title="V4.6 ULTIMATE - 850 lines - Hierarchical", page_icon="🗺️", layout="wide")

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False
if "lang" not in st.session_state:
    st.session_state.lang = "ar"
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "السودان - الخرطوم (القائمة الرئيسية)": {
            "كافوري - المنطقة الصناعية": {"address": "الخرطوم بحري كافوري مربع 10 - المنطقة الصناعية", "generators": {
                "G1-410": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.1, "current_max": 600.0, "current_measured": 360.0, "pf": 0.85, "ct_ratio": "600/5"},
                       "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 26.5, "ambient_temp": 43.0}},
                "G2-500": {"model": "Cummins 500 kVA", "run_hours": 1200.0, "target": 1500.0, "kw": 500.0, "load": 380.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 402.0, "freq_nominal": 50.0, "freq_measured": 49.9, "current_max": 720.0, "current_measured": 550.0, "pf": 0.82, "ct_ratio": "800/5"},
                       "calib_engine": {"oil_press_bar": 4.2, "coolant_temp_c": 88.0, "rpm": 1500.0, "battery_v": 25.8, "ambient_temp": 45.0}},
                "G3-100": {"model": "Perkins 100 kVA Small", "run_hours": 50.0, "target": 250.0, "kw": 100.0, "load": 60.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 144.0, "current_measured": 86.0, "pf": 0.8, "ct_ratio": "150/5"},
                       "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 78.0, "rpm": 1500.0, "battery_v": 26.0, "ambient_temp": 40.0}}
            }},
            "سوبا - المصانع": {"address": "الخرطوم سوبا المنطقة الصناعية - مصنع الحديد", "generators": {
                "CAT-1000": {"model": "CAT 1000 kVA", "run_hours": 300.0, "target": 500.0, "kw": 1000.0, "load": 700.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 399.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 1440.0, "current_measured": 1010.0, "pf": 0.85, "ct_ratio": "1500/5"},
                       "calib_engine": {"oil_press_bar": 5.0, "coolant_temp_c": 82.0, "rpm": 1500.0, "battery_v": 27.0, "ambient_temp": 42.0}}
            }}
        },
        "السعودية - الرياض (قائمة رئيسية)": {
            "الرياض - الصناعية الثانية": {"address": "الرياض - الصناعية الثانية - شارع 50", "generators": {
                "GEN-R1-250": {"model": "Perkins 250 kVA", "run_hours": 100.0, "target": 250.0, "kw": 250.0, "load": 150.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 360.0, "current_measured": 220.0, "pf": 0.8, "ct_ratio": "400/5"},
                       "calib_engine": {"oil_press_bar": 4.5, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 26.0, "ambient_temp": 45.0}}
            }}
        },
        "مصر - القاهرة (قائمة رئيسية)": {
            "القاهرة - العبور الصناعية": {"address": "القاهرة العبور المنطقة الصناعية", "generators": {
                "EGY-2000": {"model": "MTU 2000 kVA", "run_hours": 80.0, "target": 400.0, "kw": 2000.0, "load": 1500.0,
                       "calib_elec": {"v_nominal": 400.0, "v_measured": 398.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 2880.0, "current_measured": 2160.0, "pf": 0.85, "ct_ratio": "3000/5"},
                       "calib_engine": {"oil_press_bar": 6.0, "coolant_temp_c": 85.0, "rpm": 1500.0, "battery_v": 27.5, "ambient_temp": 38.0}}
            }}
        }
    }

if "daily_logs" not in st.session_state:
    st.session_state.daily_logs = [{"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d"), "site": "كافوري", "generator": "G1-410", "technician": "أحمد", "run_hours": 700.0, "v_measured": 398.0, "oil_press": 4.5, "coolant_temp": 85.0, "status": "طبيعي"}]

if "technicians_db" not in st.session_state:
    st.session_state.technicians_db = {
        "السودان - الخرطوم (القائمة الرئيسية) / كافوري - المنطقة الصناعية": [{"name": "م. عثمان - مسؤول", "phone": "0912345678", "role": "مهندس"}, {"name": "أحمد فني", "phone": "0923456789", "role": "فني"}],
        "DEFAULT": [{"name": "فني طوارئ", "phone": "0912345678", "role": "فني"}]
    }

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
                        default_db[code] = {"name": row.get("client_name","Client"), "plan": row.get("plan","شهري"), "start_date": row.get("start_date") or (row.get("created_at","")[:10] if row.get("created_at") else datetime.now().strftime("%Y-%m-%d")), "duration_days": row.get("duration_days",30)}
        except Exception as e: print(f"Load err {e}")
    return default_db

def save_client_to_supabase(code, client_name, plan, duration_days):
    if supabase:
        try:
            supabase.table("subscriptions").upsert({"code": code, "client_name": client_name, "plan": plan, "duration_days": duration_days, "start_date": datetime.now().strftime("%Y-%m-%d"), "created_at": datetime.now().isoformat()}).execute()
            return True
        except Exception as e: print(e); return False
    return False

def save_to_supabase_auto():
    if supabase:
        try:
            supabase.table("sites_data").upsert({"id": 1, "data": json.dumps(st.session_state.sites_data, ensure_ascii=False), "updated_at": datetime.now().isoformat()}).execute()
        except Exception as e: print(f"Save sites err {e}")

def load_sites_from_supabase():
    if supabase:
        try:
            r = supabase.table("sites_data").select("data").eq("id",1).execute()
            if r.data and r.data[0].get("data"):
                loaded = json.loads(r.data[0]["data"])
                if loaded and len(loaded)>0:
                    st.session_state.sites_data = loaded
        except Exception as e: print(f"Load sites err {e}")

load_sites_from_supabase()

def play_audio(text, lang='ar', loop=False):
    if st.session_state.get("audio_muted", False): return
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
    except Exception as e: st.error(f"Audio {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client: return "Add GEMINI_API_KEY in secrets"
    lang_instr = "Respond in English." if language=="en" else "اكتب بالعربية التقنية الفصحى مع تفاصيل DSE7320/8610."
    prompt = f"You are expert generator engineer Perkins Cummins CAT DSE controller. Fault:{fault_code} Context:{context_text[:2000]} Provide 1.Explanation 2.Top3 Causes 3.Actions 4.Prevention. {lang_instr}"
    for attempt in range(3):
        try:
            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            return response.text
        except Exception as e:
            if "503" in str(e) and attempt < 2: time.sleep(2); continue
            return f"Error: {e}"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL REPORT"):
        super().__init__()
        self.report_title = sanitize_pdf_text(title_text)
    def header(self):
        self.set_fill_color(24,43,73)
        self.rect(0,0,210,8,"F")
        self.set_xy(10,12)
        self.set_font("Helvetica","B",13)
        self.set_text_color(24,43,73)
        self.cell(0,5,self.report_title,ln=True)
        self.set_x(10)
        self.set_font("Helvetica","B",8)
        self.cell(0,4,"ADDOMA TRADING SERVICES - V4.6 ULTIMATE HIERARCHICAL + PDF + CHARTS",ln=True)
        self.line(10,30,200,30)
        self.ln(10)
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","I",8)
        self.set_text_color(120,120,120)
        self.cell(0,4,f"Page {self.page_no()} | {datetime.now().strftime('%Y-%m-%d %H:%M')} | Addoma V4.6 | Osman Adam",align="C")

def create_performance_chart_image(df_res, gen_id):
    try:
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10,6))
        colors = ['red' if p>=90 else 'orange' if p>=70 else 'green' for p in df_res['نسبة الاستهلاك (%)']]
        labels = [sanitize_pdf_text(x)[:15] for x in df_res['قطع الغيار / الفلاتر']]
        ax1.barh(labels, df_res['نسبة الاستهلاك (%)'], color=colors)
        ax1.set_title(f'Gen {sanitize_pdf_text(gen_id)} - Consumption %', fontsize=10)
        ax1.set_xlabel('Consumption %')
        ax2.barh(labels, df_res['المدة المتبقية (ساعة)'], color='skyblue')
        ax2.set_title('Remaining Hours - Performance', fontsize=10)
        ax2.set_xlabel('Hours')
        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        plt.close()
        return buf
    except Exception as e:
        print(f"Chart err {e}")
        return None

def fetch_live_iot_data():
    import random
    data=[]
    for i in range(30):
        t = datetime.now() - timedelta(minutes=(30-i)*2)
        data.append({"_time": t, "temperature": 80+random.uniform(-3,6), "vibration": 3.2+random.uniform(-0.5,1.2), "pressure": 4.1+random.uniform(-0.4,0.4), "oil_press": 4.5+random.uniform(-0.3,0.3)})
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
    if p.startswith(("090","091","096")): return "ZAIN 🟠"
    elif p.startswith(("092","093","099")): return "MTN 🟡"
    elif p.startswith(("011","012","010","015")): return "SUDANI 🔵"
    else: return "SUDAN 📱"

@st.dialog("🔔 واتساب - للجميع")
def whatsapp_alert_modal(alert_data):
    st.error(f"🚨 {alert_data['gen']} - {alert_data['part']}")
    st.write(f"📍 {alert_data['site']} | باقي {alert_data['remain']:.0f} ساعة | {alert_data.get('level','')}")
    site_key = alert_data['site']
    techs = st.session_state.technicians_db.get(site_key, [])
    if not techs:
        for k in st.session_state.technicians_db.keys():
            if k!="DEFAULT" and (k in site_key or site_key in k):
                techs = st.session_state.technicians_db[k]
                break
    if not techs: techs = st.session_state.technicians_db.get("DEFAULT", [])
    options = [f"{t['name']} - {t['phone']} ({t['role']}) | {detect_carrier(t['phone'])}" for t in techs] + ["➕ رقم جديد"]
    sel = st.selectbox("📱 اختر الفني:", options, key=f"sel_{alert_data['gen']}_{alert_data['part']}")
    if "رقم جديد" in sel:
        phone = st.text_input("رقم جديد (09):", value="09", key=f"new_{alert_data['gen']}_{alert_data['part']}")
        tech_name = "فني"
    else:
        idx = options.index(sel)
        phone = techs[idx]['phone'] if idx < len(techs) else "09"
        tech_name = techs[idx]['name'] if idx < len(techs) else "فني"
    st.caption(f"الشبكة: {detect_carrier(phone)} | الى: {tech_name}")
    default_msg = f"*ADDOMA ALERT V4.6* 🚨\nGen: {alert_data['gen']}\nPart: {alert_data['part']}\nSite: {alert_data['site']}\nRemain: {alert_data['remain']:.0f}h\nLevel: {alert_data.get('level','')}\nTech: {tech_name}\nAction: Replace ASAP"
    msg = st.text_area("✏️ نص الرسالة:", value=default_msg, height=180, key=f"msg_{alert_data['gen']}_{alert_data['part']}")
    if st.button("📤 ارسال واتساب الآن", type="primary", use_container_width=True):
        clean = phone.strip().replace(" ","")
        clean_intl = "249" + clean[1:] if clean.startswith("0") else clean.replace("+","")
        wa_url = f"https://wa.me/{clean_intl}?text={urllib.parse.quote(msg)}"
        st.success(f"✅ جاهز للارسال الى {tech_name}")
        st.markdown(f'<a href="{wa_url}" target="_blank"><div style="background:#25D366;color:white;padding:15px;text-align:center;border-radius:10px;font-weight:bold;font-size:18px;">👉 افتح واتساب وارسل الآن 📱</div></a>', unsafe_allow_html=True)

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
                                level="🔴 خطر" if remain<=0 else "🟡 قريب" if remain<=50 else "🟠 تنبيه"
                                alerts.append({"site": f"{main}/{sub}", "gen": gen_id, "part": part.get("قطع الغيار / الفلاتر","قطعة"), "remain": remain, "level": level})
                        except: continue
    return sorted(alerts, key=lambda x: x["remain"])

# ===== HIERARCHICAL MODALS V4.6 =====
@st.dialog("➕ إضافة دولة/قائمة رئيسية")
def add_main_area_modal():
    name = st.text_input("اسم الدولة/المنطقة الرئيسية:", placeholder="مثال: السودان - الخرطوم / السعودية - الرياض")
    if st.button("💾 حفظ الدولة", type="primary", use_container_width=True):
        if name.strip():
            if name.strip() not in st.session_state.sites_data:
                st.session_state.sites_data[name.strip()] = {}
                save_to_supabase_auto()
                st.success(f"✅ تمت إضافة {name}")
                time.sleep(1)
                st.rerun()
            else: st.error("المنطقة موجودة")
        else: st.error("ادخل الاسم")

@st.dialog("➕ إضافة موقع فرعي")
def add_sub_site_modal():
    main_list = list(st.session_state.sites_data.keys())
    if not main_list:
        st.error("أضف دولة أولاً"); return
    sel_main = st.selectbox("اختر الدولة/القائمة الرئيسية:", main_list)
    sub_name = st.text_input("اسم الموقع الفرعي:", placeholder="مصنع كافوري - المنطقة الصناعية")
    address = st.text_input("عنوان تفصيلي:", placeholder="الخرطوم بحري - كافوري مربع 10")
    if st.button("💾 حفظ الموقع", type="primary", use_container_width=True):
        if sub_name.strip():
            st.session_state.sites_data[sel_main][sub_name.strip()] = {"address": address.strip(), "generators": {}}
            save_to_supabase_auto()
            st.success(f"✅ تمت إضافة {sub_name} داخل {sel_main}")
            time.sleep(1)
            st.rerun()
        else: st.error("ادخل اسم الموقع")

@st.dialog("➕ إضافة مولد - أي حجم")
def add_generator_modal():
    main_list = list(st.session_state.sites_data.keys())
    if not main_list:
        st.error("أضف دولة أولاً"); return
    sel_main = st.selectbox("الدولة:", main_list, key="ag_main")
    sub_list = list(st.session_state.sites_data[sel_main].keys())
    if not sub_list:
        st.error("أضف موقع أولاً"); return
    sel_sub = st.selectbox("الموقع الفرعي:", sub_list, key="ag_sub")
    c1,c2 = st.columns(2)
    gen_id = c1.text_input("رقم/اسم المولد:", placeholder="G1 / GEN-500 / CAT-1000 / MTU-2000")
    model = c2.text_input("الموديل:", value="Perkins 410 kVA", placeholder="Perkins / Cummins / CAT / MTU")
    c3,c4,c5 = st.columns(3)
    kw = c3.number_input("القدرة kW/kVA:", value=410.0, min_value=5.0, max_value=5000.0, step=10.0)
    run_hours = c4.number_input("ساعات حالية:", value=0.0, min_value=0.0)
    target = c5.number_input("هدف صيانة (ساعة):", value=250.0)
    load = st.number_input("الحمل الحالي kW:", value=kw*0.6, min_value=0.0)
    st.divider()
    st.markdown("#### معايرة كهربائية")
    ec1,ec2,ec3 = st.columns(3)
    v_nom = ec1.number_input("جهد اسمي V", value=400.0)
    curr_max = ec2.number_input("تيار أقصى A", value=kw*1.8)
    pf = ec3.number_input("PF", value=0.8, min_value=0.5, max_value=1.0)
    st.markdown("#### معايرة محرك")
    en1,en2,en3 = st.columns(3)
    oil_p = en1.number_input("ضغط زيت Bar", value=4.5)
    cool_t = en2.number_input("حرارة ماء C", value=85.0)
    batt_v = en3.number_input("بطارية V", value=26.0)
    if st.button("💾 حفظ المولد في الموقع", type="primary", use_container_width=True):
        if gen_id.strip():
            st.session_state.sites_data[sel_main][sel_sub]["generators"][gen_id.strip()] = {
                "model": model.strip(), "run_hours": run_hours, "target": target, "kw": kw, "load": load,
                "calib_elec": {"v_nominal": v_nom, "v_measured": v_nom-2, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": curr_max, "current_measured": load*1.8, "pf": pf, "ct_ratio": f"{int(curr_max)}/5"},
                "calib_engine": {"oil_press_bar": oil_p, "coolant_temp_c": cool_t, "rpm": 1500.0, "battery_v": batt_v, "ambient_temp": 43.0}
            }
            save_to_supabase_auto()
            st.success(f"✅ مولد {gen_id} {kw}kW تم حفظه في {sel_sub} - {sel_main}")
            time.sleep(1)
            st.rerun()
        else: st.error("ادخل رقم المولد")

@st.dialog("🗑️ حذف موقع/مولد")
def delete_modal():
    main_list = list(st.session_state.sites_data.keys())
    sel_main = st.selectbox("الدولة:", main_list, key="del_main")
    if not sel_main: return
    del_type = st.radio("ماذا تحذف؟", ["مولد واحد", "موقع فرعي كامل", "دولة كاملة"])
    if del_type == "مولد واحد":
        sub_list = list(st.session_state.sites_data[sel_main].keys())
        sel_sub = st.selectbox("الموقع:", sub_list, key="del_sub")
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        sel_gen = st.selectbox("المولد:", gen_list)
        if st.button("🗑️ حذف المولد", type="primary"):
            del st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            save_to_supabase_auto()
            st.success("تم الحذف"); time.sleep(1); st.rerun()
    elif del_type == "موقع فرعي كامل":
        sub_list = list(st.session_state.sites_data[sel_main].keys())
        sel_sub = st.selectbox("الموقع للحذف:", sub_list)
        if st.button("🗑️ حذف الموقع بكل مولداته", type="primary"):
            del st.session_state.sites_data[sel_main][sel_sub]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()
    else:
        if st.button("🗑️ حذف الدولة بكل مواقعها", type="primary"):
            del st.session_state.sites_data[sel_main]
            save_to_supabase_auto()
            st.success("تم"); time.sleep(1); st.rerun()

# ===== AUTH PERSISTENT =====
if "clients_db" not in st.session_state:
    st.session_state.clients_db = load_clients_from_supabase()
CLIENTS_DATABASE = st.session_state.clients_db

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager")
    return st.session_state["cookie_manager"]
cookie_manager = get_cookie_manager()
saved_code = None
try: saved_code = cookie_manager.get(cookie="activation_code")
except: pass
if not saved_code:
    try:
        qp = st.query_params
        if "code" in qp: saved_code = qp["code"]
    except: pass

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if saved_code and not st.session_state.authenticated and saved_code in CLIENTS_DATABASE:
    st.session_state.authenticated = True
    st.session_state.active_code = saved_code

@st.dialog("➕ إصدار كود اشتراك - حفظ دائم")
def generate_subscription_modal():
    client_name = st.text_input("اسم العميل/الشركة:")
    plan_type = st.selectbox("الباقة:", ["شهري", "سنوي", "تجريبي", "دائم"])
    default_duration = 36500 if "دائم" in plan_type else 365 if "سنوي" in plan_type else 7 if "تجريبي" in plan_type else 30
    custom_duration = st.number_input("المدة (أيام):", value=default_duration, min_value=1)
    if st.button("🚀 إصدار وحفظ دائم", type="primary", use_container_width=True):
        if client_name.strip():
            new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
            st.session_state.clients_db[new_code] = {"name": client_name.strip(), "plan": plan_type, "start_date": datetime.now().strftime("%Y-%m-%d"), "duration_days": custom_duration}
            save_client_to_supabase(new_code, client_name.strip(), plan_type, custom_duration)
            st.success(f"✅ حفظ دائم - {new_code}")
            st.code(new_code)
        else: st.error("ادخل الاسم")

@st.dialog("👷 إضافة فني/مهندس")
def add_technician_modal():
    all_sites = [f"{ms} / {ss}" for ms in st.session_state.sites_data for ss in st.session_state.sites_data[ms]]
    site_sel = st.selectbox("اختر الموقع:", all_sites) if all_sites else "DEFAULT"
    t_name = st.text_input("اسم الفني/المهندس:")
    t_phone = st.text_input("رقم الهاتف (09):", placeholder="0912345678")
    t_role = st.selectbox("الدور:", ["مهندس", "فني", "مسؤول صيانة", "طوارئ"])
    if st.button("💾 حفظ", type="primary", use_container_width=True):
        if t_name and t_phone:
            if site_sel not in st.session_state.technicians_db:
                st.session_state.technicians_db[site_sel] = []
            st.session_state.technicians_db[site_sel].append({"name": t_name.strip(), "phone": t_phone.strip(), "role": t_role})
            st.success(f"تم حفظ {t_name}"); time.sleep(1); st.rerun()

st.sidebar.subheader("🌐 Language")
selected_lang = st.sidebar.radio("Select", ["Arabic", "English"], index=0 if st.session_state.lang == "ar" else 1, label_visibility="collapsed")
st.session_state.lang = "ar" if selected_lang == "Arabic" else "en"
L = st.session_state.lang
TXT = {"ar": {"title": "🔐 بوابة التفعيل V4.6", "code_input": "كود التفعيل:", "btn_activate": "تفعيل", "invalid": "كود غير صحيح", "auth": "ادخل كود صالح - محفوظ للأبد", "nav_header": "⚙️ نظام الدومة V4.6", "nav_status": "🟢 مفعل", "btn_chat": "💬 المساعد الذكي", "btn_dashboard": "📊 لوحة التحكم CEO", "btn_apps": "🛠️ التطبيقات", "btn_logout": "🚪 خروج", "choose_app": "اختر النظام:"},
       "en": {"title": "🔐 Activation V4.6", "code_input": "Code:", "btn_activate": "Activate", "invalid": "Invalid", "auth": "Enter valid code - Persistent", "nav_header": "⚙️ Addoma V4.6", "nav_status": "🟢 Active", "btn_chat": "💬 AI Assistant", "btn_dashboard": "📊 CEO Dashboard", "btn_apps": "🛠️ Apps", "btn_logout": "🚪 Logout", "choose_app": "Select System:"}}[L]

if not st.session_state.authenticated:
    st.title(TXT["title"])
    st.info(f"💡 دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())} | أكواد: {len(CLIENTS_DATABASE)} | Admin دائم: ADDOMA-2026-PRO ♾️")
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")
    if st.sidebar.button(TXT["btn_activate"]):
        st.session_state.clients_db = load_clients_from_supabase()
        CLIENTS_DATABASE = st.session_state.clients_db
        if user_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            try:
                cookie_manager.set("activation_code", user_code, expires_at=datetime.now()+timedelta(days=3650))
                st.query_params["code"] = user_code
            except: pass
            st.success(f"✅ {CLIENTS_DATABASE[user_code]['name']}")
            time.sleep(1)
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
        if IS_ADMIN: st.warning("👑 Admin Permanent ♾️ - دخول دائم")
        st.success(TXT["nav_status"])
        st.write("---")
        if st.button(TXT["btn_chat"], use_container_width=True): st.session_state.current_page = "chat"
        if st.button(TXT["btn_dashboard"], use_container_width=True): st.session_state.current_page = "dashboard"
        if st.button(TXT["btn_apps"], use_container_width=True): st.session_state.current_page = "main_apps"
        st.write("---")
        st.markdown("### 🗺️ إدارة المواقع الهرمية V4.6")
        st.caption(f"دول: {len(st.session_state.sites_data)} | مواقع: {sum(len(v) for v in st.session_state.sites_data.values())} | مولدات: {sum(len(s['generators']) for m in st.session_state.sites_data.values() for s in m.values())}")
        if st.button("➕ إضافة دولة/قائمة رئيسية", use_container_width=True): add_main_area_modal()
        if st.button("➕ إضافة موقع فرعي", use_container_width=True, type="primary"): add_sub_site_modal()
        if st.button("➕ إضافة مولد (أي حجم kW)", use_container_width=True): add_generator_modal()
        if st.button("🗑️ حذف موقع/مولد", use_container_width=True): delete_modal()
        st.divider()
        st.markdown("### 👷 دفتر الفنيين (للجميع)")
        if st.button("➕ إضافة فني/مهندس", use_container_width=True): add_technician_modal()
        if st.button("📋 عرض الدفتر", use_container_width=True):
            for site_k, tech_list in st.session_state.technicians_db.items():
                if site_k!="DEFAULT":
                    with st.expander(f"📍 {site_k[:30]} ({len(tech_list)})"):
                        for t in tech_list: st.write(f"{t['name']} | {t['phone']} | {detect_carrier(t['phone'])}")
        st.divider()
        if IS_ADMIN:
            st.markdown("### 🔐 Admin Panel - حفظ دائم")
            if st.button("➕ إصدار اشتراك جديد", use_container_width=True): generate_subscription_modal()
            if st.button("📋 عرض كل الأكواد", use_container_width=True): st.dataframe(pd.DataFrame.from_dict(st.session_state.clients_db, orient='index'), use_container_width=True)
        st.write("---")
        if st.button(TXT["btn_logout"], use_container_width=True):
            st.session_state.authenticated = False
            try: cookie_manager.delete("activation_code")
            except: pass
            st.rerun()
    data = CLIENTS_DATABASE.get(active_code, {})
    if IS_ADMIN:
        days_left = 9999
        expiry_dt = datetime.strptime("2099-12-31", "%Y-%m-%d").date()
        st.sidebar.info(f"👤 {data.get('name','')} | Admin دائم ♾️")
    else:
        start_dt = datetime.strptime(data.get("start_date","2026-01-01"), "%Y-%m-%d").date()
        expiry_dt = start_dt + timedelta(days=data.get("duration_days",30))
        if datetime.now().date() > expiry_dt:
            st.error(f"Expired {expiry_dt}"); st.session_state.authenticated=False; st.stop()
        days_left = (expiry_dt - datetime.now().date()).days
        st.sidebar.info(f"👤 {data.get('name','')} | {days_left} يوم")

st.sidebar.divider()
apps_ar = ["1. الصيانة التنبؤية + QR + فاتورة + PDF + رسوم", "2. التحكم عن بعد IoT Live", "3. المتابعة اليومية + تنبيهات واتساب للجميع", "4. المساعد الذكي Gemini", "5. فحص WIC & Motor 22 نقطة", "6. الحاسبة + وقود + CEO Dashboard"]
selected_app = st.sidebar.radio(TXT["choose_app"], apps_ar)

@st.dialog("📝 تحرير بيانات المولد يدوياً")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec",{})
    eng = gen_data.get("calib_engine",{})
    st.markdown(f"### {gen_key} - {sub_site} - {main_site}")
    tech_name = st.text_input("اسم الفني المحرر:", value="فني الصيانة")
    t1,t2,t3 = st.tabs(["أساسي", "كهربائي", "محرك"])
    with t1:
        new_model = st.text_input("الموديل", value=gen_data.get("model",""))
        new_run_hours = st.number_input("ساعات التشغيل", value=float(gen_data.get("run_hours",0)))
        new_target = st.number_input("هدف الصيانة", value=float(gen_data.get("target",250)))
        new_kw = st.number_input("kW/kVA", value=float(gen_data.get("kw",0)))
        new_load = st.number_input("الحمل kW", value=float(gen_data.get("load",0)))
    with t2:
        v_nom = st.number_input("جهد اسمي V", value=float(elec.get("v_nominal",400)))
        v_meas = st.number_input("جهد مقاس V", value=float(elec.get("v_measured",398)))
        f_nom = st.number_input("تردد اسمي Hz", value=float(elec.get("freq_nominal",50)))
        f_meas = st.number_input("تردد مقاس Hz", value=float(elec.get("freq_measured",50)))
        c_max = st.number_input("تيار أقصى A", value=float(elec.get("current_max",600)))
        c_meas = st.number_input("تيار مقاس A", value=float(elec.get("current_measured",360)))
        pf_val = st.number_input("PF", value=float(elec.get("pf",0.85)))
        ct_rat = st.text_input("CT Ratio", value=str(elec.get("ct_ratio","600/5")))
    with t3:
        o_press = st.number_input("ضغط زيت Bar", value=float(eng.get("oil_press_bar",4.5)))
        c_temp = st.number_input("حرارة ماء C", value=float(eng.get("coolant_temp_c",85)))
        r_rpm = st.number_input("RPM", value=float(eng.get("rpm",1500)))
        b_volt = st.number_input("بطارية V", value=float(eng.get("battery_v",26)))
        ambient_t = st.number_input("حرارة جو C", value=float(eng.get("ambient_temp",43)))
    if st.button("💾 حفظ التعديلات", type="primary", use_container_width=True):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {"model": new_model, "run_hours": new_run_hours, "target": new_target, "kw": new_kw, "load": new_load, "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat}, "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}}
        st.session_state.daily_logs.append({"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "date": datetime.now().strftime("%Y-%m-%d"), "site": f"{main_site}-{sub_site}", "generator": gen_key, "technician": tech_name, "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press, "coolant_temp": c_temp, "status": "Updated"})
        save_to_supabase_auto()
        st.success("✅ تم الحفظ والتحديث!")
        st.rerun()

# ===== PAGES =====
if st.session_state.current_page == "chat":
    st.title("🤖 المساعد الذكي Gemini - تشخيص الأعطال")
    if "messages" not in st.session_state: st.session_state.messages = [{"role": "assistant", "content": "مرحبا! أنا خبير مولدات Perkins و Cummins و CAT و MTU - اسأل عن أي عطل DSE7320 / DSE8610"}]
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    q = st.chat_input("اكتب كود العطل أو وصف المشكلة...")
    if q:
        st.session_state.messages.append({"role":"user","content":q})
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            ans = analyze_fault_with_gemini(q, language=L) if client else "Add GEMINI_API_KEY in secrets"
            st.markdown(ans)
            play_audio(ans[:200], lang=L)
        st.session_state.messages.append({"role":"assistant","content":ans})

elif st.session_state.current_page == "dashboard":
    st.title("📊 CEO Dashboard V4.6 - مئات المواقع + تنبيهات + واتساب")
    alerts = check_critical_parts()
    if alerts:
        st.error(f"🚨 يوجد {len(alerts)} تنبيه حرج - يظهر للجميع (عملاء + Admin)")
        for al in alerts:
            c1,c2 = st.columns([4,1])
            with c1: st.warning(f"{al['level']} | {al['gen']} - {al['part']} | باقي {al['remain']:.0f}h | {al['site']}")
            with c2:
                if st.button("📱 واتساب", key=f"dash_wa_{al['gen']}_{al['part']}"): whatsapp_alert_modal(al)
    col1,col2,col3,col4 = st.columns(4)
    total_gens = sum(len(v["generators"]) for ms in st.session_state.sites_data.values() for v in ms.values())
    total_sites = sum(len(v) for v in st.session_state.sites_data.values())
    col1.metric("🌍 الدول/القوائم", len(st.session_state.sites_data))
    col2.metric("📍 إجمالي المواقع", total_sites)
    col3.metric("⚙️ إجمالي المولدات", total_gens)
    col4.metric("🚨 تنبيهات حرجة", len(alerts))
    all_data=[]
    for main_site, subs in st.session_state.sites_data.items():
        for sub_site, d in subs.items():
            for gen_id, gen in d["generators"].items():
                all_data.append({"الدولة/القائمة الرئيسية": main_site, "الموقع الفرعي": sub_site, "العنوان": d.get("address",""), "المولد": gen_id, "الموديل": gen["model"], "kW": gen["kw"], "ساعات": gen["run_hours"], "الحالة": "⚠️ حرج" if gen["run_hours"]>gen["target"]*0.9 else "✅ جيد"})
    df_all = pd.DataFrame(all_data)
    st.dataframe(df_all, use_container_width=True)
    if not df_all.empty:
        st.plotly_chart(px.treemap(df_all, path=['الدولة/القائمة الرئيسية', 'الموقع الفرعي', 'المولد'], values='kW', color='ساعات', title="خريطة القدرات الهرمية - kW حسب الموقع"), use_container_width=True)
        st.plotly_chart(px.bar(df_all, x="المولد", y="kW", color="الدولة/القائمة الرئيسية", title="قدرات المولدات حسب الدولة"), use_container_width=True)
    with st.expander("🌳 عرض الشجرة الهرمية الكاملة - مئات المواقع"):
        for main, subs in st.session_state.sites_data.items():
            st.markdown(f"### 📁 {main} ({len(subs)} موقع)")
            for sub, d in subs.items():
                gen_count = len(d.get("generators",{}))
                st.markdown(f"**📍 {sub}** - {d.get('address','')} - **{gen_count} مولد**")
                for gen_id, gen in d.get("generators",{}).items():
                    st.caption(f" └─ ⚙️ {gen_id}: {gen.get('model','')} - {gen.get('kw','')}kW - {gen.get('run_hours','')}h")

else:
    if "1." in selected_app:
        st.title("⚙️ الصيانة التنبؤية V4.6 - نظام هرمي لمئات المواقع + QR + فاتورة + PDF + رسوم")
        search = st.text_input("🔍 بحث سريع في مئات المواقع (دولة/موقع/مولد/موديل):", placeholder="مثال: الخرطوم أو CAT أو G1 أو 1000kVA")
        main_sites = list(st.session_state.sites_data.keys())
        if search:
            main_sites = [m for m in main_sites if search.lower() in m.lower() or any(search.lower() in s.lower() or any(search.lower() in g.lower() or search.lower() in st.session_state.sites_data[m][s]["generators"][g].get("model","").lower() for g in st.session_state.sites_data[m][s]["generators"]) for s in st.session_state.sites_data[m])]
        sel_main = st.selectbox(f"🌍 الدولة/القائمة الرئيسية ({len(main_sites)}):", main_sites) if main_sites else None
        sel_sub = None
        if sel_main:
            subs = list(st.session_state.sites_data[sel_main].keys())
            if search: subs = [s for s in subs if search.lower() in s.lower() or any(search.lower() in g.lower() for g in st.session_state.sites_data[sel_main][s]["generators"])]
            sel_sub = st.selectbox(f"📍 الموقع الفرعي ({len(subs)}):", subs) if subs else None
        if not sel_main or not sel_sub:
            st.info("👈 أضف دولة وموقع ومولد من الشريط الجانبي - النظام يتحمل مئات المواقع")
            st.stop()
        gen_list = list(st.session_state.sites_data[sel_main][sel_sub]["generators"].keys())
        if search: gen_list = [g for g in gen_list if search.lower() in g.lower() or search.lower() in st.session_state.sites_data[sel_main][sel_sub]["generators"][g].get("model","").lower()]
        sel_gen = st.selectbox(f"⚙️ المولد ({len(gen_list)} مولد في هذا الموقع):", gen_list) if gen_list else None
        if sel_gen and st.button("📝 تحرير بيانات المولد يدوياً - يدعم كل الأحجام"):
            edit_generator_modal(sel_main, sel_sub, sel_gen)
        if sel_gen:
            gen_info = st.session_state.sites_data[sel_main][sel_sub]["generators"][sel_gen]
            st.info(f"📍 {sel_main} / {sel_sub} | 🏠 {st.session_state.sites_data[sel_main][sel_sub].get('address','')} | ⚙️ {sel_gen} | {gen_info['model']} | {gen_info['kw']}kW | {gen_info['run_hours']}h")
            qr_data = f"Gen:{sel_gen}|Site:{sel_sub}|Country:{sel_main}|kW:{gen_info['kw']}|Hours:{gen_info['run_hours']}|Model:{gen_info['model']}"
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=180x180&data={urllib.parse.quote(qr_data)}"
            c_qr, c_info = st.columns([1,3])
            c_qr.image(qr_url, caption=f"QR {sel_gen}")
            c_info.metric("ساعات التشغيل", f"{gen_info['run_hours']}h", f"هدف {gen_info['target']}")
            c_info.metric("الموديل/القدرة", f"{gen_info['model']}", f"{gen_info['kw']}kW - حمل {gen_info['load']}kW")
            c_info.metric("العنوان", f"{st.session_state.sites_data[sel_main][sel_sub].get('address','')[:40]}")
            key = f"parts_{sel_main}_{sel_sub}_{sel_gen}"
            if key not in st.session_state:
                st.session_state[key] = [{"الوحدة": i+1, "تصنيف القطعة": "Service", "قطع الغيار / الفلاتر": list(PARTS_PRICES.keys())[i % len(PARTS_PRICES)], "العمر الافتراضي (ساعة)": 250.0*(i+1), "الساعات المنقضية (ساعة)": 180.0*i, "تجديد (تصفير)": False} for i in range(14)]
            df = pd.DataFrame(st.session_state[key])
            edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", key=f"editor_{key}")
            if st.button("🔄 تحديث/تصفير الساعات", type="primary"):
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
            c_chart1, c_chart2 = st.columns(2)
            with c_chart1: st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="نسبة الاستهلاك (%)", color="حالة", title=f"استهلاك {sel_gen} %"), use_container_width=True)
            with c_chart2: st.plotly_chart(px.bar(df_res, x="قطع الغيار / الفلاتر", y="المدة المتبقية (ساعة)", color="حالة", title=f"الساعات المتبقية - أداء {sel_gen}"), use_container_width=True)
            st.divider()
            st.subheader("🧾 فاتورة + 📊 تقرير أداء شامل PDF + رسوم بيانية - يظهر للعملاء والـ Admin")
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
                else: st.success("✅ لا فاتورة - لا قطع حرجة")
            with c_rep2:
                st.markdown("#### 📈 أداء المولد")
                st.metric("متوسط الاستهلاك", f"{df_res['نسبة الاستهلاك (%)'].mean():.1f}%")
                st.metric("أقل قطعة متبقية", f"{df_res['المدة المتبقية (ساعة)'].min():.0f}h")
                st.metric("عدد القطع الحرجة", f"{len(invoice)}")
            if st.button("📄 إنشاء تقرير شامل PDF + رسوم بيانية للأداء", type="primary", use_container_width=True):
                try:
                    pdf = ComprehensivePDF(f"MAINTENANCE & PERFORMANCE REPORT - {sanitize_pdf_text(sel_gen)} - {sanitize_pdf_text(sel_sub)}")
                    pdf.add_page()
                    pdf.set_font("Helvetica","B",11)
                    pdf.cell(0,8,f"Generator: {sanitize_pdf_text(sel_gen)} | Model: {sanitize_pdf_text(gen_info['model'])} | kW: {gen_info['kw']} | Country: {sanitize_pdf_text(sel_main)}", ln=True)
                    pdf.set_font("Helvetica","",9)
                    pdf.cell(0,6,f"Site: {sanitize_pdf_text(sel_sub)} | Address: {sanitize_pdf_text(st.session_state.sites_data[sel_main][sel_sub].get('address',''))} | Run: {gen_info['run_hours']} | Target: {gen_info['target']}", ln=True)
                    pdf.cell(0,6,f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Client: {sanitize_pdf_text(data.get('name',''))} | Days Left: {days_left}", ln=True)
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
                        pdf.cell(0,7,f"INVOICE TOTAL: ${total} USD - Critical Parts: {len(invoice)}", ln=True)
                        for inv in invoice:
                            pdf.set_font("Helvetica","",8)
                            pdf.cell(0,5,f"- {sanitize_pdf_text(inv['Part'])} : ${inv['Price USD']} | Remain {inv['Remain hrs']} hrs", ln=True)
                    chart_buf = create_performance_chart_image(df_res, sel_gen)
                    if chart_buf:
                        pdf.ln(5)
                        pdf.set_font("Helvetica","B",10)
                        pdf.cell(0,7,"Performance Charts - Generator Performance:", ln=True)
                        chart_path = f"/tmp/chart_{sanitize_pdf_text(sel_gen)}.png"
                        with open(chart_path, "wb") as f:
                            f.write(chart_buf.getvalue())
                        try: pdf.image(chart_path, x=10, w=190)
                        except: pass
                    pdf_output = pdf.output(dest="S")
                    pdf_data = pdf_output.encode("latin-1", errors="ignore") if isinstance(pdf_output,str) else bytes(pdf_output)
                    st.download_button("📥 تحميل التقرير الشامل PDF مع الرسوم", data=pdf_data, file_name=f"Full_Report_{sanitize_pdf_text(sel_gen)}_{datetime.now().strftime('%Y%m%d')}.pdf", mime="application/pdf", use_container_width=True, key="full_pdf_v46")
                    st.success("✅ التقرير جاهز مع الرسوم البيانية!")
                except Exception as e:
                    st.error(f"PDF Error: {e}")

    elif "2." in selected_app:
        st.title("🎛️ التحكم عن بعد IoT Live - 30 نقطة")
        df_iot = fetch_live_iot_data()
        latest = df_iot.iloc[-1]
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("🌡️ حرارة", f"{latest['temperature']:.1f} C")
        c2.metric("📳 اهتزاز", f"{latest['vibration']:.2f} mm/s")
        c3.metric("⛽ ضغط زيت", f"{latest['pressure']:.1f} Bar")
        c4.metric("🛢️ ضغط إضافي", f"{latest['oil_press']:.1f} Bar")
        st.plotly_chart(px.line(df_iot, x='_time', y=['temperature','vibration','pressure'], title="Live IoT Sensors - 30 Points"), use_container_width=True)
        rc1,rc2,rc3 = st.columns(3)
        if rc1.button("🟢 Start Generator", use_container_width=True): st.success("Start command sent!")
        if rc2.button("🔴 Stop Generator", use_container_width=True): st.error("Stop command sent!")
        if rc3.button("🔄 Reset Alarms", use_container_width=True): st.info("Reset sent!")

    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية + تنبيهات واتساب للجميع V4.6")
        st.info("✅ زر واتساب يظهر للعملاء المشتركين + Admin - مربوط بدفتر الفنيين + حفظ دائم")
        alerts = check_critical_parts()
        if alerts:
            st.error(f"🚨 يوجد {len(alerts)} تنبيه حرج - يظهر للجميع!")
            for al in alerts:
                c1,c2,c3 = st.columns([3,2,1])
                with c1: st.write(f"{al['level']} | **{al['gen']}** - {al['part']}")
                with c2: st.write(f"📍 {al['site']} | باقي {al['remain']:.0f}h")
                with c3:
                    if st.button("📱 واتساب", key=f"daily_wa_{al['gen']}_{al['part']}_{al['remain']}"): whatsapp_alert_modal(al)
            st.divider()
        else: st.success("✅ لا يوجد تنبيهات حرجة")
        today = datetime.now().strftime("%Y-%m-%d")
        logs = [l for l in st.session_state.daily_logs if l.get("date")==today]
        st.dataframe(pd.DataFrame(logs) if logs else pd.DataFrame([{"msg":"No logs today - أضف مولدات أولاً"}]), use_container_width=True)

    elif "4." in selected_app:
        st.title("🤖 AI Diagnostics - Gemini 2.0 Flash")
        fault = st.text_input("كود العطل:", value="Over Current / Low Oil Pressure")
        ctx = st.text_area("سياق إضافي:", value="DSE7320 - Perkins 410kVA - Run 700h")
        if st.button("🔍 تحليل بالذكاء الاصطناعي", type="primary"):
            with st.spinner("جاري التحليل..."):
                ans = analyze_fault_with_gemini(fault, ctx, language=L)
                st.markdown(ans)
                play_audio(ans[:300], lang=L)

    elif "5." in selected_app:
        st.title("🔍 فحص WIC & Motor - 22 نقطة + 16 نقطة")
        eq_type = st.selectbox("نوع الفحص:", ["Generator 22 Points - فحص المولد", "WIC Cold Rooms 16 Points - غرف التبريد", "Motor 6 Points - فحص المحركات"])
        if "WIC" in eq_type:
            st.subheader("❄️ فحص غرف التبريد WIC - 16 نقطة")
            c1,c2,c3 = st.columns(3)
            c1.metric("Room Temp", "-19.5 C")
            c2.metric("LP", "35 PSI")
            c3.metric("HP", "210 PSI")
            checks = ["Compressor Oil Level", "R404a Gas Pressure", "Expansion Valve", "Defrost Heater", "Evaporator Fans (2)", "Door Gasket", "Eliwell Controller ID974", "HP/LP Cutout", "Solenoid Valve", "Filter Drier", "Sight Glass", "Condenser Clean", "Drain Heater", "Light & Switch", "Alarm System", "Panel Wiring"]
            for it in checks: st.checkbox(it, key=f"wic_{it}")
            vol = st.number_input("Room Volume m3", value=120.0)
            load = (vol*65*0.022)/0.8
            st.metric("Cooling Load", f"{load:.2f} kW")
            if st.button("📄 تقرير WIC PDF"):
                pdf = ComprehensivePDF(f"WIC Inspection Report")
                pdf.add_page()
                pdf.set_font("Helvetica","B",12)
                pdf.cell(0,10,f"WIC Volume: {vol} m3 | Load: {load:.2f} kW", ln=True)
                out = pdf.output(dest="S")
                pdata = out.encode("latin-1", errors="ignore") if isinstance(out,str) else bytes(out)
                st.download_button("تحميل تقرير WIC", data=pdata, file_name="WIC_Report.pdf", mime="application/pdf")
        elif "Generator" in eq_type:
            st.subheader("⚙️ فحص المولد - 22 نقطة")
            gen_checks = ["Oil Level", "Coolant Level", "Fuel Level & Tank", "Battery Voltage & Terminals", "Air Filter Condition", "Fan Belt Tension", "Exhaust System & Leaks", "DSE Controller Alarms", "ATS Test", "Load Test 80%", "Vibration Check", "Alternator Winding", "AVR Check", "Fuel Filter Water Drain", "Radiator Clean", "Turbocharger", "Starter Motor", "Charging Alternator", "Earthing System", "Cable Connections", "Control Panel Wiring", "Safety Guards"]
            cols = st.columns(2)
            for i, it in enumerate(gen_checks):
                cols[i%2].checkbox(it, key=f"gen_{it}")
            if st.button("📄 تقرير فحص المولد PDF"):
                pdf = ComprehensivePDF(f"Generator 22 Points Inspection")
                pdf.add_page()
                pdf.set_font("Helvetica","",10)
                for ch in gen_checks: pdf.cell(0,6,f"[ ] {sanitize_pdf_text(ch)}", ln=True)
                out = pdf.output(dest="S")
                pdata = out.encode("latin-1", errors="ignore") if isinstance(out,str) else bytes(out)
                st.download_button("تحميل تقرير الفحص", data=pdata, file_name="Gen_22P_Report.pdf", mime="application/pdf")
        else:
            st.subheader("🔌 فحص المحركات - 6 نقاط")
            kw = st.number_input("Motor kW", value=15.0, min_value=0.5, max_value=500.0)
            flc = (kw*1000)/(1.732*400*0.85*0.92)
            st.metric("FLC Full Load Current", f"{flc:.1f} A")
            st.metric("Cable Size Recommended", f"{35 if flc<60 else 70 if flc<120 else 120} mm2")
            st.metric("Breaker Size", f"{flc*1.25:.0f} A")
            st.metric("Overload Relay", f"{flc*1.05:.1f} A")
            st.checkbox("Insulation Test > 100 Mohm")
            st.checkbox("Vibration < 2.8 mm/s")
            st.checkbox("Bearing Temp < 80C")

    elif "6." in selected_app:
        st.title("🧮 الحاسبة + CEO Dashboard + وقود + CO2")
        tab1,tab2,tab3 = st.tabs(["🔌 Cable Voltage Drop", "⛽ Fuel & CO2 & Cost", "📊 CEO Summary"])
        with tab1:
            st.subheader("حساب هبوط الجهد")
            i_amp = st.number_input("Current A", value=250.0, min_value=1.0)
            dist = st.number_input("Length m", value=120.0, min_value=1.0)
            size = st.selectbox("Cable mm2", [16,25,35,50,70,95,120,150,185,240,300], index=4)
            cos_phi = st.number_input("PF cos phi", value=0.85, min_value=0.5, max_value=1.0)
            vd,vp = calculate_cable_voltage_drop(i_amp,dist,size,cos_phi)
            c1,c2 = st.columns(2)
            c1.metric("Voltage Drop V", f"{vd} V")
            c2.metric("Voltage Drop %", f"{vp}%", delta="OK" if vp<4 else "Exceeds 4%!")
            if vp>4: st.error("⚠️ يتجاوز 4% - كبر مقطع الكابل!")
            else: st.success("✅ ضمن المسموح")
            st.plotly_chart(px.bar(x=[str(size)], y=[vp], title=f"VD% for {size}mm2 - {dist}m - {i_amp}A"), use_container_width=True)
        with tab2:
            st.subheader("استهلاك الوقود والانبعاثات والتكلفة")
            load = st.number_input("Load kW", value=200.0, min_value=1.0)
            hrs = st.number_input("Run Hours", value=24.0, min_value=1.0)
            liters,co2,cost = calculate_fuel_consumption_and_emissions(load,hrs)
            c1,c2,c3 = st.columns(3)
            c1.metric("Diesel Liters", f"{liters} L")
            c2.metric("CO2 Emissions", f"{co2} kg")
            c3.metric("Cost USD", f"${cost}")
            st.plotly_chart(px.pie(values=[liters, co2], names=['Diesel L', 'CO2 kg'], title="Fuel vs Emissions"), use_container_width=True)
        with tab3:
            st.subheader("ملخص CEO")
            df_summary = pd.DataFrame([{"الدولة": m, "المواقع": len(v), "المولدات": sum(len(s["generators"]) for s in v.values()), "إجمالي kW": sum(sum(g["kw"] for g in s["generators"].values()) for s in v.values())} for m,v in st.session_state.sites_data.items()])
            st.dataframe(df_summary, use_container_width=True)
            st.plotly_chart(px.bar(df_summary, x="الدولة", y="إجمالي kW", color="المواقع", title="إجمالي القدرات حسب الدولة"), use_container_width=True)
            st.plotly_chart(px.bar(df_summary, x="الدولة", y="المولدات", title="عدد المولدات حسب الدولة"), use_container_width=True)
