from datetime import datetime, timedelta
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Monitor - Climate & Load Logic",
    layout="wide"
)

st.title("⚙️ نظام مراقبة المولدات الصناعية - إدارة الأحمال والظروف المناخية")

# قاعدة بيانات العملاء وأكواد التفعيل
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم (Addoma Trading Services)",
        "plan": "سنوي (Yearly)",
        "start_date": "2026-01-01",
        "duration_days": 365,
    },
    "CLIENT-M-881": {
        "name": "شركة النيل للصناعات الهندسية",
        "plan": "شهري (Monthly)",
        "start_date": "2026-09-01",
        "duration_days": 30,
    },
}

# الشريط الجانبي: تفعيل الاشتراك
st.sidebar.header("🔐 بوابة تفعيل العميل")
input_code = st.sidebar.text_input("أدخل كود تفعيل العميل:", type="password")

is_pro = False
client_name = "زائر (Visitor)"
plan_type = "غير مفعل"

if input_code in CLIENTS_DATABASE:
    data = CLIENTS_DATABASE[input_code]
    client_name = data["name"]
    plan_type = data["plan"]
    start_dt = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
    expiry_dt = start_dt + timedelta(days=data["duration_days"])
    
    if datetime.now().date() <= expiry_dt:
        is_pro = True
        st.sidebar.success(f"✅ مفعل: {client_name} ({plan_type})")
    else:
        st.sidebar.error("❌ انتهت صلاحية الاشتراك.")
elif input_code != "":
    st.sidebar.error("❌ كود غير صحيح.")
else:
    st.sidebar.info("💡 أدخل كود العميل لفتح الخصائص المتقدمة.")

st.sidebar.divider()

# إدخال البيانات التشغيلية والمناخية وسعة المولد
st.sidebar.header("📥 إدخال قراءات وسعة المولد")

with st.sidebar.form("generator_full_form"):
    st.subheader("سعات المولد والحمل")
    gen_kw = st.number_input("سعة المولد الكلية (Generator Capacity kW)", min_value=5.0, max_value=3000.0, value=250.0, step=10.0)
    load_kw = st.number_input("حجم الحمولة الحالية (Current Load kW)", min_value=0.0, max_value=3000.0, value=150.0, step=10.0)
    ambient_temp = st.number_input("درجة الحرارة المحيطة / المناخ (°C)", min_value=10.0, max_value=60.0, value=42.0, step=1.0)

    st.subheader("المؤشرات الميكانيكية والحماية")
    coolant_temp = st.number_input("حرارة سائل التبريد Coolant Temp (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت Oil Pressure (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    vibration = st.number_input("مستوى الاهتزاز Vibration (mm/s)", min_value=0.0, max_value=50.0, value=2.2, disabled=not is_pro)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    amperes = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=4000.0, value=350.0)
    pf = st.number_input("معامل القدرة Power Factor (PF)", min_value=0.0, max_value=1.0, value=0.85, disabled=not is_pro)

    submit_btn = st.form_submit_button("تحليل الأداء والمناخ")

# حساب نسبة الحمل المئوية
load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

# الواجهة الرئيسية
st.info(f"🔹 **العميل الحالي:** {client_name} | **الباقة:** {plan_type}")
st.subheader("📊 لوحة المراقبة التشغيلية والبيانات الكهربائية")

col1, col2, col3, col4 = st.columns(4)
col1.metric("حجم سعة المولد", f"{gen_kw} kW")
col2.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}% من السعة")
col3.metric("حرارة المحرك", f"{coolant_temp} °C")
col4.metric("ضغط الزيت", f"{oil_press} Bar")

col5, col6, col7, col8 = st.columns(4)
col5.metric("الجهد (Voltage)", f"{voltage} V")
col6.metric("التردد (Frequency)", f"{freq} Hz")
col7.metric("التيار (Amperes)", f"{amperes} A")
col8.metric("معامل القدرة (PF)", f"{pf}" if is_pro else "🔒 مقفل")

st.divider()
st.subheader("🌡️ التقييم التنبؤي للظروف المناخية وزيت المحرك")

# تطبيق شروط درجات الحرارة المحيطة والأحمال وزيوت المحرك
recommended_oil = "15W40 (الوضع القياسي)"
max_allowed_load = 80.0
climate_alerts = []

if ambient_temp >= 45.0:
    recommended_oil = "20W50 (موصى به لدرجات الحرارة القصوى 45°C فأكثر)"
    max_allowed_load = 60.0
    if load_percentage > 60.0:
        climate_alerts.append(f"🚨 **تنبيه حرارة جوية فائقة (≥ 45°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **60%** لتفادي السخونة المفرطة.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى المسموح (60%) في الأجواء الحارة جداً.")
        
elif ambient_temp >= 43.0:
    recommended_oil = "15W40 (مع مراعاة اللزوجة في الأجواء الحارة)"
    max_allowed_load = 70.0
    if load_percentage > 70.0:
        climate_alerts.append(f"⚠️ **تنبيه مناخي (≥ 43°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **70%** في المناخ الحار.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى المسموح (70%) عند درجة حرارة 43°C.")
else:
    climate_alerts.append(f"✅ **الظروف المناخية معتدلة (< 43°C):** تشغيل طبيعي ضمن الأحمال القياسية.")

st.markdown(f"🛢️ **نوع لزوجة زيت المحرك الواجب استخدامه:** **{recommended_oil}**")
st.markdown(f"📉 **الحد الأقصى الموصى به للحمولة في هذا المناخ:** **{max_allowed_load}%**")

for alert in climate_alerts:
    if "🚨" in alert or "⚠️" in alert:
        st.warning(alert)
    else:
        st.success(alert)

# التنبؤ بالأعطال الإضافية
if is_pro:
    st.subheader("🔍 تحليلات الاهتزاز ومعامل القدرة المتقدمة")
    if vibration > 4.0:
        st.error("⚠️ **تحذير اهتزاز:** مستوى الاهتزاز يتجاوز المعدل الطبيعي.")
    if pf < 0.8:
        st.warning("💡 **معامل قدرة منخفض:** يوصى بمراجعة مكثفات تحسين القدرة.")
