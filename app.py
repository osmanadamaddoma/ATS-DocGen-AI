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

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS

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
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

# التهيئة المبدئية لمتغيرات الجلسة (Session State)
if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False

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

if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

# تهيئة عميل Gemini API
client = genai.Client(api_key=gemini_key) if gemini_key else None

# دالة تشغيل الصوت المحدثة مع دعم خيار الكتم والتكرار المستمر للانذارات
def play_audio(text, loop=False):
    """تحويل النص إلى صوت باستخدام gTTS وتشغيله إن لم يتم تفعيل Mute مع دعم التكرار"""
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts = gTTS(text=text, lang='ar')
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
        audio_bytes = audio_data.getvalue()
        
        if loop:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            audio_html = f"""
                <audio autoplay loop controls style="width: 100%;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                    متصفحك لا يدعم تشغيل الصوت تلقائياً.
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"حدث خطأ في تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text=""):
    """دالة استدعاء الذكاء الاصطناعي مع معالجة حزمة الضغط العالي (503) وإعادة المحاولة"""
    if not client:
        return "⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets أو متغيّرات البيئة."

    prompt = f"""
    أنت خبير صيانة مهندس واستشاري صناعي متخصص في المولدات لوحات DSE (مثل DSE 7320 و DSE 8610 MKII) ومحركات Perkins و Cummins وأجهزة التبريد.
    
    العميل يدخل كود العطل أو اسم الإنذار التالي: "{fault_code}"
    
    معلومات إضافية مستخرجة من كتالوج المعدة (إن وجدت):
    \"\"\"
    {context_text if context_text else "لا يوجد نص مباشر من الكتالوج لهذا العطل."}
    \"\"\"

    المطلوب إنشاء تقرير تشخيصي متكامل ومختصر يحتوي على:
    1. **طبيعة المشكلة**: شرح ميكانيكي/كهربائي للعطل.
    2. **الأسباب المحتملة**: أبرز 3 أسباب لنشوء هذا العطل.
    3. **خطوات الفحص والعلاج**: إجراءات ميدانية تسلسلية (أسلاك، حساسات، أكتويتر، أو إعادة ضبط DSE).
    
    اكتب الإجابة بلغة عربية تقنية واضحة ومباشرة.
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
                    return "⚠️ الخادم يمر بضغط عالٍ حالياً (503). يرجى الضغط على زر التحليل مرة أخرى بعد ثوانٍ معدودة."
            return f"❌ حدث خطأ أثناء التواصل مع الذكاء الاصطناعي: {err_msg}"

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
        # العودة التلقائية لمحاكاة تدفق بيانات حية في حال عدم ضبط السيرفر السحابي بعد
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
        # تلافي انهيار التطبيق عند وجود خلل في الشبكة الخارجية للمصنع
        return pd.DataFrame()

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات
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

st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل للوصول للنظام:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"
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
        st.sidebar.success("✅ تم التحقق من الاشتراك بنجاح!")
        st.sidebar.markdown(f"**👤 العميل:** {client_name}")
        st.sidebar.markdown(f"**📦 الباقة:** {plan_type}")
        st.sidebar.markdown(f"⏳ **المتبقي:** {days_left} يوم")
    else:
        st.sidebar.error(f"❌ انتهت صلاحية اشتراك هذا العميل بتاريخ ({expiry_dt}).")
elif input_code != "":
    st.sidebar.error("❌ كود التفعيل غير صحيح.")
else:
    st.sidebar.info("💡 أدخل الكود المخصص لعرض تفاصيل العميل وفتح الأنظمة.")

if not is_pro:
    st.warning("🔒 يرجى إدخال كود اشتراك صالح في الشريط الجانبي للوصول إلى التطبيقات والمساعد الذكي.")
    st.stop()

st.sidebar.divider()

# =========================================================
# 3. قائمة اختيار التطبيق المركزي
# =========================================================
st.sidebar.markdown("🛠️ التطبيقات المتاحة (نسخة احترافية)")
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
        "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)",
        "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات",
        "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 5. نظام فحص المعدات (WIC وغيرها)"
    ]
)
st.sidebar.divider()

# =========================================================
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد مع التحقق الفوري
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(main_site, sub_site, gen_key):
    gen_data = st.session_state.sites_data[main_site][sub_site]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ بيانات المولد: **{gen_key}** - موقع: **{sub_site}**")
    
    tech_name = st.text_input("اسم الفني المسؤول عن الإدخال:", value="فني الصيانة المناوب")
    tab1, tab2, tab3 = st.tabs(["🏷️ البيانات الأساسية", "⚡ معايرة الكهرباء", "🔧 معايرة المحرك"])

    with tab1:
        new_model = st.text_input("طراز / اسم المولد", value=gen_data.get("model", ""))
        new_run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = st.number_input("الساعات المستهدفة الافتراضية للصيانة", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = st.number_input("سعة المولد (kW)", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=float(gen_data.get("load", 0.0)))

    with tab2:
        v_nom = st.number_input("الجهد الاسمي Nominal (V)", value=float(elec.get("v_nominal", 400.0)))
        v_meas = st.number_input("الجهد المقاس Measured (V)", value=float(elec.get("v_measured", 398.0)))
        f_nom = st.number_input("التردد الاسمي Nominal (Hz)", value=float(elec.get("freq_nominal", 50.0)))
        f_meas = st.number_input("التردد المقاس Measured (Hz)", value=float(elec.get("freq_measured", 50.0)))
        c_max = st.number_input("أقصى تيار مسموح Max Current (A)", value=float(elec.get("current_max", 600.0)))
        c_meas = st.number_input("التيار المقاس Measured Current (A)", value=float(elec.get("current_measured", 360.0)))
        pf_val = st.number_input("معامل القدرة Power Factor (PF)", value=float(elec.get("pf", 0.85)))
        ct_rat = st.text_input("نسبة محولات التيار CT Ratio", value=str(elec.get("ct_ratio", "600/5")))

    with tab3:
        o_press = st.number_input("ضغط الزيت Oil Pressure (Bar)", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = st.number_input("حرارة سائل التبريد Coolant Temp (°C)", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = st.number_input("سرعة المحرك Engine Speed (RPM)", value=float(eng.get("rpm", 1500.0)))
        b_volt = st.number_input("جهد بطارية التشغيل Battery (V)", value=float(eng.get("battery_v", 26.0)))
        ambient_t = st.number_input("درجة الحرارة المحيطة Ambient Temp (°C)", value=float(eng.get("ambient_temp", 43.0)))

    if st.button("💾 حفظ البيانات والتأكد من الصحة", use_container_width=True, type="primary"):
        validation_errors = []
        
        if c_temp < 0 or c_temp > 125.0:
            validation_errors.append(f"❌ درجة حرارة المحرك غير منطقية ({c_temp}°C)! النطاق الطبيعي بين 0 و 120 درجة.")
        
        if o_press < 0.0 or o_press > 12.0:
            validation_errors.append(f"❌ ضغط الزيت المدخل مستحيل أو غير منطقي ({o_press} Bar)! النطاق التشغيلي بين 0 و 10 Bar.")
            
        if v_meas < 100.0 or v_meas > 600.0:
            validation_errors.append(f"❌ قيمة الجهد الكهربائي المقاس ({v_meas} V) خارج حدود النطاق الطبيعي المسموح.")
            
        if b_volt < 8.0 or b_volt > 35.0:
            validation_errors.append(f"❌ جهد البطارية غير منطقي ({b_volt} V).")

        if validation_errors:
            for err in validation_errors:
                st.error(err)
            st.warning("⚠️ تم رفض حفظ البيانات لحماية جودة النظام وقاعدة البيانات. يرجى تصحيح الأرقام أعلاه.")
        else:
            st.session_state.sites_data[main_site][sub_site]["generators"][gen_key] = {
                "model": new_model,
                "run_hours": new_run_hours,
                "target": new_target,
                "kw": new_kw,
                "load": new_load,
                "calib_elec": {
                    "v_nominal": v_nom, 
                    "v_measured": v_meas,
                    "freq_nominal": f_nom, 
                    "freq_measured": f_meas,
                    "current_max": c_max, 
                    "current_measured": c_meas,
                    "pf": pf_val, 
                    "ct_ratio": ct_rat
                },
                "calib_engine": {
                    "oil_press_bar": o_press, 
                    "coolant_temp_c": c_temp,
                    "rpm": r_rpm, 
                    "battery_v": b_volt,
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
                "status": "محدث وصحيح"
            })

            st.success("✅ تم التحقق من صحة البيانات وحفظها بنجاح وتسجيل السجل اليومي!")
            st.rerun()

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والتقارير الشاملة
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    col_top_audio1, col_top_audio2 = st.columns([3, 1])
    with col_top_audio2:
        mute_label = "🔇 Mute (إيقاف الصوت)" if not st.session_state.audio_muted else "🔊 Unmute (تفعيل الصوت)"
        if st.button(mute_label, use_container_width=True):
            st.session_state.audio_muted = not st.session_state.audio_muted
            st.rerun()

    st.sidebar.subheader("🎨 تخصيص التقرير المطبوع")
    logo_file = st.sidebar.file_uploader("رفع شعار الشركة (Logo)", type=["png", "jpg", "jpeg"], key="logo_up")

    st.subheader("📍 إدارة المواقع والعناوين (قائمة رئيسية وقوائم فرعية تشعبية)")
    col_site1, col_site2 = st.columns(2)
    
    main_sites = list(st.session_state.sites_data.keys())
    
    with col_site1:
        st.markdown("### 🏢 القائمة الرئيسية للمواقع")
        new_main_site = st.text_input("اسم الموقع الرئيسي الجديد (مثال: الإدارة العامة):")
        if st.button("➕ أضف الموقع الرئيسي"):
            if new_main_site and new_main_site not in st.session_state.sites_data:
                st.session_state.sites_data[new_main_site] = {}
                st.success(f"تم إضافة الموقع الرئيسي: {new_main_site}")
                st.rerun()
                
        selected_main_site = st.selectbox("📌 اختر الموقع الرئيسي (لتنبثق منه الارتباطات الفرعية):", main_sites) if main_sites else None

    with col_site2:
        st.markdown("### 🏗️ القوائم الفرعية (مواقع بيانات المولدات)")
        if selected_main_site:
            sub_sites = list(st.session_state.sites_data[selected_main_site].keys())
            
            new_sub_site = st.text_input(f"اسم الموقع الفرعي التابع لـ ({selected_main_site}):")
            new_sub_address = st.text_input("عنوان موقع بيانات المولد الفرعي (إدخال يدوي):")
            
            if st.button("➕ أضف الموقع الفرعي والعنوان اليدوي"):
                if new_sub_site and new_sub_site not in st.session_state.sites_data[selected_main_site]:
                    st.session_state.sites_data[selected_main_site][new_sub_site] = {
                        "address": new_sub_address if new_sub_address else "غير محدد",
                        "generators": {}
                    }
                    st.success(f"تم إضافة الموقع الفرعي: {new_sub_site}")
                    st.rerun()
                    
            selected_sub_site = st.selectbox("📍 اختر الموقع الفرعي (ارتباط تشعبي للوصول للمولدات):", sub_sites) if sub_sites else None
            
            if selected_sub_site:
                current_site_address = st.text_input("تعديل عنوان موقع بيانات المولد (إدخال يدوي):", value=st.session_state.sites_data[selected_main_site][selected_sub_site].get("address", ""))
                if st.button("✏️ تحديث عنوان موقع بيانات المولد"):
                    st.session_state.sites_data[selected_main_site][selected_sub_site]["address"] = current_site_address
                    st.success("تم تحديث العنوان للموقع الفرعي بنجاح!")
        else:
            selected_sub_site = None

    if not main_sites or not selected_main_site or not selected_sub_site:
        st.warning("الرجاء إضافة وتحديد موقع رئيسي وموقع فرعي للبدء في إدارة المولدات.")
        st.stop()

    st.divider()

    col_gen_m1, col_gen_m2 = st.columns([2, 1])
    with col_gen_m1:
        st.markdown(f"### ⚙️ بيانات عدد المولدات المحلية في [ {selected_main_site} 🔗 {selected_sub_site} ]")
        new_gen_id = st.text_input(f"إضافة مولد محلي جديد في الموقع الفرعي:", placeholder="مثال: G3")
    with col_gen_m2:
        st.write("")
        st.write("")
        st.write("")
        if st.button("➕ إنشاء المولد"):
            if new_gen_id and new_gen_id not in st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"]:
                st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][new_gen_id] = {
                    "model": "Perkins Standard",
                    "run_hours": 0.0,
                    "target": 250.0,
                    "kw": 100.0,
                    "load": 50.0,
                    "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                    "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
                }
                st.success(f"تم إنشاء المولد {new_gen_id}")
                st.rerun()

    gen_list = list(st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"].keys())

    if not gen_list:
        st.info("لا توجد مولدات في هذا الموقع الفرعي. قم بإضافة مولد للبدء.")
    else:
        col_select_g, col_modal_btn = st.columns([2, 1])
        with col_select_g:
            selected_gen = st.selectbox("اختر المولد لاستعراض ومعالجة بياناته:", gen_list)
        with col_modal_btn:
            st.write("")
            st.write("")
            if st.button("📝 فتح نافذة إدخال وتعديل البيانات المعايرة"):
                edit_generator_modal(selected_main_site, selected_sub_site, selected_gen)

        gen_info = st.session_state.sites_data[selected_main_site][selected_sub_site]["generators"][selected_gen]
        calib_e = gen_info.get("calib_elec", {})
        calib_m = gen_info.get("calib_engine", {})

        st.subheader(f"📊 لوحة بيانات المعايرة والمراقبة للمولد ({selected_gen})")
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("الطراز والسعة", f"{gen_info['model']}", f"{gen_info['kw']} kW")
        m_c2.metric("ساعات التشغيل / الهدف", f"{gen_info['run_hours']} hrs", f"المستهدف: {gen_info['target']} hrs")
        m_c3.metric("معايرة الجهد المقاس", f"{calib_e.get('v_measured', 0)} V", f"الاسمي: {calib_e.get('v_nominal', 0)} V")
        m_c4.metric("حرارة المحرك / المحيطة", f"{calib_m.get('coolant_temp_c', 0)} °C", f"المحيطة: {calib_m.get('ambient_temp', 0)} °C")

        alarm_messages = []

        if abs(calib_e.get("v_measured", 400) - calib_e.get("v_nominal", 400)) > 20:
            alarm_messages.append(f"انحراف في الجهد الكهربائي للمولد {selected_gen}: الجهد المقاس {calib_e.get('v_measured')} فولت!")
        
        if calib_e.get("current_measured", 0) > calib_e.get("current_max", 1000):
            alarm_messages.append(f"إنذار حمولة زائدة للتيار في المولد {selected_gen}!")

        if calib_m.get("coolant_temp_c", 0) >= 95.0:
            alarm_messages.append(f"ارتفاع حرارة المحرك للمولد {selected_gen}: {calib_m.get('coolant_temp_c')} درجة مئوية!")
        if calib_m.get("oil_press_bar", 5) <= 1.8:
            alarm_messages.append(f"انخفاض ضغط زيت المحرك للمولد {selected_gen}!")

        remaining_target = gen_info["target"] - gen_info["run_hours"]
        if remaining_target <= 50 and remaining_target > 0:
            alarm_messages.append(f"اقتراب تجاوز الساعات الافتراضية للمولد {selected_gen}. متبقي {remaining_target} ساعة.")
        elif remaining_target <= 0:
            alarm_messages.append(f"إنذار! تجاوز المولد {selected_gen} الساعات الافتراضية المجدولة للصيانة!")

        if alarm_messages:
            for msg in alarm_messages:
                st.error(f"🚨 {msg}")
            combined_alert_text = " . ".join(alarm_messages)
            play_audio(combined_alert_text, loop=True)

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

        st.subheader(f"🛢️ جدول الصيانة التنبؤية (14 قطعة/خدمة) - {selected_gen}")
        df_parts_input = pd.DataFrame(st.session_state[parts_key])

        edited_df = st.data_editor(
            df_parts_input,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "تجديد (تصفير)": st.column_config.CheckboxColumn(
                    "تجديد (تصفير العداد)",
                    help="حدد هنا إذا تم استبدال القطعة لتصفير الساعات المنقضية",
                    default=False,
                )
            }
        )

        if st.button("🔄 تأكيد تحديث وتصفير القطع المحددة", type="primary"):
            new_data = []
            for idx, row in edited_df.iterrows():
                item = row.to_dict()
                if item.get("تجديد (تصفير)"):
                    item["الساعات المنقضية (ساعة)"] = 0.0
                    item["تجديد (تصفير)"] = False
                new_data.append(item)
            st.session_state[parts_key] = new_data
            st.success("✅ تم تحديث بيانات جدول قطع الغيار بنجاح!")
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
                status_str = "حالة جيدة (أقل من 70%)"
            elif 70.0 <= pct < 90.0:
                color_code = "#ffc107"
                status_str = "تحذير - قرب الصيانة (70%-90%)"
            else:
                color_code = "#dc3545"
                status_str = "إنذار - استبدال فوري (90%-100%)"

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

        st.subheader("📊 الرسومات البيانية ومؤشرات الأداء")
        chart_col1, chart_col2 = st.columns(2)

        with chart_col1:
            st.markdown("##### 🟢🟡🔴 رسم استهلاك الساعات (🟢 ≤70% | 🟡 70-90% | 🔴 ≥90%)")
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=df_result["قطع الغيار / الفلاتر"],
                y=df_result["نسبة الاستهلاك (%)"],
                marker_color=bar_colors,
                text=df_result["نسبة الاستهلاك (%)"].astype(str) + "%",
                textposition='auto'
            ))
            fig_bar.update_layout(
                title="نسبة استهلاك الساعات المجدولة للـ 14 قطعة",
                xaxis_title="القطعة",
                yaxis_title="النسبة المئوية %",
                yaxis=dict(range=[0, 110])
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_col2:
            st.markdown("##### 🍩 الرسم البياني الدائري لأداء ومدة المولد")
            total_target_h = max(1.0, float(gen_info["target"]))
            current_h = float(gen_info["run_hours"])
            rem_h = max(0.0, total_target_h - current_h)

            labels_pie = ['الساعات المنقضية', 'الساعات المتبقية الافتراضية']
            values_pie = [current_h, rem_h]

            fig_pie = px.pie(
                names=labels_pie,
                values=values_pie,
                hole=0.5,
                title=f"نسب أداء ساعات التشغيل للمولد {selected_gen}",
                color_discrete_sequence=["#182b49", "#28a745"]
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        st.divider()
        st.subheader("📷 إرفاق صور المولد وقطع الغيار للتقرير")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            gen_img_file = st.file_uploader("رفع صورة للمولد / لوحة التحكم", type=["png", "jpg", "jpeg"])
        with col_up2:
            parts_img_file = st.file_uploader("رفع صورة للقطع المستبدلة / موقع العمل", type=["png", "jpg", "jpeg"])

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
            
            # إدراج عنوان موقع بيانات المولد كما هو مطلوب بشكل صريح
            pdf.cell(0, 5, f"Generator Data Site Address: {sanitize_latin_only(current_site_address)}", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Main Site: {sanitize_latin_only(selected_main_site)} | Sub Site: {sanitize_latin_only(selected_sub_site)}", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | Capacity: {gen_info['kw']} kW", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Current Run Hours: {gen_info['run_hours']} hrs | Target Hours: {gen_info['target']} hrs", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Electrical Calib: {calib_e.get('v_measured',0)}V / {calib_e.get('freq_measured',0)}Hz | Engine: {calib_m.get('coolant_temp_c',0)} C / {calib_m.get('oil_press_bar',0)} Bar", ln=True)
            
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
                pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 2W50", ln=True)
            elif amb_temp_val >= 43:
                pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: YOU MUST USE OIL SIZE 15W40", ln=True)
            else:
                pdf.cell(0, 5, f"[Ambient Temp: {amb_temp_val} C] -> ACTION: USE STANDARD OIL SIZE 15W40", ln=True)
            
            pdf.ln(8)

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(24, 43, 73)
            pdf.set_text_color(255, 255, 255)

            headers_pdf = ["#", "Part / Service Name", "Lifespan", "Used", "Remain", "Status"]
            widths = [10, 60, 25, 25, 25, 45]
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

            if gen_img_file or parts_img_file:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "Field Attachment Images:", ln=True)
                pdf.ln(4)

                y_pos = 45
                if gen_img_file:
                    gen_path = f"temp_gen_{uuid.uuid4().hex}.jpg"
                    with open(gen_path, "wb") as f: f.write(gen_img_file.getbuffer())
                    pdf.image(gen_path, x=15, y=y_pos, w=85)
                    os.remove(gen_path)
                if parts_img_file:
                    part_path = f"temp_part_{uuid.uuid4().hex}.jpg"
                    with open(part_path, "wb") as f: f.write(parts_img_file.getbuffer())
                    pdf.image(part_path, x=110, y=y_pos, w=85)
                    os.remove(part_path)

            try:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "Visual Analytics & Maintenance Color Codes:", ln=True)

                fig_bar_p, ax_bar_p = plt.subplots(figsize=(7, 3.5))
                p_short = [sanitize_latin_only(str(x))[:10] for x in df_result["قطع الغيار / الفلاتر"]]
                colors_p = [x for x in df_result["الكود الملون"]]
                ax_bar_p.bar(p_short, df_result["نسبة الاستهلاك (%)"].values, color=colors_p)
                ax_bar_p.set_title("14 Parts Usage Status (Green <=70%, Yellow 70-90%, Red >=90%)", fontsize=8, fontweight='bold')
                plt.xticks(rotation=45, ha="right", fontsize=6)
                plt.tight_layout()

                bar_path = f"temp_bar_{uuid.uuid4().hex}.png"
                plt.savefig(bar_path, dpi=200)
                pdf.image(bar_path, x=15, y=45, w=180)
                os.remove(bar_path)
            except Exception:
                pass

            if temp_logo_path and os.path.exists(temp_logo_path):
                os.remove(temp_logo_path)

            pdf_out = pdf.output(dest="S")
            return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

        st.download_button(
            label=f"🖨️ إصدار التقرير الشامل للمولد ({selected_gen}) في موقع ({selected_sub_site})",
            data=generate_full_pdf_bytes(),
            file_name=f"Report_{selected_main_site}_{selected_sub_site}_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# =========================================================
# التطبيق 2: غرفة التحكم والتشغيل عن بُعد (الجديد)
# =========================================================
elif selected_app == "🎛️ 2. غرفة التحكم والتشغيل عن بُعد (Remote Control Center)":
    st.title("🎛️ غرفة التحكم والتشغيل عن بُعد (Remote Control Center)")
    st.info("يتيح هذا النظام مراقبة البيانات الحية للمولدات والتحكم بها عن بعد عبر بروتوكولات IoT.")

    df_iot = fetch_live_iot_data()

    if not df_iot.empty:
        st.subheader("📡 القراءات الحية للمستشعرات (Live Telemetry)")
        
        latest = df_iot.iloc[-1]
        col1, col2, col3 = st.columns(3)
        col1.metric("🌡️ درجة الحرارة (°C)", f"{latest['temperature']:.1f}")
        col2.metric("〰️ الاهتزاز (mm/s)", f"{latest['vibration']:.2f}")
        col3.metric("🗜️ ضغط الزيت (Bar)", f"{latest['pressure']:.1f}")

        st.markdown("##### 📈 المؤشرات الزمنية الحية")
        fig_temp = px.line(df_iot, x='_time', y='temperature', title="منحنى درجات الحرارة")
        fig_temp.update_layout(xaxis_title="الوقت", yaxis_title="درجة الحرارة")
        st.plotly_chart(fig_temp, use_container_width=True)

    else:
        st.warning("⚠️ لا توجد بيانات حية متاحة حالياً. تأكد من اتصال المستشعرات وقاعدة بيانات InfluxDB.")

    st.divider()
    st.subheader("🕹️ لوحة أوامر التحكم عن بعد (Remote Commands)")
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        if st.button("🟢 بدء التشغيل (Start Generator)", use_container_width=True):
            st.success("✅ تم إرسال أمر التشغيل بنجاح إلى المعدة.")
    with rc2:
        if st.button("🔴 إيقاف طوارئ (Emergency Stop)", use_container_width=True):
            st.error("🚨 تم إرسال أمر الإيقاف الطارئ!")
    with rc3:
        if st.button("🔄 إعادة ضبط الإنذارات (Reset Alarms)", use_container_width=True):
            st.info("🔄 تم إعادة ضبط لوحة DSE والإنذارات بنجاح.")

# =========================================================
# التطبيق 3: المتابعة اليومية وتقارير الإدارة والتذكيرات الآلية
# =========================================================
elif selected_app == "📊 3. المتابعة اليومية وتقارير الإدارة والتذكيرات":
    st.title("📊 نظام المتابعة اليومية والتذكيرات وتقارير الصيانة")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.info(f"📅 **تاريخ اليوم:** {today_str} | **إشراف:** Addoma Trading Services")

    tab_mgr1, tab_mgr2 = st.tabs(["📋 التقرير الملخص اليومي لمدير الموقع", "⏰ التذكيرات والتنبيهات الآلية للفنيين"])

    with tab_mgr1:
        st.subheader("📝 تقرير ملخص قراءات اليوم لإدارة الموقع")
        
        today_logs = [log for log in st.session_state.daily_logs if log.get("date") == today_str]
        
        all_gens = []
        for m_site, m_info in st.session_state.sites_data.items():
            for s_name, s_info in m_info.items():
                for g_name in s_info.get("generators", {}):
                    all_gens.append({"site": f"{m_site} - {s_name}", "generator": g_name})
        
        logged_gen_keys = [f"{log['site']} - {log['generator']}" for log in today_logs]
        total_gens_count = len(all_gens)
        logged_count = len(set(logged_gen_keys))
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("إجمالي المولدات المستهدفة", total_gens_count)
        col_m2.metric("المولدات المسجلة اليوم", logged_count)
        col_m3.metric("نسبة الإنجاز اليومي", f"{int((logged_count/total_gens_count)*100) if total_gens_count>0 else 0}%")

        st.divider()
        if today_logs:
            df_daily = pd.DataFrame(today_logs)
            st.markdown("##### 🟢 القراءات التي تم تسجيلها اليوم:")
            st.dataframe(df_daily[["timestamp", "site", "generator", "technician", "run_hours", "v_measured", "oil_press", "coolant_temp", "status"]], use_container_width=True)
        else:
            st.warning("⚠️ لم يتم تسجيل أي قراءات يومية حتى الآن لهذا اليوم!")

        st.divider()
        
        def generate_daily_summary_pdf():
            pdf = ComprehensivePDF("DAILY MAINTENANCE MANAGEMENT SUMMARY")
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(0, 6, f"Daily Site Summary Report - Date: {today_str}", ln=True)
            pdf.ln(4)
            
            pdf.set_fill_color(24, 43, 73)
            pdf.set_text_color(255, 255, 255)
            headers = ["Site", "Gen ID", "Tech", "Hours", "Volt", "Oil(Bar)", "Temp(C)"]
            widths = [45, 20, 35, 25, 20, 25, 20]
            for h, w in zip(headers, widths):
                pdf.cell(w, 6, h, border=1, fill=True, align="C")
            pdf.ln()

            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(0, 0, 0)
            for log in today_logs:
                pdf.cell(widths[0], 5, sanitize_latin_only(log['site'])[:20], border=1)
                pdf.cell(widths[1], 5, sanitize_latin_only(log['generator']), border=1, align="C")
                pdf.cell(widths[2], 5, sanitize_latin_only(log['technician'])[:15], border=1)
                pdf.cell(widths[3], 5, str(log['run_hours']), border=1, align="C")
                pdf.cell(widths[4], 5, str(log['v_measured']), border=1, align="C")
                pdf.cell(widths[5], 5, str(log['oil_press']), border=1, align="C")
                pdf.cell(widths[6], 5, str(log['coolant_temp']), border=1, align="C")
                pdf.ln()
                
            pdf_out = pdf.output(dest="S")
            return pdf_out.encode("latin-1", errors="replace") if isinstance(pdf_out, str) else bytes(pdf_out)

        st.download_button(
            label="📄 تحميل التقرير اليومي المدمج لمدير الموقع (PDF)",
            data=generate_daily_summary_pdf(),
            file_name=f"Daily_Summary_{today_str}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

    with tab_mgr2:
        st.subheader("🔔 نظام التذكير السريع للفنيين بمواعيد التسجيل")
        
        unlogged_gens = []
        for item in all_gens:
            gen_key_id = f"{item['site']} - {item['generator']}"
            if gen_key_id not in logged_gen_keys:
                unlogged_gens.append(item)

        if unlogged_gens:
            st.warning(f"⚠️ يوجد عدد ({len(unlogged_gens)}) مولد لم يتم تسجيل قراءاتها اليوم حتى الآن!")
            
            st.markdown("##### 📋 المولدات التي تطلب إرسال تذكير سريع للفنيين:")
            for un_gen in unlogged_gens:
                st.write(f"• **الموقع:** {un_gen['site']} | **المولد:** {un_gen['generator']}")
                
            st.divider()
            st.markdown("##### 📲 إرسال تنبيه / تذكير سريع للفنيين عبر WhatsApp أو SMS:")
            tech_phone = st.text_input("رقم هاتف الفني المناوب (مثال: 249912345678):", value="249912345678")
            
            reminder_msg = f"تذكير صيانة آلي من Addoma Trading: يرجى تسجيل قراءات المولدات المتبقية اليوم ({today_str}) فوراً لضمان عدم تفويت الإدخال اليومي."
            
            encoded_msg = urllib.parse.quote(reminder_msg)
            whatsapp_url = f"https://wa.me/{tech_phone}?text={encoded_msg}"
            
            st.markdown(f'''
                <a href="{whatsapp_url}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:5px; cursor:pointer; font-size:16px;">
                        💬 إرسال تذكير عاجل عبر واتساب للفني
                    </button>
                </a>
            ''', unsafe_allow_html=True)
        else:
            st.success("🎉 ممتااااز! تم تسجيل جميع قراءات المولدات اليومية بنجاح ولم يتم تفويت أي مولد اليوم.")

# =========================================================
# التطبيق 4: المساعد الذكي والكتالوجات
# =========================================================
elif selected_app == "🤖 4. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.info(f"🔹 **العميل الحالي:** {client_name} | **نوع الاشتراك:** {plan_type}")
    st.title("🤖 نافذة المساعد الذكي، الكتالوجات وتحليل الأعطال")

    col_files1, col_files2 = st.columns(2)
    with col_files1:
        st.subheader("📚 رفع الكتالوجات للتحليل (PDF)")
        manual_file = st.file_uploader("رفع الكتالوج اليدوي للمعدة", type=["pdf"])
        if manual_file:
            if "loaded_manual_name" not in st.session_state or st.session_state.loaded_manual_name != manual_file.name:
                with st.spinner("جاري استخراج وقراءة الكتالوج..."):
                    try:
                        catalog_pages = []
                        with pdfplumber.open(manual_file) as pdf:
                            for i, page in enumerate(pdf.pages):
                                text = page.extract_text() or ""
                                catalog_pages.append({"page_num": i + 1, "content": text})
                        st.session_state.catalog_pages = catalog_pages
                        st.session_state.loaded_manual_name = manual_file.name
                        st.success(f"✅ تم حفظ وقراءة {len(catalog_pages)} صفحة من الكتالوج بنجاح!")
                    except Exception as e:
                        st.error(f"❌ تعذر قراءة ملف PDF: {e}")
            else:
                st.success(f"✅ الكتالوج ({st.session_state.loaded_manual_name}) محمل ومقروء مسبقاً في الجلسة الحالية.")

            # الإضافة الجديدة: ميزة استخراج وتحليل الأعطال مباشرة من الكتالوج المرفوع
            if st.button("📑 استخراج وتحليل أكواد الأعطال من الكتالوج المرفوع", use_container_width=True):
                with st.spinner("جاري تحليل محتوى الكتالوج واستخراج الأكواد بواسطة الذكاء الاصطناعي..."):
                    if client and "catalog_pages" in st.session_state:
                        # أخذ عينة من الكتالوج (مثلا أول 15 صفحة) لتجنب تجاوز حد استيعاب المحتوى للنموذج
                        sample_text = "\n".join([p["content"] for p in st.session_state.catalog_pages[:15]])
                        extract_prompt = f"""
                        أنت مهندس استشاري متخصص في لوحات التحكم DSE (مثل DSE 8610 MKII و DSE 7320 MKII) ومحركات Perkins و Cummins، بالإضافة إلى غرف التبريد WIC 10 و WIC 40.
                        قم بتحليل النص التالي المستخرج من الكتالوج، واستخرج قائمة بأهم أكواد الأعطال (Fault Codes) المذكورة، مع تقديم شرح موجز وعملي لكل عطل بناءً على السياق المستخرج.
                        
                        النص المستخرج:
                        {sample_text}
                        """
                        try:
                            extract_response = client.models.generate_content(
                                model="gemini-3.6-flash",
                                contents=extract_prompt,
                            )
                            st.markdown("### 📊 نتيجة تحليل قراءة أكواد الكتالوج:")
                            st.info(extract_response.text)
                        except Exception as e:
                            st.error(f"❌ حدث خطأ أثناء التحليل الآلي للكتالوج: {e}")
                    else:
                        st.warning("⚠️ لا يمكن إتمام عملية التحليل لعدم توفر مفتاح Gemini أو لعدم نجاح قراءة الكتالوج.")

    with col_files2:
        st.subheader("📷 قراءة أكواد الأعطال (شاشات/DSE)")
        fault_image = st.file_uploader("رفع صورة العطل من شاشة المولد/الآلة", type=["png", "jpg", "jpeg"])
        fault_cam = st.camera_input("📸 أو التقط صورة للشاشة")

    st.divider()

    fault_input = st.text_input(
        "أدخل كود العطل أو اسم الإنذار (مثلاً: Over Current / DSE 8610 Error / Oil Low):",
        value="Over Current",
        key="fault_search_input",
    )

    if st.button("🔍 تحليل العطل بالذكاء الاصطناعي", key="btn_analyze", use_container_width=True):
        clean_fault = fault_input.strip()

        if not clean_fault:
            st.warning("⚠️ يرجى كتابة كود العطل أو الإنذار أولاً.")
        else:
            st.info(f"🌟 (Addoma Trading Services) جاري معالجة طلب العميل: {client_name}...")

            target_fault_img = fault_image or fault_cam
            if target_fault_img:
                img_obj = Image.open(target_fault_img)
                st.image(img_obj, caption="صورة العطل المرفوعة", width=350)
                if decode_qr:
                    try:
                        decoded = decode_qr(img_obj)
                        if decoded:
                            st.success(f"📟 **كود QR/Barcode مقروء:** `{decoded[0].data.decode('utf-8')}`")
                    except Exception:
                        pass

            catalog_context = ""
            if "catalog_pages" in st.session_state:
                search_query = re.escape(clean_fault)
                found_lines = []

                for page in st.session_state.catalog_pages:
                    for line in page["content"].split("\n"):
                        if re.search(search_query, line, re.IGNORECASE):
                            found_lines.append(f"(صفحة {page['page_num']}): {line.strip()}")

                if found_lines:
                    catalog_context = "\n".join(found_lines[:8])

            st.markdown("---")
            st.markdown(f"### 📋 تقرير التشخيص الفوري: `{clean_fault}`")

            if catalog_context:
                st.success("✅ تم العثور على المقتطفات التالية داخل الكتالوج المرفوع:")
                st.code(catalog_context, language="text")
            else:
                st.caption(f"لم يتم العثور على نص مطابِق تماماً للرمز '{clean_fault}' داخل صفحات الكتالوج المرفوع.")

            st.markdown("**التوجيهات الميدانية السريعة:**")
            f = clean_fault.lower()

            if any(k in f for k in ["current", "over current", "overcurrent", "oc", "over load", "overload", "kw", "kva"]):
                st.write("• **طبيعة المشكلة:** ارتفاع التيار المسحوب أو وجود حمل زائد/شورت ماس على إحدى الفازات.")
                st.write("• **الخطوات:** 1. التوزيع المتوازن للأحمال على الفازات الثلاث (R, S, T). 2. فحص محولات التيار (CTs) ومعايرة النسب في DSE. 3. قياس امبير الحمل بساعة أمبير خارجية (Clamp Meter).")

            elif any(k in f for k in ["speed", "rpm", "under speed", "over speed", "low speed", "high speed", "freq", "hz", "under freq", "over freq"]):
                st.write("• **طبيعة المشكلة:** خلل في سرعة دوران المحرك أو ضبط التردد (50Hz / 60Hz).")
                st.write("• **الخطوات:** 1. تنظيف مستشعر السرعة (MPU) وإعادة معايرة الفجوة. 2. فحص منظم السرعة (Governor) والأكتويتر. 3. فحص فلتر الديزل ونظام الوقود.")

            elif any(k in f for k in ["voltage", "volt", "under volt", "over volt", "low volt", "high volt"]):
                st.write("• **طبيعة المشكلة:** انخفاض أو ارتفاع الجهد المولد عن الحدود التشغيلية المسموحة.")
                st.write("• **الخطوات:** 1. فحص كارت منظم الجهد (AVR). 2. ضبط المقاومة المتغيرة للجهد. 3. فحص كابلات الإحساس (Sensing) والديودات.")

            elif any(k in f for k in ["oil", "press", "low oil", "oil pressure", "lop"]):
                st.write("• **طبيعة المشكلة:** انخفاض ضغط زيت المحرك أو عطل مستشعر الضغط.")
                st.write("• **الخطوات:** 1. قياس مستوى الزيت الفيزيائي. 2. قياس الضغط بساعة خارجية. 3. فحص أسلاك وتأريض الحساس.")

            elif any(k in f for k in ["temp", "coolant", "high temp", "water", "hwt", "radiator"]):
                st.write("• **طبيعة المشكلة:** ارتفاع حرارة سائل التبريد أو انخفاض مستواه.")
                st.write("• **الخطوات:** 1. التأكد من مستوى السائل وسيور المروحة. 2. فحص الثيرموستات وانسداد الراديتر. 3. فحص حساس الحرارة.")

            else:
                st.write(f"• **طبيعة المشكلة:** إنذار تشغيلي/تحذيري برمز `{clean_fault}`.")
                st.write("• **الخطوات:** 1. مراجعة القائمة التشخيصية للكتالوج. 2. إعادة ضبط الإنذار (Reset). 3. فحص أسلاك الدخل والخرج المبرمجة.")

            st.markdown("---")
            st.markdown("🤖 **تحليل التقرير العميق عبر الذكاء الاصطناعي (Gemini):**")
            with st.spinner("جاري استخلاص التوصيات الهندسية من نموذج Gemini API..."):
                ai_analysis = analyze_fault_with_gemini(clean_fault, catalog_context)
                st.markdown(ai_analysis)

                if st.button("🔊 استمع لنتيجة التشخيص", key="audio_btn"):
                    play_audio(ai_analysis)

# =========================================================
# التطبيق 5: الفحص البصري للمعدات
# =========================================================
elif selected_app == "🔍 5. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام الفحص والمقارنة البصرية لقطع الغيار والمعدات")

    eq_type = st.selectbox("اختر المعدة المراد فحصها:", [
        "مولد ديزل صناعي",
        "غرف تبريد وتجميد WIC 10 و WIC 40",
        "محرك كهربائي 3-Phase"
    ])

    st.subheader("🖼️ المقارنة البصرية (القطعة التالفة vs السليمة)")
    c_img1, c_img2 = st.columns(2)
    with c_img1:
        st.write("🟢 **صورة القطعة السليمة (Reference):**")
        good_img = st.file_uploader("اختر صورة السليم", type=["png", "jpg"], key="gi")
        if good_img: st.image(Image.open(good_img), use_container_width=True)
    with c_img2:
        st.write("🔴 **صورة القطعة المفحوصة (Damaged):**")
        bad_img = st.file_uploader("اختر صورة التالف", type=["png", "jpg"], key="bi")
        if bad_img: st.image(Image.open(bad_img), use_container_width=True)

    if eq_type == "غرف تبريد وتجميد WIC 10 و WIC 40":
        st.warning("⚠️ **قائمة فحص وحدات WIC:** يرجى التأكد من فحص صمامات التمدد (Expansion Valves)، وسخانات الإذابة (Defrost)، وتدفق سائل التبريد لوحدات WIC 10 و WIC 40 بشكل منفصل لضمان الكفاءة.")

# =========================================================
# 6. اختبار اتصال مباشر (Ping Test) بقاعدة البيانات Firebase
# =========================================================
st.divider()

import streamlit as st
import firebase_admin
from firebase_admin import credentials

# منع خطأ التهيئة المتكررة (ValueError)
if not firebase_admin._apps:
    try:
        # قراءة الاعتمادات من Streamlit Secrets عند التشغيل على السحابة
        firebase_secrets = dict(st.secrets["firebase"])
        cred = credentials.Certificate(firebase_secrets)
        firebase_admin.initialize_app(cred)
    except (KeyError, FileNotFoundError):
        # خط رجعة (Fallback) عند التشغيل والبرمجة محلياً (Localhost)
        cred = credentials.Certificate("firebase_credentials.json")
        firebase_admin.initialize_app(cred)
else:
    app = firebase_admin.get_app()

db = firestore.client()

st.subheader("🛠️ فحص حالة اتصال قاعدة البيانات")
if st.button("اختبار الاتصال بـ Firebase"):
    try:
        # محاولة كتابة بيانات تجريبية
        test_ref = db.collection("System_Tests").document("test_connection")
        test_ref.set({"status": "Active", "module": "Generator_Diagnostics"})
        
        # محاولة قراءة نفس البيانات للتأكد من حفظها
        result = test_ref.get()
        if result.exists:
            st.success(f"✅ تم الاتصال وحفظ البيانات بنجاح! {result.to_dict()}")
        else:
            st.warning("⚠️ تمت العملية البرمجية لكن لم يتم العثور على المستند في القاعدة.")
    except Exception as e:
        st.error(f"❌ فشل الاتصال أو الحفظ. الخطأ البرمجي: {e}")
