import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import json
from datetime import datetime

# إعدادات الصفحة
st.set_page_config(page_title="ATS DocIntel GenAI - Advanced Medical & Clinical Engineering", layout="wide")

st.title("🏥 ATS DocIntel GenAI - Advanced Medical Equipment & Radiotherapy Suite")
st.markdown("المنظومة الرقمية للرنين المغناطيسي (MRI)، الأشعة المقطعية (CT)، الروبوتات الجراحية، وأجهزة العلاج النووي - **ADDOMA TRADING SERVICES**")

# ==========================================
# 1. مكتبة الدوال الهندسية والتشخيصية الطبية
# ==========================================

def analyze_mri_helium_system(boil_off_rate, magnet_pressure, cold_head_status):
    """
    تحليل نظام التبريد والهيليوم المسال لأجهزة الرنين المغناطيسي (MRI Superconducting Magnet)
    """
    alerts = []
    status = "Optimal (نظام المغناطيس مستقر)"
    color = "green"
    
    if boil_off_rate > 0.05:
        alerts.append("معدل تبخر الهيليوم مرتفع (High Boil-Off Rate) - خطر فقدان التبريد")
        status = "Warning (مراقبة حرجة للتبريد)"
        color = "orange"
    if magnet_pressure > 1.5:
        alerts.append("ضغط خزان المغناطيس غير طبيعي (Pressure Anomaly)")
        status = "Critical (خطر ارتفاع الضغط)"
        color = "red"
    if cold_head_status == "Failed":
        alerts.append("تعطل رأس التبريد (Cold Head / Compressor Failure)")
        status = "Critical (توقف تبريد المغناطيس - يتطلب تدخل فوري)"
        color = "red"
        
    return status, color, alerts

def analyze_ct_tube_performance(tube_heat_units, anode_current, scan_artifacts):
    """
    تحليل أداء أنابيب الأشعة المقطعية (CT X-Ray Tube & Generator)
    """
    status = "Normal (أنبوب الأشعة يعمل بكفاءة)"
    color = "green"
    rec = "الأداء مستقر وضمن المعايير التصميمية."
    
    if tube_heat_units > 80.0 or scan_artifacts == "Yes":
        status = "Warning / Degrading (تآكل أو سخونة مفرطة للأنبوب)"
        color = "orange"
        rec = "ارتفاع وحدة حرارة الأبوب أو ظهور تشوهات في الصور (Artifacts). يوصى بجدولة معايرة الفلتر أو فحص الانبعاث الحراري (Anode Wear)."
    return status, color, rec

def evaluate_radiotherapy_system(linac_dose_accuracy, mlc_precision_mm, safety_interlocks):
    """
    تقييم أجهزة العلاج بالأشعة النووية والإشعاعية (Linear Accelerators / Teletherapy)
    """
    score = 100
    status = "Certified Safe (معايرة آمنة ومطابقة للمواصفات)"
    color = "green"
    
    if abs(linac_dose_accuracy) > 2.0:  # خطأ الجرعة الإشعاعية > 2%
        score -= 40
        status = "Critical Dose Deviation (انحراف خطير في الجرعة الإشعاعية)"
        color = "red"
    if mlc_precision_mm > 1.0:  # دقة الورقة متعددة الورقات Multileaf Collimator
        score -= 30
        status = "MLC Calibration Error (خطأ في دقة توجيه الأشعة MLC)"
        color = "orange"
    if safety_interlocks == "Failed":
        score = 0
        status = "Emergency Shutdown (تعطل أنظمة الأمان الإشعاعي - إيقاف فوري)"
        color = "red"
        
    return max(0, score), status, color

# ==========================================
# لوحة التحكم الجانبية (Sidebar)
# ==========================================
st.sidebar.header("لوحة تحكم الأصول الطبية الحرجة")
device_id = st.sidebar.text_input("معرف الجهاز الطبي", "ATS-MED-MRI-01")

app_mode = st.sidebar.selectbox("اختر وحدة التشخيص والصيانة:", [
    "🧲 فحص أجهزة الرنين المغناطيسي (MRI)",
    "🩻 فحص أجهزة الأشعة المقطعية (CT Scan)",
    "🦾 فحص الروبوتات الجراحية والمحاذاة الميكرونية",
    "☢️ العلاج بالأشعة النووية والإشعاعية (Radiotherapy)",
    "⚙️ قطع الغيار الحرارية والدقيقة المطلوبة",
    "📋 بروتوكولات الفحص والصيانة المعيارية (QA/QC)",
    "🤖 المساعد الذكي الطبي (GenAI Medical Copilot)"
])

# ==========================================
# 1. الرنين المغناطيسي MRI
# ==========================================
if app_mode == "🧲 فحص أجهزة الرنين المغناطيسي (MRI)":
    st.subheader("🧲 مراقبة أنظمة المغناطيس فائق التوصيل ونظام التبريد (Cryogenics)")
    
    c1, c2, c3 = st.columns(3)
    with c1: boil_off = st.number_input("معدل تبخر الهيليوم (L/h)", value=0.02, step=0.01)
    with c2: pressure = st.number_input("ضغط خزان الهيليوم (Bar)", value=1.1, step=0.1)
    with c3: cold_head = st.selectbox("حالة رأس التبريد (Cold Head)", ["Operational", "Failed"])

    if st.button("🔍 تشخيص نظام الرنين المغناطيسي"):
        status, color, alerts = analyze_mri_helium_system(boil_off, pressure, cold_head)
        st.markdown(f"### حالة النظام: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
        if alerts:
            st.error("⚠️ التنبيهات التشغيلية:\n" + "\n".join([f"- {a}" for a in alerts]))
        else:
            st.success("✅ أنظمة التبريد والمغناطيس تعمل بكفاءة تامة وتوازن فيزيائي مستقر.")

# ==========================================
# 2. الأشعة المقطعية CT Scan
# ==========================================
elif app_mode == "🩻 فحص أجهزة الأشعة المقطعية (CT Scan)":
    st.subheader("🩻 تحليل أنابيب الأشعة ومولدات الفولتاج العالي (High-Voltage Generators)")
    
    c1, c2, c3 = st.columns(3)
    with c1: heat_u = st.number_input("نسبة حرارة الأنبوب (%)", value=45.0)
    with c2: anode_c = st.number_input("تيار الأنود (mA)", value=350.0)
    with c3: artifacts = st.selectbox("وجود تشوهات أو خطوط في الصورة (Artifacts)", ["No", "Yes"])

    if st.button("⚙️ تحليل أداء أنبوب الـ CT"):
        status, color, rec = analyze_ct_tube_performance(heat_u, anode_c, artifacts)
        st.markdown(f"### حالة الأنبوب: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)
        st.info(f"**التوصية الهندسية:** {rec}")

# ==========================================
# 3. الروبوتات الجراحية
# ==========================================
elif app_mode == "🦾 فحص الروبوتات الجراحية والمحاذاة الميكرونية":
    st.subheader("🦾 دقة الأذرع الروبوتية والمحاذاة التحت-مليمترية (Sub-Millimeter Calibration)")
    
    arm_id = st.selectbox("اختر الذراع الجراحي", ["Master Console Arm 1", "Patient Side Cart - Arm 2", "Endoscopic Camera Arm"])
    backlash = st.number_input("نسبة الخلوص الميكانيكي / الارتداد (Backlash in microns)", value=12.5, step=0.5)
    tension = st.number_input("شد الأسلاك الداخلية (Cable Tension Force N)", value=45.0)

    if st.button("🎯 فحص معايرة الأذرع الجراحية"):
        if backlash < 15.0 and 40 <= tension <= 50:
            st.success(f"✅ الذراع ({arm_id}) يحقق دقة معايرة ميكرونية فائقة وضمن النطاق الجراحي الآمن.")
        else:
            st.warning(f"⚠️ تحذير: تم رصد انحراف طفيف في الخلوص أو شد الأسلاك لـ ({arm_id}). يوصى بإعادة معايرة السيرفو ومحركات التوجيه (Servo Calibration).")

# ==========================================
# 4. العلاج الإشعاعي والنووي
# ==========================================
elif app_mode == "☢️ العلاج بالأشعة النووية والإشعاعية (Radiotherapy)":
    st.subheader("☢️ تقييم أجهزة المعالجة الإشعاعية ومحددات الجرعة (Linac & Teletherapy Units)")
    
    st.markdown("""
    **أنواع أجهزة العلاج الإشعاعي والنووي التي تغطيها المنظومة:**
    1. **المعجلات الخطية الطبية (Medical Linear Accelerators - LINAC):** لتوليد أشعة إكس والإلكترونات عالية الطاقة.
    2. **أجهزة غاما كيف (Gamma Knife / Cobalt-60):** للجراحة الإشعاعية المجسمة بدقة متناهية.
    3. **أجهزة العلاج الإشعاعي الموضعي (Brachytherapy Afterloaders):** لإدخال المصادر المشعة مباشرة للأنسجة.
    """)
    
    d_acc = st.number_input("خطأ الجرعة الإشعاعية المقاسة (%)", value=0.5, step=0.1)
    mlc_p = st.number_input("دقة حركة ورقة الـ MLC (mm)", value=0.3, step=0.1)
    interlocks = st.selectbox("حالة مقاطعات الأمان الإشعاعي (Radiation Interlocks)", ["Operational", "Failed"])

    if st.button("🛡️ تقييم سلامة ومعايرة الجهاز الإشعاعي"):
        score, status, color = evaluate_radiotherapy_system(d_acc, mlc_p, interlocks)
        st.metric("مؤشر السلامة والمعايرة الإشعاعية", f"{score} / 100")
        st.markdown(f"### الحالة التنظيمية والتشغيلية: <span style='color:{color};'>{status}</span>", unsafe_allow_html=True)

# ==========================================
# 5. قطع الغيار الحرارية والدقيقة
# ==========================================
elif app_mode == "⚙️ قطع الغيار الحرارية والدقيقة المطلوبة":
    st.subheader("⚙️ جدول قطع الغيار الاستراتيجية للمعدات الطبية المتقدمة")
    
    sp_data = {
        "الجهاز الطبي": ["MRI 1.5T / 3T", "CT Scan", "الروبوت الجراحي", "المعجل الخطّي LINAC"],
        "قطع الغيار الحرجة": ["Cold Head Compressor, Helium Relief Valves, RF Shielding Gaskets", "X-Ray Tube Assembly, High-Voltage Tank, Detector Array", "EndoWrist Instrument Cables, Master Controller Joysticks, Servo Motors", "Magnetron, Klystron, MLC Drive Motors, Ionization Chambers"],
        "دورية التغيير الموصى بها": ["كل 30,000 ساعة تشغيل (Cold Head)", "كل 3 إلى 5 سنوات (بناءً على عدد السكانات)", "صيانة وقائية كل 500 حالة جراحية", "فحص ومعايرة دورية كل 3 أشهر"]
    }
    st.table(pd.DataFrame(sp_data))

# ==========================================
# 6. بروتوكولات الفحص والصيانة المعيارية (QA/QC)
# ==========================================
elif app_mode == "📋 بروتوكولات الفحص والصيانة المعيارية (QA/QC)":
    st.subheader("📋 دليل الفحص والصيانة التنبؤية للأجهزة الطبية الحرجة")
    
    st.markdown("""
    تتبع **Addoma Trading Services (ATS)** المعايير العالمية (مثل FDA, IEC 60601, و AAPM) لفحص وصيانة هذه الأجهزة:
    
    ### 1. فحوصات الجودة اليومية والأسبوعية (Daily/Weekly QC):
    * **أجهزة الرنين (MRI):** فحص نسبة الإشارة إلى الإشارة الضوضائية (SNR)، واختبار تجانس المجال المغناطيسي (Field Uniformity).
    * **الأشعة المقطعية (CT):** معايرة الهواء اليومية (Water Phantom Calibration) واختبار دقة وحدات هاونسفيل (HU Linearity).
    * **العلاج الإشعاعي (Radiotherapy):** اختبارات الجرعة الإشعاعية اليومية باستخدام مقياس التأين (Ion Chamber) وتأكيد خلو أجهزة الإنذار.

    ### 2. الصيانة الوقائية والتنبؤية (Preventive & Predictive Maintenance):
    * **المراقبة الحرارية والاهتزازية لمضخات الهيليوم وأنظمة تبريد الـ Chillers.**
    * **الفحص اللاهدمي والأشعة لأسلاك ومفاصل الروبوتات الجراحية لمنع أي إجهاد ميكانيكي أثناء العمليات الدقيقة.**
    """)

# ==========================================
# 7. المساعد الذكي الطبي
# ==========================================
else:
    st.subheader("🤖 محادثة المساعد الذكي الطبي (ATS Medical GenAI Copilot)")
    prompt = st.text_input("اطرح استفسارك الطبي الهندسي:", "كيف تتم معايرة الجرعة الإشعاعية للمعجلات الخطية؟")
    if st.button("إرسال الاستفسار"):
        st.success("**رد المنظومة الذكية:**")
        st.markdown("""
        بناءً على معايير الهندسة الطبية لـ **ATS Engineering**:
        تتم معايرة الجرعة الإشعاعية للمعجلات الخطية (LINAC) باستخدام **غرف التأين المعايرة بدقة (Standard Ionization Chambers)** المغمورة في فانتوم مائي (Water Phantom) على عمق المعيار المعتمد (مثل عمق الشبع للجسيمات)، ومقارنة القراءات ببروتوكولات التقرير الدولي (مثل AAPM TG-51 أو IAEA TRS-398) لضمان ألا يتجاوز خطأ التوصيل الإشعاعي نسبة الـ 1% إلى 2% لسلامة المريض المطلقة.
        """)
