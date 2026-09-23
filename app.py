import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta, date
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
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS

# استيراد مكتبات SQLAlchemy لإدارة قاعدة البيانات
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime, Date, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, joinedload

# محاولة استيراد مكتبة قراءة الباركود
try:
    from pyzbar.pyzbar import decode as decode_qr
except ImportError:
    decode_qr = None

# =========================================================
# 0. تهيئة قاعدة البيانات باستخدام SQLAlchemy
# =========================================================
DATABASE_URL = "sqlite:///addoma_maintenance.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)

class Company(Base):
    __tablename__ = "companies"
    id = Column(String, primary_key=True) # مثال: ADDOMA-2026-PRO
    name = Column(String, nullable=False)
    plan_type = Column(String)
    start_date = Column(Date)
    duration_days = Column(Integer)
    sites = relationship("Site", back_populates="company", cascade="all, delete-orphan")

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(String, ForeignKey("companies.id"))
    name = Column(String, nullable=False)
    address = Column(String)
    company = relationship("Company", back_populates="sites")
    generators = relationship("Generator", back_populates="site", cascade="all, delete-orphan")

class Generator(Base):
    __tablename__ = "generators"
    id = Column(Integer, primary_key=True, autoincrement=True)
    site_id = Column(Integer, ForeignKey("sites.id"))
    gen_code = Column(String, nullable=False) # مثال: G1
    model = Column(String)
    run_hours = Column(Float, default=0.0)
    target_hours = Column(Float, default=250.0)
    capacity_kw = Column(Float, default=100.0)
    current_load_kw = Column(Float, default=0.0)
    
    # المعايرة الكهربائية
    v_nominal = Column(Float, default=400.0)
    v_measured = Column(Float, default=400.0)
    freq_nominal = Column(Float, default=50.0)
    freq_measured = Column(Float, default=50.0)
    current_max = Column(Float, default=600.0)
    current_measured = Column(Float, default=0.0)
    pf = Column(Float, default=0.85)
    ct_ratio = Column(String, default="600/5")
    
    # معايرة المحرك
    oil_press_bar = Column(Float, default=4.5)
    coolant_temp_c = Column(Float, default=85.0)
    rpm = Column(Float, default=1500.0)
    battery_v = Column(Float, default=26.0)
    ambient_temp = Column(Float, default=43.0)
    
    site = relationship("Site", back_populates="generators")
    readings = relationship("DailyReading", back_populates="generator", cascade="all, delete-orphan")
    parts = relationship("MaintenancePart", back_populates="generator", cascade="all, delete-orphan")

class DailyReading(Base):
    __tablename__ = "daily_readings"
    id = Column(Integer, primary_key=True, autoincrement=True)
    generator_id = Column(Integer, ForeignKey("generators.id"))
    timestamp = Column(DateTime, default=datetime.utcnow)
    log_date = Column(Date, default=date.today)
    technician_name = Column(String)
    
    run_hours = Column(Float)
    v_measured = Column(Float)
    oil_press_bar = Column(Float)
    coolant_temp_c = Column(Float)
    battery_v = Column(Float)
    status = Column(String, default="طبيعي")
    
    generator = relationship("Generator", back_populates="readings")

class MaintenancePart(Base):
    __tablename__ = "maintenance_parts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    generator_id = Column(Integer, ForeignKey("generators.id"))
    unit_num = Column(Integer)
    category = Column(String)
    part_name = Column(String)
    lifespan_hours = Column(Float)
    used_hours = Column(Float, default=0.0)
    
    generator = relationship("Generator", back_populates="parts")

# إنشاء الجداول في قاعدة البيانات
Base.metadata.create_all(bind=engine)

def get_db_session():
    return SessionLocal()

# =========================================================
# البذر المبدئي للبيانات (Seed Initial Data)
# =========================================================
def init_db_data():
    db = get_db_session()
    try:
        # 1. إدخال الشركات والاشتراكات المبدئية
        companies_seed = [
            Company(id="ADDOMA-2026-PRO", name="عثمان آدم أدومة (Addoma Trading Services)", plan_type="شهري (Monthly)", start_date=date(2026, 9, 15), duration_days=30),
            Company(id="CLIENT-M-881", name="شركة النيل للصناعات الهندسية", plan_type="شهري (Monthly)", start_date=date(2026, 9, 1), duration_days=30),
            Company(id="CLIENT-Y-992", name="مصانع الحديد والصلب الوطنية", plan_type="سنوي (Yearly)", start_date=date(2026, 3, 15), duration_days=365)
        ]
        for comp in companies_seed:
            if not db.query(Company).filter(Company.id == comp.id).first():
                db.add(comp)
        db.commit()

        # 2. إدخال الموقع الافتراضي والمولدات لشركة Addoma
        addoma_comp = db.query(Company).filter(Company.id == "ADDOMA-2026-PRO").first()
        if addoma_comp and not db.query(Site).filter(Site.company_id == addoma_comp.id).first():
            site_main = Site(
                company_id=addoma_comp.id,
                name="الموقع الرئيسي - الخرطوم",
                address="الخرطوم - المنطقة الصناعية - كافوري"
            )
            db.add(site_main)
            db.commit()
            db.refresh(site_main)

            g1 = Generator(
                site_id=site_main.id, gen_code="G1", model="Perkins 410 kVA", run_hours=700.0, target_hours=940.0,
                capacity_kw=410.0, current_load_kw=250.0, v_nominal=400.0, v_measured=398.0, freq_nominal=50.0,
                freq_measured=50.1, current_max=600.0, current_measured=360.0, pf=0.85, ct_ratio="600/5",
                oil_press_bar=4.5, coolant_temp_c=85.0, rpm=1500.0, battery_v=26.5, ambient_temp=43.0
            )
            g2 = Generator(
                site_id=site_main.id, gen_code="G2", model="Cummins 250 kVA", run_hours=1200.0, target_hours=1500.0,
                capacity_kw=250.0, current_load_kw=180.0, v_nominal=400.0, v_measured=402.0, freq_nominal=50.0,
                freq_measured=49.9, current_max=360.0, current_measured=260.0, pf=0.82, ct_ratio="400/5",
                oil_press_bar=4.2, coolant_temp_c=88.0, rpm=1500.0, battery_v=25.8, ambient_temp=45.0
            )
            db.add_all([g1, g2])
            db.commit()

            # إدراج قطع الغيار لـ G1
            default_parts = [
                (1, "Schedule Services", "Oil Filter", 250.0, 180.0),
                (2, "Schedule Services", "Primary Fuel Filter", 500.0, 430.0),
                (3, "Schedule Services", "Secondary Fuel Filter", 500.0, 480.0),
                (4, "Air System", "Air Filter", 1000.0, 650.0),
                (5, "Fan Belt System", "Fan Belt", 2000.0, 1550.0),
                (6, "Cooling System", "ELC Coolant", 3000.0, 2800.0),
                (7, "Fuel System", "Injectors Check", 5000.0, 3200.0),
                (8, "النظام الكهربائي", "Batteries", 8000.0, 6100.0),
                (9, "Electric System", "Charging Alternator", 10000.0, 8900.0),
                (10, "Engine Motor", "Top Overhaul", 10000.0, 9200.0),
                (11, "Engine Motor", "Major Overhaul", 20000.0, 11000.0),
                (12, "Oilers System", "Oil Cooler Clean", 5000.0, 3800.0),
                (13, "نظام التبريد", "Water Pump", 6000.0, 5200.0),
                (14, "نظام الهواء", "Turbocharger Check", 8000.0, 7100.0),
            ]
            for gen in [g1, g2]:
                for u, c, p, l, us in default_parts:
                    db.add(MaintenancePart(generator_id=gen.id, unit_num=u, category=c, part_name=p, lifespan_hours=l, used_hours=us))
            
            # تسجيل قراءة يومية مبدئية
            db.add(DailyReading(
                generator_id=g1.id, log_date=date.today(), timestamp=datetime.now(),
                technician_name="أحمد فني الصيانة", run_hours=700.0, v_measured=398.0,
                oil_press_bar=4.5, coolant_temp_c=85.0, battery_v=26.5, status="طبيعي"
            ))
            db.commit()
    finally:
        db.close()

init_db_data()

# =========================================================
# 1. إعدادات الصفحة الرئيسية وتهيئة الذكاء الاصطناعي والصوت
# =========================================================
st.set_page_config(
    page_title="المجمع الصناعي الشامل - Addoma Trading Services",
    layout="wide",
)

if "audio_muted" not in st.session_state:
    st.session_state.audio_muted = False

gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

client = genai.Client(api_key=gemini_key) if gemini_key else None

def play_audio(text, loop=False):
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

def sanitize_latin_only(text):
    if not isinstance(text, str):
        text = str(text)
    clean_text = re.sub(r"[^\x00-\x7F]+", "", text).strip()
    return clean_text if clean_text else "N/A"

class ComprehensivePDF(FPDF):
    def __init__(self, title_text="INDUSTRIAL MAINTENANCE & DIAGNOSTIC REPORT", logo_path=None):
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
        self.cell(0, 4, "ADDOMA TRADING SERVICES - ENGINEERING CONSULTANCY", ln=True)

        self.set_x(text_x)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 4, "Power Systems & Electro-Mechanical Maintenance Division", ln=True)

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
        self.cell(0, 4, "Prepared by: Osman Adam Addoma | Power Systems Engineer", ln=True, align="C")
        self.cell(0, 4, f"Page {self.page_no()} | Generated Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات عبر SQLAlchemy
# =========================================================
st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل للوصول للنظام:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"
company_obj = None

if input_code != "":
    db = get_db_session()
    comp = db.query(Company).filter(Company.id == input_code).first()
    db.close()
    
    if comp:
        client_name = comp.name
        plan_type = comp.plan_type
        company_obj = comp
        
        start_dt = comp.start_date
        expiry_dt = start_dt + timedelta(days=comp.duration_days)
        today_d = date.today()
        
        if today_d <= expiry_dt:
            is_pro = True
            days_left = (expiry_dt - today_d).days
            st.sidebar.success("✅ تم التحقق من الاشتراك بنجاح!")
            st.sidebar.markdown(f"**👤 العميل:** {client_name}")
            st.sidebar.markdown(f"**📦 الباقة:** {plan_type}")
            st.sidebar.markdown(f"⏳ **المتبقي:** {days_left} يوم")
        else:
            st.sidebar.error(f"❌ انتهت صلاحية اشتراك هذا العميل بتاريخ ({expiry_dt}).")
    else:
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
# النافذة المنبثقة (Modal) لإدخال/تحديث بيانات المولد عبر SQLAlchemy
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(generator_id):
    db = get_db_session()
    gen = db.query(Generator).options(joinedload(Generator.site)).filter(Generator.id == generator_id).first()
    
    if not gen:
        st.error("❌ لم يتم العثور على المولد في قاعدة البيانات!")
        db.close()
        return

    st.markdown(f"### ⚙️ بيانات المولد: **{gen.gen_code}** - موقع: **{gen.site.name}**")
    
    tech_name = st.text_input("اسم الفني المسؤول عن الإدخال:", value="فني الصيانة المناوب")
    tab1, tab2, tab3 = st.tabs(["🏷️ البيانات الأساسية", "⚡ معايرة الكهرباء", "🔧 معايرة المحرك"])

    with tab1:
        new_model = st.text_input("طراز / اسم المولد", value=gen.model or "")
        new_run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=float(gen.run_hours or 0.0))
        new_target = st.number_input("الساعات المستهدفة الافتراضية للصيانة", min_value=0.0, value=float(gen.target_hours or 250.0))
        new_kw = st.number_input("سعة المولد (kW)", min_value=0.0, value=float(gen.capacity_kw or 0.0))
        new_load = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=float(gen.current_load_kw or 0.0))

    with tab2:
        v_nom = st.number_input("الجهد الاسمي Nominal (V)", value=float(gen.v_nominal or 400.0))
        v_meas = st.number_input("الجهد المقاس Measured (V)", value=float(gen.v_measured or 400.0))
        f_nom = st.number_input("التردد الاسمي Nominal (Hz)", value=float(gen.freq_nominal or 50.0))
        f_meas = st.number_input("التردد المقاس Measured (Hz)", value=float(gen.freq_measured or 50.0))
        c_max = st.number_input("أقصى تيار مسموح Max Current (A)", value=float(gen.current_max or 600.0))
        c_meas = st.number_input("التيار المقاس Measured Current (A)", value=float(gen.current_measured or 0.0))
        pf_val = st.number_input("معامل القدرة Power Factor (PF)", value=float(gen.pf or 0.85))
        ct_rat = st.text_input("نسبة محولات التيار CT Ratio", value=str(gen.ct_ratio or "600/5"))

    with tab3:
        o_press = st.number_input("ضغط الزيت Oil Pressure (Bar)", value=float(gen.oil_press_bar or 4.5))
        c_temp = st.number_input("حرارة سائل التبريد Coolant Temp (°C)", value=float(gen.coolant_temp_c or 85.0))
        r_rpm = st.number_input("سرعة المحرك Engine Speed (RPM)", value=float(gen.rpm or 1500.0))
        b_volt = st.number_input("جهد بطارية التشغيل Battery (V)", value=float(gen.battery_v or 26.0))
        ambient_t = st.number_input("درجة الحرارة المحيطة Ambient Temp (°C)", value=float(gen.ambient_temp or 43.0))

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
            db.close()
        else:
            # تحديث بيانات المولد في SQL
            gen.model = new_model
            gen.run_hours = new_run_hours
            gen.target_hours = new_target
            gen.capacity_kw = new_kw
            gen.current_load_kw = new_load
            
            gen.v_nominal = v_nom
            gen.v_measured = v_meas
            gen.freq_nominal = f_nom
            gen.freq_measured = f_meas
            gen.current_max = c_max
            gen.current_measured = c_meas
            gen.pf = pf_val
            gen.ct_ratio = ct_rat
            
            gen.oil_press_bar = o_press
            gen.coolant_temp_c = c_temp
            gen.rpm = r_rpm
            gen.battery_v = b_volt
            gen.ambient_temp = ambient_t

            # إضافة قراءة يومية جديدة بقاعدة البيانات
            new_reading = DailyReading(
                generator_id=gen.id,
                log_date=date.today(),
                timestamp=datetime.now(),
                technician_name=tech_name,
                run_hours=new_run_hours,
                v_measured=v_meas,
                oil_press_bar=o_press,
                coolant_temp_c=c_temp,
                battery_v=b_volt,
                status="محدث وصحيح"
            )
            db.add(new_reading)
            db.commit()
            db.close()

            st.success("✅ تم التحقق من صحة البيانات وحفظها في قاعدة البيانات بنجاح!")
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

    # --- إدارة المواقع وقائمة العناوين عبر SQLAlchemy ---
    st.subheader("📍 إدارة المواقع والعناوين")
    col_site1, col_site2 = st.columns(2)
    
    db = get_db_session()
    user_company = db.query(Company).filter(Company.id == input_code).first()

    with col_site1:
        new_site_name = st.text_input("اسم الموقع الجديد:")
        new_site_address = st.text_input("عنوان الموقع بالتفصيل (كتابة نصية):")
        if st.button("➕ أضف الموقع والعنوان"):
            if new_site_name and user_company:
                existing_site = db.query(Site).filter(Site.company_id == user_company.id, Site.name == new_site_name).first()
                if not existing_site:
                    db.add(Site(company_id=user_company.id, name=new_site_name, address=new_site_address or "غير محدد"))
                    db.commit()
                    st.success(f"تم إضافة الموقع: {new_site_name}")
                    db.close()
                    st.rerun()
                else:
                    st.warning("الموقع موجود بالفعل!")

    company_sites = db.query(Site).filter(Site.company_id == user_company.id).all() if user_company else []
    
    if not company_sites:
        st.warning("الرجاء إضافة موقع للبدء.")
        db.close()
        st.stop()

    site_dict = {s.name: s for s in company_sites}
    
    with col_site2:
        selected_site_name = st.selectbox("اختر الموقع الحالي للعمل عليه:", list(site_dict.keys()))
        current_site_obj = site_dict[selected_site_name]
        
        current_site_address = st.text_input("تعديل عنوان الموقع المختار:", value=current_site_obj.address or "")
        if st.button("✏️ تحديث عنوان الموقع"):
            current_site_obj.address = current_site_address
            db.commit()
            st.success("تم تحديث العنوان!")

    st.divider()

    # --- إدارة المولدات داخل الموقع عبر SQLAlchemy ---
    col_gen_m1, col_gen_m2 = st.columns([2, 1])
    with col_gen_m1:
        new_gen_code = st.text_input(f"إضافة مولد جديد في ({selected_site_name}):", placeholder="مثال: G3")
    with col_gen_m2:
        st.write("")
        st.write("")
        if st.button("➕ إنشاء المولد"):
            if new_gen_code:
                existing_gen = db.query(Generator).filter(Generator.site_id == current_site_obj.id, Generator.gen_code == new_gen_code).first()
                if not existing_gen:
                    new_g = Generator(
                        site_id=current_site_obj.id, gen_code=new_gen_code, model="Perkins Standard",
                        run_hours=0.0, target_hours=250.0, capacity_kw=100.0, current_load_kw=50.0
                    )
                    db.add(new_g)
                    db.commit()
                    db.refresh(new_g)
                    
                    # بذر الـ 14 قطعة افتراضياً للمولد الجديد
                    default_parts = [
                        (1, "Schedule Services", "Oil Filter", 250.0, 0.0),
                        (2, "Schedule Services", "Primary Fuel Filter", 500.0, 0.0),
                        (3, "Schedule Services", "Secondary Fuel Filter", 500.0, 0.0),
                        (4, "Air System", "Air Filter", 1000.0, 0.0),
                        (5, "Fan Belt System", "Fan Belt", 2000.0, 0.0),
                        (6, "Cooling System", "ELC Coolant", 3000.0, 0.0),
                        (7, "Fuel System", "Injectors Check", 5000.0, 0.0),
                        (8, "النظام الكهربائي", "Batteries", 8000.0, 0.0),
                        (9, "Electric System", "Charging Alternator", 10000.0, 0.0),
                        (10, "Engine Motor", "Top Overhaul", 10000.0, 0.0),
                        (11, "Engine Motor", "Major Overhaul", 20000.0, 0.0),
                        (12, "Oilers System", "Oil Cooler Clean", 5000.0, 0.0),
                        (13, "نظام التبريد", "Water Pump", 6000.0, 0.0),
                        (14, "نظام الهواء", "Turbocharger Check", 8000.0, 0.0),
                    ]
                    for u, c, p, l, us in default_parts:
                        db.add(MaintenancePart(generator_id=new_g.id, unit_num=u, category=c, part_name=p, lifespan_hours=l, used_hours=us))
                    db.commit()

                    st.success(f"تم إنشاء المولد {new_gen_code}")
                    db.close()
                    st.rerun()
                else:
                    st.warning("المولد موجود بالفعل بنفس الكود!")

    site_generators = db.query(Generator).filter(Generator.site_id == current_site_obj.id).all()
    gen_dict = {g.gen_code: g for g in site_generators}

    if not gen_dict:
        st.info("لا توجد مولدات في هذا الموقع. قم بإضافة مولد للبدء.")
        db.close()
    else:
        col_select_g, col_modal_btn = st.columns([2, 1])
        with col_select_g:
            selected_gen_code = st.selectbox("اختر المولد لاستعراض ومعالجة بياناته:", list(gen_dict.keys()))
            selected_gen_obj = gen_dict[selected_gen_code]
        with col_modal_btn:
            st.write("")
            st.write("")
            if st.button("📝 فتح نافذة إدخال وتعديل البيانات المعايرة"):
                edit_generator_modal(selected_gen_obj.id)

        # استرجاع بيانات المولد المختار
        st.subheader(f"📊 لوحة بيانات المعايرة والمراقبة للمولد ({selected_gen_obj.gen_code})")
        m_c1, m_c2, m_c3, m_c4 = st.columns(4)
        m_c1.metric("الطراز والسعة", f"{selected_gen_obj.model}", f"{selected_gen_obj.capacity_kw} kW")
        m_c2.metric("ساعات التشغيل / الهدف", f"{selected_gen_obj.run_hours} hrs", f"المستهدف: {selected_gen_obj.target_hours} hrs")
        m_c3.metric("معايرة الجهد المقاس", f"{selected_gen_obj.v_measured} V", f"الاسمي: {selected_gen_obj.v_nominal} V")
        m_c4.metric("حرارة المحرك / المحيطة", f"{selected_gen_obj.coolant_temp_c} °C", f"المحيطة: {selected_gen_obj.ambient_temp} °C")

        # فحص قيم المعايرة والتنبيهات
        alarm_messages = []
        if abs((selected_gen_obj.v_measured or 400) - (selected_gen_obj.v_nominal or 400)) > 20:
            alarm_messages.append(f"انحراف في الجهد الكهربائي للمولد {selected_gen_obj.gen_code}: الجهد المقاس {selected_gen_obj.v_measured} فولت!")
        if (selected_gen_obj.current_measured or 0) > (selected_gen_obj.current_max or 1000):
            alarm_messages.append(f"إنذار حمولة زائدة للتيار في المولد {selected_gen_obj.gen_code}!")
        if (selected_gen_obj.coolant_temp_c or 0) >= 95.0:
            alarm_messages.append(f"ارتفاع حرارة المحرك للمولد {selected_gen_obj.gen_code}: {selected_gen_obj.coolant_temp_c} درجة مئوية!")
        if (selected_gen_obj.oil_press_bar or 5) <= 1.8:
            alarm_messages.append(f"انخفاض ضغط زيت المحرك للمولد {selected_gen_obj.gen_code}!")

        remaining_target = selected_gen_obj.target_hours - selected_gen_obj.run_hours
        if remaining_target <= 50 and remaining_target > 0:
            alarm_messages.append(f"اقتراب تجاوز الساعات الافتراضية للمولد {selected_gen_obj.gen_code}. متبقي {remaining_target} ساعة.")
        elif remaining_target <= 0:
            alarm_messages.append(f"إنذار! تجاوز المولد {selected_gen_obj.gen_code} الساعات الافتراضية المجدولة للصيانة!")

        if alarm_messages:
            for msg in alarm_messages:
                st.error(f"🚨 {msg}")
            combined_alert_text = " . ".join(alarm_messages)
            play_audio(combined_alert_text, loop=True)

        # ---------------------------------------------------------
        # جدول الصيانة التنبؤية لـ 14 قطعة غيار عبر SQLAlchemy
        # ---------------------------------------------------------
        gen_parts = db.query(MaintenancePart).filter(MaintenancePart.generator_id == selected_gen_obj.id).order_by(MaintenancePart.unit_num).all()
        
        parts_list_data = []
        for p in gen_parts:
            parts_list_data.append({
                "id": p.id,
                "الوحدة": p.unit_num,
                "تصنيف القطعة": p.category,
                "قطع الغيار / الفلاتر": p.part_name,
                "العمر الافتراضي (ساعة)": p.lifespan_hours,
                "الساعات المنقضية (ساعة)": p.used_hours,
                "تجديد (تصفير)": False
            })

        st.subheader(f"🛢️ جدول الصيانة التنبؤية (14 قطعة/خدمة) - {selected_gen_obj.gen_code}")
        df_parts_input = pd.DataFrame(parts_list_data)

        edited_df = st.data_editor(
            df_parts_input,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "id": None, # إخفاء معرف قاعدة البيانات
                "تجديد (تصفير)": st.column_config.CheckboxColumn(
                    "تجديد (تصفير العداد)",
                    help="حدد هنا إذا تم استبدال القطعة لتصفير الساعات المنقضية",
                    default=False,
                )
            }
        )

        if st.button("🔄 تأكيد تحديث وتصفير القطع المحددة", type="primary"):
            for idx, row in edited_df.iterrows():
                p_id = row.get("id")
                is_reset = row.get("تجديد (تصفير)")
                life = float(row.get("العمر الافتراضي (ساعة)", 250))
                used = float(row.get("الساعات المنقضية (ساعة)", 0))
                
                if p_id:
                    part_db = db.query(MaintenancePart).filter(MaintenancePart.id == p_id).first()
                    if part_db:
                        part_db.category = row.get("تصنيف القطعة")
                        part_db.part_name = row.get("قطع الغيار / الفلاتر")
                        part_db.lifespan_hours = life
                        part_db.used_hours = 0.0 if is_reset else used
            db.commit()
            st.success("✅ تم تحديث قاعدة البيانات وتصفير القطع المحددة بنجاح!")
            db.close()
            st.rerun()

        # حساب النسب والألوان
        processed_rows = []
        bar_colors = []

        for idx, row in edited_df.iterrows():
            cat = str(row.get("تصنيف القطعة", "Other"))
            part = str(row.get("قطع الغيار / الفلاتر", "Part"))
            life = float(row.get("العمر الافتراضي (ساعة)", 250)) or 250.0
            used = float(row.get("الساعات المنقضية (ساعة)", 0)) or 0.0
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

        # الرسم البياني
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
            total_target_h = max(1.0, float(selected_gen_obj.target_hours))
            current_h = float(selected_gen_obj.run_hours)
            rem_h = max(0.0, total_target_h - current_h)

            labels_pie = ['الساعات المنقضية', 'الساعات المتبقية الافتراضية']
            values_pie = [current_h, rem_h]

            fig_pie = px.pie(
                names=labels_pie,
                values=values_pie,
                hole=0.5,
                title=f"نسب أداء ساعات التشغيل للمولد {selected_gen_obj.gen_code}",
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
            pdf.rect(10, 35, 190, 40, "F")
            pdf.set_xy(12, 37)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(24, 43, 73)
            
            pdf.cell(0, 5, f"Site Name: {sanitize_latin_only(selected_site_name)} | Address: {sanitize_latin_only(current_site_address)}", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Generator ID: {sanitize_latin_only(selected_gen_obj.gen_code)} | Model: {sanitize_latin_only(selected_gen_obj.model)} | Capacity: {selected_gen_obj.capacity_kw} kW", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Current Run Hours: {selected_gen_obj.run_hours} hrs | Target Hours: {selected_gen_obj.target_hours} hrs", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Electrical Calib: {selected_gen_obj.v_measured}V / {selected_gen_obj.freq_measured}Hz | Engine: {selected_gen_obj.coolant_temp_c} C / {selected_gen_obj.oil_press_bar} Bar", ln=True)
            
            amb_temp_val = selected_gen_obj.ambient_temp or 43.0
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
            label=f"🖨️ إصدار التقرير الشامل للمولد ({selected_gen_obj.gen_code}) في ({selected_site_name})",
            data=generate_full_pdf_bytes(),
            file_name=f"Report_{selected_site_name}_{selected_gen_obj.gen_code}_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
        db.close()

# =========================================================
# التطبيق 2: المتابعة اليومية وتقارير الإدارة والتذكيرات الآلية عبر SQLAlchemy
# =========================================================
elif selected_app == "📊 2. المتابعة اليومية وتقارير الإدارة والتذكيرات":
    st.title("📊 نظام المتابعة اليومية والتذكيرات وتقارير الصيانة")
    
    today_str = date.today().strftime("%Y-%m-%d")
    st.info(f"📅 **تاريخ اليوم:** {today_str} | **إشراف:** Addoma Trading Services")

    tab_mgr1, tab_mgr2 = st.tabs(["📋 التقرير الملخص اليومي لمدير الموقع", "⏰ التذكيرات والتنبيهات الآلية للفنيين"])

    db = get_db_session()
    user_company = db.query(Company).filter(Company.id == input_code).first()

    # الاستعلام عن القراءات اليومية للشركة الحالية
    today_readings = db.query(DailyReading).join(Generator).join(Site).filter(
        Site.company_id == user_company.id,
        DailyReading.log_date == date.today()
    ).all() if user_company else []

    # استعلام جميع المولدات التابعة للشركة
    all_company_generators = db.query(Generator).join(Site).filter(Site.company_id == user_company.id).all() if user_company else []

    logged_gen_ids = [r.generator_id for r in today_readings]
    total_gens_count = len(all_company_generators)
    logged_count = len(set(logged_gen_ids))

    with tab_mgr1:
        st.subheader("📝 تقرير ملخص قراءات اليوم لإدارة الموقع")
        
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("إجمالي المولدات المستهدفة", total_gens_count)
        col_m2.metric("المولدات المسجلة اليوم", logged_count)
        col_m3.metric("نسبة الإنجاز اليومي", f"{int((logged_count/total_gens_count)*100) if total_gens_count>0 else 0}%")

        st.divider()
        if today_readings:
            logs_list = []
            for r in today_readings:
                logs_list.append({
                    "timestamp": r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    "site": r.generator.site.name,
                    "generator": r.generator.gen_code,
                    "technician": r.technician_name,
                    "run_hours": r.run_hours,
                    "v_measured": r.v_measured,
                    "oil_press": r.oil_press_bar,
                    "coolant_temp": r.coolant_temp_c,
                    "status": r.status
                })
            df_daily = pd.DataFrame(logs_list)
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
            for r in today_readings:
                pdf.cell(widths[0], 5, sanitize_latin_only(r.generator.site.name)[:20], border=1)
                pdf.cell(widths[1], 5, sanitize_latin_only(r.generator.gen_code), border=1, align="C")
                pdf.cell(widths[2], 5, sanitize_latin_only(r.technician_name or "N/A")[:15], border=1)
                pdf.cell(widths[3], 5, str(r.run_hours), border=1, align="C")
                pdf.cell(widths[4], 5, str(r.v_measured), border=1, align="C")
                pdf.cell(widths[5], 5, str(r.oil_press_bar), border=1, align="C")
                pdf.cell(widths[6], 5, str(r.coolant_temp_c), border=1, align="C")
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
        
        unlogged_gens = [g for g in all_company_generators if g.id not in logged_gen_ids]

        if unlogged_gens:
            st.warning(f"⚠️ يوجد عدد ({len(unlogged_gens)}) مولد لم يتم تسجيل قراءاتها اليوم حتى الآن!")
            
            st.markdown("##### 📋 المولدات التي تطلب إرسال تذكير سريع للفنيين:")
            for un_gen in unlogged_gens:
                st.write(f"• **الموقع:** {un_gen.site.name} | **المولد:** {un_gen.gen_code}")
                
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
            
    db.close()

# =========================================================
# التطبيق 3: المساعد الذكي والكتالوجات (مدمج ومتطور)
# =========================================================
elif selected_app == "🤖 3. المساعد الذكي والكتالوجات وقراءة الأكواد":
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
# التطبيق 4: الفحص البصري للمعدات
# =========================================================
elif selected_app == "🔍 4. نظام فحص المعدات (WIC وغيرها)":
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
