from datetime import datetime, timedelta
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Predictive Maintenance & Climate Monitor",
    layout="wide"
)

st.title("⚙️ نظام الصيانة التنبؤية وإدارة الأسطول الصناعي للمولدات")

# قاعدة بيانات العملاء وأكواد التفعيل الفردية
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

# الشريط الجانبي: بوابة تفعيل العميل
st.sidebar.header("🔐 بوابة تفعيل العميل والصلاحيات")
input_code = st.sidebar.text_input("أدخل كود التفعيل الخاص بالعميل:", type="password")

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
        st.sidebar.error("❌ انتهت صلاحية اشتراك هذا العميل.")
elif input_code != "":
    st.sidebar.error("❌ كود التفعيل غير صحيح.")
else:
    st.sidebar.info("💡 أدخل كود العميل لفتح التحليلات المتقدمة.")

st.sidebar.divider()

# إدخال البيانات التشغيلية والمناخية وساعات المولد
st.sidebar.header("📥 لوحة إدخال البيانات والتشغيل")

with st.sidebar.form("generator_comprehensive_form"):
    st.subheader("ساعات التشغيل وسعات المولد")
    run_hours = st.number_input("ساعات التشغيل التراكمية (Run Hours)", min_value=0.0, max_value=50000.0, value=1250.0, step.0 if 'step' in dir() else 10.0)
    gen_kw = st.number_input("سعة المولد الكلية (Generator kW)", min_value=5.0, max_value=3000.0, value=250.0, step=10.0)
    load_kw = st.number_input("حجم الحمولة الحالية (Load kW)", min_value=0.0, max_value=3000.0, value=150.0, step=10.0)
    ambient_temp = st.number_input("درجة الحرارة المحيطة / المناخ (°C)", min_value=10.0, max_value=60.0, value=43.0, step=1.0)

    st.subheader("قراءات الشاشة والمؤشرات الميكانيكية")
    coolant_temp = st.number_input("حرارة سائل التبريد (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    vibration = st.number_input("مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2, disabled=not is_pro)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    amperes = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=4000.0, value=350.0)
    pf = st.number_input("معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85, disabled=not is_pro)

    submit_btn = st.form_submit_button("تحليل الأداء والصيانة")

# حساب نسبة الحمل المئوية
load_percentage = (load_kw / gen_kw) * 100 if gen_kw > 0 else 0

# الواجهة الرئيسية
st.info(f"🔹 **العميل الحالي:** {client_name} | **الباقة:** {plan_type}")
st.subheader("📊 لوحة المراقبة التشغيلية والبيانات الكهربائية")

col1, col2, col3, col4 = st.columns(4)
col1.metric("ساعات التشغيل (Run Hours)", f"{run_hours} hrs")
col2.metric("سعة المولد", f"{gen_kw} kW")
col3.metric("الحمولة الحالية", f"{load_kw} kW", f"{load_percentage:.1f}%")
col4.metric("الحرارة المحيطة", f"{ambient_temp} °C")

col5, col6, col7, col8 = st.columns(4)
col5.metric("حرارة المحرك", f"{coolant_temp} °C")
col6.metric("ضغط الزيت", f"{oil_press} Bar")
col7.metric("الجهد / التردد", f"{voltage}V | {freq}Hz")
col8.metric("التيار / معامل القدرة", f"{amperes}A | {pf}" if is_pro else f"{amperes}A | 🔒")

st.divider()

# التقييم المناخي وتوصيات الزيوت والأحمال
st.subheader("🌡️ التقييم المناخي وتوصيات الزيوت والأحمال القصوى")

recommended_oil = "15W40 (الوضع القياسي)"
max_allowed_load = 80.0
climate_alerts = []

if ambient_temp >= 45.0:
    recommended_oil = "20W50 (موصى به لدرجات الحرارة القصوى 45°C فأكثر)"
    max_allowed_load = 60.0
    if load_percentage > 60.0:
        climate_alerts.append(f"🚨 **تحذير مناخي فائق (≥ 45°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **60%**.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى (60%) في الأجواء الحارة جداً.")
        
elif ambient_temp >= 43.0:
    recommended_oil = "15W40 (مع مراعاة اللزوجة في المناخ الحار)"
    max_allowed_load = 70.0
    if load_percentage > 70.0:
        climate_alerts.append(f"⚠️ **تحذير مناخي (≥ 43°C):** الحمولة الحالية ({load_percentage:.1f}%) تتجاوز الحد الآمن الموصى به وهو **70%**.")
    else:
        climate_alerts.append(f"✅ **الحمولة آمنة:** الحمولة ({load_percentage:.1f}%) ضمن الحد الأقصى المسموح (70%) عند درجة حرارة 43°C.")
else:
    climate_alerts.append(f"✅ **الظروف المناخية معتدلة (< 43°C):** تشغيل ضمن الحدود القياسية.")

st.markdown(f"🛢️ **نوع لزوجة زيت المحرك الواجب استخدامه:** **{recommended_oil}**")
st.markdown(f"📉 **الحد الأقصى الموصى به للحمولة في هذا المناخ:** **{max_allowed_load}%**")

for alert in climate_alerts:
    if "🚨" in alert or "⚠️" in alert:
        st.warning(alert)
    else:
        st.success(alert)

st.divider()

# نظام الصيانة الدورية وقطع الغيار بناءً على Run Hours
st.subheader("🔧 جداول الصيانة الدورية وتغيير الفلاتر والزيوت (بناءً على Run Hours)")

# حساب الساعات المتبقية للصيانة بناءً على دورات قياسية
oil_interval = 250      # تغيير الزيت والفلتر الأولي كل 250 ساعة
air_fuel_interval = 500 # فلاتر الهواء والوقود كل 500 ساعة
major_interval = 1000   # الصيانة الشاملة والفحص العميق كل 1000 ساعة

oil_remaining = oil_interval - (run_hours % oil_interval)
air_fuel_remaining = air_fuel_interval - (run_hours % air_fuel_interval)
major_remaining = major_interval - (run_hours % major_interval)

col_m1, col_m2, col_m3 = st.columns(3)

with col_m1:
    st.markdown("### 🛢️ تغيير الزيت والفلتر")
    st.metric("الفترة المعتادة", f"كل {oil_interval} ساعة")
    if oil_remaining <= 25:
        st.error(f"⚠️ موعد الصيانة وشيك! متبقي {oil_remaining} ساعة فقط.")
    else:
        st.success(f"✅ متبقي {oil_remaining} ساعة للتغيير القادم.")

with col_m2:
    st.markdown("### ⛽ فلاتر الهواء والوقود")
    st.metric("الفترة المعتادة", f"كل {air_fuel_interval} ساعة")
    if air_fuel_remaining <= 50:
        st.warning(f"⚠️ اقترب موعد تغيير الفلاتر (متبقي {air_fuel_remaining} ساعة).")
    else:
        st.success(f"✅ متبقي {air_fuel_remaining} ساعة.")

with col_m3:
    st.markdown("### ⚙️ الصيانة الشاملة (Major Service)")
    st.metric("الفترة المعتادة", f"كل {major_interval} ساعة")
    if major_remaining <= 100:
        st.warning(f"⚠️ اقترب موعد الفحص الشامل (متبقي {major_remaining} ساعة).")
    else:
        st.success(f"✅ متبقي {major_remaining} ساعة للفحص الشامل.")

# التنبؤ بالأعطال المتقدمة للعملاء المفعلين
if is_pro:
    st.divider()
    st.subheader("🔍 تحليلات التنبؤ بالأعطال المتقدمة (AI Diagnostics)")
    
    advanced_alerts = []
    if vibration > 4.0:
        advanced_alerts.append("⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن المحور أو تآكل كراسي المحرك.")
    if pf < 0.8:
        advanced_alerts.append("💡 **معامل قدرة منخفض (< 0.8):** يوصى بمراجعة لوحة مكثفات تحسين القدرة (PFC).")
    if coolant_temp >= 95:
        advanced_alerts.append("🚨 **خطر ارتفاع الحرارة:** حرارة سائل التبريد تتجاوز الحد الطبيعي.")
        
    if advanced_alerts:
        for alert in advanced_alerts:
            st.error(alert)
    else:
        st.success("🌟 كافة مؤشرات الاهتزاز ومعامل القدرة ضمن النطاق المثالي الآمن.")
else:
    st.info("ℹ️ للوصول إلى تحليلات الاهتزاز ومعامل القدرة المتقدمة، يرجى تفعيل كود العميل في الشريط الجانبي.")
