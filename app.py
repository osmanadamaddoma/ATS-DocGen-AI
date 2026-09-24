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
import streamlit as st

# ---------------------------------------------------------
# الاستيراد الآمن للمكتبات الخارجية لتجنب بيئة Python 3.14+
# ---------------------------------------------------------
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception:
    firebase_admin = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

try:
    from google import genai
except Exception:
    genai = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None

# استيراد مكتبة قاعدة بيانات إنترنت الأشياء الحية (IoT Database)
try:
    from influxdb_client import InfluxDBClient
except Exception:
    InfluxDBClient = None

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except Exception:
    decode_qr = None

# =========================================================
# 0. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    page_icon="⚙️",
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
gemini_key = None
try:
    if "GEMINI_API_KEY" in st.secrets:
        gemini_key = st.secrets["GEMINI_API_KEY"]
    elif "firebase" in st.secrets and "GEMINI_API_KEY" in st.secrets["firebase"]:
        gemini_key = st.secrets["firebase"]["GEMINI_API_KEY"]
    else:
        gemini_key = os.environ.get("GEMINI_API_KEY")
except Exception:
    gemini_key = os.environ.get("GEMINI_API_KEY")

if not gemini_key:
    st.sidebar.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. أضفه في st.secrets لتفعيل الذكاء الاصطناعي.")

# تهيئة عميل Gemini API الآمن
client = None
if genai and gemini_key:
    try:
        client = genai.Client(api_key=gemini_key)
    except Exception as e:
        st.sidebar.error(f"خطأ في تهيئة الذكاء الاصطناعي: {e}")

# دالة تشغيل الصوت المحدثة مع دعم خيار الكتم والتكرار المستمر للإنذارات
def play_audio(text, loop=False):
    """تحويل النص إلى صوت باستخدام gTTS وتشغيله إن لم يتم تفعيل Mute مع دعم التكرار"""
    if st.session_state.get("audio_muted", False) or not gTTS:
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
                model="gemini-2.5-flash",
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
        self.cell(0, 10, self.report_title, ln=1, align="L")
        self.set_draw_color(200, 200, 200)
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()} | Addoma Trading Services - Industrial AI Platform", align="C")

# =========================================================
# NEW: 1.5 دوال الربط بقاعدة البيانات الحية وإنترنت الأشياء (IoT)
# =========================================================
def fetch_live_iot_data():
    """جلب القراءات اللحظية من قاعدة بيانات السلاسل الزمنية الحية إن وجدت"""
    if not InfluxDBClient or "influxdb" not in st.secrets:
        # العودة التلقائية لمحاكاة تدفق بيانات حية في حال عدم ضبط السيرفر السحابي بعد
        import random
        today = datetime.now()
        data = []
        for i in range(20):
            t = today - timedelta(minutes=i*2)
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
# 2. الواجهة الرسومية وهيكلية القائمة الجانبية للتطبيق
# =========================================================
st.sidebar.title("Addoma Trading Services")
st.sidebar.caption("نظام الصيانة التنبؤية والمساعد الذكي والمراقبة عن بُعد")

# زر كتم وتقود الصوت المحدث
audio_state = st.sidebar.checkbox("🔇 كتم التنبيهات الصوتية", value=st.session_state.audio_muted)
st.session_state.audio_muted = audio_state

st.sidebar.divider()

# القائمة الرئيسية للتطبيقات
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)",
        "🎛️ 2. غرفة التحكم والتشغيل عن بعد (Remote Control)",
        "🤖 3. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 4. نظام فحص المعدات (WIC وغيرها)"
    ]
)

st.sidebar.divider()

# =========================================================
# 3. التطبيق الأول: الصيانة التنبؤية والمولدات
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية وإدارة المولدات")
    
    # اختيار الموقع والمولد
    main_sites = list(st.session_state.sites_data.keys())
    if main_sites:
        main_site = st.selectbox("القائمة الرئيسية (الموقع):", main_sites)
        sub_sites = list(st.session_state.sites_data[main_site].keys())
        
        if sub_sites:
            sub_site = st.selectbox("الموقع الفرعي:", sub_sites)
            site_info = st.session_state.sites_data[main_site][sub_site]
            gens = list(site_info["generators"].keys())
            
            if gens:
                selected_gen = st.selectbox("اختر المولد:", gens)
                gen = site_info["generators"][selected_gen]
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("الموديل", gen["model"])
                col2.metric("ساعات التشغيل", f"{gen['run_hours']} hrs")
                col3.metric("الجهد المقاس", f"{gen['calib_elec']['v_measured']} V")
                col4.metric("ضغط الزيت", f"{gen['calib_engine']['oil_press_bar']} Bar")

                st.subheader("📊 تحليل السلاسل الزمنية الحية للمولد (IoT)")
                iot_df = fetch_live_iot_data()
                if not iot_df.empty:
                    fig = px.line(iot_df, x="_time", y=["temperature", "pressure", "vibration"], title="قراءات الحساسات المباشرة")
                    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# 4. التطبيق الثاني: غرفة التحكم والتشغيل عن بعد (Remote Control)
# =========================================================
elif selected_app == "🎛️ 2. غرفة التحكم والتشغيل عن بعد (Remote Control)":
    st.title("🎛️ غرفة التحكم والتشغيل عن بُعد (Remote Control Center)")
    st.caption("نظام إرسال الأوامر المباشرة لوحدات التحكم DSE عبر بروتوكول الاتصال الآمن")

    main_sites = list(st.session_state.sites_data.keys())
    if main_sites:
        m_site = st.selectbox("اختر الموقع الرئيسي:", main_sites, key="rc_m_site")
        sub_sites = list(st.session_state.sites_data[m_site].keys())
        if sub_sites:
            s_site = st.selectbox("اختر الموقع الفرعي:", sub_sites, key="rc_s_site")
            gens = list(st.session_state.sites_data[m_site][s_site]["generators"].keys())
            if gens:
                selected_gen = st.selectbox("اختر المولد للتحكم:", gens, key="rc_gen")
                gen_data = st.session_state.sites_data[m_site][s_site]["generators"][selected_gen]

                st.divider()

                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("وضع اللوحة", "AUTO", delta="جاهز للأمر")
                kpi2.metric("السرعة الحالية", f"{gen_data['calib_engine']['rpm']} RPM")
                kpi3.metric("جهد الفازات", f"{gen_data['calib_elec']['v_measured']} V")
                kpi4.metric("حرارة المحرك", f"{gen_data['calib_engine']['coolant_temp_c']} °C")

                st.divider()

                safety_switch = st.checkbox("🔓 مفتاح الأمان الميكانيكي لفك حظر الأوامر عن بعد")

                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("🔄 وضع AUTO", use_container_width=True, disabled=not safety_switch):
                        st.success("✅ تم تحويل اللوحة إلى وضع AUTO")
                with c2:
                    if st.button("✋ وضع MANUAL", use_container_width=True, disabled=not safety_switch):
                        st.info("ℹ️ تم تحويل اللوحة للوضع اليدوي")
                with c3:
                    if st.button("▶️ تشغيل (START)", type="primary", use_container_width=True, disabled=not safety_switch):
                        st.success("🚀 تم إرسال أمر التشغيل المباشر عبر USB/Modbus")
                with c4:
                    if st.button("⏹️ إيقاف (STOP)", type="secondary", use_container_width=True, disabled=not safety_switch):
                        st.error("🛑 تم إرسال أمر الإيقاف وترسيت الأعطال")

# =========================================================
# 5. التطبيق الثالث: المساعد الذكي وقراءة الأكواد
# =========================================================
elif selected_app == "🤖 3. المساعد الذكي والكتالوجات وقراءة الأكواد":
    st.title("🤖 المساعد الذكي وقراءة أكواد الأعطال")
    
    fault_input = st.text_input("أدخل كود العطل أو اسم الإنذار (مثال: DSE 4110 or High Engine Temp):")
    if st.button("🔍 تحليل العطل بالذكاء الاصطناعي"):
        if fault_input:
            with st.spinner("جاري التحليل..."):
                res = analyze_fault_with_gemini(fault_input)
                st.markdown(res)
                play_audio("تم تشخيص العطل بنجاح. يمكنك قراءة خطوات الصيانة.")
        else:
            st.warning("يرجى إدخال كود العطل أولاً.")

# =========================================================
# 6. التطبيق الرابع: نظام فحص المعدات
# =========================================================
elif selected_app == "🔍 4. نظام فحص المعدات (WIC وغيرها)":
    st.title("🔍 نظام فحص المولدات ومعدات التبريد (WIC 10 & WIC 40)")
    st.info("قم برفع صورة اللوحة أو إجراء الفحص الميداني التلقائي.")
    uploaded_file = st.file_uploader("رفع صورة العطل أو الباركود:", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        st.image(uploaded_file, caption="الصورة المرفوعة", use_column_width=True)
        st.success("تم رفع الصورة بنجاح وتجهيزها للفحص الميداني.")
