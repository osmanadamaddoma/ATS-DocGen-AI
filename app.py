from datetime import datetime, timedelta
import streamlit as st

st.set_page_config(
    page_title="Industrial Generator Monitor & Subscriptions",
    layout="wide",
)

st.title("⚙️ نظام مراقبة المولدات الصناعية - إدارة الاشتراكات الفردية")

# قاعدة بيانات العملاء: كل عميل له كود فريد، اسم، نوع الاشتراك، وتاريخ البدء
CLIENTS_DATABASE = {
    "ADDOMA-2026-PRO": {
        "name": "عثمان آدم (Addoma Trading Services)",
        "plan": "سنوي (Month)",
        "start_date": "2026-09-11",
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

# الشريط الجانبي لتسجيل وتفعيل العملاء
st.sidebar.header("🔐 بوابة تفعيل أكواد العملاء")
input_code = st.sidebar.text_input("أدخل كود التفعيل الخاص بالعميل:", type="password")

is_pro = False
client_name = "زائر (Visitor / Free)"
plan_type = "غير مفعل"
expiry_dt = None
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
    st.sidebar.markdown(f"**👤 اسم العميل:** {client_name}")
    st.sidebar.markdown(f"**📦 نوع الباقة:** {plan_type}")
    st.sidebar.markdown(
        f"⏳ **المدة المتبقية:** {days_left} يوم (تاريخ الانتهاء: {expiry_dt})"
    )
  else:
    st.sidebar.error(
        f"❌ انتهت صلاحية اشتراك هذا العميل بتاريخ ({expiry_dt}). يرجى تجديد"
        " الاشتراك."
    )
elif input_code != "":
  st.sidebar.error("❌ كود التفعيل غير صحيح أو غير مسجل في النظام.")
else:
  st.sidebar.info("💡 أدخل الكود المخصص لعرض تفاصيل العميل وفتح الميزات.")

st.sidebar.divider()

# نموذج إدخال القراءات التشغيلية للمولد
st.sidebar.header("📥 إدخال القراءات الحية")

with st.sidebar.form("generator_data_form"):
  st.subheader("المؤشرات الميكانيكية")
  temp = st.number_input(
      "درجة الحرارة Coolant Temp (°C)", min_value=0.0, max_value=150.0, value=85.0
  )
  oil_press = st.number_input(
      "ضغط الزيت Oil Pressure (Bar)", min_value=0.0, max_value=10.0, value=4.2
  )
  vibration = st.number_input(
      "مستوى الاهتزاز Vibration (mm/s)",
      min_value=0.0,
      max_value=50.0,
      value=2.2,
      disabled=not is_pro,
  )

  st.subheader("المؤشرات الكهربائية")
  voltage = st.number_input(
      "الجهد Voltage (V)", min_value=0.0, max_value=600.0, value=400.0
  )
  freq = st.number_input(
      "التردد Frequency (Hz)", min_value=0.0, max_value=70.0, value=50.0
  )
  current = st.number_input(
      "التيار Amperes (A)", min_value=0.0, max_value=2000.0, value=300.0
  )
  pf = st.number_input(
      "معامل القدرة Power Factor (PF)",
      min_value=0.0,
      max_value=1.0,
      value=0.85,
      disabled=not is_pro,
  )

  submit_btn = st.form_submit_button("تحليـل القراءات")

# عرض لوحة المؤشرات الرئيسية وبيانات العميل النشط
st.subheader("📊 لوحة المراقبة التشغيلية")
st.info(f"🔹 **العميل الحالي بالجلسة:** {client_name} | **الباقة:** {plan_type}")

col1, col2, col3 = st.columns(3)
col1.metric("درجة الحرارة", f"{temp} °C", "حرج" if temp >= 95 else "طبيعي")
col2.metric("ضغط الزيت", f"{oil_press} Bar", "منخفض" if oil_press < 2.5 else "مستقر")
col3.metric(
    "مستوى الاهتزاز", f"{vibration} mm/s" if is_pro else "🔒 مقفل (يتطلب تفعيل)"
)

col4, col5, col6, col7 = st.columns(4)
col4.metric("الجهد", f"{voltage} V")
col5.metric("التردد", f"{freq} Hz")
col6.metric("التيار", f"{current} A")
col7.metric(
    "معامل القدرة (PF)", f"{pf}" if is_pro else "🔒 مقفل (يتطلب تفعيل)"
)

# تقرير التنبؤ بالأعطال والتحليل الذكي
st.divider()
st.subheader("🔍 تقرير التنبؤ بالأعطال (AI Diagnostics)")

if is_pro:
  st.success(
      f"🌟 حساب العميل (**{client_name}**) مفعل بنجاح وفق باقة {plan_type}."
      " يتم تحليل كافة المعلمات بدمج الاهتزاز ومعامل القدرة."
  )

  alerts = []
  if vibration > 4.0:
    alerts.append(
        "⚠️ **تحذير اهتزاز عالي:** يشير إلى عدم توازن في المحور أو تآكل كراسي"
        " المحرك."
    )
  if pf < 0.8:
    alerts.append(
        "💡 **معامل قدرة منخفض:** يوصى بمراجعة مكثفات تحسين القدرة (PFC)."
    )
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
    st.warning(
        "⚠️ تم رصد مؤشرات حرجة أساسية. يرجى إدخال كود العميل المخصص للحصول على"
        " تفاصيل التنبؤ."
    )
  else:
    st.info(
        "ℹ️ النظام يعمل في وضع الزائر. قم بإدخال كود التفعيل الخاص بالعميل في"
        " الشريط الجانبي لفتح صلاحيات المراقبة والتحليل."
    )
