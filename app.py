from datetime import datetime, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator & Lifespan Maintenance Tracker",
    layout="wide"
)

st.title("⚙️ نظام الصيانة التنبؤية وإدارة قطع الغيار والتشغيل الصناعي")

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

# الشريط الجانبي: بوابة تفعيل العميل والصلاحيات
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
    run_hours = st.number_input("ساعات التشغيل التراكمية (Run Hours)", min_value=0.0, max_value=50000.0, value=1250.0, step=10.0)
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

# التقييم المناخي وتوصيات الزيوت والأحمال حسب الشروط المطلوبة
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

# جدول تتبع الصيانة الدورية وقطع الغيار (Lifespan Tracker المطابق للصورة)
st.subheader("🔧 جدول تتبع العمر الافتراضي لقطع الغيار والصيانة (Lifespan Tracker)")

# قاعدة بيانات قطع الغيار والأعمار الافتراضية المستخرجة من جدولك
maintenance_items = [
    {"category": "الصيانة الدورية (Service)", "part": "فلتر زيت (Oil Filter)", "lifespan": 250},
    {"category": "الصيانة الدورية (Service)", "part": "فلتر وقود - أولي (Primary Fuel Filter)", "lifespan": 500},
    {"category": "الصيانة الدورية (Service)", "part": "فلتر وقود - ثانوي (Secondary Fuel Filter)", "lifespan": 500},
    {"category": "نظام الهواء (Air System)", "part": "فلتر هواء (Air Filter)", "lifespan": 1000},
    {"category": "نظام التبريد (Cooling System)", "part": "قشاط المروحة (Fan Belt)", "lifespan": 2000},
    {"category": "نظام التبريد (Cooling System)", "part": "سائل تبريد (Coolant ELC)", "lifespan": 3000},
    {"category": "نظام الوقود (Fuel System)", "part": "بخاخات الوقود (Injectors Check)", "lifespan": 5000},
    {"category": "النظام الكهربائي (Electrical)", "part": "بطاريات (Batteries)", "lifespan": 8000},
    {"category": "النظام الكهربائي (Electrical)", "part": "دينامو الشحن (Charging Alternator)", "lifespan": 10000},
    {"category": "المحرك - ميكانيك (Motor - Mechanical)", "part": "طقم عمرة رأس (Top Overhaul)", "lifespan": 10000},
    {"category": "المحرك - ميكانيك (Motor - Mechanical)", "part": "عمرة كاملة (Major Overhaul)", "lifespan": 20000},
    {"category": "نظام التبريد (Cooling System)", "part": "مبرد الزيت (Oil Cooler Clean)", "lifespan": 5000},
    {"category": "نظام التبريد (Cooling System)", "part": "مضخة الماء (Water Pump)", "lifespan": 6000},
    {"category": "نظام الهواء (Air System)", "part": "تيربو (Turbocharger Check)", "lifespan": 8000}
]

table_rows = []
for item in maintenance_items:
    lifespan = item["lifespan"]
    # حساب الساعات المنقضية اعتماداً على دورة التشغيل (Run Hours)
    used_hours = run_hours % lifespan
    if used_hours == 0 and run_hours > 0:
        used_hours = lifespan
        
    usage_pct = (used_hours / lifespan) * 100
    remaining_hours = lifespan - used_hours
    
    # تحديد حالة التنبيه مطابقة للجدول
    if usage_pct >= 90:
        status = "تغيير فوري (خطر) 🔴"
    elif usage_pct >= 80:
        status = "قرب الخدمة 🟡"
    elif usage_pct >= 70:
        status = "تنبيه (استعداد) 🟠"
    else:
        status = "حالة جيدة 🟢"
        
    table_rows.append({
        "تصنيف القطعة": item["category"],
        "اسم قطعة الغيار (Spare Part)": item["part"],
        "العمر الافتراضي (Hours)": lifespan,
        "الساعات المنقضية (Hours Used)": round(used_hours, 1),
        "نسبة الاستهلاك (%)": f"{usage_pct:.1f}%",
        "العمر المتبقي (Remaining)": round(remaining_hours, 1),
        "حالة التنبيه (Alert Status)": status
    })

df_tracker = pd.DataFrame(table_rows)
st.dataframe(df_tracker, use_container_width=True)

# التحليلات التنبؤية المتقدمة للعملاء المفعلين فقط
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
