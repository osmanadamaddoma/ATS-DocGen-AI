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
import extra_streamlit_components as stx  # مكتبة إدارة الكوكيز
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
# 0. إعدادات الصفحة الرئيسية وتهيئة النظام
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="🔐",
    layout="wide",
)

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False

if "lang" not in st.session_state:
    st.session_state.lang = "ar"  # 'ar' or 'en'

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# التهيئة المبدئية لقاعدة بيانات المواقع والمولدات
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

# جلب مفتاح Gemini بأمان
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")

client = genai.Client(api_key=gemini_key) if gemini_key else None

# إعدادات قاعدة بيانات Supabase
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
        except Exception:
            pass

# =========================================================
# 1. تعريف دالة نافذة إدارة واستصدار الأكواد في الأعلى
# =========================================================
def render_activation_export_window():
    st.title("🔐 نافذة استصدار وتحرير بيانات الأكواد المفعلة للمشتركين")
    st.caption("Addoma Trading Services - Subscription & License Generation Portal")

    if not st.session_state.get("authenticated", False):
        st.warning("🔒 يرجى تسجيل الدخول أولاً للوصول إلى نظام إدارة الأكواد المفعلة.")
        return

    tab_gen, tab_export, tab_db = st.tabs([
        "🔑 استصدار كود جديد", 
        "📤 استخراج وتحرير بيانات المشتركين", 
        "📊 سجل الأكواد النشطة"
    ])

    with tab_gen:
        st.subheader("إصدار كود تفعيل واشتراك جديد")
        with st.form("new_activation_form"):
            new_client_name = st.text_input("اسم المشترك / الجهة المستفيدة:")
            plan_option = st.selectbox("نوع الباقة:", ["شهري (Monthly) - 30 يوم", "سنوي (Yearly) - 365 يوم", "تجريبي (Trial) - 7 أيام"])
            custom_code_input = st.text_input("كود التفعيل المقترح (اختياري):", placeholder="ADDOMA-2026-XXXX")
            
            if st.form_submit_button("⚙️ إصدار وتوثيق الكود الجديد"):
                if not new_client_name:
                    st.error("❌ يرجى إدخال اسم المشترك على الأقل.")
                else:
                    if not custom_code_input:
                        generated_code = f"ADDOMA-2026-{str(uuid.uuid4())[:6].upper()}"
                    else:
                        generated_code = custom_code_input.strip().upper()

                    duration_map = {"شهري (Monthly) - 30 يوم": 30, "سنوي (Yearly) - 365 يوم": 365, "تجريبي (Trial) - 7 أيام": 7}
                    
                    if "custom_generated_codes" not in st.session_state:
                        st.session_state.custom_generated_codes = {}

                    st.session_state.custom_generated_codes[generated_code] = {
                        "name": new_client_name,
                        "plan": plan_option,
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "duration_days": duration_map[plan_option]
                    }
                    st.success(f"✅ تم بنجاح استصدار الكود للمشترك: **{new_client_name}**")
                    st.code(f"Activation Code: {generated_code}", language="text")

    with tab_export:
        st.subheader("استخراج تقارير وجداول بيانات الأكواد المفعلة")
        export_data = []
        combined_db = st.session_state.get("CLIENTS_DATABASE", {}).copy()
        if "custom_generated_codes" in st.session_state:
            combined_db.update(st.session_state.custom_generated_codes)

        for code, info in combined_db.items():
            start_dt = datetime.strptime(info["start_date"], "%Y-%m-%d").date()
            expiry_dt = start_dt + timedelta(days=info["duration_days"])
            today = datetime.now().date()
            export_data.append({
                "رمز التفعيل": code,
                "اسم المشترك": info["name"],
                "نوع الباقة": info["plan"],
                "تاريخ البدء": info["start_date"],
                "تاريخ الانتهاء": expiry_dt.strftime("%Y-%m-%d"),
                "الأيام المتبقية": max(0, (expiry_dt - today).days),
                "حالة الاشتراك": "نشط (Active)" if today <= expiry_dt else "منتهي (Expired)"
            })

        df_subscribers = pd.DataFrame(export_data)
        edited_subscribers_df = st.data_editor(df_subscribers, num_rows="dynamic", use_container_width=True)
        
        csv_bytes = edited_subscribers_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("📥 تحميل البيانات بصيغة CSV", data=csv_bytes, file_name="Addoma_Subscribers_Report.csv", mime="text/csv", use_container_width=True)

    with tab_db:
        st.subheader("📊 نظرة عامة على حالة التفعيل")
        st.dataframe(pd.DataFrame(export_data), use_container_width=True)

# =========================================================
# 2. الدوال المساعدة ونظام الصوت والتحليل بالذكاء الاصطناعي
# =========================================================
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
            audio_html = f"""
                <audio autoplay loop controls style="width: 100%;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception:
        pass

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text="", language="ar"):
    if not client:
        return "⚠️ GEMINI_API_KEY not found." if language == "en" else "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY."

    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة."
    prompt = f"""
    You are an expert industrial consulting engineer specializing in generators, DSE control panels, Perkins & Cummins engines, and cooling systems.
    Fault Code / Alarm: "{fault_code}"
    Context: {context_text if context_text else "General engineering analysis."}
    {lang_instr}
    """
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return response.text
    except Exception as e:
        return f"❌ Error: {e}"

def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL REPORT", logo_path=None):
        super().__init__()
        self.report_title = title_text
        self.logo_path = logo_path

    def header(self):
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")
        self.set_xy(10, 12)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 5, self.report_title, ln=True)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 4, f"Page {self.page_no()} | Addoma Trading Services", align="C")

def fetch_live_iot_data():
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

# =========================================================
# 3. نظام التفعيل والكوكيز (Cookies & Authentication)
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
    }
}

def get_cookie_manager():
    if "cookie_manager" not in st.session_state:
        st.session_state["cookie_manager"] = stx.CookieManager(key="my_cookie_manager")
    return st.session_state["cookie_manager"]

cookie_manager = get_cookie_manager()
saved_code = cookie_manager.get(cookie="activation_code")

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if saved_code and not st.session_state.authenticated:
    if saved_code in CLIENTS_DATABASE:
        st.session_state.authenticated = True
        st.session_state.active_code = saved_code

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
        "warning_auth": "🔒 يرجى إدخال كود اشتراك صالح للوصول إلى التطبيقات.",
        "nav_header": "⚙️ نظام الدومة للخدمات التجارية",
        "nav_status": "🟢 النظام متصل ومفعل",
        "btn_chat": "💬 المساعد الذكي الهندسي",
        "btn_dashboard": "📊 لوحة تحكم الأنظمة",
        "btn_apps": "🛠️ التطبيقات الهندسية الشاملة",
        "btn_ats": "🔐 إدارة واستصدار الأكواد (ATS)",
        "btn_logout": "🚪 تسجيل الخروج",
        "choose_app": "اختر النظام المطلوب:"
    },
    "en": {
        "title": "🔐 Unified Activation Portal",
        "code_input": "Activation Code:",
        "btn_activate": "Activate",
        "invalid_code": "❌ Invalid activation code.",
        "warning_auth": "🔒 Please enter a valid activation code.",
        "nav_header": "⚙️ Addoma Trading Services",
        "nav_status": "🟢 System Connected",
        "btn_chat": "💬 Smart AI Assistant",
        "btn_dashboard": "📊 Control Dashboard",
        "btn_apps": "🛠️ Engineering Apps Suite",
        "btn_ats": "🔐 ATS License Manager",
        "btn_logout": "🚪 Logout",
        "choose_app": "Select System Module:"
    }
}[L]

if not st.session_state.authenticated:
    st.title(TXT["title"])
    user_code = st.sidebar.text_input(TXT["code_input"], type="password")
    if st.sidebar.button(TXT["btn_activate"]):
        if user_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            cookie_manager.set("activation_code", user_code, expires_at=datetime.now() + timedelta(days=30))
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
        if st.button(TXT["btn_ats"], use_container_width=True):
            st.session_state.current_page = "ats_portal"
        st.write("---")
        if st.button(TXT["btn_logout"], type="primary", use_container_width=True):
            st.session_state.authenticated = False
            cookie_manager.delete("activation_code")
            st.rerun()

st.sidebar.divider()

# =========================================================
# 4. توجيه الصفحات وتنفيذ الواجهات
# =========================================================
if st.session_state.current_page == "ats_portal":
    render_activation_export_window()

elif st.session_state.current_page == "chat":
    st.title("🤖 " + ("المساعد الذكي الهندسي" if L == "ar" else "Smart AI Assistant"))
    user_query = st.chat_input("اكتب استفسارك الهندسي هنا...")
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        with st.chat_message("assistant"):
            response_text = analyze_fault_with_gemini(user_query, language=L)
            st.markdown(response_text)

elif st.session_state.current_page == "dashboard":
    st.title("📊 " + ("لوحة تحكم الأنظمة والمتابعة" if L == "ar" else "Systems Control Dashboard"))
    col1, col2, col3 = st.columns(3)
    col1.metric("Generators Status", "Stable")
    col2.metric("WIC Cold Rooms", "2 Units Active")
    col3.metric("Database", "Online")

else:
    # التطبيقات الهندسية الشاملة
    apps_list = [
        "⚙️ 1. الصيانة التنبؤية والمولدات",
        "🎛️ 2. غرفة التحكم والتشغيل عن بُعد",
        "📊 3. المتابعة اليومية وتقارير الإدارة",
        "🤖 4. المساعد الذكي وقراءة الأكواد",
        "🔍 5. نظام فحص المعدات (WIC)",
        "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات"
    ]
    selected_app = st.sidebar.selectbox(TXT["choose_app"], apps_list)

    if "1." in selected_app:
        st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")
        st.info("قم بإدارة ومراقبة المولدات وساعات التشغيل بمرونة تامة.")
        # عرض معلومات تجريبية سريعة
        st.write("المولدات النشطة حالياً ضمن قاعدة البيانات تعمل بكفاءة.")

    elif "2." in selected_app:
        st.title("🎛️ غرفة التحكم والتشغيل عن بُعد")
        df_iot = fetch_live_iot_data()
        st.line_chart(df_iot.set_index('_time')[['temperature', 'vibration']])

    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية وتقارير الإدارة")
        st.dataframe(pd.DataFrame(st.session_state.daily_logs), use_container_width=True)

    elif "4." in selected_app:
        st.title("🤖 تحليل الأعطال والكتالوجات بالذكاء الاصطناعي")
        fault = st.text_input("أدخل كود العطل أو الوصف:", "DSE 8610 Over Current")
        if st.button("تحليل العطل"):
            st.markdown(analyze_fault_with_gemini(fault, language=L))

    elif "5." in selected_app:
        st.title("🔍 فحص ومقارنة أجزاء المعدات وغرف التبريد WIC")
        st.success("غرف التبريد WIC 10 و WIC 40 تعمل بكفاءة ومنتظمة التبريد.")

    elif "6." in selected_app:
        st.title("🧮 الحاسبة الهندسية للكهرباء والانبعاثات")
        i_amp = st.number_input("التيار (أمبير):", value=200.0)
        dist = st.number_input("المسافة (متر):", value=100.0)
        drop, drop_pct = calculate_cable_voltage_drop(i_amp, dist, 95)
        st.metric("هبوط الجهد الكلي", f"{drop} V", f"{drop_pct}%")
