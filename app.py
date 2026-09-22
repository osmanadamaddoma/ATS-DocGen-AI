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

# دالة تشغيل الصوت المحدثة مع دعم خيار الكتم
def play_audio(text):
    """تحويل النص إلى صوت باستخدام gTTS وتشغيله إن لم يتم تفعيل Mute"""
    if st.session_state.get("audio_muted", False):
        return
    try:
        tts = gTTS(text=text, lang='ar')
        audio_data = io.BytesIO()
        tts.write_to_fp(audio_data)
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
    
    # بديل يعمل دائماً بصفة مستقرة داخل النوافذ المنبثقة والنماذج بدلاً من st.tabs
    selected_tab = st.radio(
        "اختر القسم:",
        ["🏷️ البيانات الأساسية", "⚡ معايرة الكهرباء", "🔧 معايرة المحرك"],
        horizontal=True
    )

    if selected_tab == "🏷️ البيانات الأساسية":
        st.write("### 🏷️ البيانات الأساسية")
        st.text_input("طراز / اسم المولد", value=gen_data.get("model", ""), key="new_model")
        st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)), key="new_run_hours")
        st.number_input("الساعات المستهدفة الافتراضية للصيانة", min_value=0.0, value=float(gen_data.get("target", 250.0)), key="new_target")
        st.number_input("سعة المولد (kW)", min_value=0.0, value=float(gen_data.get("kw", 0.0)), key="new_kw")
        st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=float(gen_data.get("load", 0.0)), key="new_load")

    elif selected_tab == "⚡ معايرة الكهرباء":
        st.write("### ⚡ معايرة الكهرباء")
        st.number_input("الجهد الاسمي Nominal (V)", value=float(elec.get("v_nominal", 400.0)), key="v_nom")
        st.number_input("الجهد المقاس Measured (V)", value=float(elec.get("v_measured", 398.0)), key="v_meas")
        st.number_input("التردد الاسمي Nominal (Hz)", value=float(elec.get("freq_nominal", 50.0)), key="f_nom")
        st.number_input("التردد المقاس Measured (Hz)", value=float(elec.get("freq_measured", 50.0)), key="f_meas")
        st.number_input("أقصى تيار مسموح Max Current (A)", value=float(elec.get("current_max", 600.0)), key="c_max")
        st.number_input("التيار المقاس Measured Current (A)", value=float(elec.get("current_measured", 360.0)), key="c_meas")
        st.number_input("معامل القدرة Power Factor (PF)", value=float(elec.get("pf", 0.85)), key="pf_val")
        st.text_input("نسبة محولات التيار CT Ratio", value=str(elec.get("ct_ratio", "600/5")), key="ct_rat")

    elif selected_tab == "🔧 معايرة المحرك":
        st.write("### 🔧 معايرة المحرك")
        st.number_input("ضغط الزيت Oil Pressure (Bar)", value=float(eng.get("oil_press_bar", 4.5)), key="o_press")
        st.number_input("حرارة سائل التبريد Coolant Temp (°C)", value=float(eng.get("coolant_temp_c", 85.0)), key="c_temp")
        st.number_input("سرعة المحرك Engine Speed (RPM)", value=float(eng.get("rpm", 1500.0)), key="r_rpm")
        st.number_input("جهد بطارية التشغيل Battery (V)", value=float(eng.get("battery_v", 26.0)), key="b_volt")

    st.write("---")
    
    if st.button("💾 حفظ البيانات والتغييرات", use_container_width=True, type="primary"):
        # استدعاء القيم من الجلسة لتفادي فقدان البيانات في الأقسام غير المحددة
        st.session_state.sites_data[site_key]["generators"][gen_key] = {
            "model": st.session_state.get("new_model", gen_data.get("model", "")),
            "run_hours": st.session_state.get("new_run_hours", gen_data.get("run_hours", 0.0)),
            "target": st.session_state.get("new_target", gen_data.get("target", 250.0)),
            "kw": st.session_state.get("new_kw", gen_data.get("kw", 0.0)),
            "load": st.session_state.get("new_load", gen_data.get("load", 0.0)),
            "calib_elec": {
                "v_nominal": st.session_state.get("v_nom", elec.get("v_nominal", 400.0)),
                "v_measured": st.session_state.get("v_meas", elec.get("v_measured", 398.0)),
                "freq_nominal": st.session_state.get("f_nom", elec.get("freq_nominal", 50.0)),
                "freq_measured": st.session_state.get("f_meas", elec.get("freq_measured", 50.0)),
                "current_max": st.session_state.get("c_max", elec.get("current_max", 600.0)),
                "current_measured": st.session_state.get("c_meas", elec.get("current_measured", 360.0)),
                "pf": st.session_state.get("pf_val", elec.get("pf", 0.85)),
                "ct_ratio": st.session_state.get("ct_rat", elec.get("ct_ratio", "600/5"))
            },
            "calib_engine": {
                "oil_press_bar": st.session_state.get("o_press", eng.get("oil_press_bar", 4.5)),
                "coolant_temp_c": st.session_state.get("c_temp", eng.get("coolant_temp_c", 85.0)),
                "rpm": st.session_state.get("r_rpm", eng.get("rpm", 1500.0)),
                "battery_v": st.session_state.get("b_volt", eng.get("battery_v", 26.0))
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
        # فحص قيم المعايرة وإطلاق التنبيهات الصوتية المستمرة
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

        # إطلاق التنبيهات مع Mute Option
        if alarm_messages:
            for msg in alarm_messages:
                st.error(f"🚨 {msg}")
            combined_alert_text = " . ".join(alarm_messages)
            play_audio(combined_alert_text)

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
                color_code = "#dc3545" # أحمر (تجاوز 90% أو خطر)
                status_str = "إنذار - صيانة فورية!"

            processed_rows.append({
                "Part": part,
                "Category": cat,
                "Life": life,
                "Used": used,
                "Remaining": rem,
                "Percent": pct,
                "Status": status_str,
                "Color": color_code
            })
            bar_colors.append(color_code)

        df_viz = pd.DataFrame(processed_rows)

        # الرسم البياني
        if not df_viz.empty:
            st.subheader("📈 رسم بياني: نسبة استهلاك قطع الغيار والمكونات")
            fig = px.bar(
                df_viz,
                x='Percent',
                y='Part',
                orientation='h',
                title="مؤشر الصيانة التنبؤية (النسبة المئوية للاستهلاك)",
                labels={'Percent': 'نسبة الاستهلاك (%)', 'Part': 'القطعة'},
                color='Status',
                color_discrete_map={
                    "حالة جيدة (أقل من 70%)": "#28a745",
                    "تحذير - قرب الصيانة (70%-90%)": "#ffc107",
                    "إنذار - صيانة فورية!": "#dc3545"
                },
                text=df_viz['Percent'].apply(lambda x: f"{x:.1f}%")
            )
            fig.update_layout(yaxis={'categoryorder': 'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
