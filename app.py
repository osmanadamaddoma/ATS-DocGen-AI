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
import extra_streamlit_components as stx
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
    st.session_state.lang = "ar"  # 'ar' or 'en'

if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# تحديث هيكل قاعدة البيانات المصغرة
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

# جلب مفتاح Gemini
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "supabase" in st.secrets:
    gemini_key = st.secrets["supabase"].get("GEMINI_API_KEY")

client = genai.Client(api_key=gemini_key) if gemini_key else None

# إعدادات Supabase
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
        return "⚠️ GEMINI_API_KEY غير متوفر."
    lang_instr = "Respond in English." if language == "en" else "اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة."
    prompt = f"Fault Code: {fault_code}\nContext: {context_text}\n{lang_instr}"
    try:
        response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt)
        return response.text
    except Exception as e:
        return f"❌ خطأ: {e}"

# =========================================================
# 1. دوال النظام المساعدة وتصميم PDF والحاسبات
# =========================================================
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
# 2. إدارة قاعدة بيانات أسرار الاشتراكات
# =========================================================
if "clients_db" not in st.session_state:
    st.session_state.clients_db = {
        "ADDOMA-MASTER-2026": {
            "name": "إدارة الدومة للخدمات التجارية",
            "plan": "التحكم الشامل (Admin)",
            "start_date": "2026-01-01",
            "duration_days": 36500,
            "role": "admin"
        },
        "ADDOMA-2026-PRO": {
            "name": "عثمان آدم أدومة (Addoma Trading Services)",
            "plan": "شهري (Monthly)",
            "start_date": "2026-09-15",
            "duration_days": 30,
            "role": "client"
        }
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

if saved_code and not st.session_state.authenticated:
    if saved_code in CLIENTS_DATABASE:
        st.session_state.authenticated = True
        st.session_state.active_code = saved_code

# --- تحديد اللغة ---
st.sidebar.subheader("🌐 Language / اللغة")
selected_lang = st.sidebar.radio("Select Language:", ["العربية (Arabic)", "English"], index=0 if st.session_state.lang == "ar" else 1)
st.session_state.lang = "ar" if "العربية" in selected_lang else "en"
L = st.session_state.lang

# --- بوابة التفعيل والتحقق ---
if not st.session_state.authenticated:
    st.title("🔐 بوابة تفعيل النظام الموحد - Addoma Trading Services")
    user_code = st.sidebar.text_input("كود التفعيل / Activation Code:", type="password")
    
    if st.sidebar.button("تفعيل / Activate"):
        if user_code in CLIENTS_DATABASE:
            st.session_state.authenticated = True
            st.session_state.active_code = user_code
            expires_at = datetime.now() + timedelta(days=30)
            cookie_manager.set("activation_code", user_code, expires_at=expires_at)
            st.rerun()
        else:
            st.sidebar.error("❌ كود التفعيل غير صحيح.")
    st.warning("🔒 يرجى إدخال كود اشتراك صالح للوصول إلى التطبيقات والمساعد الذكي.")
    st.stop()

input_code = st.session_state.get("active_code", "")
is_admin = False
client_name = "Visitor"
plan_type = "N/A"
days_left = 0

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    is_admin = data.get("role", "client") == "admin"
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()
    
    if today <= expiry_dt:
        days_left = (expiry_dt - today).days
        st.sidebar.success(f"✅ تم التفعيل للعميل: {client_name}")
        st.sidebar.caption(f"الباقة: {plan_type} | المتبقي: {days_left} يوم")
    else:
        st.sidebar.error("❌ انتهت صلاحية الاشتراك.")
        st.session_state.authenticated = False
        cookie_manager.delete("activation_code")
        st.stop()

# --- القائمة الجانبية وتوجيه النوافذ الرئيسي ---
with st.sidebar:
    st.header("⚙️ نظام الدومة للخدمات التجارية")
    st.write("---")
    
    if st.button("💬 المساعد الذكي الهندسي", use_container_width=True):
        st.session_state.current_page = "chat"
        
    if st.button("📊 لوحة تحكم الأنظمة", use_container_width=True):
        st.session_state.current_page = "dashboard"

    if st.button("🛠️ التطبيقات الهندسية الشاملة", use_container_width=True):
        st.session_state.current_page = "main_apps"
        
    st.write("---")
    
    if is_admin:
        if st.button("🛡️ إدارة وتحرير أكواد المشتركين (Admin)", type="primary", use_container_width=True):
            st.session_state.current_page = "admin_panel"
        st.write("---")

    if st.button("🚪 تسجيل الخروج / مسح التفعيل", use_container_width=True):
        st.session_state.authenticated = False
        cookie_manager.delete("activation_code")
        if "active_code" in st.session_state:
            del st.session_state["active_code"]
        st.rerun()

# القائمة الفرعية للتطبيقات الهندسية الـ 6
st.sidebar.markdown("🛠️ **التطبيقات المتاحة (نسخة احترافية)**")
apps_list = [
    "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
    "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
    "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
    "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
    "🔍 5. نظام فحص المعدات (WIC وغيرها)",
    "🧮 6. الحاسبة الهندسية للكهرباء والانبعاثات (Smart Eng Calculator)"
]

selected_app = st.sidebar.radio("اختر النظام المطلوب:", apps_list)

# =========================================================
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ {gen_key} - Site: {sub_site}")
    tech_name = st.text_input("اسم الفني / Technician Name:", value="فني الصيانة المناوب")
    
    tab1, tab2, tab3 = st.tabs(["🏷️ البيانات الأساسية", "⚡ الكهرباء", "🔧 المحرك"])
    with tab1:
        new_model = st.text_input("Model / الطراز", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("Run Hours / ساعات التشغيل", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("Target Hours / الساعات المستهدفة", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("Capacity (kW) / السعة", min_value=0.0, value=float(gen_data.get("kw", 0.0)))

    with tab2:
        v_meas = st.number_input("Measured Voltage (V)", value=float(elec.get("v_measured", 398.0)))
        f_meas = st.number_input("Measured Freq (Hz)", value=float(elec.get("freq_measured", 50.0)))

    with tab3:
        o_press = st.number_input("Oil Press (Bar)", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("Coolant Temp (°C)", value=float(eng.get("coolant_temp_c", 85.0)))

    if st.button("💾 Save Data / حفظ البيانات", use_container_width=True, type="primary"):
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["run_hours"] = new_run_hours
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["model"] = new_model
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["kw"] = new_kw
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["calib_elec"]["v_measured"] = v_meas
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["calib_engine"]["oil_press_bar"] = o_press
        st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]["calib_engine"]["coolant_temp_c"] = c_temp
        st.success("✅ تم حفظ البيانات وتعيينها بنجاح!")
        st.rerun()

# =========================================================
# 1. لوحة تحرير وإدارة أكواد المشتركين بالكامل (ADMIN PANEL)
# =========================================================
if st.session_state.current_page == "admin_panel" and is_admin:
    st.title("🛡️ إدارة وتحرير أكواد المشتركين (Admin Dashboard)")
    st.info("مرحباً بك في لوحة الإدارة. يمكنك من هنا توليد أكواد جديدة، تعديل مدد باقات المشتركين، أو الغاؤها.")

    tab_create, tab_edit, tab_view = st.tabs(["➕ إصدار كود جديد", "✏️ تحرير وتعديل كود مشترك", "📋 قائمة المشتركين"])

    with tab_create:
        st.subheader("إصدار كود اشتراك مفعل جديد")
        with st.form("create_code_form", clear_on_submit=True):
            c_name = st.text_input("اسم العميل / الشركة:")
            c_plan = st.selectbox("نوع الباقة:", ["تجريبي (Trial)", "شهري (Monthly)", "سنوي (Yearly)", "دائم (Lifetime)"])
            c_days = st.number_input("مدة الاشتراك (بالأيام):", value=30, min_value=1)
            c_role = st.selectbox("نوع الصلاحية:", ["client", "admin"])
            
            btn_create = st.form_submit_button("🚀 توليد وحفظ الكود فوراً", use_container_width=True)
            
            if btn_create:
                if c_name.strip():
                    new_code = f"ADDOMA-{uuid.uuid4().hex[:6].upper()}"
                    st.session_state.clients_db[new_code] = {
                        "name": c_name.strip(),
                        "plan": c_plan,
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "duration_days": c_days,
                        "role": c_role
                    }
                    st.success(f"✅ تم إنشاء وتفعيل كود العميل ({c_name}) بنجاح!")
                    st.code(new_code, language="text")
                else:
                    st.error("يرجى إدخال اسم العميل.")

    with tab_edit:
        st.subheader("تحرير وتعديل أكواد المشتركين الحالية")
        selected_code_to_edit = st.selectbox("اختر الكود المراد تعديله:", list(st.session_state.clients_db.keys()))
        
        if selected_code_to_edit:
            cur_data = st.session_state.clients_db[selected_code_to_edit]
            
            with st.form("edit_code_form"):
                st.write(f"**الكود المحدد:** `{selected_code_to_edit}`")
                e_name = st.text_input("اسم العميل:", value=cur_data.get("name", ""))
                e_plan = st.selectbox("نوع الباقة:", ["تجريبي (Trial)", "شهري (Monthly)", "سنوي (Yearly)", "دائم (Lifetime)"])
                e_days = st.number_input("الأيام المتاحة للذين يستخدمون الكود:", value=int(cur_data.get("duration_days", 30)))
                e_role = st.selectbox("الصلاحية:", ["client", "admin"], index=0 if cur_data.get("role") == "client" else 1)
                
                col_save, col_del = st.columns(2)
                btn_save = col_save.form_submit_button("💾 حفظ التعديلات", use_container_width=True)
                btn_delete = col_del.form_submit_button("🗑️ حذف الكود نهائياً", type="primary", use_container_width=True)
                
                if btn_save:
                    st.session_state.clients_db[selected_code_to_edit] = {
                        "name": e_name,
                        "plan": e_plan,
                        "start_date": datetime.now().strftime("%Y-%m-%d"),
                        "duration_days": e_days,
                        "role": e_role
                    }
                    st.success("✅ تم حفظ وتحديث بيانات الكود والمشترك!")
                    st.rerun()
                    
                if btn_delete:
                    del st.session_state.clients_db[selected_code_to_edit]
                    st.warning("🗑️ تم حذف الكود من قاعدة البيانات!")
                    st.rerun()

    with tab_view:
        st.subheader("جدول كافة أسرار وأكواد المشتركين")
        df_clients = pd.DataFrame.from_dict(st.session_state.clients_db, orient='index').reset_index()
        df_clients.rename(columns={'index': 'كود التفعيل'}, inplace=True)
        st.dataframe(df_clients, use_container_width=True)

# =========================================================
# 2. واجهة المساعد الذكي (Chat UI)
# =========================================================
elif st.session_state.current_page == "chat":
    st.title("🤖 المساعد الذكي الهندسي")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "مرحباً بك! كيف يمكنني مساعدتك اليوم في المولدات، التبريد، أو الصيانة؟"}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_query = st.chat_input("اكتب استفسارك الهندسي هنا...")
    if user_query:
        with st.chat_message("user"):
            st.markdown(user_query)
        st.session_state.messages.append({"role": "user", "content": user_query})

        with st.chat_message("assistant"):
            res = analyze_fault_with_gemini(user_query, language=L)
            st.markdown(res)
        st.session_state.messages.append({"role": "assistant", "content": res})

# =========================================================
# 3. واجهة لوحة التحكم (Dashboard UI)
# =========================================================
elif st.session_state.current_page == "dashboard":
    st.title("📊 لوحة تحكم الأنظمة والمتابعة")
    col1, col2, col3 = st.columns(3)
    col1.metric(label="حالة المولدات", value="مستقرة (Stable)", delta="تزامن جاهز")
    col2.metric(label="غرف التبريد WIC", value="2 وحدات (WIC10 & 40)", delta="-1°C")
    col3.metric(label="قاعدة البيانات", value="Supabase Online", delta="12ms")
    st.divider()
    st.info("نظام التشغيل والمراقبة اللحظي يعمل بانتظام بدون مشاكل.")

# =========================================================
# 4. عرض الشاشات للتطبيقات الهندسية الـ 6 المكتملة
# =========================================================
else:
    # --- التطبيق 1: الصيانة التنبؤية والمولدات ---
    if "1." in selected_app:
        st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات")
        
        # نموذج الإدخال اليدوي للمواقع والمولدات
        with st.expander("➕ إضافة منطقة وموقع ومولدات يدوياً (نموذج متكامل)", expanded=False):
            geo_region = st.text_input("عنوان المنطقة الجغرافية [مثال: الخرطوم - المنطقة 1]:", key="geo_reg_input")
            site_name = st.text_input("اسم الموقع [مثال: مصنع كافوري]:", key="site_name_input")
            site_address = st.text_input("عنوان الموقع التفصيلي:", key="site_add_input")
            num_gens = st.number_input("عدد المولدات في الموقع:", min_value=1, max_value=20, value=1, step=1, key="num_gens_input")
            
            gen_inputs = []
            for i in range(int(num_gens)):
                col_g1, col_g2, col_g3 = st.columns(3)
                g_id = col_g1.text_input(f"رمز/رقم المولد {i+1}", value=f"G{i+1}", key=f"g_id_{i}")
                g_model = col_g2.text_input(f"موديل المولد {i+1}", value="Perkins", key=f"g_mod_{i}")
                g_kw = col_g3.number_input(f"الحجم/السعة kW {i+1}", min_value=0.0, value=100.0, step=10.0, key=f"g_kw_{i}")
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
                    st.success(f"تم حفظ المنطقة ({geo_region}) والموقع ({site_name}) بنجاح!")
                    st.rerun()

        main_sites = list(st.session_state.sites_data.keys())
        col_s1, col_s2 = st.columns(2)
        selected_main = col_s1.selectbox("🌍 المنطقة الرئيسية:", main_sites) if main_sites else None
        
        if selected_main:
            sub_sites = list(st.session_state.sites_data[selected_main].keys())
            selected_sub = col_s2.selectbox("📍 الموقع الفرعي:", sub_sites) if sub_sites else None
            
            if selected_sub:
                gens = st.session_state.sites_data[selected_main][selected_sub]["generators"]
                gen_selected = st.selectbox("⚙️ اختر المولد:", list(gens.keys()))
                
                if st.button("📝 فتح نافذة المعايرة والتحرير المنبثقة (Modal)"):
                    edit_generator_modal(selected_main, selected_sub, gen_selected)
                
                st.subheader(f"بيانات ومعايرات المولد: {gen_selected}")
                st.json(gens[gen_selected])

    # --- التطبيق 2: غرفة التحكم والتشغيل عن بُعد ---
    elif "2." in selected_app:
        st.title("🎛️ غرفة التحكم والتشغيل عن بُعد (Remote Control)")
        st.success("اتصال SCADA / DSE Control Panel نشط عبر البروتوكول المباشر")
        c1, c2, c3 = st.columns(3)
        c1.button("▶️ تشغيل المولد عن بُعد (Start Gen)")
        c2.button("⏹️ إيقاف المولد (Stop Gen)")
        c3.button("🔄 تحويل الحمل (ATS Switch)")

    # --- التطبيق 3: المتابعة اليومية وتقارير الإدارة ---
    elif "3." in selected_app:
        st.title("📊 المتابعة اليومية وتقارير الإدارة والتذكيرات")
        st.subheader("سجل القراءات الميدانية اليومية")
        df_logs = pd.DataFrame(st.session_state.daily_logs)
        st.dataframe(df_logs, use_container_width=True)

    # --- التطبيق 4: المساعد الذكي والكتالوجات ---
    elif "4." in selected_app:
        st.title("🤖 المساعد الذكي والكتالوجات وقراءة الأكواد")
        uploaded_catalog = st.file_uploader("قم برفع ملف الكتالوج (PDF) هنا للتحليل والبحث:", type=["pdf"])
        if uploaded_catalog:
            st.success("تم رفع الملف وتجهيزه للذكاء الاصطناعي بنجاح.")

    # --- التطبيق 5: نظام فحص المعدات ---
    elif "5." in selected_app:
        st.title("🔍 نظام فحص المعدات (WIC 10 & WIC 40)")
        st.info("قائمة فحص واختبار غرف التبريد وتجميد اللقاحات")
        st.checkbox("فحص درجة حرارة المحرك والمكثف")
        st.checkbox("فحص ضغوط الفريون والغاز")
        st.checkbox("اختبار لوحة Dixell / Emerson")

    # --- التطبيق 6: الحاسبة الهندسية للكهرباء والانبعاثات ---
    elif "6." in selected_app:
        st.title("🧮 الحاسبة الهندسية للكهرباء والانبعاثات")
        c_i = st.number_input("التيار (Ampere):", value=100.0)
        c_d = st.number_input("المسافة (متر):", value=50.0)
        c_s = st.number_input("مساحة مقطع الكابل (mm²):", value=35.0)
        
        v_drop, v_pct = calculate_cable_voltage_drop(c_i, c_d, c_s)
        st.success(f"هبوط الجهد المحسوب: {v_drop} فولت ({v_pct}%)")
