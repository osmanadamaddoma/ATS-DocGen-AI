import os
import re
import uuid
import time
import urllib.parse
from datetime import datetime, timedelta
import io

import pandas as pd
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import pdfplumber
import streamlit as st
from google import genai
from gtts import gTTS
from fpdf import FPDF

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
    initial_sidebar_state="expanded"
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
                    "model": "Perkins 410 kVA - DSE 7320",
                    "run_hours": 700.0,
                    "target": 940.0,
                    "kw": 328.0,
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
                    "model": "Cummins 250 kVA - DSE 8610 MKII",
                    "run_hours": 1200.0,
                    "target": 1500.0,
                    "kw": 200.0,
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

if "daily_logs" not in st.session_state:
    today_str = datetime.now().strftime("%Y-%m-%d")
    st.session_state.daily_logs = [
        {
            "timestamp": f"{today_str} 08:30:00",
            "date": today_str,
            "site": "الموقع الرئيسي - الخرطوم",
            "generator": "G1",
            "technician": "فني الصيانة المناوب",
            "run_hours": 700.0,
            "v_measured": 398.0,
            "oil_press": 4.5,
            "coolant_temp": 85.0,
            "status": "طبيعي"
        }
    ]

# جلب مفتاح Gemini بأمان
gemini_key = st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
if not gemini_key and "firebase" in st.secrets:
    gemini_key = st.secrets["firebase"].get("GEMINI_API_KEY")

if not gemini_key:
    st.sidebar.warning("⚠️ لم يتم العثور على مفتاح GEMINI_API_KEY.")

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
                <audio autoplay loop controls style="width: 100%; border-radius: 8px;">
                    <source src="data:audio/mp3;base64,{b64_audio}" type="audio/mp3">
                </audio>
            """
            st.components.v1.html(audio_html, height=60)
        else:
            audio_data.seek(0)
            st.audio(audio_data, format='audio/mp3', autoplay=True)
    except Exception as e:
        st.error(f"تعذر تشغيل الصوت: {e}")

@st.cache_data(ttl=3600)
def analyze_fault_with_gemini(fault_code, context_text=""):
    if not client:
        return "⚠️ مفتاح API غير متوفر للذكاء الاصطناعي."

    prompt = f"""
    أنت استشاري هندسة كهروميكانيكية خبير في:
    - صيانة وتزامن المولدات الصناعية (Perkins, Cummins) باستخدام لوحات DSE (8610 MKII, 7320 MKII).
    - أنظمة التبريد الصناعية ومتحكمات Emerson (غرف WIC 10 و WIC 40).
    - لف المحركات الكهربائية 3-Phase.

    العميل يستفسر عن العطل: "{fault_code}"
    
    مقتطفات الكتالوج (إن وجدت):
    \"\"\"
    {context_text if context_text else "لا يوجد نص مباشر."}
    \"\"\"

    أصدر تقريراً تشخيصياً دقيقاً يشمل:
    1. **طبيعة المشكلة**: تحليل هندسي للسبب (ميكانيكي/كهربائي/برمجي).
    2. **الأسباب الجذرية**: أهم 3 أسباب محتملة.
    3. **خطوات الفحص والمعالجة**: الإجراءات الميدانية خطوة بخطوة.
    الرد بلغة عربية تقنية واضحة.
    """

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-1.5-flash", 
                contents=prompt,
            )
            return response.text
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                if attempt < 2:
                    time.sleep(2)
                    continue
                return "⚠️ خوادم الذكاء الاصطناعي تواجه ضغطاً عالياً حالياً. يرجى المحاولة بعد قليل."
            return f"❌ خطأ في النظام الذكي: {e}"

# =========================================================
# 1. دوال النظام المساعدة وتصميم تقرير الـ PDF
# =========================================================
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
        text_x = 10
        if self.logo_path and os.path.exists(self.logo_path):
            self.image(self.logo_path, x=10, y=12, w=25)
            text_x = 40
        
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
        self.cell(0, 4, f"Page {self.page_no()} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="C")

# =========================================================
# 2. نظام الاشتراكات الموحد والباقات
# =========================================================
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم أدومة (Addoma Trading Services)",
        "plan": "الوصول الإداري الشامل (Admin)",
        "start_date": "2026-01-01",
        "duration_days": 365,
    },
    "CLIENT-M-881": {
        "name": "شركة النيل للصناعات الهندسية",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-01",
        "duration_days": 30,
    }
}

st.sidebar.header("🔐 بوابة تفعيل النظام الموحد")
input_code = st.sidebar.text_input("أدخل كود التفعيل:", type="password")

is_pro = False
client_name = "زائر"
plan_type = "غير مفعل"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    today = datetime.now().date()
    
    if today <= expiry_dt:
        is_pro = True
        st.sidebar.success(f"مرحباً بك: {client_name}")
        st.sidebar.caption(f"الباقة: {plan_type} | المتبقي: {(expiry_dt - today).days} يوم")
    else:
        st.sidebar.error("❌ انتهت صلاحية الاشتراك.")
elif input_code:
    st.sidebar.error("❌ كود التفعيل غير صحيح.")

if not is_pro:
    st.warning("🔒 أدخل كود التفعيل في القائمة الجانبية للوصول لخدمات الصيانة والتنبؤ.")
    st.stop()

st.sidebar.divider()

# =========================================================
# 3. قائمة اختيار التطبيق المركزي
# =========================================================
selected_app = st.sidebar.radio(
    "اختر النظام المطلوب:",
    [
        "⚙️ 1. الصيانة التنبؤية والمولدات",
        "📊 2. المتابعة اليومية وتقارير الإدارة",
        "🤖 3. المساعد الذكي والتشخيص (DSE/Emerson)",
        "🔍 4. نظام فحص المعدات (WIC & Motors)"
    ]
)
st.sidebar.divider()

# =========================================================
# النافذة المنبثقة لإدخال بيانات المولد
# =========================================================
@st.dialog("📝 إدخال وتعديل بيانات المولد والمعايرة")
def edit_generator_modal(site_key, gen_key):
    gen_data = st.session_state.sites_data[site_key]["generators"][gen_key]
    elec = gen_data.get("calib_elec", {})
    eng = gen_data.get("calib_engine", {})

    st.markdown(f"### ⚙️ {gen_key} - {site_key}")
    tech_name = st.text_input("اسم الفني المسؤول:", value="فني الصيانة المناوب")
    
    t1, t2, t3 = st.tabs(["البيانات الأساسية", "معايرة الكهرباء", "معايرة المحرك"])

    with t1:
        new_model = st.text_input("طراز / لوحة التحكم (مثل DSE 8610)", value=gen_data.get("model", ""))
        c1, c2 = st.columns(2)
        new_run_hours = c1.number_input("ساعات التشغيل", min_value=0.0, value=float(gen_data.get("run_hours", 0.0)))
        new_target = c2.number_input("الهدف للصيانة", min_value=0.0, value=float(gen_data.get("target", 250.0)))
        new_kw = c1.number_input("سعة المولد (kW)", min_value=0.0, value=float(gen_data.get("kw", 0.0)))
        new_load = c2.number_input("الحمولة الحالية (kW)", min_value=0.0, value=float(gen_data.get("load", 0.0)))

    with t2:
        ec1, ec2 = st.columns(2)
        v_nom = ec1.number_input("الجهد الاسمي (V)", value=float(elec.get("v_nominal", 400.0)))
        v_meas = ec2.number_input("الجهد المقاس (V)", value=float(elec.get("v_measured", 398.0)))
        f_nom = ec1.number_input("التردد الاسمي (Hz)", value=float(elec.get("freq_nominal", 50.0)))
        f_meas = ec2.number_input("التردد المقاس (Hz)", value=float(elec.get("freq_measured", 50.0)))
        c_max = ec1.number_input("أقصى تيار (A)", value=float(elec.get("current_max", 600.0)))
        c_meas = ec2.number_input("التيار المقاس (A)", value=float(elec.get("current_measured", 360.0)))
        pf_val = ec1.number_input("معامل القدرة (PF)", value=float(elec.get("pf", 0.85)))
        ct_rat = ec2.text_input("نسبة CT", value=str(elec.get("ct_ratio", "600/5")))

    with t3:
        mc1, mc2 = st.columns(2)
        o_press = mc1.number_input("ضغط الزيت (Bar)", value=float(eng.get("oil_press_bar", 4.5)))
        c_temp = mc2.number_input("حرارة التبريد (°C)", value=float(eng.get("coolant_temp_c", 85.0)))
        r_rpm = mc1.number_input("سرعة المحرك (RPM)", value=float(eng.get("rpm", 1500.0)))
        b_volt = mc2.number_input("جهد البطارية (V)", value=float(eng.get("battery_v", 26.0)))
        ambient_t = mc1.number_input("الحرارة المحيطة (°C)", value=float(eng.get("ambient_temp", 43.0)))

    if st.button("💾 حفظ السجل", use_container_width=True, type="primary"):
        errors = []
        if not (0 <= c_temp <= 125): errors.append(f"❌ حرارة المحرك غير منطقية ({c_temp}°C).")
        if not (0 <= o_press <= 12): errors.append(f"❌ ضغط الزيت خارج النطاق التشغيلي ({o_press} Bar).")
        if not (100 <= v_meas <= 600): errors.append(f"❌ الجهد المقاس غير منطقي ({v_meas} V).")

        if errors:
            for err in errors: st.error(err)
        else:
            st.session_state.sites_data[site_key]["generators"][gen_key].update({
                "model": new_model, "run_hours": new_run_hours, "target": new_target,
                "kw": new_kw, "load": new_load,
                "calib_elec": {"v_nominal": v_nom, "v_measured": v_meas, "freq_nominal": f_nom, "freq_measured": f_meas, "current_max": c_max, "current_measured": c_meas, "pf": pf_val, "ct_ratio": ct_rat},
                "calib_engine": {"oil_press_bar": o_press, "coolant_temp_c": c_temp, "rpm": r_rpm, "battery_v": b_volt, "ambient_temp": ambient_t}
            })
            st.session_state.daily_logs.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "site": site_key, "generator": gen_key, "technician": tech_name,
                "run_hours": new_run_hours, "v_measured": v_meas, "oil_press": o_press,
                "coolant_temp": c_temp, "status": "محدث وصحيح"
            })
            st.toast("✅ تم التحديث بنجاح!", icon="💾")
            time.sleep(1)
            st.rerun()

# =========================================================
# التطبيق 1: الصيانة التنبؤية والمولدات
# =========================================================
if selected_app.startswith("⚙️ 1"):
    st.title("⚙️ نظام الصيانة التنبؤية للمولدات الصناعية")

    col_top1, col_top2 = st.columns([5, 1])
    with col_top2:
        mute_label = "🔇 كتم الصوت" if not st.session_state.audio_muted else "🔊 تفعيل الصوت"
        if st.button(mute_label, use_container_width=True):
            st.session_state.audio_muted = not st.session_state.audio_muted
            st.rerun()

    logo_file = st.sidebar.file_uploader("تخصيص: رفع شعار التقرير", type=["png", "jpg", "jpeg"])

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        new_site = st.text_input("إضافة موقع جديد:")
        new_addr = st.text_input("عنوان الموقع:")
        if st.button("➕ إضافة الموقع") and new_site and new_site not in st.session_state.sites_data:
            st.session_state.sites_data[new_site] = {"address": new_addr or "غير محدد", "generators": {}}
            st.toast(f"تمت الإضافة: {new_site}")
            st.rerun()

    site_list = list(st.session_state.sites_data.keys())
    if not site_list:
        st.stop()

    with col_s2:
        selected_site = st.selectbox("الموقع الحالي:", site_list)

    st.divider()
    c_g1, c_g2 = st.columns([2, 1])
    with c_g1:
        new_gen = st.text_input(f"معرف مولد جديد في {selected_site}:", placeholder="G3")
    with c_g2:
        st.write("")
        st.write("")
        if st.button("➕ إنشاء المولد") and new_gen and new_gen not in st.session_state.sites_data[selected_site]["generators"]:
            st.session_state.sites_data[selected_site]["generators"][new_gen] = {
                "model": "Standard Engine - DSE Panel", "run_hours": 0.0, "target": 250.0, "kw": 100.0, "load": 50.0,
                "calib_elec": {"v_nominal": 400.0, "v_measured": 400.0, "freq_nominal": 50.0, "freq_measured": 50.0, "current_max": 200.0, "current_measured": 100.0, "pf": 0.8, "ct_ratio": "200/5"},
                "calib_engine": {"oil_press_bar": 4.0, "coolant_temp_c": 80.0, "rpm": 1500.0, "battery_v": 24.0, "ambient_temp": 43.0}
            }
            st.rerun()

    gen_list = list(st.session_state.sites_data[selected_site]["generators"].keys())
    if not gen_list:
        st.info("لا توجد مولدات مسجلة في هذا الموقع.")
    else:
        c_sel, c_btn = st.columns([3, 1])
        with c_sel:
            selected_gen = st.selectbox("المولد النشط:", gen_list)
        with c_btn:
            st.write("")
            st.write("")
            if st.button("📝 تحديث القراءات", use_container_width=True):
                edit_generator_modal(selected_site, selected_gen)

        gen_info = st.session_state.sites_data[selected_site]["generators"][selected_gen]
        cal_e = gen_info.get("calib_elec", {})
        cal_m = gen_info.get("calib_engine", {})

        st.markdown(f"#### 📊 مؤشرات الأداء: {selected_gen}")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("طراز اللوحة والسعة", f"{gen_info.get('kw')} kW", f"{gen_info.get('model')}")
        m2.metric("الساعات / الهدف", f"{gen_info['run_hours']} h", f"متبقي: {max(0, gen_info['target'] - gen_info['run_hours'])} h", delta_color="inverse")
        m3.metric("الجهد الكهربائي", f"{cal_e.get('v_measured')} V", f"الفرق: {cal_e.get('v_measured', 400) - cal_e.get('v_nominal', 400)} V", delta_color="inverse")
        m4.metric("حرارة المحرك", f"{cal_m.get('coolant_temp_c')} °C", f"المحيطة: {cal_m.get('ambient_temp')} °C", delta_color="off")

        alarms = []
        if abs(cal_e.get("v_measured", 400) - cal_e.get("v_nominal", 400)) > 20:
            alarms.append(f"انحراف في الجهد المولد {selected_gen}.")
        if cal_e.get("current_measured", 0) > cal_e.get("current_max", 1000):
            alarms.append(f"Over Current (حمولة زائدة) في {selected_gen}.")
        if cal_m.get("coolant_temp_c", 0) >= 95.0:
            alarms.append(f"ارتفاع حرارة المحرك (High Coolant Temp).")
        if gen_info["target"] - gen_info["run_hours"] <= 0:
            alarms.append(f"تجاوز الساعات الافتراضية المجدولة للصيانة!")

        if alarms:
            for msg in alarms: st.error(f"🚨 {msg}")
            play_audio(" . ".join(alarms), loop=True)

        # جدول الصيانة
        p_key = f"parts_{selected_site}_{selected_gen}"
        if p_key not in st.session_state:
            st.session_state[p_key] = [
                {"الوحدة": 1, "القطعة": "Oil Filter", "الافتراضي": 250.0, "المنقضي": 180.0, "تصفير": False},
                {"الوحدة": 2, "القطعة": "Primary Fuel Filter", "الافتراضي": 500.0, "المنقضي": 430.0, "تصفير": False},
                {"الوحدة": 3, "القطعة": "Air Filter", "الافتراضي": 1000.0, "المنقضي": 650.0, "تصفير": False},
                {"الوحدة": 4, "القطعة": "Fan Belt", "الافتراضي": 2000.0, "المنقضي": 1550.0, "تصفير": False},
            ]

        st.subheader("🛢️ الصيانة الدورية وقطع الغيار")
        ed_df = st.data_editor(pd.DataFrame(st.session_state[p_key]), num_rows="dynamic", use_container_width=True)
        
        if st.button("🔄 تأكيد تحديث الساعات وتصفير القطع المحددة", type="primary"):
            new_list = []
            for _, row in ed_df.iterrows():
                d = row.to_dict()
                if d.get("تصفير"):
                    d["المنقضي"] = 0.0
                    d["تصفير"] = False
                new_list.append(d)
            st.session_state[p_key] = new_list
            st.rerun()

# =========================================================
# التطبيق 2: المتابعة اليومية والتقارير
# =========================================================
elif selected_app.startswith("📊 2"):
    st.title("📊 نظام المتابعة اليومية وتقارير الإدارة")
    today = datetime.now().strftime("%Y-%m-%d")
    logs = [l for l in st.session_state.daily_logs if l["date"] == today]

    if logs:
        st.dataframe(pd.DataFrame(logs), use_container_width=True)
    else:
        st.warning("لم يتم إدخال أي قراءات اليوم.")

    st.divider()
    tech_phone = st.text_input("رقم هاتف الفني لإرسال تذكير (مثال: 249912345678):")
    if tech_phone:
        msg = urllib.parse.quote(f"تذكير: يرجى استكمال تسجيل قراءات المولدات لتاريخ {today}.")
        st.markdown(f'<a href="https://wa.me/{tech_phone}?text={msg}" target="_blank"><button style="background:#25D366; color:white; padding:8px 16px; border:none; border-radius:4px;">💬 إرسال تذكير عبر واتساب</button></a>', unsafe_allow_html=True)

# =========================================================
# التطبيق 3: المساعد الذكي والكتالوجات (DSE/Emerson)
# =========================================================
elif selected_app.startswith("🤖 3"):
    st.title("🤖 المساعد الذكي الهندسي والتشخيص الفوري")
    
    col_1, col_2 = st.columns(2)
    with col_1:
        st.subheader("📚 رفع كتالوج PDF (DSE/Engine)")
        m_file = st.file_uploader("رفع دليل الاستخدام", type=["pdf"])
        if m_file and ("loaded_pdf" not in st.session_state or st.session_state.loaded_pdf != m_file.name):
            with st.spinner("جاري القراءة..."):
                pages = []
                with pdfplumber.open(m_file) as pdf:
                    for i, p in enumerate(pdf.pages):
                        pages.append({"num": i+1, "txt": p.extract_text() or ""})
                st.session_state.pdf_pages = pages
                st.session_state.loaded_pdf = m_file.name
                st.toast("تمت القراءة بنجاح!")
    
    with col_2:
        st.subheader("📷 قراءة أكواد الشاشات")
        cam = st.camera_input("تصوير شاشة العطل")

    fault_code = st.text_input("أدخل كود العطل (مثال: MSC Link Failure, Defrost Error, Over Current):")
    if st.button("🔍 تحليل هندسي متقدم", type="primary") and fault_code:
        f = fault_code.lower().strip()
        st.markdown(f"### التشخيص الميداني السريع لـ: `{fault_code}`")
        
        # التخصيص المخفي الدقيق لمعدات العميل (DSE & Emerson)
        if "msc" in f or "sync" in f or "bus not live" in f:
            st.write("• **الأنظمة المتأثرة:** لوحات التزامن (DSE 8610 MKII).")
            st.write("• **الإجراءات:** 1. فحص كابل ربط MSC (Belden). 2. التأكد من تطابق الـ MSC ID للمولدات. 3. قياس مقاومة نهاية الخط (120 Ohm) على أطراف MSC.")
        elif "defrost" in f or "sensor" in f or "wic" in f:
            st.write("• **الأنظمة المتأثرة:** غرف التبريد WIC 10 / WIC 40 (متحكمات Emerson).")
            st.write("• **الإجراءات:** 1. فحص حساس المبخر (Evaporator Sensor). 2. التأكد من تلامس سخانات الإذابة (Defrost Heaters). 3. مراجعة بارامترات الإذابة في لوحة Emerson.")
        elif "current" in f or "overload" in f:
            st.write("• **الأنظمة المتأثرة:** المولدات والحمل الكهربائي.")
            st.write("• **الإجراءات:** 1. موازنة الأحمال بين الفازات. 2. فحص محولات التيار (CT) ولوحة التوزيع.")
        else:
            st.write("• **توجيه عام:** قم بمراجعة الكتالوج أو إجراء إعادة ضبط (Reset) للإنذار وفحص الحساسات المرتبطة.")

        st.markdown("---")
        st.markdown("**🤖 تحليل Gemini الاستشاري العميق:**")
        with st.spinner("استخلاص التوصيات من نموذج الذكاء الاصطناعي..."):
            ctx = ""
            if "pdf_pages" in st.session_state:
                lines = []
                for p in st.session_state.pdf_pages:
                    for l in p["txt"].split("\n"):
                        if re.search(re.escape(f), l, re.IGNORECASE):
                            lines.append(l)
                ctx = "\n".join(lines[:5])
            
            ai_res = analyze_fault_with_gemini(fault_code, ctx)
            st.write(ai_res)

# =========================================================
# التطبيق 4: نظام فحص المعدات (WIC & Motors)
# =========================================================
elif selected_app.startswith("🔍 4"):
    st.title("🔍 الفحص البصري التخصصي للمعدات")
    eq = st.selectbox("المعدة المستهدفة:", [
        "غرف تبريد وتجميد WIC 10 و WIC 40",
        "لوحات التحكم والتزامن (DSE)",
        "محركات 3-Phase (Stator Rewinding)"
    ])
    
    if eq == "غرف تبريد وتجميد WIC 10 و WIC 40":
        st.info("💡 **إرشادات الفحص (Emerson & Porkka):** تأكد من عمل صمامات التمدد (Expansion Valves)، قراءة حساسات الغرفة، وفحص عدم وجود تراكم جليدي زائد على المبخر.")
    elif eq == "محركات 3-Phase (Stator Rewinding)":
        st.info("💡 **إرشادات فحص اللف:** فحص الورنيش العازل، قياس العزل (Megger)، والتأكد من عدم وجود تلامس بين الفازات وجسم المحرك.")

    c1, c2 = st.columns(2)
    with c1:
        st.write("🟢 **الحالة المرجعية (السليمة):**")
        st.file_uploader("رفع صورة مرجعية", type=["png", "jpg"], key="gi")
    with c2:
        st.write("🔴 **القطعة المفحوصة:**")
        st.file_uploader("رفع الصورة الحالية", type=["png", "jpg"], key="bi")
