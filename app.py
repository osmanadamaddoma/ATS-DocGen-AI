import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import threading
import io

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

if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الموقع الرئيسي - الخرطوم": {
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

# سجل الإدخالات اليومية وتتبع القراءات
if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "الموقع الرئيسي - الخرطوم",
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
            import base64
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
        "📊 2. المتابعة اليومية وتقارير الإدارة والتذكيرات",
        "🤖 3. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 4. نظام فحص المعدات (WIC وغيرها)"
    ]
)
st.sidebar.divider()

# =========================================================
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد مع التحقق الفوري (Data Validation)
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(site_key, gen_key):
    gen_data = st.session_state.sites_data[site_key]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ بيانات المولد: **{gen_key}** - موقع: **{site_key}**")
    
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
        # =========================================================
        # الميزة 1: التحقق الفوري من صحة البيانات (Data Validation)
        # =========================================================
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
            st.session_state.sites_data[site_key]["generators"][gen_key] = {
                "model": new_model,
                "run_hours": new_run_hours,
                "target": new_target,
                "kw": new_kw,
                "load": new_load,
                "calib_elec": {
                    "v_nominal": v_nom, "v_measured": v_meas,
                    "freq_nominal": f_nom, "freq_measured": f_meas,
                    "current_max": c_max, "current_mea
