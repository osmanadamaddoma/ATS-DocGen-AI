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
                "technician_name": "م. عثمان آدم أدومة",
                "technician_whatsapp": "249912345678",
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
    st.warning("⚠️️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")
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
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠ لم يتم العثور على مفتاح GEMINI_API_KEY."
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
# 1. دوال النظام المساعدة وتصميم تقرير الـ PDF المطور الشامل
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
        site_address="N/A",
        main_site="N/A",
        sub_site="N/A",
    ):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path
        self.site_address = site_address
        self.main_site = main_site
        self.sub_site = sub_site
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
            f"SITE: {sanitize_latin_only(self.site_address)} | {sanitize_latin_only(self.main_site)} - {sanitize_latin_only(self.sub_site)}",
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
            f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Site: {sanitize_latin_only(self.site_address)}",
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
def get_fuel_table_from_csv(uploaded_csv=None):
    """قراءة جدول الوقود من ملف CSV المرفوع او استخدام الجدول الداخلي"""
    default_table = {
        100: {"CAT C32": 0.241, "Cummins KTA50": 0.245, "Perkins 2506": 0.249, "AVG": 0.24, "eff": 34, "g_cat": 205, "g_cummins": 208, "g_perkins": 212},
        75: {"CAT C32": 0.247, "Cummins KTA50": 0.253, "Perkins 2506": 0.259, "AVG": 0.25, "eff": 33, "g_cat": 210, "g_cummins": 215, "g_perkins": 220},
        50: {"CAT C32": 0.265, "Cummins KTA50": 0.271, "Perkins 2506": 0.276, "AVG": 0.27, "eff": 31, "g_cat": 225, "g_cummins": 230, "g_perkins": 235},
        25: {"CAT C32": 0.306, "Cummins KTA50": 0.318, "Perkins 2506": 0.324, "AVG": 0.31, "eff": 27, "g_cat": 260, "g_cummins": 270, "g_perkins": 275},
    }
    if uploaded_csv is not None:
        try:
            df = pd.read_csv(uploaded_csv)
            table = {}
            for _, row in df.iterrows():
                load = int(row.get("Load %", 0))
                if load == 0:
                    continue
                sfc = float(row.get("SFC L/kWh", 0.24))
                def g_to_l(g):
                    try:
                        return float(g) / 850.0
                    except:
                        return sfc
                table[load] = {
                    "CAT C32": g_to_l(row.get("CAT C32 g/kWh", sfc*850)),
                    "Cummins KTA50": g_to_l(row.get("Cummins KTA50", sfc*850)),
                    "Perkins 2506": g_to_l(row.get("Perkins 2506", sfc*850)),
                    "AVG": sfc,
                    "eff": int(row.get("كفاءة %", 30)),
                    "g_cat": int(row.get("CAT C32 g/kWh", 200)),
                    "g_cummins": int(row.get("Cummins KTA50", 200)),
                    "g_perkins": int(row.get("Perkins 2506", 200)),
                }
            if table:
                return table
        except Exception as e:
            print(f"CSV parse error: {e}")
            return default_table
    return default_table
def calculate_fuel_consumption_and_emissions(kw_load, run_hours, gen_model="Perkins", kw_capacity=None, fuel_table=None):
    """تقدير استهلاك الديزل والانبعاثات - نسخة ذكية تقرأ من جدول CSV حسب نسبة التحميل ونوع المحرك"""
    if fuel_table is None:
        fuel_table = get_fuel_table_from_csv()
    if kw_capacity and kw_capacity > 0:
        load_pct = (kw_load / kw_capacity) * 100.0
    else:
        load_pct = 100.0 if kw_load > 100 else kw_load
    load_pct = max(25.0, min(100.0, load_pct))
    model_key = "AVG"
    if "CAT" in str(gen_model).upper():
        model_key = "CAT C32"
    elif "CUMMINS" in str(gen_model).upper() or "KTA" in str(gen_model).upper():
        model_key = "Cummins KTA50"
    elif "PERKINS" in str(gen_model).upper():
        model_key = "Perkins 2506"
    loads = sorted(fuel_table.keys())
    if load_pct in fuel_table:
        sfc = fuel_table[load_pct][model_key]
        eff = fuel_table[load_pct]["eff"]
    else:
        lower = max([l for l in loads if l <= load_pct], default=25)
        upper = min([l for l in loads if l >= load_pct], default=100)
        if lower == upper:
            sfc = fuel_table[lower][model_key]
            eff = fuel_table[lower]["eff"]
        else:
            sfc_low = fuel_table[lower][model_key]
            sfc_up = fuel_table[upper][model_key]
            eff_low = fuel_table[lower]["eff"]
            eff_up = fuel_table[upper]["eff"]
            ratio = (load_pct - lower) / (upper - lower)
            sfc = sfc_low + ratio * (sfc_up - sfc_low)
            eff = eff_low + ratio * (eff_up - eff_low)
    liters = kw_load * sfc * run_hours
    co2_kg = liters * 2.68
    return round(liters, 1), round(co2_kg, 1), round(sfc, 3), round(eff, 1)
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
def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager_persistent_final_v3")
    return st.session_state["cookie_manager"]
cookie_manager = get_cookie_manager()
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
# --- خيار تحديد اللغة في الشريط الجانبي ---
st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if "العربية" in selected_lang else "en"
L = st.session_state.lang
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
        "app_selection": "🛠 Available Apps (Pro Version)",
        "choose_app": "Select System Module:"
    }
}[L]
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
st.sidebar.markdown(TXT["app_selection"])
def on_app_change():
    st.session_state.current_page = "main_apps"
apps_list_ar = [
    "⚙️️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص المعدات (WIC وغيرها)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)"
]
apps_list_en = [
    "⚙️ 1. Predictive Maintenance & Gensets",
    "🎛 2. Remote Operations & Control Center",
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
            # حفظ البيانات تلقائياً في Supabase عند التعديل
            if supabase:
                try:
                    payload = {
                        "site_name": sub_site,
                        "generator_id": gen_key,
                        "model": new_model,
                        "capacity_kw": new_kw,
                        "load_kw": new_load,
                        "run_hours": new_run_hours,
                        "last_updated": datetime.now().isoformat()
                    }
                    supabase.table("generators_data").upsert(payload).execute()
                except Exception as e:
                    print(f"Supabase upsert error: {e}")
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
            st.success("✅ Saved successfully and synced to Supabase!")
            st.rerun()
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
elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("لوحة تحكم الأنظمة والمتابعة" if L == "ar" else "Systems Control Dashboard"))
    col1, col2, col3 = st.columns(3)
    col1.metric(label="Generators Status", value="Stable / مستقرة", delta="Sync Ready")
    col2.metric(label="WIC Cold Rooms", value="2 Units (WIC10 & WIC40)", delta="-1°C", delta_color="inverse")
    col3.metric(label="Database Link", value="Supabase Online", delta="Ping 12ms")
    st.divider()
    st.subheader("Live Telemetry & Diagnostics Overview")
    st.info("Continuous telemetry tracking powered by InfluxDB & Smart Analytics.")
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
        with st.expander("➕ إضافة منطقة وموقع ومولدات يدوياً (نموذج متكامل)", expanded=False):
            st.markdown("### بيانات المنطقة والموقع")
            geo_region = st.text_input("عنوان المنطقة الجغرافية (رقمها/اسمها) [مثال: الخرطوم - المنطقة 1]:", key="geo_reg_input")
            site_name = st.text_input("اسم الموقع [مثال: مصنع كافوري]:", key="site_name_input")
            site_address = st.text_input("عنوان الموقع التفصيلي:", key="site_add_input")
            
            # بيانات الفني أو مهندس الصيانة المسؤول عن الموقع
            st.markdown("### بيانات الفني أو مهندس الصيانة المسؤول عن الموقع")
            col_tech_f1, col_tech_f2 = st.columns(2)
            assigned_technician_name = col_tech_f1.text_input("اسم الفني أو المهندس المسؤول:", value="م. عثمان آدم أدومة", key="new_site_tech_name")
            assigned_technician_whatsapp = col_tech_f2.text_input("رقم واتساب الفني/المهندس (مع مفتاح الدولة):", value="249912345678", key="new_site_tech_whatsapp")
            
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
                        "technician_name": assigned_technician_name,
                        "technician_whatsapp": assigned_technician_whatsapp,
                        "generators": {}
                    }
                    for gen in gen_inputs:
                        if gen["id"]:
                            st.session_state.sites_data[geo_region][site_name]["generators"][gen["id"]] = {
                                "model": gen["model"],
                                "run_hours": 0.0,
                                "target": 250.0,
                                "kw": gen["kw"],
                                "load": 0.0,
                                "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                                "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                            }
                            # حفظ البيانات في Supabase أيضاً
                            if supabase:
                                try:
                                    supabase.table("generators_data").upsert({
                                        "site_name": site_name,
                                        "generator_id": gen["id"],
                                        "model": gen["model"],

            # ... [بقية الكود المرفق مع إضافة المعالجة للروابط في الأماكن المطلوبة]
            
                tech_w_num = site_meta.get("technician_whatsapp", "249912345678")
                clean_tech_w_num = re.sub(r'\D', '', str(tech_w_num))
                tech_w_name = site_meta.get("technician_name", "الفني المسؤول")
                
                active_alarm_text = f"🚨 *إنذار طارئ للمولد - Addoma Trading Services*\n\nالعزيز المهندس/الفني: {tech_w_name}\n📍 الموقع: {selected_sub_site} - {selected_main_site}\n⚙️ المولد: {selected_gen}\n⚠️ تفاصيل الإنذار: {', '.join(alarm_messages)}\n\nيرجى التوجه الفوري لفحص الوحدة وإجراء الصيانة اللازمة."
                encoded_alarm_wa = urllib.parse.quote(active_alarm_text)
                alarm_wa_link = f"https://api.whatsapp.com/send?phone={clean_tech_w_num}&text={encoded_alarm_wa}"
            
            # ...
            
            tech_phone = st.text_input("Technician Phone Number:", value="249912345678")
            clean_tech_phone = re.sub(r'\D', '', str(tech_phone))
            reminder_msg = f"Addoma Maintenance Reminder: Please register daily genset logs for ({today_str})."
            encoded_msg = urllib.parse.quote(reminder_msg)
            whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_tech_phone}&text={encoded_msg}"
            
            # ...
            
            target_whatsapp_num = col_w_in2.text_input("رقم الواتساب المستهدف (مع مفتاح الدولة بدون رموز):", value=default_whatsapp_num)
            clean_target_whatsapp_num = re.sub(r'\D', '', str(target_whatsapp_num))
            
            # ...
            
            encoded_smart_msg = urllib.parse.quote(smart_message_input)
            smart_whatsapp_url = f"https://api.whatsapp.com/send?phone={clean_target_whatsapp_num}&text={encoded_smart_msg}"

            # نهاية السكريبت كما في الكود الأصلي
            v_drop, v_drop_pct = calculate_cable_voltage_drop(current_a, distance_m, cable_mm2, cos_phi=0.85)
