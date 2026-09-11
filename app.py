import streamlit as st

st.set_page_config(page_title="Industrial Generator Monitor & Subscriptions", layout="wide")

st.title("⚙️ نظام مراقبة وصيانة المولدات الصناعية")

# 1. إدارة باقات الاشتراك في الشريط الجانبي
st.sidebar.header("🔐 إدارة باقات الاشتراك والصلاحيات")

plan_choice = st.sidebar.selectbox(
    "اختر الباقة الحالية:",
    ["الباقة الأساسية (Basic - وحدة واحدة)", "الباقة الاحترافية (Professional)", "باقة المؤسسات (Enterprise - أسطول كامل)"]
)

# مفتاح إدخال كود التفعيل لتأكيد الباقة
activation_code = st.sidebar.text_input("أدخل كود تفعيل الباقة:", type="password")

# التحقق من الصلاحيات بناءً على الباقة أو الكود
is_pro = (plan_choice != "الباقة الأساسية (Basic - وحدة واحدة)") or (activation_code == "ADDOMA2026")

if is_pro:
    st.sidebar.success(f"✅ الباقة مفعلة بنجاح: {plan_choice}")
else:
    st.sidebar.info("💡 أنت تستخدم الباقة الأساسية. قم بترقية الباقة أو أدخل كود التفعيل لفتح كافة المؤشرات.")

st.divider()

# 2. إدخال القراءات التشغيلية للمولد
st.sidebar.header("📥 إدخال القراءات الحية")
with st.sidebar.form("generator_data_form"):
    st.subheader("المؤشرات الميكانيكية")
    temp = st.number_input("درجة الحرارة (°C)", min_value=0.0, max_value=150.0, value=85.0)
    oil_press = st.number_input("ضغط الزيت (Bar)", min_value=0.0, max_value=10.0, value=4.2)
    
    # الاهتزاز متاح حصرياً للباقات الاحترافية والمؤسسات
    vibration = st.number_input("مستوى الاهتزاز (mm/s)", min_value=0.0, max_value=50.0, value=2.2, disabled=not is_pro)

    st.subheader("المؤشرات الكهربائية")
    voltage = st.number_input("الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0)
    freq = st.number_input("التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0)
    current = st.number_input("التيار Amperes (A)", min_value=0.0, max_value=2000.0, value=300.0)
    
    # معامل القدرة PF متاح حصرياً للباقات المتقدمة
    pf = st.number_input("معامل القدرة (PF)", min_value=0.0, max_value=1.0, value=0.85, disabled=not is_pro)

    submit_btn = st.form_submit_button("تحليـل القراءات")

# 3. عرض لوحة المؤشرات للمستخدم
st.subheader("📊 لوحة المراقبة التشغيلية")

col1, col2, col3 = st.columns(3)
col1.metric("درجة الحرارة", f"{temp} °C", "حرج" if temp >= 95 else "طبيعي")
col2.metric("ضغط الزيت", f"{oil_press} Bar", "منخفض" if oil_press < 2.5 else "مستقر")
col3.metric("مستوى الاهتزاز", f"{vibration} mm/s" if is_pro else "🔒 مقفل (يتطلب ترقية)")

# تعديل السطر المصحح
col4, col5, col6, col7 = st.columns(4)
col4.metric("الجهد", f"{voltage} V")
col5.metric("التردد", f"{freq} Hz")
col6.metric("التيار", f"{current} A")
col7.metric("معامل القدرة (PF)", f"{pf}" if is_pro else "🔒 مقفل")

# 4. التنبؤ بالأعطال والتحليل الذكي
st.divider()
st.subheader("🔍 تقرير التنبؤ بالأعطال (AI Diagnostics)")

if not is_pro and (temp >= 95 or oil_press < 2.5):
    st.warning("⚠️ تم رصد مؤشرات حرجة أساسية. يرجى الترقية إلى الباقة الاحترافية للحصول على تفاصيل التنبؤ المتقدمة للأعطال.")
elif is_pro:
    st.success("🌟 باقة المراقبة المتقدمة مفعلة: جارٍ تحليل الاهتزاز ومعامل القدرة لتفادي الأعطال المفاجئة.")
    
    alerts = []
    if vibration > 4.0:
        alerts.append("⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن في المحور أو تآكل كراسي المحرك.")
    if pf < 0.8:
        alerts.append("💡 **معامل قدرة منخفض:** يوصى بمراجعة مكثفات تحسين القدرة (PFC).")
    if temp >= 95:
        alerts.append("⚠️ **تحذير حرارة:** ارتفاع غير طبيعي في سائل التبريد.")
        
    if alerts:
        for alert in alerts:
            st.error(alert)
    else:
        st.success("✅ جميع الأنظمة تعمل ضمن الكفاءة القصوى والمثلى.")
else:
    st.info("ℹ️ النظام يعمل بالوضع الأساسي. أدخل كود التفعيل في الشريط الجانبي لفتح كامل خصائص التنبؤ.")
