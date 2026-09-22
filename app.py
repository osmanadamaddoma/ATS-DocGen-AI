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
                        "rpm": 1500.0, "battery_v": 26.5
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
                        "rpm": 1500.0, "battery_v": 25.8
                    }
                }
            }
        }
    }

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
        "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد",
        "🔍 3. نظام فحص المعدات (WIC وغيرها)"
    ]
)
st.sidebar.divider()

# =========================================================
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد ومعايرته
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(site_key, gen_key):
    gen_data = st.session_state.sites_data[site_key]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ بيانات المولد: **{gen_key}** - موقع: **{site_key}**")
    
    # تفكيك القائمة المرجعة إلى 3 متغيرات مستقلة
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

    if st.button("💾 حفظ البيانات وتكرار صوت المنبه والإنذار حتى يتم توقيفه بزر Mute والتغييرات", use_container_width=True, type="primary"):
        st.session_state.sites_data[site_key]["generators"][gen_key] = {
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
                "rpm": r_rpm, "battery_v": b_volt
            }
        }
        st.success("✅ تم تحديث بيانات المولد والمعايرة بنجاح!")
        st.rerun()

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والتقارير الشاملة
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    # زر Mute الصوتي الرئيسي في أعلى الصفحة
    col_top_audio1, col_top_audio2 = st.columns([3, 1])
    with col_top_audio2:
        mute_label = "🔇 Mute (إيقاف الصوت)" if not st.session_state.audio_muted else "🔊 Unmute (تفعيل الصوت)"
        if st.button(mute_label, use_container_width=True):
            st.session_state.audio_muted = not st.session_state.audio_muted
            st.rerun()

    # خيار رفع الشعار
    st.sidebar.subheader("🎨 تخصيص التقرير المطبوع")
    logo_file = st.sidebar.file_uploader("رفع شعار الشركة (Logo)", type=["png", "jpg", "jpeg"], key="logo_up")

    # --- إدارة المواقع وقائمة العناوين ---
    st.subheader("📍 إدارة المواقع والعناوين")
    col_site1, col_site2 = st.columns(2)
    with col_site1:
        new_site_name = st.text_input("اسم الموقع الجديد:")
        new_site_address = st.text_input("عنوان الموقع بالتفصيل (كتابة نصية):")
        if st.button("➕ أضف الموقع والعنوان"):
            if new_site_name and new_site_name not in st.session_state.sites_data:
                st.session_state.sites_data[new_site_name] = {
                    "address": new_site_address if new_site_address else "غير محدد",
                    "generators": {}
                }
                st.success(f"تم إضافة الموقع: {new_site_name}")
                st.rerun()

    site_list = list(st.session_state.sites_data.keys())
    if not site_list:
        st.warning("الرجاء إضافة موقع للبدء.")
        st.stop()

    with col_site2:
        selected_site = st.selectbox("اختر الموقع الحالي للعمل عليه:", site_list)
        current_site_address = st.text_input("تعديل عنوان الموقع المختار:", value=st.session_state.sites_data[selected_site].get("address", ""))
        if st.button("✏️ تحديث عنوان الموقع"):
            st.session_state.sites_data[selected_site]["address"] = current_site_address
            st.success("تم تحديث العنوان!")

    st.divider()

    # --- إدارة المولدات داخل الموقع ---
    col_gen_m1, col_gen_m2 = st.columns([2, 1])
    with col_gen_m1:
        new_gen_id = st.text_input(f"إضافة مولد جديد في ({selected_site}):", placeholder="مثال: G3")
    with col_gen_m2:
        st.write("")
        st.write("")
        if st.button("➕ إنشاء المولد"):
            if new_gen_id and new_gen_id not in st.session_state.sites_data[selected_site]["generators"]:
                st.session_state.sites_data[selected_site]["generators"][new_gen_id] = {
                    "model": "Perkins Standard",
                    "run_hours": 0.0,
                    "target": 250.0,
                    "kw": 100.0,
                    "load": 50.0,
                    "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                    "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0}
                }
                st.success(f"تم إنشاء المولد {new_gen_id}")
                st.rerun()

    gen_list = list(st.session_state.sites_data[selected_site]["generators"].keys())

    if not gen_list:
        st.info("لا توجد مولدات في هذا الموقع. قم بإضافة مولد للبدء.")
    else:
        col_select_g, col_modal_btn = st.columns([2, 1])
        with col_select_g:
            selected_gen = st.selectbox("اختر المولد لاستعراض ومعالجة بياناته:", gen_list)
        with col_modal_btn:
            st.write("")
            st.write("")
            if st.button("📝 فتح نافذة إدخال وتعديل البيانات المعايرة"):
                edit_generator_modal(selected_site, selected_gen)

        # استرجاع بيانات المولد المختار
        gen_info = st.session_state.sites_data[selected_site]["generators"][selected_gen]
        calib_e = gen_info.get("calib_elec", {})
        calib_m = gen_info.get("calib_engine", {})

        # عرض ملخص بيانات المولد والمعايرة
        st.subheader(f"📊 لوحة بيانات المعايرة والمراقبة للمولد ({selected_gen})")
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("الطراز والسعة", f"{gen_info['model']}", f"{gen_info['kw']} kW")
        m_c2.metric("ساعات التشغيل / الهدف", f"{gen_info['run_hours']} hrs", f"المستهدف: {gen_info['target']} hrs")
        m_c3.metric("معايرة الجهد المقاس", f"{calib_e.get('v_measured', 0)} V", f"الاسمي: {calib_e.get('v_nominal', 0)} V")
        m_c4.metric("معايرة حرارة المحرك", f"{calib_m.get('coolant_temp_c', 0)} °C", f"الضغط: {calib_m.get('oil_press_bar', 0)} Bar")

        # ---------------------------------------------------------
        # فحص قيم المعايرة وإطلاق التنبيهات الصوتية المستمرة (Looping Alarms)
        # ---------------------------------------------------------
        alarm_messages = []

        # فحص الجهد
        if abs(calib_e.get("v_measured", 400) - calib_e.get("v_nominal", 400)) > 20:
            alarm_messages.append(f"انحراف في الجهد الكهربائي للمولد {selected_gen}: الجهد المقاس {calib_e.get('v_measured')} فولت!")
        
        # فحص التيار
        if calib_e.get("current_measured", 0) > calib_e.get("current_max", 1000):
            alarm_messages.append(f"إنذار حمولة زائدة للتيار في المولد {selected_gen}!")

        # فحص الحرارة والضغط
        if calib_m.get("coolant_temp_c", 0) >= 95.0:
            alarm_messages.append(f"ارتفاع حرارة المحرك للمولد {selected_gen}: {calib_m.get('coolant_temp_c')} درجة مئوية!")
        if calib_m.get("oil_press_bar", 5) <= 1.8:
            alarm_messages.append(f"انخفاض ضغط زيت المحرك للمولد {selected_gen}!")

        # فحص الساعات الافتراضية
        remaining_target = gen_info["target"] - gen_info["run_hours"]
        if remaining_target <= 50 and remaining_target > 0:
            alarm_messages.append(f"اقتراب تجاوز الساعات الافتراضية للمولد {selected_gen}. متبقي {remaining_target} ساعة.")
        elif remaining_target <= 0:
            alarm_messages.append(f"إنذار! تجاوز المولد {selected_gen} الساعات الافتراضية المجدولة للصيانة!")

        # إطلاق التنبيهات مع خيار التكرار المستمر للصوت حتى Mute
        if alarm_messages:
            for msg in alarm_messages:
                st.error(f"🚨 {msg}")
            combined_alert_text = " . ".join(alarm_messages)
            play_audio(combined_alert_text, loop=True)

        # ---------------------------------------------------------
        # جدول الصيانة التنبؤية لـ 14 قطعة غيار
        # ---------------------------------------------------------
        parts_key = f"parts_{selected_site}_{selected_gen}"
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

        # حساب النسب والألوان للرسم البياني
        processed_rows = []
        bar_colors = []

        for idx, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
            cat = str(row.get("تصنيف القطعة", "Other"))
            part = str(row.get("قطع الغيار / الفلاتر", "Part"))
            life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
            used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
            rem = life - used
            pct = (used / life) * 100 if life > 0 else 0

            # ترميز الألوان بناءً على نسبة استهلاك ساعات العمل المجدولة
            if pct < 70.0:
                color_code = "#28a745" # أخضر (أقل من 70%)
                status_str = "حالة جيدة (أقل من 70%)"
            elif 70.0 <= pct < 90.0:
                color_code = "#ffc107" # أصفر (70% - 90%)
                status_str = "تحذير - قرب الصيانة (70%-90%)"
            else:
                color_code = "#dc3545" # أحمر (تجاوز 90% - 100%)
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

        # ---------------------------------------------------------
        # الرسومات البيانية (البار الملون والدائري)
        # ---------------------------------------------------------
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

        # ---------------------------------------------------------
        # دالة توليد تقرير PDF المطور
        # ---------------------------------------------------------
        def generate_full_pdf_bytes():
            temp_logo_path = None
            if logo_file:
                temp_logo_path = f"temp_logo_{uuid.uuid4().hex}.png"
                with open(temp_logo_path, "wb") as f:
                    f.write(logo_file.getbuffer())

            pdf = ComprehensivePDF("GENERATOR PREDICTIVE MAINTENANCE REPORT", logo_path=temp_logo_path)
            pdf.add_page()

            # قسم الموقع والبيانات
            pdf.set_fill_color(245, 247, 250)
            pdf.rect(10, 35, 190, 25, "F")
            pdf.set_xy(12, 37)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(24, 43, 73)
            
            pdf.cell(0, 5, f"Site Name: {sanitize_latin_only(selected_site)} | Address: {sanitize_latin_only(current_site_address)}", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen)} | Model: {sanitize_latin_only(gen_info['model'])} | Capacity: {gen_info['kw']} kW", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Current Run Hours: {gen_info['run_hours']} hrs | Target Hours: {gen_info['target']} hrs", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Electrical Calib: {calib_e.get('v_measured',0)}V / {calib_e.get('freq_measured',0)}Hz | Engine: {calib_m.get('coolant_temp_c',0)} C / {calib_m.get('oil_press_bar',0)} Bar", ln=True)
            pdf.ln(8)

            # جدول الـ 14 قطعة
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

            # إدراج الصور
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

            # إدراج الرسم البياني في الـ PDF
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
            label=f"🖨️ إصدار التقرير الشامل للمولد ({selected_gen}) في ({selected_site})",
            data=generate_full_pdf_bytes(),
            file_name=f"Report_{selected_site}_{selected_gen}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )

# =========================================================
# التطبيق 2: المساعد الذكي والكتالوجات (مدمج ومتطور)
# =========================================================
elif selected_app == "🤖 2. المساعد الذكي والكتالوجات وقراءة الأكواد":
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
# التطبيق 3: الفحص البصري للمعدات
# =========================================================
elif selected_app == "🔍 3. نظام فحص المعدات (WIC وغيرها)":
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
