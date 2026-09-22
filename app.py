import os
import re
import json
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import threading

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
from PIL import Image
from bs4 import BeautifulSoup
import requests
from fpdf import FPDF
import firebase_admin
from firebase_admin import credentials, firestore
import pdfplumber
import streamlit as st
from google import genai
import pyttsx3 # استيراد مكتبة تحويل النص إلى كلام

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

# جلب مفتاح Gemini بأمان من الإعدادات
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")

if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY. يرجى إضافته في st.secrets.")

# تهيئة عميل Gemini API
client = genai.Client(api_key=gemini_key) if gemini_key else None

# تهيئة محرك تحويل النص إلى كلام
engine = pyttsx3.init()
voices = engine.getProperty('voices')
# محاولة ضبط صوت عربي إن وجد (يعتمد على نظام التشغيل)
for voice in voices:
    if 'arabic' in voice.name.lower():
        engine.setProperty('voice', voice.id)
        break

def speak_text(text):
    """دالة لنطق النص باستخدام مسار منفصل لتجنب تجميد الواجهة"""
    def run_speech():
        try:
            # محرك pyttsx3 قد يحتاج إلى إعادة تهيئة داخل الـ thread في بعض الأنظمة
            local_engine = pyttsx3.init()
            local_engine.say(text)
            local_engine.runAndWait()
        except RuntimeError:
            pass # تجاهل خطأ التشغيل المتكرر
    
    t = threading.Thread(target=run_speech)
    t.start()


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
        # شريط علوي ملون (أزرق صناعي احترافي)
        self.set_fill_color(24, 43, 73)
        self.rect(0, 0, 210, 8, "F")

        # إضافة الشعار إن وجد
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=12, w=25)
            text_x = 40
        else:
            text_x = 10

        # عنوان التقرير وتفاصيل الشركة
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

        # خط فاصل أزرق خفيف 
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
# نظام إدارة المواقع والمولدات المتعددة (يُخزن في Session State)
# =========================================================
if "sites_data" not in st.session_state:
    st.session_state.sites_data = {
        "الموقع الرئيسي - الخرطوم": {
            "G1": {"model": "Perkins 410 kVA", "run_hours": 700.0, "target": 940.0, "kw": 410.0, "load": 250.0},
            "G2": {"model": "Cummins 250 kVA", "run_hours": 1200.0, "target": 1500.0, "kw": 250.0, "load": 180.0}
        }
    }

# =========================================================
# التطبيق 1: نظام الصيانة التنبؤية والتقارير الشاملة
# =========================================================
if selected_app == "⚙️ 1. الصيانة التنبؤية والمولدات (شامل التقارير)":
    st.title("⚙️ نظام الصيانة التنبؤية ومراقبة المولدات الصناعية")

    # خيار رفع الشعار
    st.sidebar.subheader("🎨 تخصيص التقرير المطبوع")
    logo_file = st.sidebar.file_uploader("رفع شعار الشركة (Logo)", type=["png", "jpg", "jpeg"], key="logo_up")

    # --- إدارة المواقع ---
    st.subheader("📍 إدارة المواقع والمولدات")
    col_site1, col_site2 = st.columns(2)
    with col_site1:
        new_site_name = st.text_input("إضافة موقع جديد:")
        if st.button("➕ أضف الموقع"):
            if new_site_name and new_site_name not in st.session_state.sites_data:
                st.session_state.sites_data[new_site_name] = {}
                st.success(f"تم إضافة الموقع: {new_site_name}")
                st.rerun()

    # اختيار الموقع الحالي
    site_list = list(st.session_state.sites_data.keys())
    if not site_list:
        st.warning("الرجاء إضافة موقع للبدء.")
        st.stop()
        
    selected_site = st.selectbox("اختر الموقع للعمل عليه:", site_list)

    # --- إدارة المولدات داخل الموقع ---
    with col_site2:
        new_gen_id = st.text_input(f"إضافة مولد جديد في ({selected_site}):", placeholder="مثال: G3")
        if st.button("➕ أضف المولد"):
            if new_gen_id and new_gen_id not in st.session_state.sites_data[selected_site]:
                st.session_state.sites_data[selected_site][new_gen_id] = {
                    "model": "غير محدد", "run_hours": 0.0, "target": 250.0, "kw": 0.0, "load": 0.0
                }
                st.success(f"تم إضافة المولد {new_gen_id} للموقع {selected_site}")
                st.rerun()

    gen_list = list(st.session_state.sites_data[selected_site].keys())
    
    if not gen_list:
         st.info("لا توجد مولدات في هذا الموقع. قم بإضافة مولد.")
    else:
        selected_gen = st.selectbox("اختر المولد:", gen_list)
        
        # استرجاع بيانات المولد المختار
        gen_info = st.session_state.sites_data[selected_site][selected_gen]

        with st.form("generator_comprehensive_form"):
            st.subheader(f"مدخلات القراءات والخدمة - المولد ({selected_gen})")
            gen_model = st.text_input("طراز / اسم المولد", value=gen_info["model"])
            run_hours = st.number_input("ساعات التشغيل الحالية", min_value=0.0, value=gen_info["run_hours"], step=10.0)
            future_run_hours = st.number_input("ساعات التشغيل المستهدفة", min_value=0.0, value=gen_info["target"], step=10.0)
            gen_kw = st.number_input("سعة المولد (kW)", min_value=0.0, value=float(gen_info["kw"]), step=10.0)
            load_kw = st.number_input("الحمولة الحالية (kW)", min_value=0.0, value=float(gen_info["load"]), step=10.0)
            
            voltage = st.number_input("الجهد (V)", value=400.0)
            freq = st.number_input("التردد (Hz)", value=50.0)
            coolant_temp = st.number_input("حرارة المحرك (°C)", value=85.0)
            amperes = st.number_input("التيار (A)", value=360.0)
            
            submit_btn = st.form_submit_button("💾 تحديث وحفظ بيانات المولد")
            
            if submit_btn:
                st.session_state.sites_data[selected_site][selected_gen] = {
                    "model": gen_model,
                    "run_hours": run_hours,
                    "target": future_run_hours,
                    "kw": gen_kw,
                    "load": load_kw
                }
                st.success("تم حفظ البيانات بنجاح!")

        # ---------------------------------------------------------
        # نظام التنبيه الصوتي
        # ---------------------------------------------------------
        # التحقق من اقتراب الساعات من الهدف (مثلاً باقي 50 ساعة أو أقل)
        remaining_target = future_run_hours - run_hours
        if remaining_target <= 50 and remaining_target > 0:
            msg = f"تنبيه! المولد {selected_gen} في موقع {selected_site} يقترب من موعد الصيانة. متبقي {remaining_target} ساعة."
            st.warning(f"🔊 {msg}")
            speak_text(msg)
        elif remaining_target <= 0:
             msg = f"إنذار! المولد {selected_gen} في موقع {selected_site} تجاوز موعد الصيانة المجدول!"
             st.error(f"🚨🔊 {msg}")
             speak_text(msg)
        
        # ---------------------------------------------------------
        # جدول قطع الغيار والصيانة (منفصل لكل مولد)
        # ---------------------------------------------------------
        # لتبسيط المثال، نستخدم مفتاح فريد لكل مولد في الـ Session State لحفظ قطع الغيار
        parts_key = f"parts_{selected_site}_{selected_gen}"
        if parts_key not in st.session_state:
            st.session_state[parts_key] = [
                {"الوحدة": 1, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Oil Filter", "العمر الافتراضي (ساعة)": 250.0, "الساعات المنقضية (ساعة)": 210.0, "تجديد (تصفير)": False},
                {"الوحدة": 2, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Primary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 430.0, "تجديد (تصفير)": False},
                {"الوحدة": 3, "تصنيف القطعة": "Schedule Services", "قطع الغيار / الفلاتر": "Secondary Fuel Filter", "العمر الافتراضي (ساعة)": 500.0, "الساعات المنقضية (ساعة)": 455.0, "تجديد (تصفير)": False},
                {"الوحدة": 4, "تصنيف القطعة": "Air System", "قطع الغيار / الفلاتر": "Air Filter", "العمر الافتراضي (ساعة)": 1000.0, "الساعات المنقضية (ساعة)": 860.0, "تجديد (تصفير)": False},
                {"الوحدة": 5, "تصنيف القطعة": "Fan Belt System", "قطع الغيار / الفلاتر": "Fan Belt", "العمر الافتراضي (ساعة)": 2000.0, "الساعات المنقضية (ساعة)": 1550.0, "تجديد (تصفير)": False},
                {"الوحدة": 6, "تصنيف القطعة": "Cooling System", "قطع الغيار / الفلاتر": "ELC Coolant", "العمر الافتراضي (ساعة)": 3000.0, "الساعات المنقضية (ساعة)": 2200.0, "تجديد (تصفير)": False},
                {"الوحدة": 7, "تصنيف القطعة": "Feul System", "قطع الغيار / الفلاتر": "Injectors Check", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 4400.0, "تجديد (تصفير)": False},
                {"الوحدة": 8, "تصنيف القطعة": "النظام الكهربائي", "قطع الغيار / الفلاتر": "Batteries", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 6100.0, "تجديد (تصفير)": False},
                {"الوحدة": 9, "تصنيف القطعة": "Electric System", "قطع الغيار / الفلاتر": "Charging Alternator", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 8900.0, "تجديد (تصفير)": False},
                {"الوحدة": 10, "تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Top Overhaul", "العمر الافتراضي (ساعة)": 10000.0, "الساعات المنقضية (ساعة)": 9100.0, "تجديد (تصفير)": False},
                {"الوحدة": 11, "تصنيف القطعة": "Engine Motor", "قطع الغيار / الفلاتر": "Major Overhaul", "العمر الافتراضي (ساعة)": 20000.0, "الساعات المنقضية (ساعة)": 15000.0, "تجديد (تصفير)": False},
                {"الوحدة": 12, "تصنيف القطعة": "Oilers System", "قطع الغيار / الفلاتر": "Oil Cooler Clean", "العمر الافتراضي (ساعة)": 5000.0, "الساعات المنقضية (ساعة)": 3800.0, "تجديد (تصفير)": False},
                {"الوحدة": 13, "تصنيف القطعة": "نظام التبريد", "قطع الغيار / الفلاتر": "Water Pump", "العمر الافتراضي (ساعة)": 6000.0, "الساعات المنقضية (ساعة)": 5200.0, "تجديد (تصفير)": False},
                {"الوحدة": 14, "تصنيف القطعة": "نظام الهواء", "قطع الغيار / الفلاتر": "Turbocharger Check", "العمر الافتراضي (ساعة)": 8000.0, "الساعات المنقضية (ساعة)": 7100.0, "تجديد (تصفير)": False},
            ]

        st.subheader(f"🛢️ جدول الصيانة التنبؤية - {selected_gen}")
        df_parts_input = pd.DataFrame(st.session_state[parts_key])
        
        st.info("💡 **طريقة الاستبدال:** حدد مربع (تجديد) بجانب القطعة التي تم تغييرها، ثم اضغط على زر التحديث بالأسفل لتصفير عداد ساعاتها.")
        
        edited_df = st.data_editor(
            df_parts_input, 
            num_rows="dynamic", 
            width="stretch",
            column_config={
                "تجديد (تصفير)": st.column_config.CheckboxColumn(
                    "تجديد (تصفير العداد)",
                    help="حدد هنا إذا تم تغيير القطعة بجديدة لتصفير الساعات",
                    default=False,
                )
            }
        )

        if st.button("🔄 تأكيد التحديث واستبدال القطع المحددة", type="primary"):
            new_data = []
            for idx, row in edited_df.iterrows():
                item = row.to_dict()
                if item.get("تجديد (تصفير)"):
                    item["الساعات المنقضية (ساعة)"] = 0.0
                    item["تجديد (تصفير)"] = False 
                new_data.append(item)
            st.session_state[parts_key] = new_data
            st.success("✅ تم التحديث بنجاح!")
            st.rerun()

        # معالجة البيانات وإطلاق الإنذارات لقطع الغيار
        processed_rows = []
        for idx, row in pd.DataFrame(st.session_state[parts_key]).iterrows():
            cat = str(row.get("تصنيف القطعة", "Other"))
            part = str(row.get("قطع الغيار / الفلاتر", "Part"))
            life = pd.to_numeric(row.get("العمر الافتراضي (ساعة)", 250), errors="coerce") or 250.0
            used = pd.to_numeric(row.get("الساعات المنقضية (ساعة)", 0), errors="coerce") or 0.0
            rem = life - used
            pct = (used / life) * 100 if life > 0 else 0
            status = "تنبيه فوري (خطر)" if rem <= 0 or pct >= 90 else ("قرب الخدمة (استعداد)" if pct >= 75 else "حالة جيدة")
            
            # إنذار صوتي لقطع الغيار
            if rem <= 0 or pct >= 90:
                part_msg = f"تنبيه! القطعة {part} في المولد {selected_gen} تحتاج لاستبدال فوري."
                st.error(f"🚨 {part_msg}")
                # speak_text(part_msg) # يمكنك تفعيله، قد يكون مزعجاً إذا كثرت القطع

            processed_rows.append({
                "تصنيف القطعة": cat, "قطع الغيار / الفلاتر": part, "العمر الافتراضي (ساعة)": life,
                "الساعات المنقضية (ساعة)": used, "المدة المتبقية (ساعة)": max(0.0, rem),
                "نسبة الاستهلاك": f"{pct:.0f}%", "حالة التنبيه": status
            })
        df_result = pd.DataFrame(processed_rows)

        st.divider()
        st.subheader("📷 إرفاق صور المولد وقطع الغيار للتقرير")
        col_up1, col_up2 = st.columns(2)
        with col_up1:
            gen_img_file = st.file_uploader("رفع صورة للمولد / لوحة التحكم", type=["png", "jpg", "jpeg"])
        with col_up2:
            parts_img_file = st.file_uploader("رفع صورة للقطع المستبدلة / موقع العمل", type=["png", "jpg", "jpeg"])

        st.divider()
        st.subheader("📊 الرسوم البيانية لتحديد كفاءة المولد والقطع")
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            fig_bar = px.bar(df_result, x="قطع الغيار / الفلاتر", y=["الساعات المنقضية (ساعة)", "المدة المتبقية (ساعة)"], title="استهلاك قطع الغيار", barmode="stack", color_discrete_sequence=["#d9534f", "#28a745"])
            st.plotly_chart(fig_bar, use_container_width=True)
        with chart_col2:
            fig_pie = px.pie(df_result, names="حالة التنبيه", title="توزيع حالات الصيانة", color_discrete_sequence=["#28a745", "#ffc107", "#dc3545"])
            st.plotly_chart(fig_pie, use_container_width=True)

        def generate_full_pdf_bytes():
            temp_logo_path = None
            if logo_file:
                temp_logo_path = f"temp_logo_{uuid.uuid4().hex}.png"
                with open(temp_logo_path, "wb") as f:
                    f.write(logo_file.getbuffer())

            pdf = ComprehensivePDF("GENERATOR PREDICTIVE MAINTENANCE REPORT", logo_path=temp_logo_path)
            pdf.add_page()
            
            pdf.set_fill_color(245, 247, 250)
            pdf.rect(10, 35, 190, 15, "F")
            pdf.set_xy(12, 37)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(24, 43, 73)
            # إضافة اسم الموقع والمولد في التقرير
            pdf.cell(0, 5, f"Site: {sanitize_latin_only(selected_site)} | Gen ID: {sanitize_latin_only(selected_gen)}", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Generator Model: {sanitize_latin_only(gen_model)} | Total Operating Hours: {run_hours} hrs", ln=True)
            pdf.set_x(12)
            pdf.cell(0, 5, f"Client Name: {sanitize_latin_only(client_name)} | Capacity: {gen_kw} kW", ln=True)
            pdf.ln(8)

            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(24, 43, 73)
            pdf.set_text_color(255, 255, 255)
            
            headers_pdf = ["Part / Service Name", "Lifespan", "Used Hours", "Remaining", "Maintenance Status"]
            widths = [50, 25, 25, 25, 65]
            for h, w in zip(headers_pdf, widths):
                pdf.cell(w, 6, h, border=1, fill=True, align="C")
            pdf.ln()
            
            pdf.set_font("Helvetica", "", 7)
            pdf.set_text_color(0, 0, 0)
            
            for i, row in df_result.iterrows():
                fill = (i % 2 == 0)
                pdf.set_fill_color(240, 243, 246) if fill else pdf.set_fill_color(255, 255, 255)
                
                pdf.cell(widths[0], 5, sanitize_latin_only(str(row["قطع الغيار / الفلاتر"]))[:28], border=1, fill=fill)
                pdf.cell(widths[1], 5, str(row["العمر الافتراضي (ساعة)"]), border=1, align="C", fill=fill)
                pdf.cell(widths[2], 5, str(row["الساعات المنقضية (ساعة)"]), border=1, align="C", fill=fill)
                pdf.cell(widths[3], 5, str(row["المدة المتبقية (ساعة)"]), border=1, align="C", fill=fill)
                pdf.cell(widths[4], 5, sanitize_latin_only(str(row["حالة التنبيه"])), border=1, fill=fill)
                pdf.ln()

            if gen_img_file or parts_img_file:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(24, 43, 73)
                pdf.cell(0, 6, "Field Images & Documentation:", ln=True)
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
                pdf.cell(0, 6, "Performance & Maintenance Visual Analytics:", ln=True)
                
                fig_bar_p, ax_bar_p = plt.subplots(figsize=(7, 3.2))
                p_short = [sanitize_latin_only(str(x))[:12] for x in df_result["قطع الغيار / الفلاتر"]]
                ax_bar_p.bar(p_short, df_result["الساعات المنقضية (ساعة)"].values, label="Used", color="#d9534f")
                ax_bar_p.set_title("Parts Lifespan Chart", fontsize=9, fontweight='bold', color='#182B49')
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
            label=f"🖨️ إصدار التقرير للمولد ({selected_gen}) في ({selected_site})",
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

    # 1. مدخل كود العطل
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

            # 2. البحث داخل صفحات الكتالوج المرفوع (إن وجد)
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

            # 3. القاعدة السريعة للأعطال الشائعة
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

            elif any(k in f for k in ["fail to start", "start fail", "crank", "fail to stop", "stop fail"]):
                st.write("• **طبيعة المشكلة:** فشل المحرك في الدوران أو الاستجابة لأمر التشغيل/الإيقاف.")
                st.write("• **الخطوات:** 1. فحص ريليه التشغيل وسولينويد الديزل. 2. فحص قوة البطاريات والمارش. 3. فحص خطوط الوقود.")

            elif any(k in f for k in ["battery", "charge", "charge alt", "low battery", "high battery"]):
                st.write("• **طبيعة المشكلة:** عدم شحن البطارية أو خلل في دينامو الشحن.")
                st.write("• **الخطوات:** 1. فحص سير الدينامو وتوصيلة الطرف (WL/D+). 2. قياس الجهد على أطراف البطارية أثناء التشغيل.")

            elif any(k in f for k in ["breaker", "contactor", "ats", "fail to close", "fail to open"]):
                st.write("• **طبيعة المشكلة:** فشل قاطع التغذية أو الكونتاكتور في الفتح أو الإغلاق.")
                st.write("• **الخطوات:** 1. فحص ملف المساعد (Auxiliary Switch). 2. التأكد من جهد إشارة التوصيل من DSE. 3. فحص الوقاية الميكانيكية للقاطع.")

            elif any(k in f for k in ["emergency", "e-stop", "estop", "stop button"]):
                st.write("• **طبيعة المشكلة:** تفعيل زر الإيقاف في الطوارئ أو انقطاع دائرة التغذية عنه.")
                st.write("• **الخطوات:** 1. إعادة إرجاع مفتاح الطوارئ الفيزيائي. 2. فحص الدخل (Input) خلف اللوحة ورقم النقطة في DSE.")

            else:
                st.write(f"• **طبيعة المشكلة:** إنذار تشغيلي/تحذيري برمز `{clean_fault}`.")
                st.write("• **الخطوات:** 1. مراجعة القائمة التشخيصية للكتالوج. 2. إعادة ضبط الإنذار (Reset). 3. فحص أسلاك الدخل والخرج المبرمجة.")

            # 4. التوليد والتحليل العميق عبر الذكاء الاصطناعي (Gemini)
            st.markdown("---")
            st.markdown("🤖 **تحليل التقرير العميق عبر الذكاء الاصطناعي (Gemini):**")
            with st.spinner("جاري استخلاص التوصيات الهندسية من نموذج Gemini API..."):
                ai_analysis = analyze_fault_with_gemini(clean_fault, catalog_context)
                st.markdown(ai_analysis)

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
