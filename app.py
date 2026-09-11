import streamlit as st
from datetime import datetime

# 1. إعداد الصفحة
st.set_page_config(
    page_title="Industrial Generator Monitor",
    layout="wide"
)

st.title("⚙️ نظام مراقبة وصيانة المولدات الصناعية")

# 2. إدارة الاشتراك الشهري في الشريط الجانبي
st.sidebar.header("🔐 إدارة الاشتراك الشهري")

# قائمة الأكواد الشهريّة المعتمدة وتاريخ انتهاء الصلاحية
VALID_MONTHLY_CODES = {
    "ADDOMA2026": "2026-12-31",
    "ADDOMA-PRO-1M": "2026-10-31",
    "OCT-2026-X89": "2026-10-31",
}

user_code = st.sidebar.text_input("أدخل كود الاشتراك الشهري:", type="password")

is_pro = False

if user_code in VALID_MONTHLY_CODES:
    expiry_date_str = VALID_MONTHLY_CODES[user_code]
    expiry_date = datetime.strptime(expiry_date_str, "%Y-%m-%d").date()
    today = datetime.now().date()

    if today <= expiry_date:
        is_pro = True
        days_left = (expiry_date - today).days
        st.sidebar.success(f"✅ الاشتراك فعال! متبقي {days_left} يومًا (ينتهي في {expiry_date_str}).")
    else:
        st.sidebar.error(f"❌ انتهت صلاحية هذا الكود بتاريخ {expiry_date_str}.")
elif user_code != "":
    st.sidebar.error("❌ كود الاشتراك غير صحيح.")
else:
    st.sidebar.info("💡 أدخل كود الاشتراك لفتح الميزات المتقدمة.")

st.sidebar.divider()

# 3. نموذج إدخال القراءات التشغيلية
st.sidebar.header("📥 إدخال القراءات الحية")

with st.sidebar.form("generator_data_form"):
    st.subheader("المؤشرات الميكانيكية")
    temp = st.number_input("درجة الحرارة (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    vibration = st.number_input("مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2, disabled=not is_pro)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    current = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=2000.0, value=300.0)
    pf = st.number_input("معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85, disabled=not is_pro)

    submit_btn = st.form_submit_button("تحليـل القراءات")

# 4. عرض لوحة المؤشرات الرئيسية
st.subheader("📊 لوحة المراقبة التشغيلية")

col1, col2, col3 = st.columns(3)
col1.metric("درجة الحرارة", f"{temp} °C", "حرج" if temp >= 95 else "طبيعي")
col2.metric("ضغط الزيت", f"{oil_press} Bar", "منخفض" if oil_press < 2.5 else "مستقر")
col3.metric("مستوى الاهتزاز", f"{vibration} mm/s" if is_pro else "🔒 مقفل")

col4, col5, col6, col7 = st.columns(4)
col4.metric("الجهد", f"{voltage} V")
col5.metric("التردد", f"{freq} Hz")
col6.metric("التيار", f"{current} A")
col7.metric("معامل القدرة (PF)", f"{pf}" if is_pro else "🔒 مقفل")

# 5. التنبؤ بالأعطال والتحليل الذكي
st.divider()
st.subheader("🔍 تقرير التنبؤ بالأعطال (AI Diagnostics)")

if is_pro:
    st.success("🌟 باقة المراقبة الشهرية المتقدمة مفعلة: تم تحليل كامل المؤشرات.")
    
    alerts = []
    if vibration > 4.0:
        alerts.append("⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن في المحور أو تآكل كراسي المحرك.")
    if pf < 0.8:
        alerts.append("💡 **معامل قدرة منخفض:** يوصى بمراجعة مكثفات تحسين القدرة (PFC).")
    if temp >= 95:
        alerts.append("⚠️ **تحذير حرارة:** ارتفاع غير طبيعي في سائل التبريد.")
    if oil_press < 2.5:
        alerts.append("🚨 **خطر ضغط الزيت:** انخفاض ضغط الزيت عن 2.5 Bar.")

    if alerts:
        for alert in alerts:
            st.error(alert)
    else:
        st.success("✅ جميع الأنظمة تعمل ضمن الكفاءة القصوى والمثلى.")
else:
    if temp >= 95 or oil_press < 2.5:
        st.warning("⚠️ تم رصد مؤشرات حرجة أساسية. أدخل كود الاشتراك الشهري للحصول على التحليل التفصيلي.")
    else:
        st.info("ℹ️ النظام يعمل بالوضع الأساسي. أدخل كود الاشتراك الشهري في الشريط الجانبي لفتح كامل الخصائص.")
