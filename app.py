import streamlit as st

st.set_page_config(page_title="Industrial Generator Monitor", layout="wide")

st.title("⚙️ نظام مراقبة وإدخال قراءات المولد الصناعي")

# 1. قائمة إدخال البيانات في الشريط الجانبي
st.sidebar.header("📥 إدخال القراءات التشغيلية")

with st.sidebar.form("generator_input_form"):
    st.subheader("المؤشرات الميكانيكية")
    temp = st.number_input("درجة الحرارة Coolant Temp (°C)", min_value=0.0, max_value=150.0, value=85.0, step=1.0)
    vibration = st.number_input("مستوى الاهتزاز Vibration (mm/s)", min_value=0.0, max_value=50.0, value=2.5, step=0.1)
    oil_press = st.number_input("ضغط الزيت Oil Pressure (Bar)", min_value=0.0, max_value=10.0, value=4.5, step=0.1)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد الكهربائي Voltage (V)", min_value=0.0, max_value=600.0, value=400.0, step=1.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0, step=0.1)
    current = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=2000.0, value=350.0, step=5.0)
    pf = st.number_input("معامل القدرة Power Factor (PF)", min_value=0.0, max_value=1.0, value=0.85, step=0.01)

    submit_button = st.form_submit_button("تحديث وتحليل البيانات")

# 2. عرض القراءات على لوحة المراقبة الرئيسية
st.subheader("📊 لوحة المؤشرات المباشرة (Live Readings)")

col1, col2, col3, col4 = st.columns(4)
col1.metric("الحرارة", f"{temp} °C", "حرج" if temp >= 95 else "طبيعي")
col2.metric("الاهتزاز", f"{vibration} mm/s", "مرتفع" if vibration > 4.5 else "سليم")
col3.metric("ضغط الزيت", f"{oil_press} Bar", "منخفض" if oil_press < 2.5 else "طبيعي")
col4.metric("معامل القدرة (PF)", f"{pf}", "منخفض" if pf < 0.8 else "ممتاز")

col5, col6, col7 = st.columns(3)
col5.metric("الجهد (Voltage)", f"{voltage} V")
col6.metric("التردد (Frequency)", f"{freq} Hz")
col7.metric("التيار (Amperes)", f"{current} A")

# 3. التحليل التنبؤي الذكي بناءً على القيم المدخلة
st.divider()
st.subheader("🔍 التقييم التنبؤي وحالة التشغيل")

alerts = []

if temp >= 95:
    alerts.append("⚠️ **تحذير حرارة:** ارتفعت حرارة السائل المحرك عن 95°C — افحص مروحة التبريد، انسداد الرديتر، أو مستوى السائل.")
if oil_press < 2.5:
    alerts.append("🚨 **خطر ضغط الزيت:** انخفاض ضغط الزيت عن 2.5 Bar — افحص فلتر الزيت أو مضخة الزيت فوراً لمنع تلف المحرك.")
if vibration > 4.5:
    alerts.append("⚠️ **تحذير اهتزاز:** مستوى الاهتزاز يتجاوز الحدود الآمنة — تحقق من كراسي المحرك (Engine Mounts) وتوازن المحور.")
if pf < 0.8:
    alerts.append("💡 **كفاءة القدرة:** معامل القدرة أقل من 0.8 — يوصى بتفعيل لوحة تحسين معامل القدرة (PFC Panel) لتقليل الحمل الضائع.")
if freq < 48.5 or freq > 51.5:
    alerts.append("⚙️ **استقرار التردد:** تذبذب التردد بعيداً عن 50Hz — افحص منظم السرعة (Governor) ومضخة الوقود.")

if alerts:
    for alert in alerts:
        st.warning(alert)
else:
    st.success("✅ جميع القراءات الميكانيكية والكهربائية ضمن الحدود التشغيلية الآمنة ولا توجد مؤشرات أعطال وشيكة.")
