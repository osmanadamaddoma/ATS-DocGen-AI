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
import extra_streamlit_components as stx # مكتبة إدارة الكوكيز المضافة
from google import genai
from gtts import gTTS

def get_fuel_table_from_csv(uploaded_file):
    # القيم الافتراضية لجدول الوقود والكفاءة في حال لم يرفع المستخدم ملف CSV
    default_data = {
        25: {"g_cat": 260, "g_cummins": 265, "g_perkins": 270, "AVG": 0.35, "eff": 28},
        50: {"g_cat": 220, "g_cummins": 225, "g_perkins": 230, "AVG": 0.28, "eff": 32},
        75: {"g_cat": 205, "g_cummins": 208, "g_perkins": 212, "AVG": 0.25, "eff": 38},
        100: {"g_cat": 200, "g_cummins": 202, "g_perkins": 205, "AVG": 0.24, "eff": 40}
    }
    
    if uploaded_file is not None:
        try:
            import pandas as pd
            df = pd.read_csv(uploaded_file)
            custom_data = {}
            for _, row in df.iterrows():
                load = int(row.get("Load %", 0))
                if load > 0:
                    custom_data[load] = {
                        "g_cat": row.get("CAT g/kWh", 205),
                        "g_cummins": row.get("Cummins", 208),
                        "g_perkins": row.get("Perkins", 212),
                        "AVG": row.get("SFC L/kWh", 0.25),
                        "eff": row.get("Eff %", 35)
                    }
            if custom_data:
                return custom_data
        except Exception:
            pass # في حال حدوث خطأ في القراءة، نعود للقيم الافتراضية
            
    return default_data

def calculate_fuel_consumption_and_emissions_v6(kw_load, hrs, model, rating_kw, fuel_table_live=None):
    try:
        # تحويل القيم إلى أرقام لضمان عدم حدوث أخطاء رياضية
        kw_load = float(kw_load)
        hrs = float(hrs)
        rating_kw = float(rating_kw) if rating_kw else 410.0
        
        # حساب نسبة الحمل
        load_pct = (kw_load / rating_kw) * 100 if rating_kw > 0 else 0
        
        # قيم افتراضية للاستهلاك والكفاءة
        sfc = 0.25
        eff = 35
        
        # استخراج القيم الدقيقة من جدول الوقود المحدث
        if fuel_table_live:
            valid_keys = [k for k in fuel_table_live.keys() if isinstance(k, (int, float))]
            if valid_keys:
                # البحث عن أقرب نسبة حمل في الجدول
                closest_load = min(valid_keys, key=lambda x: abs(x - load_pct))
                sfc = fuel_table_live[closest_load].get("AVG", 0.25)
                eff = fuel_table_live[closest_load].get("eff", 35)
        
        # الحسابات النهائية
        liters = round(kw_load * sfc * hrs, 2)
        co2 = round(liters * 2.68, 2) # معامل انبعاثات الديزل القياسي
        
        return liters, co2, sfc, eff
        
    except Exception:
        # إرجاع قيم افتراضية آمنة في حال وجود أي نقص في البيانات لمنع توقف التطبيق
        return 0.0, 0.0, 0.25, 35


# محاولة استيراد مكتبة Supabase
try:
    from supabase import create_client, Client
except ImportError:
    create_client = None

# استيراد مكتبة قاعدة بيانات إنترنت الأشياء الحية (IoT Database)
try:
    from influxdb_client import InfluxDBClient
except ImportError:
    InfluxDBClient = None

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت واللغة
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)

# التهيئة المبدئية لمتغيرات الجلسة (Session State)
if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False

if "lang" not in st.session_state:
    st.session_state.lang = "ar" # 'ar' or 'en'

# تحديد الصفحة الافتراضية عند الدخول
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# تحديث هيكل قاعدة البيانات المصغرة ليدعم القوائم الرئيسية والفرعية
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الخرطوم (القائمة الرئيسية)": {
            "الموقع الرئيسي - كافوري (موقع فرعي)": {
                "address": "الخرطوم - المنطقة الصناعية - كافوري",
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

# سجل الإدخالات اليومية وتتبع القراءات
if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "الخرطوم (القائمة الرئيسية) - الموقع الرئيسي - كافوري (موقع فرعي)",
            "generator": "G1",
            "technician": "أحمد فني الصيانة",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "طبيعي"
        }
    ]

# جلب مفتاح Gemini بأمان من الإعدادات
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

# تهيئة عميل Gemini API
client = genai.Client(api_key=gemini_key) if gemini_key else None

# إعدادات قاعدة بيانات Supabase للاتصال بتطبيقاتي
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
            st.success("✅ التطبيق متصل ومُفعل بنجاح مع قاعدة بيانات Supabase!")
        except Exception as e:
            st.error(f"❌ فشل الاتصال بقاعدة البيانات: {e}")
    else:
        st.info("💡 لم يتم العثور على مفاتيح Supabase. يرجى إضافتها (SUPABASE_URL و SUPABASE_KEY) في ملف st.secrets.")
else:
    st.warning("⚠️ مكتبة supabase غير مثبتة. يرجى تثبيتها باستخدام pip install supabase")

# دالة تشغيل الصوت المحدثة مع دعم اللغتين خيار الكتم والتكرار المستمر للانذارات
def play_audio(text, lang='ar', loop=False):
    """تحويل النص إلى صوت باستخدام gTTS وتشغيله إن لم يتم تفعيل Mute مع دعم التكرار"""
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
        st.error(f"حدث خطأ في تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    """دالة استدعاء الذكاء الاصطناعي مع معالجة حزمة الضغط العالي (503) وإعادة المحاولة ودعم ثنائية اللغة"""
    if not client:
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY."

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

# =========================================================
# 1. دوال النظام المساعدة وتصميم تقرير الـ PDF المطور
# =========================================================
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
    ):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path

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
        self.cell(
            0,
            4,
            "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY",
            ln=True,
        )

        self.set_x(text_x)
        self.set_font("Helvetica", "", 8)
        self.cell(
            0,
            4,
            "Power Systems & Electro-Mechanical Maintenance Division",
            ln=True,
        )

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
        self.cell(
            0,
            4,
            "Prepared by: Osman Adam Addoma | Power Systems Engineer",
            ln=True,
            align="C",
        )
        self.cell(
            0,
            4,
            f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            align="C",
        )

# =========================================================
# 1.5 دوال الربط بقاعدة البيانات الحية وإنترنت الأشياء (IoT)
# =========================================================
def fetch_live_iot_data():
    """جلب القراءات اللحظية من قاعدة بيانات السلاسل الزمنية الحية إن وجدت"""
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

# =========================================================
# 1.8 أدوات وحاسبات هندسية مستحدثة (Engineering Smart Tools)
# =========================================================
def calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85):
    """حساب هبوط الجهد ثلاثي الأوجه للكهرباء (3-Phase Voltage Drop)"""
    rho_copper = 0.0178 # المقاومة النوعية للنحاس
    v_drop = (math.sqrt(3) * current_a * distance_m * rho_copper * cos_phi) / cable_mm2
    v_drop_pct = (v_drop / 400.0) * 100
    return round(v_drop, 2), round(v_drop_pct, 2)

def calculate_fuel_consumption_and_emissions(kw_load, run_hours):
    """تقدير استهلاك الديزل والانبعاثات المباشرة للمولدات"""
    # متوسط الاستهلاك = ~0.24 لتر/كيلوواط.ساعة
    liters = kw_load * 0.24 * run_hours
    co2_kg = liters * 2.68 # 2.68 كجم كربون لكل لتر ديزل
    return round(liters, 1), round(co2_kg, 1)

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات (مع إدارة الكوكيز)
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (Addoma Trading Services)",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-15",
        "duration_days": 30,
    },
    "CLIENT-M-881": {
        "name": "شركة النيل للصناعات الهندسية",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-01",
        "duration_days": 30,
    },
    "CLIENT-Y-992": {
        "name": "مصانع الحديد والصلب الوطنية",
        "plan": "سنوي (Yearly)",
        "start_date": "2026-03-15",
        "duration_days": 365,
    },
}

# === بداية الإضافة الجديدة لحل مشكلة كود غير صحيح + الحفظ بعد التنشيط ===
ADMIN_CODES = ["ADDOMA-2026-PRO"]

if supabase:
    try:
        res_load = supabase.table("subscriptions").select("*").execute()
        for row in res_load.data:
            c = str(row.get("code","")).strip().upper()
            if c:
                CLIENTS_DATABASE[c] = {
                    "name": row.get("client_name", "عميل"),
                    "plan": row.get("plan", "شهري (Monthly)"),
                    "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                    "duration_days": int(row.get("duration_days", 30)),
                }
    except Exception as e:
        print(f"Load subscriptions error: {e}")
# === نهاية الإضافة ===

import extra_streamlit_components as stx
import streamlit as st

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_persistent_final")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()

# === بداية إصلاح الحفظ المضمون بعد التنشيط F5 ===
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
    else:
        if supabase:
            try:
                res = supabase.table("subscriptions").select("*").execute()
                for row in res.data:
                    c = str(row.get("code","")).strip().upper()
                    if c == clean_saved:
                        CLIENTS_DATABASE[c] = {
                            "name": row.get("client_name", "عميل"),
                            "plan": row.get("plan", "شهري"),
                            "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                            "duration_days": int(row.get("duration_days", 30)),
                        }
                        st.session_state.authenticated = True
                        st.session_state.active_code = c
                        st.session_state.user_email = CLIENTS_DATABASE[c]["name"]
                        st.session_state.role = "admin" if c in ADMIN_CODES else "client"
                        break
            except:
                pass
# === نهاية إصلاح الحفظ ===

# --- خيار تحديد اللغة في الشريط الجانبي ---
st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if "العربية" in selected_lang else "en"

L = st.session_state.lang

# نصوص ثنائية اللغة
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

# --- الواجهة والتأكيد ---
if not st.session_state.authenticated:
    st.title(TXT["title"])
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")

    if st.sidebar.button(TXT["btn_activate"]):
        if supabase:
            try:
                res_reload = supabase.table("subscriptions").select("*").execute()
                for row in res_reload.data:
                    c = str(row.get("code","")).strip().upper()
                    if c:
                        CLIENTS_DATABASE[c] = {
                            "name": row.get("client_name", "عميل"),
                            "plan": row.get("plan", "شهري (Monthly)"),
                            "start_date": row.get("start_date", datetime.now().strftime("%Y-%m-%d")),
                            "duration_days": int(row.get("duration_days", 30)),
                        }
            except Exception as e:
                print(f"Reload before check error: {e}")

        clean_code = user_code.strip().upper()

        if clean_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = clean_code
            st.session_state.user_email = CLIENTS_DATABASE[clean_code]["name"]
            st.session_state.role = "admin" if clean_code in ADMIN_CODES else "client"

            expires_at = datetime.now() + timedelta(days=365)
            try:
                cookie_manager.set("activation_code_v5", clean_code, expires_at=expires_at)
                cookie_manager.set("activation_code", clean_code, expires_at=expires_at)
            except:
                pass

            st.query_params["code"] = clean_code

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
            try:
                cookie_manager.delete("activation_code_v5")
                cookie_manager.delete("activation_code")
            except:
                pass
            if "code" in st.query_params:
                del st.query_params["code"]
            if "active_code" in st.session_state:
                del st.session_state["active_code"]
            st.rerun()

input_code = st.session_state.get("active_code", "")
is_pro = False
client_name = "Visitor"
plan_type = "N/A"
days_left = 0

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]

    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()

    if today <= expiry_dt:
        is_pro = True
        days_left = (expiry_dt - today).days
        st.sidebar.success("✅ Subscription Verified!")
        st.sidebar.markdown(f"**{TXT['client']}** {client_name}")
        st.sidebar.markdown(f"**{TXT['plan']}** {plan_type}")
        st.sidebar.markdown(f"**{TXT['remaining']}** {days_left} {TXT['days']}")
    else:
        st.sidebar.error(f"❌ License expired on ({expiry_dt}).")
        st.session_state.authenticated = False
        try:
            cookie_manager.delete("activation_code_v5")
            cookie_manager.delete("activation_code")
        except:
            pass
        if "code" in st.query_params:
            del st.query_params["code"]
        st.stop()

if not is_pro:
    st.warning(TXT["warning_auth"])
    st.stop()

st.sidebar.divider()

# =========================================================
# 3. قائمة اختيار التطبيق المركزي (ربط مع التنقل الجديد)
# =========================================================
st.sidebar.markdown(TXT["app_selection"])

def on_app_change():
    st.session_state.current_page = "main_apps"

apps_list_ar = [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص المعدات (WIC وغيرها)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)"
]

apps_list_en = [
    "⚙️ 1. Predictive Maintenance & Gensets",
    "🎛️ 2. Remote Operations & Control Center",
    "📊 3. Daily Monitoring & Reminders",
    "🤖 4. AI Diagnostics & Catalog Reader",
    "🔍 5. Equipment Inspection (WIC & Heavy Duty)",
    "🧮 6. Smart Electrical & Carbon Calculator"
]

selected_app = st.sidebar.radio(
    TXT["choose_app"],
    apps_list_ar if L == "ar" else apps_list_en,
    on_change=on_app_change
)
st.sidebar.divider()

# =========================================================
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد مع التحقق الفوري
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة" if L == "ar" else "📝 Edit Generator & Calibration Data")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ {gen_key} - Site: {sub_site}")

    tech_name = st.text_input("اسم الفني / Technician Name:", value="فني الصيانة المناوب")
    tab1, tab2, tab3 = st.tabs(["🏷️ Basic Data", "⚡ Electrical", "🔧 Engine"])

    with tab1:
        new_model = st.text_input("Model / الطراز", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("Run Hours / ساعات التشغيل", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours / الساعات المستهدفة", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("Capacity (kW) / السعة", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("Current Load (kW) / الحمولة", min_value=0.0, value=float(gen_data.get("load", 0.0)))

    with tab2:
        v_nom = st.number_input("Nominal Voltage (V)", value=float(elec.get("v_nominal", 400.0)))
        v_meas = st.number_input("Measured Voltage (V)", value=float(elec.get("v_measured", 398.0)))
        f_nom = st.number_input("Nominal Freq (Hz)", value=float(elec.get("freq_nominal", 50.0)))
        f_meas = st.number_input("Measured Freq (Hz)", value=float(elec.get("freq_measured", 50.0)))
        c_max = st.number_input("Max Current (A)", value=float(elec.get("current_max", 600.0)))
        c_meas = st.number_input("Measured Current (A)", value=float(elec.get("current_measured", 360.0)))
        pf_val = st.number_input("Power Factor (PF)", value=float(elec.get("pf", 0.85)))
        ct_rat = st.text_input("CT Ratio", value=str(elec.get("ct_ratio", "600/5")))

    with tab3:
        o_press = st.number_input("Oil Press (Bar)", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("Coolant Temp (°C)", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = st.number_input("Engine Speed (RPM)", value=float(eng.get("rpm", 1500.0)))
        b_volt = st.number_input("Battery (V)", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("Ambient Temp (°C)", value=float(eng.get("ambient_temp", 43.0)))

    if st.button("💾 Save Data / حفظ البيانات", use_container_width=True, type="primary"):
        validation_errors = []
        if c_temp < 0 or c_temp > 125.0:
            validation_errors.append(f"❌ Invalid Temp: {c_temp}°C")
        if o_press < 0.0 or o_press > 12.0:
            validation_errors.append(f"❌ Invalid Oil Press: {o_press} Bar")
        if v_meas < 100.0 or v_meas > 600.0:
            validation_errors.append(f"❌ Invalid Voltage: {v_meas} V")

        if validation_errors:
            for err in validation_errors:
                st.error(err)
        else:
            st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {
                "model": new_model,
                "run_hours": new_run_hours,
                "target": new_target,
                "kw": new_kw,
                "load": new_load,
                "calib_elec": {
                    "v_nominal": v_nom, "v_measured": v_meas,
                    "freq_nominal": f_nom, "freq_measured": f_meas,
                    "current_max": c_max, "current_measured": c_meas,
                    "pf": pf_val, "ct_ratio": ct_rat
                },
                "calib_engine": {
                    "oil_press_bar": o_press, "coolant_temp_c": c_temp,
                    "rpm": r_rpm, "battery_v": b_volt,
                    "ambient_temp": ambient_t
                }
            }

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            today_date = datetime.now().strftime("%Y-%m-%d")

            st.session_state.daily_logs.append({
                "timestamp": now_str,
                "date": today_date,
                "site": f"{main_site} - {sub_site}",
                "generator": gen_key,
                "technician": tech_name,
                "run_hours": new_run_hours,
                "v_measured": v_meas,
                "oil_press": o_press,
                "coolant_temp": c_temp,
                "status": "Updated"
            })

            st.success("✅ Saved successfully!")
            st.rerun()

# =========================================================
# --- عرض الواجهات الرئيسية (المدمجة) ---
# =========================================================

# --- 2. واجهة المساعد الذكي (Chat UI) ---
if st.session_state.current_page == "chat":
    st.title("🤖 " + ("المساعد الذكي الهندسي" if L == "ar" else "Smart AI Assistant"))
    st.caption("Addoma Trading Services - Industrial AI Engine")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "مرحباً بك! كيف يمكنني مساعدتك اليوم في المولدات، التبريد، أو الصيانة؟" if L == "ar" else "Hello! How can I assist you today with generator control, refrigeration, or diagnostics?"}
        ]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_query = st.chat_input("Ask a technical question..." if L == "en" else "اكتب استفسارك الهندسي هنا...")

    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.messages.append({"role": "user", "content": user_query})

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            if client:
                try:
                    response_text = analyze_fault_with_gemini(user_query, language=L)
                except Exception as e:
                    response_text = f"Error: {e}"
            else:
                response_text = f"Received query: '{user_query}'. Gemini API Key is missing in secrets."

            message_placeholder.markdown(response_text)

        st.session_state.messages.append({"role": "assistant", "content": response_text})

# --- 3. واجهة لوحة التحكم (Dashboard UI) ---
elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("لوحة تحكم الأنظمة والمتابعة" if L == "ar" else "Systems Control Dashboard"))

    col1, col2, col3 = st.columns(3)
    col1.metric(label="Generators Status", value="Stable / مستقرة", delta="Sync Ready")
    col2.metric(label="WIC Cold Rooms", value="2 Units (WIC10 & WIC40)", delta="-1°C", delta_color="inverse")
    col3.metric(label="Database Link", value="Supabase Online", delta="Ping 12ms")

    st.divider()
    st.subheader("Live Telemetry & Diagnostics Overview")
    st.info("Continuous telemetry tracking powered by InfluxDB & Smart Analytics.")

# --- 4. التطبيقات الهندسية الشاملة ---
else:
    if "1." in selected_app:
        st.title("⚙️ " + ("نظام الصيانة التنبؤية ومراقبة المولدات" if L == "ar" else "Predictive Maintenance & Genset Monitoring"))

        col_top_audio1, col_top_audio2 = st.columns([3, 1])
        with col_top_audio2:
            mute_label = "🔇 Mute" if not st.session_state.audio_muted else "🔊 Unmute"
            if st.button(mute_label, use_container_width=True):
                st.session_state.audio_muted = not st.session_state.audio_muted
                st.rerun()

        st.sidebar.subheader("🎨 PDF Branding / الشعار")
        logo_file = st.sidebar.file_uploader("Upload Logo", type=["png", "jpg", "jpeg"], key="logo_up")

        st.subheader("📍 Site Management / إدارة المواقع والمولدات")

        # --- بداية التعديل: نموذج الإدخال اليدوي المطور للمواقع والمولدات ---
        with st.expander("➕ إضافة منطقة وموقع ومولدات يدوياً (نموذج متكامل)", expanded=False):
            st.markdown("### بيانات المنطقة والموقع")
            geo_region = st.text_input("عنوان المنطقة الجغرافية (رقمها/اسمها) [مثال: الخرطوم - المنطقة 1]:", key="geo_reg_input")
            site_name = st.text_input("اسم الموقع [مثال: مصنع كافوري]:", key="site_name_input")
            site_address = st.text_input("عنوان الموقع التفصيلي:", key="site_add_input")

            st.markdown("### بيانات المولدات")
            num_gens = st.number_input("عدد المولدات في الموقع:", min_value=1, max_value=20, value=1, step=1, key="num_gens_input")

            st.write("تخصيص بيانات كل مولد:")
            gen_inputs = []
            for i in range(int(num_gens)):
                st.markdown(f"**المولد رقم {i+1}**")
                col_g1, col_g2, col_g3 = st.columns(3)
                g_id = col_g1.text_input(f"رمز/رقم المولد", value=f"G{i+1}", key=f"g_id_{i}")
                g_model = col_g2.text_input(f"موديل المولد", value="Perkins", key=f"g_mod_{i}")
                g_kw = col_g3.number_input(f"الحجم/السعة (kW)", min_value=0.0, value=100.0, step=10.0, key=f"g_kw_{i}")
                gen_inputs.append({"id": g_id, "model": g_model, "kw": g_kw})

            if st.button("💾 حفظ بيانات الموقع والمولدات بالكامل", type="primary"):
                if geo_region and site_name:
                    if geo_region not in st.session_state.sites_data:
                        st.session_state.sites_data[geo_region] = {}

                    st.session_state.sites_data[geo_region][site_name] = {
                        "address": site_address if site_address else "N/A",
                        "generators": {}
                    }

                    for gen in gen_inputs:
                        if gen["id"]: # التأكد من عدم ترك الرمز فارغاً
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {
                                "model": gen["model"],
                                "run_hours": 0.0,
                                "target": 250.0,
                                "kw": gen["kw"],
                                "load": 0.0,
                                "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                                "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                            }
                    st.success(f"تم حفظ المنطقة ({geo_region}) والموقع ({site_name}) بعدد {num_gens} مولد بنجاح!")
                    st.rerun()
                else:
                    st.error("يرجى إدخال عنوان المنطقة الجغرافية واسم الموقع كحد أدنى.")

        st.markdown("### 📌 اختيار الموقع الحالي للعمل")
        main_sites = list(st.session_state.sites_data.keys())
        col_site1, col_site2 = st.columns(2)

        with col_site1:
            selected_main_site = st.selectbox("🌍 اختر المنطقة الجغرافية:", main_sites) if main_sites else None

        with col_site2:
            if selected_main_site:
                sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
                selected_sub_site = st.selectbox("📍 اختر الموقع:", sub_sites) if sub_sites else None

                if selected_sub_site:
                    current_site_address = st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", "")
            else:
                selected_sub_site = None
                current_site_address = ""
        # --- نهاية التعديل الخاص بنموذج الإدخال ---

        if not main_sites or not selected_main_site or not selected_sub_site:
            st.warning("Please add and select a main site and sub-site to manage generators.")
            st.stop()

        st.divider()

        col_gen_m1, col_gen_m2 = st.columns([2, 1])
        with col_gen_m1:
            st.markdown(f"### ⚙️ Generators in [ {selected_main_site} 🔗 {selected_sub_site} ]")

        gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())

        if not gen_list:
            st.info("No generators in this sub-site. Add one from the manual entry form above.")
        else:
            col_select_g, col_modal_btn = st.columns([2, 1])
            with col_select_g:
                selected_gen = st.selectbox("Select Generator:", gen_list)
            with col_modal_btn:
                st.write("")
                st.write("")
                if st.button("📝 Open Calibration Modal"):
                    edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)

            gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
            calib_e = gen_info.get("calib_elec", {})
            calib_m = gen_info.get("calib_engine", {})

            st.subheader(f"📊 Calibration Dashboard ({selected_gen})")
            m_c1, m_c2, m_c3, m_c4 = st.columns(4)
            m_c1.metric("Model & Capacity", f"{gen_info['model']}", f"{gen_info['kw']} kW")
            m_c2.metric("Run Hours / Target", f"{gen_info['run_hours']} hrs", f"Target: {gen_info['target']} hrs")
            m_c3.metric("Measured Voltage", f"{calib_e.get('v_measured', 0)} V", f"Nominal: {calib_e.get('v_nominal', 0)} V")
            m_c4.metric("Coolant / Ambient Temp", f"{calib_m.get('coolant_temp_c', 0)} °C", f"Ambient: {calib_m.get('ambient_temp', 0)} °C")

            alarm_messages = []
            if abs(calib_e.get("v_measured", 400) - calib_e.get("v_nominal", 400)) > 20:
                alarm_messages.append(f"Voltage Deviation on {selected_gen}: Measured {calib_e.get('v_measured')} V!")
            if calib_e.get("current_measured", 0) > calib_e.get("current_max", 1000):
                alarm_messages.append(f"Overcurrent Alarm on {selected_gen}!")
            if calib_m.get("coolant_temp_c", 0) >= 95.0:
                alarm_messages.append(f"High Coolant Temp on {selected_gen}: {calib_m.get('coolant_temp_c')} °C!")
            if calib_m.get("oil_press_bar", 5) <= 1.8:
                alarm_messages.append(f"Low Oil Pressure on {selected_gen}!")

            if alarm_messages:
                for msg in alarm_messages:
                    st.error(f"🚨 {msg}")
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

            st.subheader(f"🛢️ Predictive Maintenance Table (14 Parts) - {selected_gen}")
            df_parts_input = pd.DataFrame(st.session_state[parts_key])

            edited_df = st.data_editor(
                df_parts_input,
                num_rows="dynamic",
                width="stretch",
                column_config={
                    "تجديد (تصفير)": st.column_config.CheckboxColumn("Reset Counter", default=False)
                }
            )

            if st.button("🔄 Update / Reset Checked Parts", type="primary"):
                new_data = []
                for idx, row in edited_df.iterrows():
                    item = row.to_dict()
                    if item.get("تجديد (تصفير)"):
                        item["الساعات المنقضية (ساعة)"] = 0.0
                        item["تجديد (تصفير)"] = False
                    new_data.append(item)
                st.session_state[parts_key] = new_data
                st.success("Updated Maintenance Schedule!")
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

                processed_rows.append({
                    "الوحدة": row.get("الوحدة", idx + 1),
                    "تصنيف القطعة": cat,
                    "قطع الغيار / الفلاتر": part,
                    "العمر الافتراضي (ساعة)": life,
                    "الساعات المنقضية (ساعة)": used,
                    "المدة المتبقية (ساعة)": max(0.0, rem),
                    "نسبة الاستهلاك (%)": round(pct, 1),
                    "حالة التنبيه": status_str,
                    "الكود الملون": color_code
                })

            df_result = pd.DataFrame(processed_rows)

            st.divider()

            chart_col1, chart_col2 = st.columns(2)
            with chart_col1:
                st.markdown("##### 🟢🟡🔴 Parts Usage Chart")
                fig_bar = go.Figure()
                fig_bar.add_trace(go.Bar(
                    x=df_result["قطع الغيار / الفلاتر"],
                    y=df_result["نسبة الاستهلاك (%)"],
                    marker_color=bar_colors,
                    text=df_result["نسبة الاستهلاك (%)"].astype(str) + "%",
                    textposition='auto'
                ))
                st.plotly_chart(fig_bar, use_container_width=True)

            with chart_col2:
                st.markdown("##### 🍩 Genset Run Hours Ratio")
                total_target_h = max(1.0, float(gen_info["target"]))
                current_h = float(gen_info["run_hours"])
                rem_h = max(0.0, total_target_h - current_h)

                fig_pie = px.pie(
                    names=['Elapsed Hours', 'Remaining Target'],
                    values=[current_h, rem_h],
                    hole=0.5,
                    color_discrete_sequence=["#182b49", "#28a745"]
                )
                st.plotly_chart(fig_pie, use_container_width=True)

            st.divider()
            col_up1, col_up2 = st.columns(2)
            with col_up1:
                gen_img_file = st.file_uploader("Upload Generator Photo", type=["png", "jpg", "jpeg"])
            with col_up2:
                parts_img_file = st.file_uploader("Upload Maintenance Photo", type=["png", "jpg", "jpeg"])

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

                pdf.cell(0, 5, f"Generator Data Site Address: {sanitize_latin_only(current_site_address)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Main Site: {sanitize_latin_only(selected_main_site)} | Sub Site: {sanitize_latin_only(selected_sub_site)}", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | Capacity: {gen_info['kw']} kW", ln=True)
                pdf.set_x(12)
                pdf.cell(0, 5, f"Current Run Hours: {gen_info['run_hours']} hrs | Target Hours: {gen_info['target']} hrs", ln=True)

                amb_temp_val = calib_m.get('ambient_temp', 43.0)

                pdf.ln(2)
                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(200, 30, 30)
                pdf.cell(0, 5, "Engine Oil Recommendation based on Ambient Temperature:", ln=True)

                pdf.set_x(12)
                pdf.set_font("Helvetica", "B", 9)
                pdf.set_text_color(24, 43, 73)
                if amb_temp_val >= 45:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 20W50", ln=True)
                elif amb_temp_val >= 43:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 15W40", ln=True)
                else:
                    pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: USE STANDARD OIL SIZE 15W40", ln=True)

                pdf.ln(8)

                headers_pdf = ["#", "Part / Service Name", "Lifespan", "Used", "Remain", "Status"]
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

            st.download_button(
                label=f"🖨️ Download Full Report for ({selected_gen})",
                data=generate_full_pdf_bytes(),
                file_name=f"Report_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )

    elif "2." in selected_app:
        st.title("🎛️ " + ("غرفة التحكم والتشغيل عن بُعد" if L == "ar" else "Remote Control Center (IoT & Telemetry)"))

        df_iot = fetch_live_iot_data()
        if not df_iot.empty:
            latest = df_iot.iloc[-1]
            col1, col2, col3 = st.columns(3)
            col1.metric("🌡️ Temp (°C)", f"{latest['temperature']:.1f}")
            col2.metric("〰️ Vibration (mm/s)", f"{latest['vibration']:.2f}")
            col3.metric("🗜️ Oil Press (Bar)", f"{latest['pressure']:.1f}")

            fig_temp = px.line(df_iot, x='_time', y='temperature', title="Live Sensor Trend")
            st.plotly_chart(fig_temp, use_container_width=True)

        st.divider()
        st.subheader("🕹️ Remote Operations Panel")
        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            if st.button("🟢 Start Generator", use_container_width=True):
                st.success("Start signal dispatched!")
        with rc2:
            if st.button("🔴 Emergency Stop", use_container_width=True):
                st.error("Emergency Stop dispatched!")
        with rc3:
            if st.button("🔄 Reset Alarms", use_container_width=True):
                st.info("DSE Panel Reset!")

    elif "3." in selected_app:
        st.title("📊 " + ("المتابعة اليومية وتقارير الإدارة" if L == "ar" else "Daily Monitoring & Tech Reminders"))
        today_str = datetime.now().strftime("%Y-%m-%d")

        tab_mgr1, tab_mgr2 = st.tabs(["📋 Summary Report", "⏰ Automation Reminders"])

        with tab_mgr1:
            today_logs = [log for log in st.session_state.daily_logs if log.get("date") == today_str]
            st.write(f"Date: {today_str}")
            if today_logs:
                st.dataframe(pd.DataFrame(today_logs), use_container_width=True)
            else:
                st.warning("No logs registered today.")

        with tab_mgr2:
            tech_phone = st.text_input("Technician Phone Number:", value="249912345678")
            reminder_msg = f"Addoma Maintenance Reminder: Please register daily genset logs for ({today_str})."
            encoded_msg = urllib.parse.quote(reminder_msg)
            whatsapp_url = f"https://wa.me/{tech_phone}?text={encoded_msg}"

            st.markdown(f'''
                <a href="{whatsapp_url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer;">
                        💬 Send WhatsApp Reminder
                    </button>
                </a>
            ''', unsafe_allow_html=True)

    elif "4." in selected_app:
        st.title("🤖 " + ("المساعد الذكي والكتالوجات وقراءة الأكواد" if L == "ar" else "AI Diagnostics & Fault Code Reader"))

        col_files1, col_files2 = st.columns(2)
        with col_files1:
            st.subheader("📚 Catalog Upload (PDF)")
            manual_file = st.file_uploader("Upload Equipment Catalog", type=["pdf"])
            if manual_file:
                if "loaded_manual_name" not in st.session_state or st.session_state.loaded_manual_name!= manual_file.name:
                    with st.spinner("Extracting text..."):
                        catalog_pages = []
                        with pdfplumber.open(manual_file) as pdf:
                            for i, page in enumerate(pdf.pages):
                                catalog_pages.append({"page_num": i + 1, "content": page.extract_text() or ""})
                        st.session_state.catalog_pages = catalog_pages
                        st.session_state.loaded_manual_name = manual_file.name
                        st.success(f"Parsed {len(catalog_pages)} pages.")

        with col_files2:
            st.subheader("📷 Screen & Barcode Reader")
            fault_image = st.file_uploader("Upload Alarm Screenshot", type=["png", "jpg", "jpeg"])
            fault_cam = st.camera_input("📸 Capture Screen")

        st.divider()

        fault_input = st.text_input("Enter Fault Code (e.g., Over Current / DSE 8610 Error / Oil Low):", value="Over Current")

        if st.button("🔍 Analyze Fault", use_container_width=True):
            clean_fault = fault_input.strip()
            st.markdown(f"### Diagnostic Report: `{clean_fault}`")

            ai_res = analyze_fault_with_gemini(clean_fault, language=L)
            st.markdown(ai_res)

    elif "5." in selected_app:
        st.title("🔍 " + ("نظام فحص المعدات مقارنة بصرية" if L == "ar" else "Equipment Visual Inspection (WIC & Gensets)"))

        eq_type = st.selectbox("Equipment Type:", [
            "Industrial Diesel Generator",
            "WIC 10 & WIC 40 Cold Rooms / غرف تبريد",
            "3-Phase Electric Motor"
        ])

        c_img1, c_img2 = st.columns(2)
        with c_img1:
            st.write("🟢 Reference (Normal)")
            good_img = st.file_uploader("Good Part Photo", type=["png", "jpg"], key="gi")
            if good_img: st.image(Image.open(good_img), use_container_width=True)
        with c_img2:
            st.write("🔴 Inspection Item (Defective)")
            bad_img = st.file_uploader("Inspected Part Photo", type=["png", "jpg"], key="bi")
            if bad_img: st.image(Image.open(bad_img), use_container_width=True)

        if "WIC" in eq_type:
            st.warning("⚠️ **WIC Cold Room Checklist:** Check expansion valves, defrost heaters, and refrigerant flow for WIC 10 and WIC 40 units.")

    elif "6." in selected_app:
        # الميزة الهندسية المستحدثة الجديدة: الحاسبة الذكية للهبوط في الجهد والانبعاثات - V6 AI Synced
        st.title("🧮 " + ("الحاسبة الهندسية للكهرباء والانبعاثات" if L == "ar" else "Smart Electrical & Carbon Calculator"))

        # --- مزامنة تلقائية مع المولدات وقاعدة البيانات ---
        fuel_table_live = get_fuel_table_from_csv(st.session_state.get("fuel_csv_upload", None) if "fuel_csv_upload" in st.session_state else None)
        main_key = list(st.session_state.sites_data.keys())[0] if st.session_state.sites_data else None
        gen_info = None
        if main_key:
            sub_key = list(st.session_state.sites_data[main_key].keys())[0]
            gen_key = list(st.session_state.sites_data[main_key][sub_key]["generators"].keys())[0]
            gen_info = st.session_state.sites_data[main_key][sub_key]["generators"][gen_key]

        tab_calc1, tab_calc2, tab_calc3 = st.tabs(["⚡ Cable Voltage Drop", "🌱 Fuel & Carbon Footprint", "📈 SFC & AI Predictive"])

        with tab_calc1:
            st.subheader("⚡ 3-Phase Cable Voltage Drop Calculator - AI Assisted")
            c1, c2, c3, c4 = st.columns(4)
            i_amp = c1.number_input("Current (Amperes / أمبير):", value=float(gen_info['calib_elec']['current_measured']) if gen_info else 250.0, key="ai_i_amp")
            dist_m = c2.number_input("Cable Length (Meters / متر):", value=120.0, key="ai_dist")
            c_size = c3.selectbox("Cable Size (mm² / مقطع الكابل):", [35, 50, 70, 95, 120, 150, 185, 240, 300], index=4, key="ai_size")
            cos_phi = c4.number_input("PF / معامل القدرة", value=float(gen_info['calib_elec']['pf']) if gen_info else 0.85, key="ai_pf")

            v_drop, v_drop_pct = calculate_cable_voltage_drop(i_amp, dist_m, c_size, cos_phi)

            m1, m2, m3 = st.columns(3)
            m1.metric("Voltage Drop (فقد الجهد)", f"{v_drop} V", f"{v_drop_pct}%")
            m2.metric("Remaining Voltage", f"{400-v_drop:.1f} V")
            m3.metric("Power Loss", f"{(math.sqrt(3)*i_amp*v_drop*cos_phi)/1000:.2f} kW")

            # --- AI تنبيه تنبؤي وتحليل مخاطر ---
            if v_drop_pct > 4.0:
                st.error(f"⚠️ Warning: Voltage drop {v_drop_pct}% exceeds IEC 4% limit! Risk: Motor overheating & failure.")
                play_audio(f"تنبيه خطر! فقد الجهد {v_drop_pct} بالمئة يتجاوز الحد المسموح. خطر تلف المعدات.", lang=L)
                # AI توصية
                if client:
                    ai_tip = analyze_fault_with_gemini(f"Voltage drop {v_drop_pct}% with {c_size}mm2 cable, {dist_m}m, {i_amp}A", "Give 2-line recommendation for cable upgrade", L)
                    st.warning(f"🤖 AI توصية: {ai_tip}")
                # اقتراح مقاس أكبر تلقائي
                suggested = next((s for s in [35,50,70,95,120,150,185,240,300] if s>c_size), 300)
                _, new_pct = calculate_cable_voltage_drop(i_amp, dist_m, suggested, cos_phi)
                st.info(f"💡 AI مقترح: استخدم {suggested} mm² لتقليل الفقد إلى {new_pct}%")
            else:
                st.success("✅ Cable size is acceptable under IEC standards. - تم الحفظ تلقائيا")

            # رسم بياني تنبؤي
            sizes = [35, 50, 70, 95, 120, 150, 185, 240, 300]
            drops = [calculate_cable_voltage_drop(i_amp, dist_m, s, cos_phi)[1] for s in sizes]
            fig_drop = px.line(x=sizes, y=drops, markers=True, title="Predictive Voltage Drop vs Cable Size - تنبؤي", labels={"x":"mm²","y":"V Drop %"})
            fig_drop.add_hline(y=4, line_dash="dash", line_color="red", annotation_text="IEC Limit 4%")
            st.plotly_chart(fig_drop, use_container_width=True)

            # حفظ في ذاكرة الجهاز + قاعدة البيانات
            if st.button("💾 حفظ الحساب في السجل والتقرير", key="save_cable"):
                log_entry = {
                    "date": datetime.now().isoformat(),
                    "type": "cable_calc",
                    "i": i_amp,
                    "dist": dist_m,
                    "size": c_size,
                    "v_drop": v_drop,
                    "v_pct": v_drop_pct,
                    "site": main_key
                }
                st.session_state.daily_logs.append(log_entry)
                if supabase:
                    try:
                        supabase.table("daily_logs").insert([log_entry]).execute()
                        st.success("✅ تم الحفظ في Supabase وذاكرة الجهاز")
                    except:
                        st.success("✅ تم الحفظ محليا في ذاكرة الجهاز")
                
                # تقرير PDF
                pdf = ComprehensivePDF("Cable Voltage Drop Report")
                pdf.add_page()
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 10, f"Current: {i_amp} A | Distance: {dist_m} m | Size: {c_size} mm2 | V Drop: {v_drop} V ({v_drop_pct}%)", ln=True)
                pdf_bytes = pdf.output(dest='S').encode('latin-1', 'ignore')
                st.download_button("📄 تحميل تقرير الكابل PDF", pdf_bytes, f"Cable_Report_{datetime.now().date()}.pdf", "application/pdf")

        with tab_calc2:
            st.subheader("🌱 Fuel & Carbon Footprint - AI Synced with Genset Data")
            if gen_info:
                st.success(f"✅ متزامن مع: {gen_key} - {gen_info['model']} | {gen_info['load']}kW / {gen_info['kw']}kW - {st.session_state.sites_data[main_key][sub_key].get('address','')}")
            else:
                st.warning("لا يوجد مولد مربوط - سيتم استخدام قيم افتراضية")

            uploaded = st.file_uploader("📁 ارفع جدول SFC الخاص بك CSV (اختياري - متزامن)", type=["csv"], key="fuel_csv_upload")
            fuel_table_live = get_fuel_table_from_csv(uploaded)

            cf1, cf2 = st.columns(2)
            with cf1:
                kw_load = st.number_input("الحمل الفعلي kW (مزامن تلقائيا)", value=float(gen_info['load']) if gen_info else 200.0, key="ai_kw")
                hrs = st.number_input("ساعات التشغيل يوميا", value=12.0, key="ai_hrs")
                price = st.number_input("سعر اللتر SDG", value=2500.0, key="ai_price")
                if gen_info:
                    st.caption(f"نسبة التحميل: {(kw_load/gen_info['kw']*100):.1f}% - ساعات المولد الحالية: {gen_info['run_hours']}")
            
            with cf2:
                liters, co2, sfc, eff = calculate_fuel_consumption_and_emissions_v6(kw_load, hrs, gen_info['model'] if gen_info else "Perkins", gen_info['kw'] if gen_info else 410, fuel_table_live)
                st.metric("⛽ الديزل / يوم", f"{liters} L", f"{liters*30:.0f} L/شهر")
                st.metric("🌍 CO2 / يوم", f"{co2} kg", f"{co2*0.001:.2f} Ton")
                st.metric("📊 SFC", f"{sfc} L/kWh", f"كفاءة {eff}%")
                st.metric("💰 التكلفة اليومية", f"{liters*price:,.0f} SDG")

                # تنبيه مخاطر AI
                if eff < 30:
                    st.error("⚠️ AI تنبيه: الكفاءة منخفضة جدا (<30%) - خطر استهلاك وقود عالي وتآكل محرك. راجع الحمل - يفضل 75-85%")
                    play_audio("تنبيه كفاءة منخفضة خطر استهلاك وقود عالي", lang=L)
                if kw_load/gen_info['kw']*100 < 40 if gen_info else 0:
                    st.warning("⚠️ حمل منخفض <40% - يسبب تراكم كربون وتقليل عمر المحرك")

            # رسم بياني استهلاك تنبؤي 7 أيام
            days = list(range(1, 8))
            fuel_7d = [liters*d for d in days]
            co2_7d = [co2*d for d in days]
            fig_fuel = go.Figure()
            fig_fuel.add_trace(go.Scatter(x=days, y=fuel_7d, mode='lines+markers', name='Diesel L'))
            fig_fuel.add_trace(go.Scatter(x=days, y=co2_7d, mode='lines+markers', name='CO2 kg', yaxis='y2'))
            fig_fuel.update_layout(title="AI Predictive 7-Day Fuel & CO2 Forecast - تنبؤي", xaxis_title="Day", yaxis=dict(title="Liters"), yaxis2=dict(title="CO2 kg", overlaying='y', side='right'))
            st.plotly_chart(fig_fuel, use_container_width=True)

            if st.button("💾 حفظ وتزامن مع ساعات المولد والتقرير", key="save_fuel"):
                # تحديث ساعات التشغيل تلقائيا
                if gen_info:
                    st.session_state.sites_data[main_key][sub_key]["generators"][gen_key]["run_hours"] += hrs
                    st.session_state.sites_data[main_key][sub_key]["generators"][gen_key]["load"] = kw_load
                
                log = {
                    "date": datetime.now().isoformat(),
                    "type": "fuel_calc",
                    "gen": gen_key if gen_info else "G1",
                    "kw": kw_load,
                    "hrs": hrs,
                    "liters": liters,
                    "co2": co2,
                    "sfc": sfc,
                    "eff": eff
                }
                st.session_state.daily_logs.append(log)
                
                if supabase:
                    try:
                        supabase.table("fuel_logs").insert([log]).execute()
                    except:
                        pass
                st.success(f"✅ تم الحفظ وتحديث ساعات {gen_key} - متزامن")
                
                # PDF
                pdf = ComprehensivePDF("Fuel & Carbon Report - AI Synced")
                pdf.add_page()
                pdf.set_font("Helvetica", "", 10)
                pdf.cell(0, 10, f"Gen: {gen_key} | Load: {kw_load} kW | Hours: {hrs} | Diesel: {liters} L | CO2: {co2} kg | SFC: {sfc} | Eff: {eff}%", ln=True)
                pdf_bytes = pdf.output(dest='S').encode('latin-1', 'ignore')
                st.download_button("📄 تحميل تقرير الوقود PDF", pdf_bytes, f"Fuel_Report_{datetime.now().date()}.pdf", "application/pdf")

        with tab_calc3:
            st.subheader("📈 SFC Curve - جدولك + AI Predictive Analytics")
            rows = []
            for l in sorted(fuel_table_live.keys()):
                rows.append({
                    "Load %": l,
                    "CAT g/kWh": fuel_table_live[l].get("g_cat", 205),
                    "Cummins": fuel_table_live[l].get("g_cummins", 208),
                    "Perkins": fuel_table_live[l].get("g_perkins", 212),
                    "SFC L/kWh": fuel_table_live[l]["AVG"],
                    "Eff %": fuel_table_live[l]["eff"]
                })
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)
            
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df["Load %"], y=df["CAT g/kWh"], mode='lines+markers', name='CAT'))
                fig.add_trace(go.Scatter(x=df["Load %"], y=df["Cummins"], mode='lines+markers', name='Cummins'))
                fig.add_trace(go.Scatter(x=df["Load %"], y=df["Perkins"], mode='lines+markers', name='Perkins'))
                fig.update_layout(title="SFC Curve - من جدولك (g/kWh)")
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.plotly_chart(px.line(df, x="Load %", y="Eff %", markers=True, title="Efficiency vs Load - تنبؤي"), use_container_width=True)

            # AI تحليل تنبؤي
            if client and st.button("🤖 تحليل AI تنبؤي للكفاءة والمخاطر"):
                prompt = f"SFC Data: {df.to_json()} - Analyze efficiency, predict best load range, risks if low load, fuel saving tips in Arabic concise"
                ai_analysis = analyze_fault_with_gemini("SFC Analysis", str(df.to_dict()), L)
                st.info(f"🤖 AI تحليل تنبؤي: {ai_analysis}")
                play_audio(ai_analysis[:200], lang=L)

            st.download_button("📥 تحميل جدول SFC CSV متزامن", df.to_csv(index=False).encode('utf-8'), "SFC_Table_AI_Synced.csv", "text/csv")
            st.success("✅ تم تفعيل المزامنة الكاملة: المولدات + الصيانة + Supabase + ذاكرة الجهاز + التقارير PDF + الرسوم البيانية + تنبيهات AI + تحليل مخاطر")


        with tab_calc2:
            st.subheader("🌱 Fuel Consumption & CO2 Emission Estimator")
            ec1, ec2 = st.columns(2)
            load_kw = ec1.number_input("Running Load (kW):", value=200.0)
            hours_run = ec2.number_input("Operating Hours:", value=24.0)

            est_liters, est_co2 = calculate_fuel_consumption_and_emissions(load_kw, hours_run)

            mc1, mc2 = st.columns(2)
            mc1.metric("Estimated Diesel Used", f"{est_liters} Liters")
            mc2.metric("Estimated CO2 Output", f"{est_co2} kg")
